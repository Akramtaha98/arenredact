"""Extended input-perturbation operators (revision 2).

The original operators (ARZ, TAT, DIA, HGL, CMB in operators.py) mostly touch
Arabic letters or digit script. These operators perturb the *identifier
itself* in ways that keep it readable to a human or downstream parser:

  INV   insert invisible format characters inside the identifier
  BIDI  insert bidirectional control characters inside the identifier
  FW    replace ASCII digits/letters with fullwidth or mathematical forms
  DIG   replace ASCII digits with Arabic-Indic or extended Arabic-Indic digits
  SEP   insert or change separators between characters (length-changing)
  CONF  replace Latin letters (IBAN country/bank code, e-mail) with
        look-alike letters from other scripts
  CTX   alter the identity keyword that precedes a national ID
  COMBO apply a random combination of the above

Operators take an identifier string and return a modified identifier string;
`apply_to_spans` rewrites a sentence and returns the new text together with
the transformed gold spans, so length-changing attacks keep correct gold
offsets. Each inventory exists in a "dev" and a "held-out" variant: the dev
inventory is what the Stage 1 rules were written against, the held-out
inventory contains characters that were not used while writing those rules.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

INV_DEV = ["​", "‌", "‍", "⁠", "﻿", "­"]
INV_HELD = ["⁢", "⁣", "᠎", "͏", "️", "‎", "‏", "\U000e0020"]
BIDI = ["‪", "‫", "‬", "‭", "‮", "⁦", "⁧", "⁨", "⁩", "؜"]
SEP_DEV = ["-", ".", " ", " ", " ", " "]
SEP_HELD = ["/", "_", "·", "•", ",", ";"]

# Look-alikes that Stage 1 folds (dev) and some it does not (held-out).
CONF_DEV = {"A": "А", "B": "В", "E": "Е", "K": "К", "M": "М", "H": "Н",
            "O": "О", "P": "Р", "C": "С", "T": "Т", "X": "Х", "S": "Ѕ",
            "a": "а", "e": "е", "o": "о", "p": "р", "c": "с", "x": "х",
            "i": "і", "y": "у"}
CONF_HELD = {"A": "Ꭺ", "B": "Ᏼ", "C": "Ꮯ", "E": "Ꭼ", "S": "Ꮪ", "H": "Ꮋ",
             "a": "ɑ", "o": "օ", "g": "ɡ", "i": "ı", "n": "ո", "u": "ս",
             "l": "ǀ", "v": "ν" , "d": "ԁ", "s": "ƽ"}

AR_INDIC = "٠١٢٣٤٥٦٧٨٩"
EXT_INDIC = "۰۱۲۳۴۵۶۷۸۹"

CTX_ZW = lambda kw, r: "​".join(kw)  # noqa: E731


def _fullwidth(ch: str, rng: random.Random) -> str:
    if ch.isdigit() and ch.isascii():
        return rng.choice([chr(0xFF10 + int(ch)), chr(0x1D7CE + int(ch)), chr(0x1D7D8 + int(ch))])
    if ch.isascii() and ch.isalpha():
        base = ord("A") if ch.isupper() else ord("a")
        return chr((0xFF21 if ch.isupper() else 0xFF41) + ord(ch) - base)
    return ch


def op_inv(ident: str, rng: random.Random, held: bool, rate: float = 0.35) -> str:
    inv = INV_HELD if held else INV_DEV
    out = []
    for i, ch in enumerate(ident):
        out.append(ch)
        if i < len(ident) - 1 and rng.random() < rate:
            out.append(rng.choice(inv))
    return "".join(out)


def op_bidi(ident: str, rng: random.Random, held: bool = False, rate: float = 0.35) -> str:
    out = []
    for i, ch in enumerate(ident):
        out.append(ch)
        if i < len(ident) - 1 and rng.random() < rate:
            out.append(rng.choice(BIDI))
    return "".join(out)


def op_fw(ident: str, rng: random.Random, held: bool = False, rate: float = 0.6) -> str:
    return "".join(_fullwidth(c, rng) if rng.random() < rate else c for c in ident)


def op_dig(ident: str, rng: random.Random, held: bool = False, rate: float = 0.6) -> str:
    table = AR_INDIC if rng.random() < 0.5 else EXT_INDIC
    return "".join(table[int(c)] if (c.isdigit() and c.isascii() and rng.random() < rate) else c for c in ident)


def op_sep(ident: str, rng: random.Random, held: bool, rate: float = 0.3) -> str:
    seps = SEP_HELD if held else SEP_DEV
    # only insert between two alphanumerics so that "+" prefixes stay attached
    out = []
    for i, ch in enumerate(ident):
        out.append(ch)
        if i < len(ident) - 1 and ch.isalnum() and ident[i + 1].isalnum() and rng.random() < rate:
            out.append(rng.choice(seps))
    return "".join(out)


def op_conf(ident: str, rng: random.Random, held: bool, rate: float = 0.5) -> str:
    table = CONF_HELD if held else CONF_DEV
    out = []
    changed = False
    for ch in ident:
        if ch in table and rng.random() < rate:
            out.append(table[ch]); changed = True
        else:
            out.append(ch)
    if not changed:  # force at least one substitution if any letter is eligible
        idx = [i for i, ch in enumerate(ident) if ch in table]
        if idx:
            i = rng.choice(idx)
            out = list(ident); out[i] = table[ident[i]]
    return "".join(out)


IDENT_OPS = {"INV": op_inv, "BIDI": op_bidi, "FW": op_fw, "DIG": op_dig, "SEP": op_sep, "CONF": op_conf}

CTX_KEYWORDS = ["national id", "id number", "iqama", "identity", "civil id",
                "الهوية", "هوية", "إقامة",
                "قومي", "بطاقة"]
CTX_SYNONYMS = ["civil number", "citizen number", "الرقم المدني",
                "رقم المواطن", "personal no.", "resident file"]
TASHKEEL = "َُِّْ"


def op_ctx(text: str, id_start: int, rng: random.Random, mode: str) -> str:
    """Alter the identity keyword in the 60 characters before the identifier.
    mode: 'zw' (zero-width inside keyword), 'tashkeel' (Arabic diacritics),
    'conf' (Cyrillic look-alike), 'synonym' (replace by an unlisted phrase)."""
    lo = max(0, id_start - 60)
    window = text[lo:id_start]
    low = window.lower()
    for kw in CTX_KEYWORDS:
        k = low.find(kw)
        if k == -1:
            continue
        a, b = lo + k, lo + k + len(kw)
        if mode == "zw":
            new = "​".join(text[a:b])
        elif mode == "tashkeel":
            new = "".join(c + (rng.choice(TASHKEEL) if "؀" <= c <= "ۿ" and rng.random() < 0.7 else "") for c in text[a:b])
        elif mode == "conf":
            new = "".join(CONF_DEV.get(c, c) if rng.random() < 0.6 else c for c in text[a:b])
        else:
            new = rng.choice(CTX_SYNONYMS)
        return text[:a] + new + text[b:]
    return text


@dataclass
class AppliedAttack:
    text: str
    gold: list  # [(start, end, type)] in the new text
    altered: list  # bool per gold item: identifier text changed


def apply_to_spans(text: str, spans, fn) -> AppliedAttack:
    """Rewrite each gold identifier with fn(identifier, type) and rebuild the
    sentence, tracking the new offsets of every identifier."""
    out, gold_new, altered = [], [], []
    cur = 0
    delta = 0
    for (s, e, t) in sorted(spans):
        out.append(text[cur:s])
        new_ident = fn(text[s:e], t)
        ns = s + delta
        out.append(new_ident)
        gold_new.append((ns, ns + len(new_ident), t))
        altered.append(new_ident != text[s:e])
        delta += len(new_ident) - (e - s)
        cur = e
    out.append(text[cur:])
    return AppliedAttack("".join(out), gold_new, altered)


def eligible(op: str, etype: str, ident: str) -> bool:
    if op == "CONF":
        return etype in ("IBAN", "EMAIL") and any(c.isalpha() for c in ident)
    if op == "CTX":
        return etype == "NATIONAL_ID"
    return True


ALL_OPS = ["INV", "BIDI", "FW", "DIG", "SEP", "CONF"]


def random_combo(ident: str, etype: str, rng: random.Random, k: int, held_prob: float = 0.5) -> str:
    ops = [o for o in ALL_OPS if eligible(o, etype, ident)]
    for o in rng.sample(ops, min(k, len(ops))):
        ident = IDENT_OPS[o](ident, rng, rng.random() < held_prob)
    return ident
