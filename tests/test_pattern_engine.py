"""Tests for Stage 3 (arenredact.pattern_engine) — Section 4.3."""

from arenredact.pattern_engine import PatternEngine
from arenredact.span_fusion import SpanOrigin


def test_detects_email():
    engine = PatternEngine()
    spans = engine.detect("Contact me at ahmed.test@example.com please.")
    emails = [s for s in spans if s.entity_type == "EMAIL"]
    assert len(emails) == 1
    assert emails[0].origin == SpanOrigin.REGEX


def test_detects_saudi_phone_number():
    engine = PatternEngine()
    spans = engine.detect("Call +966501234567 now.")
    phones = [s for s in spans if s.entity_type == "PHONE"]
    assert len(phones) == 1


def test_detects_uae_phone_number():
    engine = PatternEngine()
    spans = engine.detect("رقمي +971501234567")
    phones = [s for s in spans if s.entity_type == "PHONE"]
    assert len(phones) == 1


def test_detects_saudi_iban():
    engine = PatternEngine()
    iban = "SA" + "1" * 22
    spans = engine.detect(f"Transfer to {iban} account.")
    ibans = [s for s in spans if s.entity_type == "IBAN"]
    assert len(ibans) == 1
    assert (spans_text := iban) and ibans[0].end - ibans[0].start == len(iban)


def test_detects_national_id():
    engine = PatternEngine()
    spans = engine.detect("National ID: 1234567890 recorded.")
    ids = [s for s in spans if s.entity_type == "NATIONAL_ID"]
    assert len(ids) == 1


def test_national_id_not_matched_when_prefixed_by_plus():
    """A 10-digit run immediately preceded by '+' should not double-count as
    a national ID (it's part of a phone-like token)."""
    engine = PatternEngine()
    spans = engine.detect("+1234567890")
    ids = [s for s in spans if s.entity_type == "NATIONAL_ID"]
    assert len(ids) == 0


def test_detects_url():
    engine = PatternEngine()
    spans = engine.detect("Visit https://example.com/path for info.")
    urls = [s for s in spans if s.entity_type == "URL"]
    assert len(urls) == 1


def test_detects_ipv4():
    engine = PatternEngine()
    spans = engine.detect("Server at 192.168.1.100 is down.")
    ips = [s for s in spans if s.entity_type == "IP_ADDRESS"]
    assert len(ips) == 1


def test_no_false_positive_on_plain_text():
    engine = PatternEngine()
    spans = engine.detect("This is just a normal sentence with no PII at all.")
    assert spans == []


def test_entity_counts_matches_detect():
    engine = PatternEngine()
    text = "Email a@b.com or call +966501234567."
    counts = engine.entity_counts(text)
    assert counts["EMAIL"] == 1
    assert counts["PHONE"] == 1
    assert counts["URL"] == 0


def test_spans_sorted_by_start():
    engine = PatternEngine()
    text = "b@b.com then +966501234567"
    spans = engine.detect(text)
    starts = [s.start for s in spans]
    assert starts == sorted(starts)


# ---------------------------------------------------------------------------
# Regression tests added after the noisy challenge set (Section 6.1) surfaced
# two real pattern-engine limitations: an all-digit Bahrain IBAN pattern that
# misses the real letter-containing bank-code segment, and bare 10-digit
# NATIONAL_ID matches on non-ID numbers (order numbers, quantities, etc.).
# ---------------------------------------------------------------------------


def test_detects_bahrain_iban_with_letter_bank_code():
    """Real Bahrain IBANs embed a 4-letter bank code (e.g. BMAG), which the
    original all-digit pattern could never match."""
    engine = PatternEngine()
    spans = engine.detect("Confirm the IBAN BH67BMAG00001299123456 before Friday.")
    ibans = [s for s in spans if s.entity_type == "IBAN"]
    assert len(ibans) == 1
    assert ibans[0].end - ibans[0].start == len("BH67BMAG00001299123456")


def test_national_id_requires_identity_context():
    """A bare 10-digit run with no identity-context keyword nearby (e.g. an
    order number or a quantity) must NOT be tagged NATIONAL_ID."""
    engine = PatternEngine()
    spans = engine.detect("Order #1234567890 was shipped yesterday.")
    ids = [s for s in spans if s.entity_type == "NATIONAL_ID"]
    assert len(ids) == 0


def test_national_id_matched_with_arabic_identity_context():
    engine = PatternEngine()
    spans = engine.detect("أبو خالد قال إن رقمه القومي 9876543210 ضاع منه.")
    ids = [s for s in spans if s.entity_type == "NATIONAL_ID"]
    assert len(ids) == 1


def test_national_id_not_matched_on_unrelated_quantity():
    engine = PatternEngine()
    spans = engine.detect("The building has 4567890123 square feet of office space.")
    ids = [s for s in spans if s.entity_type == "NATIONAL_ID"]
    assert len(ids) == 0


# ---------------------------------------------------------------------------
# Regression tests added after the FROZEN HOLDOUT set
# (scripts/noisy_challenge_set_holdout.py), run once after the two fixes
# above, found 4 false negatives — all NATIONAL_ID, all caused by
# identity-context phrasing this keyword list didn't yet cover: "civil ID"
# and the Arabic possessive-suffixed "هويته" (not a literal substring of
# "هوية"). Note: the holdout file's originally recorded result is reported
# as-is in the paper and NOT re-run/re-scored here — these tests verify the
# fix in isolation, distinct from re-litigating the frozen holdout score.
# ---------------------------------------------------------------------------


def test_national_id_matched_with_civil_id_context():
    engine = PatternEngine()
    spans = engine.detect("His civil registry number, 7138217852, needs to be updated on file.")
    ids = [s for s in spans if s.entity_type == "NATIONAL_ID"]
    assert len(ids) == 1


def test_national_id_matched_with_arabic_possessive_suffix_context():
    """رقم هويته ("his identity number") uses the possessive-suffixed form,
    which does not contain the literal substring هوية."""
    engine = PatternEngine()
    spans = engine.detect("سجّل الموظف رقم هويته 5166427427 في الاستمارة الجديدة.")
    ids = [s for s in spans if s.entity_type == "NATIONAL_ID"]
    assert len(ids) == 1


import pytest
from arenredact.pipeline import ArEnRedactPipeline as _P


@pytest.mark.parametrize("text,label", [
    ("Call 00966501234567 now", "[PHONE]"),
    ("Dial +966 (50) 123-4567 today", "[PHONE]"),
    ("Call +973 (37) 237 956 ASAP", "[PHONE]"),          # 8-digit Bahrain number, parenthesised area group
    ("Reach +966.50.123.4567 please", "[PHONE]"),
    ("wire to sa7912345678901234567890 ok", "[IBAN]"),
    ("IBAN SA79 1234 5678 9012 3456 7890 with spaces.", "[IBAN]"),
    ("IBAN BH14 BMAG 3844 6095505822 with spaces.", "[IBAN]"),
    ("1234567890 (civil ID) was matched", "[NATIONAL_ID]"),
    ("\u0631\u0642\u0645 \u0627\u0644\u0647\u064f\u0648\u0650\u064a\u0651\u0629 1234567890", "[NATIONAL_ID]"),  # decorated keyword
    ("a.b@example.com", "[EMAIL]"),
])
def test_revision2_formats_detected(text, label):
    assert label in _P().redact(text, record_audit=False).redacted_text


@pytest.mark.parametrize("text", [
    "Order 1234567890 shipped", "Reference 123456789 is nine digits", "Invoice total 500.00 SAR",
    "SA1234 is not an IBAN", "IBAN SA79 1234 5678 9012 3456 78 too short", "2024-05-12 at 3pm",
])
def test_revision2_negatives_untouched(text):
    r = _P().redact(text, record_audit=False)
    assert r.redacted_text == r.normalized_text
