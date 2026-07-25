"""Adversarial attack operators (Section 3.5 / 5.2 of the paper).

Five perturbation operators targeting the Arabic-English code-mixed PII
detection surface. Each operator accepts the full text plus an optional list
of `(start, end)` character-offset ranges identifying the PII entity tokens
to perturb (if omitted, the operator treats the whole string as one token —
convenient for unit testing, but production adversarial-set construction
should always pass entity spans from the corpus annotations).

    ARZ  Arabizi Substitution      arabizi_substitution
    TAT  Tatweel Injection         apply_tatweel_injection
    DIA  Diacritization Attack     apply_diacritization_attack
    HGL  Homoglyph Substitution    apply_homoglyph_substitution
    CMB  Combined Attack           apply_combined_attack

All operators are deterministic given a seeded `random.Random` instance,
so adversarial test sets are exactly reproducible across runs.
"""

from __future__ import annotations

import random
from enum import Enum

from arenredact.data.lexicons import DA3I_MAPPING

Span = tuple[int, int]


class AttackOperator(str, Enum):
    ARZ = "arz"
    TAT = "tat"
    DIA = "dia"
    HGL = "hgl"
    CMB = "cmb"


# Homoglyph substitution table: Latin/Arabic-Indic characters that are
# visually confusable with Arabic script or Western digits (Section 3.5 /
# Boucher et al., 2022). Applied *before* Stage 1 normalization in the
# threat model — i.e., these are the raw adversarial inputs Stage 1 must
# neutralize.
_HOMOGLYPH_TABLE: dict[str, str] = {
    "ا": "l",  # Arabic alif -> Latin lowercase L (visually similar in many fonts)
    "0": "٠", "1": "١", "2": "٢", "3": "٣", "4": "٤",
    "5": "٥", "6": "٦", "7": "٧", "8": "٨", "9": "٩",
}

# A small set of Arabic combining diacritics (tashkeel) for the DIA operator.
# For linguistically accurate diacritization, replace this with
# camel_tools.disambig.mle.MLEDisambiguator (see the `arabic` extra) — this
# lightweight version applies plausible-position diacritics without full
# morphological analysis, sufficient for adversarial robustness testing.
_TASHKEEL = ("ً", "ٌ", "ٍ", "َ", "ُ", "ِ", "ّ")

_ARABIC_LETTER_RE_CHARS = set(
    chr(c) for c in range(0x0621, 0x064A + 1)
)


def _default_spans(text: str, spans: list[Span] | None) -> list[Span]:
    return spans if spans is not None else [(0, len(text))]


def _apply_per_span(text: str, spans: list[Span], transform) -> str:
    """Apply `transform(substring) -> str` to each span, right-to-left so
    earlier offsets stay valid, and splice the results back into `text`."""
    out = text
    for start, end in sorted(spans, key=lambda s: s[0], reverse=True):
        out = out[:start] + transform(out[start:end]) + out[end:]
    return out


def arabizi_substitution(text: str, spans: list[Span] | None = None, budget: float = 1.0,
                          rng: random.Random | None = None) -> str:
    """ARZ — replace Arabic entity characters with Latin/digit surrogates
    using the Da3i phoneme mapping (Darwish, 2014). `budget` is the fraction
    of eligible characters within each span that get substituted (paper
    default: 100% of Arabic entity tokens)."""
    rng = rng or random.Random()

    def transform(sub: str) -> str:
        chars = list(sub)
        eligible_idxs = [i for i, c in enumerate(chars) if c in DA3I_MAPPING]
        n_to_replace = round(len(eligible_idxs) * budget)
        chosen = set(rng.sample(eligible_idxs, k=min(n_to_replace, len(eligible_idxs))))
        for i in chosen:
            chars[i] = DA3I_MAPPING[chars[i]]
        return "".join(chars)

    return _apply_per_span(text, _default_spans(text, spans), transform)


def apply_tatweel_injection(text: str, spans: list[Span] | None = None,
                             insert_every: int = 2,
                             rng: random.Random | None = None) -> str:
    """TAT — insert U+0640 (Tatweel/kashida) at alternating character
    positions within each span. `insert_every=2` matches the paper's budget
    of "1 insertion per 2 characters"."""
    rng = rng or random.Random()

    def transform(sub: str) -> str:
        out = []
        for i, ch in enumerate(sub):
            out.append(ch)
            if ch in _ARABIC_LETTER_RE_CHARS and (i + 1) % insert_every == 0:
                out.append("ـ")
        return "".join(out)

    return _apply_per_span(text, _default_spans(text, spans), transform)


def apply_diacritization_attack(text: str, spans: list[Span] | None = None,
                                 rng: random.Random | None = None) -> str:
    """DIA — inject tashkeel (diacritics) after Arabic letters within each
    span, simulating the distributional shift between diacritized and
    undiacritized training data. For production-grade linguistically
    accurate diacritization, swap in CAMeL Tools' MLE disambiguator (the
    `arabic` extra) — this operator is intentionally lightweight so the
    adversarial test set can be regenerated without a heavyweight
    dependency."""
    rng = rng or random.Random()

    def transform(sub: str) -> str:
        out = []
        for ch in sub:
            out.append(ch)
            if ch in _ARABIC_LETTER_RE_CHARS:
                out.append(rng.choice(_TASHKEEL))
        return "".join(out)

    return _apply_per_span(text, _default_spans(text, spans), transform)


def apply_homoglyph_substitution(text: str, spans: list[Span] | None = None,
                                  budget: float = 0.20,
                                  rng: random.Random | None = None) -> str:
    """HGL — substitute visually confusable Latin/Arabic-Indic characters
    for a random `budget` fraction of eligible characters per span (paper
    default: 20% of characters per token)."""
    rng = rng or random.Random()

    def transform(sub: str) -> str:
        chars = list(sub)
        eligible_idxs = [i for i, c in enumerate(chars) if c in _HOMOGLYPH_TABLE]
        n_to_replace = round(len(eligible_idxs) * budget)
        chosen = set(rng.sample(eligible_idxs, k=min(n_to_replace, len(eligible_idxs))))
        for i in chosen:
            chars[i] = _HOMOGLYPH_TABLE[chars[i]]
        return "".join(chars)

    return _apply_per_span(text, _default_spans(text, spans), transform)


def apply_combined_attack(text: str, spans: list[Span] | None = None,
                           per_token_prob: float = 0.25,
                           rng: random.Random | None = None) -> str:
    """CMB — stochastically compose all four operators, each independently
    applied with probability `per_token_prob` per span (paper default:
    0.25 each), simulating a sophisticated attacker exploiting multiple
    evasion channels simultaneously."""
    rng = rng or random.Random()
    resolved_spans = _default_spans(text, spans)

    result = text
    if rng.random() < per_token_prob:
        result = arabizi_substitution(result, resolved_spans, rng=rng)
    if rng.random() < per_token_prob:
        result = apply_tatweel_injection(result, resolved_spans, rng=rng)
    if rng.random() < per_token_prob:
        result = apply_diacritization_attack(result, resolved_spans, rng=rng)
    if rng.random() < per_token_prob:
        result = apply_homoglyph_substitution(result, resolved_spans, rng=rng)
    return result


#: Dispatch table used by scripts/run_adversarial_eval.py.
OPERATOR_FUNCS = {
    AttackOperator.ARZ: arabizi_substitution,
    AttackOperator.TAT: apply_tatweel_injection,
    AttackOperator.DIA: apply_diacritization_attack,
    AttackOperator.HGL: apply_homoglyph_substitution,
    AttackOperator.CMB: apply_combined_attack,
}
