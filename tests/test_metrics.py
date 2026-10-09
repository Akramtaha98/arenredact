"""Tests for arenredact.evaluation.metrics — Section 5.3."""

from arenredact.evaluation.metrics import (
    attack_success_rate,
    bootstrap_ci,
    precision_recall_f1,
    privacy_utility_score,
)
from arenredact.span_fusion import Span, SpanOrigin


def _span(start, end, entity_type):
    return Span(start=start, end=end, entity_type=entity_type, origin=SpanOrigin.REGEX)


def test_precision_recall_f1_perfect_match():
    gold = [_span(0, 5, "PERSON"), _span(10, 15, "EMAIL")]
    pred = [_span(0, 5, "PERSON"), _span(10, 15, "EMAIL")]
    result = precision_recall_f1(gold, pred)
    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.f1 == 1.0
    assert result.false_positives == 0
    assert result.false_negatives == 0


def test_precision_recall_f1_no_predictions():
    gold = [_span(0, 5, "PERSON")]
    result = precision_recall_f1(gold, [])
    assert result.precision == 0.0
    assert result.recall == 0.0
    assert result.f1 == 0.0
    assert result.false_negatives == 1


def test_precision_recall_f1_partial_overlap_counts_as_miss():
    """Exact-match semantics: a span shifted by even one character is a
    full miss, not a partial credit."""
    gold = [_span(0, 5, "PERSON")]
    pred = [_span(0, 6, "PERSON")]
    result = precision_recall_f1(gold, pred)
    assert result.true_positives == 0
    assert result.false_positives == 1
    assert result.false_negatives == 1


def test_attack_success_rate_full_evasion():
    assert attack_success_rate(tp_clean=100, tp_adversarial=0) == 1.0


def test_attack_success_rate_no_degradation():
    assert attack_success_rate(tp_clean=100, tp_adversarial=100) == 0.0


def test_attack_success_rate_zero_clean_returns_zero():
    assert attack_success_rate(tp_clean=0, tp_adversarial=0) == 0.0


def test_attack_success_rate_clamped_nonnegative():
    """If adversarial TP somehow exceeds clean TP (shouldn't happen but
    guard against negative ASR from a degenerate input)."""
    assert attack_success_rate(tp_clean=10, tp_adversarial=15) == 0.0


def test_privacy_utility_score_perfect():
    assert privacy_utility_score(recall=1.0, prir=0.0) == 1.0


def test_privacy_utility_score_worst_case():
    assert privacy_utility_score(recall=0.0, prir=1.0) == 0.0


def test_bootstrap_ci_identical_samples_zero_diff():
    sample = [0.9, 0.8, 0.95, 0.7, 0.85]
    result = bootstrap_ci(sample, sample, n_resamples=500, seed=1)
    assert result["observed_diff"] == 0.0
    assert result["ci_lower"] <= 0.0 <= result["ci_upper"]


def test_bootstrap_ci_clear_difference_detected():
    sample_a = [0.95] * 30
    sample_b = [0.60] * 30
    result = bootstrap_ci(sample_a, sample_b, n_resamples=1000, seed=1)
    assert result["observed_diff"] > 0.3
    assert result["ci_lower"] > 0.0  # CI excludes zero -> significant
    assert result["p_value"] < 0.05


def test_bootstrap_ci_raises_on_length_mismatch():
    try:
        bootstrap_ci([1.0, 2.0], [1.0], n_resamples=10)
        assert False, "expected ValueError"
    except ValueError:
        pass
