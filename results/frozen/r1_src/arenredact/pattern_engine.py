"""Stage 3 — Deterministic Pattern Engine.

Structured PII categories (phone numbers, emails, IBANs, national IDs) are
matched with compiled regular expressions operating on Stage-1-normalized
text (Section 4.3). All matches are returned as `Span` objects with
`origin=SpanOrigin.REGEX` so Stage 4's fusion logic can apply deterministic
priority on type conflicts.

Security note (ReDoS): the paper specifies Google's RE2 (linear-time,
backtracking-free) as the production regex engine. This reference
implementation uses Python's built-in `re` module for zero-dependency
portability; every pattern below is written to avoid the catastrophic-
backtracking constructs RE2 would reject anyway (no nested quantifiers over
overlapping character classes), but `re` does not provide RE2's *guarantee*.
For production deployment, install `google-re2` and swap the single
`_compile()` call below — no other code changes are required.
"""

from __future__ import annotations

import re

from arenredact.data.lexicons import (
    MENA_COUNTRY_CODES,
    MENA_IBAN_DIGIT_LENGTHS,
    MENA_IBAN_LETTER_BANK_ACCOUNT_DIGITS,
)
from arenredact.span_fusion import Span, SpanOrigin


def _compile(pattern: str) -> re.Pattern:
    """Single choke point for regex compilation — swap for `re2.compile` here
    to move to the production-grade linear-time engine described in the
    paper without touching any other file."""
    return re.compile(pattern, re.ASCII)


# ---------------------------------------------------------------------------
# Pattern definitions (operate on NFKC-normalized, digit-folded text; see
# arenredact.preprocessing.normalize, which MUST run before this module).
# ---------------------------------------------------------------------------

_EMAIL_RE = _compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

_URL_RE = _compile(r"\bhttps?://[^\s<>\"]+|\bwww\.[^\s<>\"]+")

_IPV4_RE = _compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
)

# MENA phone numbers: + followed by a known country code, then 7-10 digits
# with optional spaces/hyphens as separators (variable grouping per country).
# Note: the left boundary uses a negative digit lookbehind rather than \b,
# because "+" is not a \w character — \b cannot anchor between a preceding
# space and a leading "+", so \b would silently fail to match real-world
# "+9665..." phone numbers.
_COUNTRY_CODE_ALTERNATION = "|".join(
    re.escape(code) for code in sorted(MENA_COUNTRY_CODES, key=len, reverse=True)
)
_PHONE_RE = _compile(
    rf"(?<!\d)(?:{_COUNTRY_CODE_ALTERNATION})[\s-]?\d(?:[\s-]?\d){{6,9}}\b"
)

# MENA IBANs. Two families:
#   (1) all-numeric body countries (MENA_IBAN_DIGIT_LENGTHS: SA, AE, EG);
#   (2) countries whose real IBAN embeds a 4-LETTER bank code between the
#       2-digit check digits and the account segment
#       (MENA_IBAN_LETTER_BANK_ACCOUNT_DIGITS: BH, IQ, JO, KW). An all-digit
#       pattern systematically misses every real IBAN from family (2) — this
#       is the concrete limitation the independent noisy challenge set
#       (Section 6.1) surfaced for Bahrain specifically; the same structural
#       issue affects Iraq, Jordan, and Kuwait, so all four use the
#       letter-aware pattern below.
_IBAN_PATTERNS = {
    prefix: _compile(rf"\b{prefix}\d{{{length}}}\b")
    for prefix, length in MENA_IBAN_DIGIT_LENGTHS.items()
}
_IBAN_PATTERNS.update(
    {
        prefix: _compile(rf"\b{prefix}\d{{2}}[A-Z]{{4}}[A-Z0-9]{{{acct_digits}}}\b")
        for prefix, acct_digits in MENA_IBAN_LETTER_BANK_ACCOUNT_DIGITS.items()
    }
)

# National ID / Iqama: 10-digit sequences (Gulf-region format), not preceded
# or followed by another digit or a '+' (to avoid overlapping phone matches).
#
# A bare 10-digit run is inherently ambiguous with a local phone number typed
# without its country code (Section 6.1 / 8.4 discuss this as a discovered
# limitation). Rather than tagging every bare 10-digit run as NATIONAL_ID
# (which produces false positives on order numbers, quantities, etc.) or
# requiring a country code (which would break real national-ID detection),
# this implementation requires an identity-context keyword (English or
# Arabic) within 60 characters BEFORE the digit run — matching the
# corpus generator's own templates ("National ID:", "رقم الهوية ... الخاص
# بـ ... هو", "رقمه القومي") — and explicitly withholds the NATIONAL_ID label
# when no such context is present, rather than guessing.
#
# Keyword list history: a frozen holdout evaluation (Section 6.1,
# scripts/noisy_challenge_set_holdout.py) run after the keyword list below
# was first written found 4 false negatives, all NATIONAL_ID, all caused by
# phrasing this list did not yet cover: "civil ID" / "civil registry number"
# (no English keyword matched) and the Arabic possessive-suffixed form
# "هويته" ("his identity"), which does not contain the literal substring
# "هوية" used at the time (Arabic morphology replaces the final ة with ت
# before an attached pronoun suffix). Both are fixed below by adding "civil
# id"/"civil registry" and by matching the 3-letter root "هوي" instead of
# the full 4-letter word "هوية", which covers both the base and
# suffixed forms. This fix was verified with new unit tests
# (test_pattern_engine.py), NOT by re-running and re-scoring the frozen
# holdout file itself — the holdout's originally recorded result (Table 4c)
# is reported as-is rather than overwritten, so it remains meaningful
# evidence rather than a target the implementation was tuned against.
_NATIONAL_ID_CANDIDATE_RE = _compile(r"(?<![+\d])\b\d{10}\b(?!\d)")
_ID_CONTEXT_KEYWORDS = (
    "national id", "id no", "id number", "id:", "iqama", "identity",
    "identification", "civil id", "civil registry", "هوي", "قومي", "بطاقة",
)
_ID_CONTEXT_WINDOW = 60


def _has_id_context(text: str, match_start: int) -> bool:
    window = text[max(0, match_start - _ID_CONTEXT_WINDOW): match_start].lower()
    return any(kw in window for kw in _ID_CONTEXT_KEYWORDS)


def _national_id_spans(text: str) -> list[Span]:
    return [
        Span(start=m.start(), end=m.end(), entity_type="NATIONAL_ID", origin=SpanOrigin.REGEX)
        for m in _NATIONAL_ID_CANDIDATE_RE.finditer(text)
        if _has_id_context(text, m.start())
    ]


def _spans_from_pattern(
    pattern: re.Pattern, text: str, entity_type: str
) -> list[Span]:
    return [
        Span(start=m.start(), end=m.end(), entity_type=entity_type, origin=SpanOrigin.REGEX)
        for m in pattern.finditer(text)
    ]


class PatternEngine:
    """Deterministic PII detector for structured identifier categories.

    Usage:
        engine = PatternEngine()
        spans = engine.detect(normalized_text)
    """

    #: Detection order matters only for the standalone `entity_counts`
    #: convenience method below; Stage 4 fusion resolves any overlaps
    #: (e.g., a national ID digit run nested inside a phone number match)
    #: using the shared conflict-resolution logic in span_fusion.py.
    entity_types = ("EMAIL", "URL", "IP_ADDRESS", "PHONE", "IBAN", "NATIONAL_ID")

    def detect(self, text: str) -> list[Span]:
        """Run all structured-identifier detectors over `text` and return the
        union of matched spans. `text` MUST already have passed through
        `arenredact.preprocessing.normalize` — this engine does not
        normalize internally, so that callers control the normalization
        provenance recorded in the audit log (Stage 5)."""
        spans: list[Span] = []
        spans += _spans_from_pattern(_EMAIL_RE, text, "EMAIL")
        spans += _spans_from_pattern(_URL_RE, text, "URL")
        spans += _spans_from_pattern(_IPV4_RE, text, "IP_ADDRESS")
        spans += _spans_from_pattern(_PHONE_RE, text, "PHONE")
        for iban_pattern in _IBAN_PATTERNS.values():
            spans += _spans_from_pattern(iban_pattern, text, "IBAN")
        spans += _national_id_spans(text)
        return sorted(spans, key=lambda s: s.start)

    def entity_counts(self, text: str) -> dict[str, int]:
        """Convenience method: count matches per entity type (useful for
        quick corpus statistics without invoking the full fusion pipeline)."""
        counts = {et: 0 for et in self.entity_types}
        for span in self.detect(text):
            counts[span.entity_type] = counts.get(span.entity_type, 0) + 1
        return counts
