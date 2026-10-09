"""Stage 1 — Input Security and Unicode Normalization.

Implements the four normalization operations described in Section 4.1 of the
paper, applied before any content reaches the neural or regex detectors:

1. NFKC Unicode normalization (Unicode Standard Annex #15). NFC alone only
   composes canonically equivalent sequences and does NOT fold Arabic
   presentation forms (U+FB50-FDFF, U+FE70-FEFF) or full-width digits
   (U+FF10-FF19); those are compatibility characters and are folded to their
   base letters / ASCII digits only by the compatibility forms (NFKC/NFKD).
   NFKC is therefore used to close the compatibility-character
   (presentation-form, full-width) homoglyph surface.
2. Bidirectional control character stripping (U+202A-202E, U+2066-2069) to
   prevent Trojan-Source-class bidi injection (Boucher & Anderson).
3. Arabic-Indic / Extended Arabic-Indic digit normalization to Western digits,
   so that \\d-anchored regexes in the pattern engine (Stage 3) match all
   digit representations.
4. Tatweel (kashida, U+0640) sequence capping to defeat tokenization-inflation
   and ReDoS-style attacks via repeated kashida insertion.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Bidirectional control characters (Trojan-Source attack surface).
_BIDI_CONTROL_CHARS = "".join(
    chr(c) for c in range(0x202A, 0x202F)
) + "".join(chr(c) for c in range(0x2066, 0x206A))
_BIDI_STRIP_RE = re.compile(f"[{re.escape(_BIDI_CONTROL_CHARS)}]")

# Eastern Arabic-Indic digits (U+0660-0669) and Extended Arabic-Indic digits
# (U+06F0-06F9) mapped to Western equivalents (0-9).
_ARABIC_INDIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_EXTENDED_ARABIC_INDIC_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_WESTERN_DIGITS = "0123456789"
_DIGIT_TRANSLATION = str.maketrans(
    _ARABIC_INDIC_DIGITS + _EXTENDED_ARABIC_INDIC_DIGITS,
    _WESTERN_DIGITS + _WESTERN_DIGITS,
)

# Tatweel / kashida (U+0640): cap runs to at most 1 consecutive occurrence.
_TATWEEL = "ـ"
_TATWEEL_RUN_RE = re.compile(f"{_TATWEEL}{{2,}}")


@dataclass(frozen=True)
class NormalizationReport:
    """Records which defensive transforms fired, for audit-log provenance."""

    nfkc_changed: bool
    bidi_chars_stripped: int
    digits_normalized: int
    tatweel_runs_capped: int

    @property
    def any_adversarial_signal(self) -> bool:
        """True if any transform actually altered the input — a weak proxy
        for "this input looked like it might be trying something", useful
        for flagging inputs for closer audit-log review (Section 4.1)."""
        return (
            self.nfkc_changed
            or self.bidi_chars_stripped > 0
            or self.digits_normalized > 0
            or self.tatweel_runs_capped > 0
        )


def strip_bidi_controls(text: str) -> tuple[str, int]:
    """Remove bidirectional control characters. Returns (clean_text, count_removed)."""
    count = len(_BIDI_STRIP_RE.findall(text))
    return _BIDI_STRIP_RE.sub("", text), count


def normalize_digits(text: str) -> tuple[str, int]:
    """Fold Arabic-Indic and Extended Arabic-Indic digits to Western digits.

    Returns (converted_text, count_converted). Silent regex failures against
    \\d-anchored patterns (Section 3.5, HGL attack) are the direct motivation
    for this step running *before* Stage 3 pattern matching.
    """
    count = sum(
        1 for ch in text if ch in _ARABIC_INDIC_DIGITS or ch in _EXTENDED_ARABIC_INDIC_DIGITS
    )
    return text.translate(_DIGIT_TRANSLATION), count


def cap_tatweel(text: str, max_run: int = 1) -> tuple[str, int]:
    """Collapse runs of >= 2 consecutive Tatweel characters down to `max_run`.

    Mitigates both the tokenization-inflation attack (TAT, Section 3.5) and
    ReDoS amplification from adversarially long kashida sequences.
    """
    runs_found = len(_TATWEEL_RUN_RE.findall(text))
    collapsed = _TATWEEL_RUN_RE.sub(_TATWEEL * max_run, text)
    return collapsed, runs_found


def normalize(text: str) -> str:
    """Apply the full Stage 1 normalization chain. Convenience wrapper around
    `normalize_with_report` for callers that don't need provenance detail."""
    normalized, _ = normalize_with_report(text)
    return normalized


def normalize_with_report(text: str) -> tuple[str, NormalizationReport]:
    """Apply NFKC normalization, bidi stripping, digit folding, and Tatweel
    capping in sequence, returning both the cleaned text and a report of
    what fired (useful for audit-log entries per Section 4.5 / Stage 5)."""
    nfkc = unicodedata.normalize("NFKC", text)
    nfkc_changed = nfkc != text

    stripped, bidi_count = strip_bidi_controls(nfkc)
    digit_normalized, digit_count = normalize_digits(stripped)
    final, tatweel_count = cap_tatweel(digit_normalized)

    report = NormalizationReport(
        nfkc_changed=nfkc_changed,
        bidi_chars_stripped=bidi_count,
        digits_normalized=digit_count,
        tatweel_runs_capped=tatweel_count,
    )
    return final, report
