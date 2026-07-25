#!/usr/bin/env python
"""Run the Post-Redaction Re-Identification Rate evaluation (Section 5.3,
6.3) against a configurable adversary.

Example:
    python scripts/run_reidentification_eval.py \\
        --test-corpus data/synthetic/test.jsonl \\
        --config configs/pipeline_config.yaml \\
        --out results/reidentification_eval.json
"""

from __future__ import annotations

import argparse
import json

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

from arenredact.evaluation.reidentification import (
    LexicalOverlapAdversary,
    NullAdversary,
    RedactedRecord,
    compute_prir,
)
from arenredact.pipeline import ArEnRedactPipeline


def _load_config(path: str) -> dict:
    if yaml is None:
        raise ImportError("PyYAML is required: pip install pyyaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_jsonl(path: str) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-corpus", required=True)
    parser.add_argument("--config", default="configs/pipeline_config.yaml")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    cfg = _load_config(args.config)
    test_records = _load_jsonl(args.test_corpus)

    checkpoint = cfg["pipeline"].get("checkpoint_path")
    pipeline = (
        ArEnRedactPipeline.from_checkpoint(checkpoint)
        if checkpoint
        else ArEnRedactPipeline()
    )

    redacted_records = []
    for rec in test_records:
        result = pipeline.redact(rec["text"], record_audit=False)
        redacted_records.append(
            RedactedRecord(
                redacted_text=result.redacted_text,
                original_text=result.normalized_text,
                redacted_spans=result.spans,
            )
        )

    adversary_name = cfg["reidentification_eval"]["adversary"]
    if adversary_name == "null":
        adversary = NullAdversary()
    elif adversary_name == "lexical_overlap":
        bg_path = cfg["reidentification_eval"]["background_corpus_path"]
        background = [
            (entry["context"], entry["entity_value"]) for entry in _load_jsonl(bg_path)
        ]
        adversary = LexicalOverlapAdversary(background_entities=background)
    else:
        raise ValueError(f"Unknown adversary: {adversary_name}")

    results = compute_prir(redacted_records, adversary)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Wrote results to {args.out}")
    print(f"PRIR ({adversary_name}): {results['prir']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
