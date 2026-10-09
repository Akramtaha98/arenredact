"""Tests for the deterministic parts of the evaluation harnesses:
arenredact.evaluation.reidentification and .membership_inference. These do
not require a trained model or GPU (Section 5.5), so they run in CI."""

from arenredact.evaluation.membership_inference import (
    ShadowModelResult,
    compute_auc,
    lira_score,
    run_lira_evaluation,
    tpr_at_fpr,
)
from arenredact.evaluation.reidentification import (
    LexicalOverlapAdversary,
    NullAdversary,
    RedactedRecord,
    compute_prir,
)
from arenredact.span_fusion import Span, SpanOrigin


def test_null_adversary_never_reidentifies():
    records = [
        RedactedRecord(
            redacted_text="Contact [PERSON] at [EMAIL]",
            original_text="Contact Ahmed at ahmed@example.com",
            redacted_spans=[
                Span(8, 13, "PERSON", SpanOrigin.NEURAL),
                Span(17, 35, "EMAIL", SpanOrigin.REGEX),
            ],
        )
    ]
    result = compute_prir(records, NullAdversary())
    assert result["prir"] == 0.0
    assert result["n_reidentified"] == 0


def test_lexical_overlap_adversary_recovers_exact_context_match():
    original = "Contact Ahmed at the office"
    redacted = "Contact [PERSON] at the office"
    span = Span(8, 13, "PERSON", SpanOrigin.NEURAL)
    record = RedactedRecord(redacted_text=redacted, original_text=original, redacted_spans=[span])

    background = [("Contact [PERSON] at the office", "Ahmed")]
    adversary = LexicalOverlapAdversary(background_entities=background)
    result = compute_prir([record], adversary)
    assert result["n_reidentified"] == 1
    assert result["prir"] == 1.0


def test_compute_prir_empty_records_returns_zero():
    result = compute_prir([], NullAdversary())
    assert result["prir"] == 0.0
    assert result["n_records"] == 0


def test_compute_prir_skips_records_with_no_masked_spans():
    record = RedactedRecord(redacted_text="no pii here", original_text="no pii here", redacted_spans=[])
    result = compute_prir([record], NullAdversary())
    assert result["n_records"] == 1
    assert result["n_reidentified"] == 0


def test_compute_auc_perfect_separation():
    labels = [1, 1, 1, 0, 0, 0]
    scores = [0.9, 0.8, 0.7, 0.3, 0.2, 0.1]
    assert compute_auc(labels, scores) == 1.0


def test_compute_auc_random_separation_near_half():
    labels = [1, 0, 1, 0]
    scores = [0.5, 0.5, 0.5, 0.5]  # all tied -> AUC should be 0.5
    assert compute_auc(labels, scores) == 0.5


def test_compute_auc_inverted_separation_near_zero():
    labels = [1, 1, 0, 0]
    scores = [0.1, 0.2, 0.8, 0.9]  # members score lower than non-members
    assert compute_auc(labels, scores) == 0.0


def test_compute_auc_degenerate_single_class():
    assert compute_auc([1, 1, 1], [0.5, 0.6, 0.7]) == 0.5


def test_tpr_at_fpr_perfect_classifier():
    labels = [1, 1, 0, 0]
    scores = [0.9, 0.8, 0.2, 0.1]
    assert tpr_at_fpr(labels, scores, target_fpr=0.5) == 1.0


def test_lira_score_higher_for_in_distribution_loss():
    shadow_in = [0.1, 0.12, 0.11, 0.09]   # members: low loss
    shadow_out = [0.9, 0.95, 0.85, 0.88]  # non-members: high loss
    score_member_like = lira_score(0.1, shadow_in, shadow_out)
    score_nonmember_like = lira_score(0.9, shadow_in, shadow_out)
    assert score_member_like > score_nonmember_like


def test_run_lira_evaluation_end_to_end():
    target_losses = {"ex1": 0.1, "ex2": 0.9}
    shadow_results = [
        ShadowModelResult(in_losses={"ex1": 0.1, "ex2": 0.15}, out_losses={"ex1": 0.9, "ex2": 0.85}),
        ShadowModelResult(in_losses={"ex1": 0.12}, out_losses={"ex1": 0.88, "ex2": 0.91}),
    ]
    membership_labels = {"ex1": 1, "ex2": 0}
    results = run_lira_evaluation(target_losses, shadow_results, membership_labels)
    assert results["n_examples_scored"] == 2
    assert 0.0 <= results["auc"] <= 1.0
