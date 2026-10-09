"""Stage 3 — Deterministic Pattern Engine.

Structured PII categories (phone numbers, emails, IBANs, national IDs) are
matched with compiled regular expressions operating on Stage-1-normalized
text (Section 4.3). All matches are returned as `Span` objects with
`origin=SpanOrigin.REGEX` so Stage 4's fusion logic can apply deterministic
priority on type conflicts.

Security note (ReDoS): this implementation uses Python's built-in `re` module.
`re.ASCII` only restricts what \\d and \\w match; it does NOT make matching
linear-time, and CPython's engine is a backtracking engine. The patterns are
written without nested quantifiers over overlapping classes, the IBAN scanner
is a bounded loop, and scripts/redos_scaling.py measures matching time against
adversarial inputs of increasing length (results/redos_scaling.json). For a
hard linear-time guarantee, swap `_compile()` for a RE2 binding; no other
code needs to change.
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

# E-mail: a single regex of the form [local]+@[domain] is quadratic on inputs
# such as "a.a.a.a....@" because every start position rescans to the end
# (measured: scripts/redos_scaling.py). The scanner below anchors on each "@"
# and expands a bounded distance left (local part, <= 64 chars) and right
# (domain, <= 255 chars), so matching time is linear in the input length.
_EMAIL_LOCAL_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._%+-")
_EMAIL_DOMAIN_RE = _compile(r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def _email_spans(text: str) -> list[Span]:
    spans: list[Span] = []
    pos = text.find("@")
    while pos != -1:
        lo = pos
        while lo > 0 and pos - lo < 64 and text[lo - 1] in _EMAIL_LOCAL_CHARS:
            lo -= 1
        while lo < pos and not (text[lo].isascii() and (text[lo].isalnum() or text[lo] == "_")):
            lo += 1
        m = _EMAIL_DOMAIN_RE.match(text[pos + 1: pos + 1 + 255])
        if lo < pos and m:
            spans.append(Span(start=lo, end=pos + 1 + m.end(), entity_type="EMAIL", origin=SpanOrigin.REGEX))
        pos = text.find("@", pos + 1)
    return spans



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
    re.escape(code.lstrip("+")) for code in sorted(MENA_COUNTRY_CODES, key=len, reverse=True)
)
# International prefix: "+" or "00". Separators: space, hyphen or dot.
# An optional parenthesised trunk/area group such as "(50)" may follow the
# country code. Local numbers without a country code are NOT detected.
_PHONE_RE = _compile(
    rf"(?<![\d+])(?:\+|00)(?:{_COUNTRY_CODE_ALTERNATION})[\s.-]?(?:"
    rf"\(\d{{2,3}}\)[\s.-]?\d(?:[\s.-]?\d){{4,8}}"      # "+973 (37) 237 956": area group in parentheses
    rf"|\d(?:[\s.-]?\d){{6,9}})(?!\d)"                     # plain grouped digits, 7-10 digits
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
_IBAN_STRUCTURES: dict[str, re.Pattern] = {
    prefix: _compile(rf"{prefix}\d{{{length}}}")
    for prefix, length in MENA_IBAN_DIGIT_LENGTHS.items()
}
_IBAN_STRUCTURES.update(
    {
        prefix: _compile(rf"{prefix}\d{{2}}[A-Z]{{4}}[A-Z0-9]{{{acct_digits}}}")
        for prefix, acct_digits in MENA_IBAN_LETTER_BANK_ACCOUNT_DIGITS.items()
    }
)
_IBAN_TOTAL_LEN = {
    **{p: 2 + n for p, n in MENA_IBAN_DIGIT_LENGTHS.items()},
    **{p: 2 + 2 + 4 + n for p, n in MENA_IBAN_LETTER_BANK_ACCOUNT_DIGITS.items()},
}
_IBAN_PREFIX_RE = _compile(r"(?<![A-Za-z0-9])[A-Za-z]{2}\d{2}")


def _iban_spans(text: str) -> list[Span]:
    """Find IBANs written compactly or in the printed 4-character-group form,
    in upper or lower case. For every candidate whose country prefix is in the
    supported set, consume exactly the registry length (skipping single spaces
    between groups), then check the country structure and that the next
    character does not continue the token."""
    spans: list[Span] = []
    for m in _IBAN_PREFIX_RE.finditer(text):
        country = m.group(0)[:2].upper()
        total = _IBAN_TOTAL_LEN.get(country)
        if total is None:
            continue
        i, chars = m.start(), []
        while i < len(text) and len(chars) < total:
            ch = text[i]
            if ch == " " and chars and i + 1 < len(text) and text[i + 1] != " ":
                i += 1
                continue
            if not (ch.isascii() and ch.isalnum()):
                break
            chars.append(ch)
            i += 1
        if len(chars) != total:
            continue
        if i < len(text) and text[i].isascii() and text[i].isalnum():
            continue
        if _IBAN_STRUCTURES[country].fullmatch("".join(chars).upper()):
            spans.append(Span(start=m.start(), end=i, entity_type="IBAN", origin=SpanOrigin.REGEX))
    return spans


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
    "identification", "civil id", "civil registry", "\u0647\u0648\u064a", "\u0642\u0648\u0645\u064a",
    "\u0628\u0637\u0627\u0642\u0629", "\u0627\u0642\u0627\u0645\u0629", "\u0625\u0642\u0627\u0645\u0629",
)
_ID_CONTEXT_WINDOW = 60
_ID_CONTEXT_AFTER_WINDOW = 20
# Arabic diacritics and Tatweel are removed from the context window before
# keyword matching, so that decorated keywords still match.
_MARKS_RE = _compile(r"[\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")


def _has_id_context(text: str, match_start: int, match_end: int | None = None) -> bool:
    window = _MARKS_RE.sub("", text[max(0, match_start - _ID_CONTEXT_WINDOW): match_start]).lower()
    if any(kw in window for kw in _ID_CONTEXT_KEYWORDS):
        return True
    if match_end is not None:
        after = _MARKS_RE.sub("", text[match_end: match_end + _ID_CONTEXT_AFTER_WINDOW]).lower()
        after = after.lstrip()
        if after.startswith("(") and any(kw in after for kw in _ID_CONTEXT_KEYWORDS):
            return True
    return False


def _national_id_spans(text: str) -> list[Span]:
    return [
        Span(start=m.start(), end=m.end(), entity_type="NATIONAL_ID", origin=SpanOrigin.REGEX)
        for m in _NATIONAL_ID_CANDIDATE_RE.finditer(text)
        if _has_id_context(text, m.start(), m.end())
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
        spans += _email_spans(text)
        spans += _spans_from_pattern(_URL_RE, text, "URL")
        spans += _spans_from_pattern(_IPV4_RE, text, "IP_ADDRESS")
        spans += _spans_from_pattern(_PHONE_RE, text, "PHONE")
        spans += _iban_spans(text)
        spans += _national_id_spans(text)
        return sorted(spans, key=lambda s: s.start)

    def entity_counts(self, text: str) -> dict[str, int]:
        """Convenience method: count matches per entity type (useful for
        quick corpus statistics without invoking the full fusion pipeline)."""
        counts = {et: 0 for et in self.entity_types}
        for span in self.detect(text):
            counts[span.entity_type] = counts.get(span.entity_type, 0) + 1
        return counts
