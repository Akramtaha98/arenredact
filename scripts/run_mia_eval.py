#!/usr/bin/env python
"""Run the LiRA membership-inference evaluation (Section 5.3, 6.4, Table 7).

This drives the *scoring* logic in arenredact.evaluation.membership_inference
against precomputed per-example losses. Training the `n_shadow_models` shadow
models themselves is a separate, expensive step (multi-GPU-day for
n_shadow_models=128 as specified in the paper) and is intentionally left to
the caller to implement against their training backend — see the
`ShadowModelTrainer` protocol in that module. This script assumes shadow
model losses have already been computed and stored as JSON.

Expected input format for --target-losses and --shadow-losses:
    target-losses.json: {"example_id": loss, ...}
    shadow-losses.json: [{"in_losses": {...}, "out_losses": {...}}, ...]
    membership-labels.json: {"example_id": 0 or 1, ...}

Example:
    python scripts/run_mia_eval.py \\
        --target-losses results/target_losses.json \\
        --shadow-losses results/shadow_losses.json \\
        --membership-labels results/membership_labels.json \\
        --out results/mia_eval.json
"""

from __future__ import annotations

import argparse
import json

from arenredact.evaluation.membership_inference import ShadowModelResult, run_lira_evaluation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-losses", required=True)
    parser.add_argument("--shadow-losses", required=True)
    parser.add_argument("--membership-labels", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    with open(args.target_losses, encoding="utf-8") as f:
        target_losses = json.load(f)
    with open(args.shadow_losses, encoding="utf-8") as f:
        shadow_raw = json.load(f)
    with open(args.membership_labels, encoding="utf-8") as f:
        membership_labels = json.load(f)

    shadow_results = [
        ShadowModelResult(in_losses=entry["in_losses"], out_losses=entry["out_losses"])
        for entry in shadow_raw
    ]

    results = run_lira_evaluation(target_losses, shadow_results, membership_labels)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Wrote results to {args.out}")
    print(f"MIA AUC: {results['auc']:.4f}  TPR@1%FPR: {results['tpr_at_1pct_fpr']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
