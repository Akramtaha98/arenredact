#!/usr/bin/env python
"""Run the adversarial robustness evaluation (Section 5.2, Table 5) and
compute bootstrap confidence intervals for the ArEnRedact-vs-baseline
difference (Section 6.2).

This produces *measured* numbers from whatever checkpoint/regex engine is
configured — it does not know about the paper's illustrative Table 5 figures
and will simply report whatever the pipeline actually does on the input
corpus. Running this against a trained checkpoint is the concrete mechanism
described in Section 5.5 (Reproducibility and Data Provenance Statement) for
replacing illustrative figures with audited ones.

Example:
    python scripts/run_adversarial_eval.py \\
        --test-corpus data/synthetic/test.jsonl \\
        --config configs/pipeline_config.yaml \\
        --out results/adversarial_eval.json
"""

from __future__ import annotations

import argparse
import json

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

from arenredact.attacks.operators import OPERATOR_FUNCS, AttackOperator
from arenredact.evaluation.metrics import (
    attack_success_rate,
    bootstrap_ci,
    precision_recall_f1,
)
from arenredact.pipeline import ArEnRedactPipeline
from arenredact.span_fusion import Span, SpanOrigin


def _load_config(path: str) -> dict:
    if yaml is None:
        raise ImportError("PyYAML is required: pip install pyyaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_test_corpus(path: str) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _gold_spans(record: dict) -> list[Span]:
    return [
        Span(start=e["start"], end=e["end"], entity_type=e["entity_type"], origin=SpanOrigin.REGEX)
        for e in record["entities"]
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-corpus", required=True)
    parser.add_argument("--config", default="configs/pipeline_config.yaml")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    cfg = _load_config(args.config)
    records = _load_test_corpus(args.test_corpus)

    checkpoint = cfg["pipeline"].get("checkpoint_path")
    pipeline = (
        ArEnRedactPipeline.from_checkpoint(checkpoint)
        if checkpoint
        else ArEnRedactPipeline()
    )

    results = {}
    per_sentence_f1_clean = []

    # Clean-input pass.
    tp_clean_total = 0
    for rec in records:
        result = pipeline.redact(rec["text"], record_audit=False)
        prf1 = precision_recall_f1(_gold_spans(rec), result.spans)
        per_sentence_f1_clean.append(prf1.f1)
        tp_clean_total += prf1.true_positives
    results["clean"] = {
        "f1_mean": sum(per_sentence_f1_clean) / len(per_sentence_f1_clean) if per_sentence_f1_clean else 0.0,
        "tp_total": tp_clean_total,
    }

    # Adversarial passes, one per operator configured in pipeline_config.yaml.
    for op_name in cfg["adversarial_eval"]["operators"]:
        op = AttackOperator(op_name)
        op_func = OPERATOR_FUNCS[op]
        per_sentence_f1_adv = []
        tp_adv_total = 0
        for rec in records:
            spans_for_attack = [(e["start"], e["end"]) for e in rec["entities"]]
            perturbed_text = op_func(rec["text"], spans=spans_for_attack)
            result = pipeline.redact(perturbed_text, record_audit=False)
            prf1 = precision_recall_f1(_gold_spans(rec), result.spans)
            per_sentence_f1_adv.append(prf1.f1)
            tp_adv_total += prf1.true_positives

        asr = attack_success_rate(tp_clean_total, tp_adv_total)
        ci = bootstrap_ci(
            per_sentence_f1_clean,
            per_sentence_f1_adv,
            n_resamples=cfg["adversarial_eval"]["n_bootstrap_resamples"],
            confidence=cfg["adversarial_eval"]["confidence"],
            seed=cfg["adversarial_eval"]["seed"],
        )
        results[op_name] = {
            "f1_mean": sum(per_sentence_f1_adv) / len(per_sentence_f1_adv) if per_sentence_f1_adv else 0.0,
            "attack_success_rate": asr,
            "bootstrap_ci_vs_clean": ci,
        }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Wrote results to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
