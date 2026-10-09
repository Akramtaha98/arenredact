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
   and long-run attacks via repeated kashida insertion.
5. (revision 2) Removal of invisible format characters (Unicode category Cf,
   U+034F, variation selectors, U+3164, U+115F/1160), which an attacker can
   insert inside an identifier without changing how it renders.
6. (revision 2) Folding of Latin look-alike letters (Cyrillic, Greek) inside
   tokens that also contain ASCII letters or digits, so that a confusable
   letter in an IBAN or e-mail address does not hide it from Stage 3.

Each step can be enabled or disabled individually (`steps=`), which is what
the component ablation in the paper uses; the default is all steps.
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


ALL_STEPS = ("nfkc", "bidi", "invisible", "digits", "tatweel", "confusables")

# Characters an attacker can insert without changing the rendered text.
_EXTRA_INVISIBLE = {0x034F, 0x115F, 0x1160, 0x3164, 0xFFA0, 0x180B, 0x180C, 0x180D, 0x180E}
_EXTRA_INVISIBLE |= set(range(0xFE00, 0xFE10)) | set(range(0xE0100, 0xE01F0))


def _is_invisible(ch: str) -> bool:
    cp = ord(ch)
    return unicodedata.category(ch) == "Cf" or cp in _EXTRA_INVISIBLE


def strip_invisible(text: str) -> tuple[str, int]:
    """Remove invisible format characters. Returns (clean_text, count_removed)."""
    out = [ch for ch in text if not _is_invisible(ch)]
    return "".join(out), len(text) - len(out)


# Look-alike letters that NFKC does not fold (Cyrillic and Greek capitals and
# lowercase letters whose glyphs are near-identical to Latin letters).
_CONFUSABLE_MAP = str.maketrans({
    # Cyrillic
    "\u0410": "A", "\u0412": "B", "\u0415": "E", "\u041A": "K", "\u041C": "M", "\u041D": "H",
    "\u041E": "O", "\u0420": "P", "\u0421": "C", "\u0422": "T", "\u0425": "X", "\u0406": "I",
    "\u0408": "J", "\u0405": "S",
    "\u0430": "a", "\u0435": "e", "\u043E": "o", "\u0440": "p", "\u0441": "c", "\u0443": "y",
    "\u0445": "x", "\u0456": "i", "\u0458": "j", "\u0455": "s", "\u04BB": "h", "\u0501": "d",
    # Greek
    "\u0391": "A", "\u0392": "B", "\u0395": "E", "\u0396": "Z", "\u0397": "H", "\u0399": "I",
    "\u039A": "K", "\u039C": "M", "\u039D": "N", "\u039F": "O", "\u03A1": "P", "\u03A4": "T",
    "\u03A5": "Y", "\u03A7": "X",
    "\u03BF": "o", "\u03BD": "v", "\u03B9": "i", "\u03C1": "p", "\u03C5": "u",
})
_CONFUSABLE_CHARS = {chr(k) for k in _CONFUSABLE_MAP}
_TOKEN_RE = re.compile(r"\S+")


def fold_confusables(text: str) -> tuple[str, int]:
    """Replace Cyrillic/Greek look-alikes by their Latin counterparts, but only
    inside whitespace-delimited tokens that also contain an ASCII letter or
    digit. A token written wholly in Cyrillic or Greek is left unchanged, so
    ordinary text in those scripts is not corrupted."""
    count = 0

    def repl(m: re.Match) -> str:
        nonlocal count
        tok = m.group(0)
        if not any(c in _CONFUSABLE_CHARS for c in tok):
            return tok
        if not any(("a" <= c <= "z") or ("A" <= c <= "Z") or ("0" <= c <= "9") for c in tok):
            return tok
        out = tok.translate(_CONFUSABLE_MAP)
        count += sum(1 for a, b in zip(tok, out) if a != b)
        return out

    return _TOKEN_RE.sub(repl, text), count


@dataclass(frozen=True)
class NormalizationReport:
    """Records which defensive transforms fired, for audit-log provenance."""

    nfkc_changed: bool
    bidi_chars_stripped: int
    digits_normalized: int
    tatweel_runs_capped: int
    invisible_chars_stripped: int = 0
    confusables_folded: int = 0

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
            or self.invisible_chars_stripped > 0
            or self.confusables_folded > 0
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


def normalize(text: str, steps: tuple[str, ...] = ALL_STEPS) -> str:
    """Apply Stage 1 (all steps by default). Convenience wrapper around
    `normalize_with_report` for callers that don't need provenance detail."""
    normalized, _ = normalize_with_report(text, steps)
    return normalized


def normalize_with_report(
    text: str, steps: tuple[str, ...] = ALL_STEPS
) -> tuple[str, NormalizationReport]:
    """Apply the enabled Stage 1 steps in a fixed order (NFKC, bidi,
    invisible, digits, tatweel, confusables) and return the cleaned text with a
    report of what fired. Disabling steps exists for ablation experiments."""
    unknown = set(steps) - set(ALL_STEPS)
    if unknown:
        raise ValueError(f"unknown normalization steps: {sorted(unknown)}")
    cur = text
    nfkc_changed = False
    if "nfkc" in steps:
        nfk = unicodedata.normalize("NFKC", cur)
        nfkc_changed = nfk != cur
        cur = nfk
    bidi = 0
    if "bidi" in steps:
        cur, bidi = strip_bidi_controls(cur)
    inv = 0
    if "invisible" in steps:
        cur, inv = strip_invisible(cur)
    dig = 0
    if "digits" in steps:
        cur, dig = normalize_digits(cur)
    tat = 0
    if "tatweel" in steps:
        cur, tat = cap_tatweel(cur)
    conf = 0
    if "confusables" in steps:
        cur, conf = fold_confusables(cur)
    return cur, NormalizationReport(
        nfkc_changed=nfkc_changed,
        bidi_chars_stripped=bidi,
        digits_normalized=dig,
        tatweel_runs_capped=tat,
        invisible_chars_stripped=inv,
        confusables_folded=conf,
    )
