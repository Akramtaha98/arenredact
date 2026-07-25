"""Core evaluation metrics (Section 5.3).

    - precision_recall_f1: standard span-level P/R/F1 (Tjong Kim Sang & De Meulder, 2003)
    - attack_success_rate: ASR = (TP_clean - TP_adv) / TP_clean
    - privacy_utility_score: PUS = harmonic mean of recall and (1 - PRIR)
    - bootstrap_ci: paired bootstrap resampling for significance testing,
      used to produce the confidence intervals reported in Section 6.2

These are pure functions with no ML dependency — usable standalone against
any span-prediction output, including non-ArEnRedact baselines, for a
fair apples-to-apples comparison.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from arenredact.span_fusion import Span


def _span_key(span: Span) -> tuple[int, int, str]:
    return (span.start, span.end, span.entity_type)


@dataclass(frozen=True)
class PRF1Result:
    precision: float
    recall: float
    f1: float
    true_positives: int
    false_positives: int
    false_negatives: int


def precision_recall_f1(gold_spans: list[Span], pred_spans: list[Span]) -> PRF1Result:
    """Exact-match span-level P/R/F1, per Section 5.3."""
    gold_set = {_span_key(s) for s in gold_spans}
    pred_set = {_span_key(s) for s in pred_spans}

    tp = len(gold_set & pred_set)
    fp = len(pred_set - gold_set)
    fn = len(gold_set - pred_set)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return PRF1Result(precision=precision, recall=recall, f1=f1,
                       true_positives=tp, false_positives=fp, false_negatives=fn)


def attack_success_rate(tp_clean: int, tp_adversarial: int) -> float:
    """ASR = (TP_clean - TP_adv) / TP_clean — the fraction of clean-input PII
    entities that are missed (classified as non-PII) after adversarial
    perturbation (Section 5.3). Returns 0.0 if tp_clean is 0 to avoid
    division by zero on a degenerate (empty) gold set."""
    if tp_clean == 0:
        return 0.0
    return max(0.0, (tp_clean - tp_adversarial) / tp_clean)


def privacy_utility_score(recall: float, prir: float) -> float:
    """PUS = harmonic mean of recall and (1 - PRIR), aggregating privacy and
    utility into a single deployment-readiness metric (Section 5.3)."""
    utility_term = recall
    privacy_term = 1.0 - prir
    if utility_term + privacy_term == 0:
        return 0.0
    return 2 * utility_term * privacy_term / (utility_term + privacy_term)


def bootstrap_ci(
    sample_a: list[float],
    sample_b: list[float],
    n_resamples: int = 10_000,
    confidence: float = 0.95,
    seed: int = 42,
) -> dict:
    """Paired bootstrap resampling over per-example metric values (e.g.,
    per-sentence F1) to estimate a confidence interval for the difference
    `mean(sample_a) - mean(sample_b)`, and a two-sided bootstrap p-value for
    the null hypothesis that the true difference is zero. Used to produce
    the significance figures reported in Section 6.2.

    `sample_a` and `sample_b` must be paired (same length, same underlying
    examples, e.g. per-sentence F1 for ArEnRedact vs. a baseline over the
    identical test set) for the resampling to be valid.
    """
    if len(sample_a) != len(sample_b):
        raise ValueError("sample_a and sample_b must be the same length (paired samples).")

    rng = random.Random(seed)
    n = len(sample_a)
    observed_diff = (sum(sample_a) - sum(sample_b)) / n

    diffs = [a - b for a, b in zip(sample_a, sample_b)]
    boot_means = []
    for _ in range(n_resamples):
        resample = [diffs[rng.randrange(n)] for _ in range(n)]
        boot_means.append(sum(resample) / n)

    boot_means.sort()
    alpha = 1 - confidence
    lower_idx = int((alpha / 2) * n_resamples)
    upper_idx = int((1 - alpha / 2) * n_resamples) - 1
    ci_lower = boot_means[max(lower_idx, 0)]
    ci_upper = boot_means[min(upper_idx, n_resamples - 1)]

    # Two-sided bootstrap p-value: fraction of resampled diffs at least as
    # extreme (in magnitude, centered at zero) as the observed difference.
    centered = [d - observed_diff for d in diffs]
    boot_centered_means = []
    for _ in range(n_resamples):
        resample = [centered[rng.randrange(n)] for _ in range(n)]
        boot_centered_means.append(sum(resample) / n)
    p_value = sum(1 for m in boot_centered_means if abs(m) >= abs(observed_diff)) / n_resamples

    return {
        "observed_diff": observed_diff,
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "confidence": confidence,
        "p_value": p_value,
        "n_resamples": n_resamples,
    }
