"""End-to-end orchestration of the five ArEnRedact stages (Section 4, Figure 1):

    raw text -> [1] normalize -> [2] LoRA NER  \\
                                -> [3] regex PII -> [4] fuse -> [5] audit log -> redacted text

Usage as a library:

    from arenredact.pipeline import ArEnRedactPipeline

    pipeline = ArEnRedactPipeline.from_checkpoint("runs/lora_xlmr/checkpoint-best")
    result = pipeline.redact("تواصل مع محمد أبو سالم على +966501234567")
    print(result.redacted_text)
    print(result.audit_entry.transaction_id)

Usage as a CLI (deterministic stages only, no trained checkpoint required):

    python -m arenredact.pipeline --input examples/sample.txt --no-neural
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from arenredact.audit_log import AuditLog, AuditLogEntry
from arenredact.pattern_engine import PatternEngine
from arenredact.preprocessing import NormalizationReport, normalize_with_report
from arenredact.span_fusion import Span, fuse_spans, redact


@dataclass
class RedactionResult:
    original_text: str
    normalized_text: str
    redacted_text: str
    spans: list[Span]
    normalization_report: NormalizationReport
    audit_entry: AuditLogEntry | None


class ArEnRedactPipeline:
    """Ties Stages 1-5 together. The neural NER component (Stage 2) is
    optional: when no `neural_ner` is supplied, the pipeline runs
    regex-only (Stage 3 + Stage 4 + Stage 5), which is useful for testing
    and for environments without a trained checkpoint or GPU."""

    def __init__(
        self,
        neural_ner=None,  # arenredact.neural_ner.LoraNER, optional
        pattern_engine: PatternEngine | None = None,
        audit_log: AuditLog | None = None,
        model_version_hash: str = "regex-only",
    ):
        self.neural_ner = neural_ner
        self.pattern_engine = pattern_engine or PatternEngine()
        self.audit_log = audit_log or AuditLog()
        self.model_version_hash = model_version_hash

    @classmethod
    def from_checkpoint(cls, checkpoint_path: str, **kwargs) -> "ArEnRedactPipeline":
        """Convenience constructor that also loads the LoRA NER checkpoint
        (Stage 2). Requires the `ml` extra."""
        from arenredact.neural_ner import LoraNER

        ner = LoraNER.from_checkpoint(checkpoint_path)
        return cls(neural_ner=ner, model_version_hash=checkpoint_path, **kwargs)

    def redact(
        self,
        text: str,
        client_cert_fingerprint: str = "sha256:unknown",
        record_audit: bool = True,
    ) -> RedactionResult:
        # Stage 1
        normalized, norm_report = normalize_with_report(text)

        # Stage 2 (optional) + Stage 3, run over the normalized text
        neural_spans = self.neural_ner.predict(normalized) if self.neural_ner else []
        regex_spans = self.pattern_engine.detect(normalized)

        # Stage 4
        fused = fuse_spans(neural_spans=neural_spans, regex_spans=regex_spans, text=normalized)

        # Redaction output
        redacted_text = redact(normalized, fused)

        # Stage 5
        audit_entry = None
        if record_audit:
            audit_entry = self.audit_log.append(
                input_text=normalized,
                output_text=redacted_text,
                spans=fused,
                model_version_hash=self.model_version_hash,
                client_cert_fingerprint=client_cert_fingerprint,
            )

        return RedactionResult(
            original_text=text,
            normalized_text=normalized,
            redacted_text=redacted_text,
            spans=fused,
            normalization_report=norm_report,
            audit_entry=audit_entry,
        )


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the ArEnRedact pipeline over a text file.")
    parser.add_argument("--input", required=True, help="Path to a UTF-8 text file, one record per line.")
    parser.add_argument("--checkpoint", default=None, help="Path to a trained LoRA checkpoint.")
    parser.add_argument("--no-neural", action="store_true", help="Skip Stage 2 (regex-only mode).")
    parser.add_argument("--output", default=None, help="Write redacted output here (default: stdout).")
    args = parser.parse_args(argv)

    if args.checkpoint and not args.no_neural:
        pipeline = ArEnRedactPipeline.from_checkpoint(args.checkpoint)
    else:
        pipeline = ArEnRedactPipeline()

    with open(args.input, encoding="utf-8") as f:
        lines = [line.rstrip("\n") for line in f if line.strip()]

    out_stream = open(args.output, "w", encoding="utf-8") if args.output else sys.stdout
    try:
        for line in lines:
            result = pipeline.redact(line)
            print(result.redacted_text, file=out_stream)
    finally:
        if args.output:
            out_stream.close()

    print(f"Processed {len(lines)} lines.", file=sys.stderr)
    print(f"Audit chain valid: {pipeline.audit_log.verify_chain()}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
