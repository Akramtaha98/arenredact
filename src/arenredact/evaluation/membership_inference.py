"""Membership Inference Attack (MIA) evaluation via LiRA (Section 5.3, 6.4).

Implements the Likelihood-Ratio Attack (Carlini et al., 2022) comparing
per-example loss under a target model against a distribution of losses from
`n_shadow_models` shadow models trained on random subsets of the same data
distribution. Used to compare LoRA vs. full fine-tuning memorization risk
(Table 7 in the paper).

This module provides the LiRA scoring logic (`lira_scores`, `compute_auc`,
`tpr_at_fpr`) as pure functions over precomputed per-example losses, plus a
`ShadowModelTrainer` protocol so the (expensive, GPU-bound) shadow-model
training loop can be swapped for any training backend. Training 128 shadow
models is a multi-GPU-day workload and is intentionally *not* run as part of
this repository's test suite — see `scripts/run_mia_eval.py` for the CLI
that drives a real run, and Section 5.5 of the paper for the reproducibility
status of the resulting numbers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol


@dataclass
class ShadowModelResult:
    """Per-example losses from one shadow model, split by whether the
    example was in that shadow model's training set ("in") or not ("out")."""

    in_losses: dict[str, float]  # example_id -> loss
    out_losses: dict[str, float]


class ShadowModelTrainer(Protocol):
    """Trains one shadow model on a random data split and returns per-example
    losses for both the training split ("in") and held-out split ("out").
    Implement this against your training backend (see neural_ner.py /
    train_lora.py for the LoRA case)."""

    def train_and_score(self, seed: int) -> ShadowModelResult:
        ...


def _gaussian_pdf(x: float, mean: float, var: float, eps: float = 1e-8) -> float:
    var = max(var, eps)
    return math.exp(-((x - mean) ** 2) / (2 * var)) / math.sqrt(2 * math.pi * var)


def lira_score(
    target_loss: float,
    shadow_in_losses: list[float],
    shadow_out_losses: list[float],
) -> float:
    """Compute the LiRA likelihood-ratio score for one example: the ratio of
    the likelihood that `target_loss` came from the "in" (member) loss
    distribution vs. the "out" (non-member) distribution, both modeled as
    Gaussian per Carlini et al. (2022)."""
    in_mean = sum(shadow_in_losses) / len(shadow_in_losses)
    in_var = sum((x - in_mean) ** 2 for x in shadow_in_losses) / max(len(shadow_in_losses) - 1, 1)
    out_mean = sum(shadow_out_losses) / len(shadow_out_losses)
    out_var = sum((x - out_mean) ** 2 for x in shadow_out_losses) / max(len(shadow_out_losses) - 1, 1)

    p_in = _gaussian_pdf(target_loss, in_mean, in_var)
    p_out = _gaussian_pdf(target_loss, out_mean, out_var)
    if p_out == 0:
        return float("inf") if p_in > 0 else 1.0
    return p_in / p_out


def compute_auc(labels: list[int], scores: list[float]) -> float:
    """AUROC via the rank-sum (Mann-Whitney U) formula — no sklearn
    dependency required. `labels`: 1 for member, 0 for non-member."""
    paired = sorted(zip(scores, labels), key=lambda p: p[0])
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5

    # Assign ranks, averaging ties.
    ranks = [0.0] * len(paired)
    i = 0
    while i < len(paired):
        j = i
        while j + 1 < len(paired) and paired[j + 1][0] == paired[i][0]:
            j += 1
        avg_rank = (i + j) / 2 + 1  # 1-indexed
        for k in range(i, j + 1):
            ranks[k] = avg_rank
        i = j + 1

    rank_sum_pos = sum(r for r, (_, label) in zip(ranks, paired) if label == 1)
    auc = (rank_sum_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)
    return auc


def tpr_at_fpr(labels: list[int], scores: list[float], target_fpr: float = 0.01) -> float:
    """True positive rate at a fixed false positive rate — the metric most
    relevant to high-assurance privacy evaluation per Section 5.3, since it
    reflects an adversary's confident-guess success rate rather than
    aggregate discriminability."""
    paired = sorted(zip(scores, labels), key=lambda p: -p[0])  # descending score
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.0

    fp = 0
    tp = 0
    for score, label in paired:
        if label == 1:
            tp += 1
        else:
            fp += 1
        if fp / n_neg >= target_fpr:
            return tp / n_pos
    return tp / n_pos


def run_lira_evaluation(
    target_losses: dict[str, float],
    shadow_results: list[ShadowModelResult],
    membership_labels: dict[str, int],
) -> dict:
    """Full LiRA pipeline: for each example scored under the target model,
    compute its LiRA score against the shadow-model loss distributions, then
    report AUC and TPR@1%FPR (Table 7 columns)."""
    scores, labels = [], []

    for example_id, target_loss in target_losses.items():
        shadow_in = [
            r.in_losses[example_id] for r in shadow_results if example_id in r.in_losses
        ]
        shadow_out = [
            r.out_losses[example_id] for r in shadow_results if example_id in r.out_losses
        ]
        if not shadow_in or not shadow_out:
            continue
        score = lira_score(target_loss, shadow_in, shadow_out)
        scores.append(score)
        labels.append(membership_labels[example_id])

    return {
        "auc": compute_auc(labels, scores),
        "tpr_at_1pct_fpr": tpr_at_fpr(labels, scores, target_fpr=0.01),
        "n_examples_scored": len(scores),
    }
