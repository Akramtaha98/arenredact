"""Tests for Stage 4 (arenredact.span_fusion) — Algorithm 1, Section 4.4."""

from arenredact.span_fusion import Span, SpanOrigin, fuse_spans, redact


def _neural(start, end, entity_type, score=0.9):
    return Span(start=start, end=end, entity_type=entity_type, origin=SpanOrigin.NEURAL, score=score)


def _regex(start, end, entity_type, score=1.0):
    return Span(start=start, end=end, entity_type=entity_type, origin=SpanOrigin.REGEX, score=score)


def test_fuse_spans_union_of_disjoint_spans():
    neural = [_neural(0, 4, "PERSON")]
    regex = [_regex(10, 20, "EMAIL")]
    fused = fuse_spans(neural, regex, text="محمد at test@example.com sends")
    assert len(fused) == 2


def test_fuse_spans_regex_wins_on_type_conflict():
    """Algorithm 1 line 5: regex-origin span wins over neural-origin span of
    a different type when they overlap."""
    neural = [_neural(0, 15, "PHONE")]
    regex = [_regex(0, 15, "NATIONAL_ID")]
    fused = fuse_spans(neural, regex, text="1234567890ABCDE", expand_quasi_identifiers=False)
    assert len(fused) == 1
    assert fused[0].entity_type == "NATIONAL_ID"
    assert fused[0].origin == SpanOrigin.REGEX


def test_fuse_spans_same_type_keeps_higher_score():
    neural = [_neural(0, 4, "PERSON", score=0.7)]
    regex = [_regex(0, 6, "PERSON", score=0.99)]
    fused = fuse_spans(neural, regex, text="محمدxx", expand_quasi_identifiers=False)
    assert len(fused) == 1
    assert fused[0].start == 0 and fused[0].end == 6


def test_quasi_identifier_expansion_kunya_prefix():
    text = "أبو محمد قال ذلك"
    person_span = _neural(4, 8, "PERSON")  # covers "محمد"
    fused = fuse_spans([person_span], [], text=text)
    assert len(fused) == 1
    assert fused[0].expanded is True
    assert text[fused[0].start : fused[0].end] == "أبو محمد"


def test_quasi_identifier_expansion_nisbah_suffix():
    text = "محمد الدوسري وصل"
    person_span = _neural(0, 4, "PERSON")  # covers "محمد"
    fused = fuse_spans([person_span], [], text=text)
    assert fused[0].expanded is True
    assert text[fused[0].start : fused[0].end] == "محمد الدوسري"


def test_quasi_identifier_expansion_noop_for_non_person():
    text = "email at a@b.com today"
    email_span = _regex(9, 15, "EMAIL")
    fused = fuse_spans([], [email_span], text=text)
    assert fused[0].expanded is False


def test_fuse_spans_empty_input():
    assert fuse_spans([], [], text="") == []


def test_redact_replaces_spans_with_mask():
    text = "call +966501234567 now"
    spans = [Span(start=5, end=18, entity_type="PHONE", origin=SpanOrigin.REGEX)]
    out = redact(text, spans)
    assert out == "call [PHONE] now"


def test_redact_multiple_spans_right_to_left_safe():
    text = "a@b.com and c@d.com"
    spans = [
        Span(start=0, end=7, entity_type="EMAIL", origin=SpanOrigin.REGEX),
        Span(start=12, end=19, entity_type="EMAIL", origin=SpanOrigin.REGEX),
    ]
    out = redact(text, spans)
    assert out == "[EMAIL] and [EMAIL]"


def test_span_overlaps_true():
    a = _regex(0, 10, "PHONE")
    b = _regex(5, 15, "NATIONAL_ID")
    assert a.overlaps(b) is True


def test_span_overlaps_false_for_adjacent():
    a = _regex(0, 10, "PHONE")
    b = _regex(10, 20, "NATIONAL_ID")
    assert a.overlaps(b) is False
