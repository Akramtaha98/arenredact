"""Shared evaluation utilities (revision 2): systems, scoring, relabelled sets,
stratification, output-leakage scoring and code provenance."""

from __future__ import annotations

import hashlib
import math
import os
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from arenredact.pattern_engine import PatternEngine  # noqa: E402
from arenredact.span_fusion import fuse_spans, redact  # noqa: E402
import arenredact.preprocessing as prep  # noqa: E402

TYPES = ("PHONE", "EMAIL", "IBAN", "NATIONAL_ID")
SHARED = ("PHONE", "EMAIL", "IBAN")  # types a stock Presidio install can in principle detect


# --------------------------------------------------------------------------- provenance
def code_sha256(pkg_dir: Path | None = None) -> str:
    """SHA-256 over every .py file of the arenredact package (sorted paths),
    so each results file records exactly which detector produced it."""
    pkg = pkg_dir or Path(prep.__file__).resolve().parent
    h = hashlib.sha256()
    for p in sorted(pkg.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        h.update(str(p.relative_to(pkg)).encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --------------------------------------------------------------------------- systems
HAS_STEPS = "steps" in prep.normalize_with_report.__code__.co_varnames


class OursSystem:
    """Deterministic tier with a configurable set of Stage 1 steps."""

    def __init__(self, steps=None):
        self.engine = PatternEngine()
        self.steps = steps

    def run(self, text: str):
        if self.steps is None:
            proc = prep.normalize(text)
        elif self.steps == ():
            proc = text
        else:
            proc = prep.normalize(text, tuple(self.steps)) if HAS_STEPS else prep.normalize(text)
        spans = fuse_spans(neural_spans=[], regex_spans=self.engine.detect(proc), text=proc)
        spans = [s for s in spans if s.entity_type in TYPES]
        return {(s.start, s.end, s.entity_type) for s in spans}, proc, redact(proc, spans)


PRES_MAP = {"EMAIL_ADDRESS": "EMAIL", "IBAN_CODE": "IBAN", "PHONE_NUMBER": "PHONE", "NATIONAL_ID": "NATIONAL_ID"}
GULF_REGIONS = ["SA", "AE", "EG", "IQ", "JO", "KW", "BH"]
NID_CONTEXT = ["id", "iqama", "identity", "identification", "civil", "national", "هوية",
               "الهوية", "إقامة", "الإقامة",
               "قومي", "بطاقة", "البطاقة"]


class PresidioSystem:
    """Presidio AnalyzerEngine on a blank spaCy pipeline.

    variant 'default'      : stock pattern recognizers, raw text
    variant 'norm'         : stock recognizers, input first passed through our Stage 1
    variant 'norm_regional': Stage 1 + phone recognizer restricted to the seven
                             regions + a national-ID PatternRecognizer with
                             Presidio's own context-word boost (score >= 0.6
                             required, i.e. context present)
    """

    def __init__(self, variant="default"):
        import spacy
        from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern, RecognizerRegistry
        from presidio_analyzer.nlp_engine import NlpEngineProvider
        from presidio_analyzer.predefined_recognizers import PhoneRecognizer

        self.variant = variant
        from spacy.language import Language

        if "lemma_lower" not in Language.factories:
            @Language.component("lemma_lower")
            def _lemma_lower(doc):  # blank pipelines have no lemmatizer; use the lower-cased token
                for tok in doc:
                    tok.lemma_ = tok.lower_
                return doc

        model_dir = "/tmp/blank_en_lemma_model"
        nlp0 = spacy.blank("en")
        nlp0.add_pipe("lemma_lower")
        nlp0.to_disk(model_dir)
        conf = {"nlp_engine_name": "spacy", "models": [{"lang_code": "en", "model_name": model_dir}]}
        nlp = NlpEngineProvider(nlp_configuration=conf).create_engine()
        registry = RecognizerRegistry()
        registry.load_predefined_recognizers(nlp_engine=nlp, languages=["en"])
        if variant == "norm_regional":
            registry.remove_recognizer("PhoneRecognizer")
            registry.add_recognizer(PhoneRecognizer(supported_regions=GULF_REGIONS))
            registry.add_recognizer(PatternRecognizer(
                supported_entity="NATIONAL_ID",
                patterns=[Pattern("ten_digit_id", r"(?<![+\d])\b\d{10}\b(?!\d)", 0.3)],
                context=NID_CONTEXT, supported_language="en"))
        kw = {}
        if variant == "norm_regional":
            # widen Presidio's context window (default: 5 tokens before, 0 after) to roughly
            # our 60-character look-back plus a short look-ahead, so that the comparison
            # does not hinge on a window-size default.
            from presidio_analyzer.context_aware_enhancers import LemmaContextAwareEnhancer
            kw["context_aware_enhancer"] = LemmaContextAwareEnhancer(context_prefix_count=12, context_suffix_count=4)
        self.an = AnalyzerEngine(nlp_engine=nlp, registry=registry, supported_languages=["en"], **kw)
        self.entities = ["EMAIL_ADDRESS", "IBAN_CODE", "PHONE_NUMBER"] + (["NATIONAL_ID"] if variant == "norm_regional" else [])

    def run(self, text: str):
        proc = prep.normalize(text) if self.variant != "default" else text
        res = self.an.analyze(text=proc, language="en", entities=self.entities)
        spans = []
        for r in res:
            if r.entity_type == "NATIONAL_ID" and r.score < 0.6:
                continue
            spans.append((r.start, r.end, PRES_MAP[r.entity_type]))
        spans = _resolve(spans)
        redacted = proc
        for s, e, t in sorted(spans, reverse=True):
            redacted = redacted[:s] + f"[{t}]" + redacted[e:]
        return set(spans), proc, redacted


def _resolve(spans):
    """Drop spans fully contained in a longer span of another type (Presidio
    often returns both PHONE and a nested digit match)."""
    spans = sorted(set(spans), key=lambda x: (x[0], -(x[1] - x[0])))
    out = []
    for s in spans:
        if any(o[0] <= s[0] and s[1] <= o[1] and (o[1] - o[0]) > (s[1] - s[0]) for o in out):
            continue
        out.append(s)
    return out


# --------------------------------------------------------------------------- scoring
def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def clopper_pearson_upper_zero(n: int, alpha: float = 0.05):
    return 1 - alpha ** (1 / n) if n > 0 else None


def _iou(a, b):
    inter = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    union = (a[1] - a[0]) + (b[1] - b[0]) - inter
    return inter / union if union else 0.0


def score_case(pred, gold, lenient=False):
    """Return per-type (tp, fp, fn) counters for one sentence."""
    out = {t: [0, 0, 0] for t in TYPES}
    pred, gold = set(pred), set(gold)
    matched_p = set()
    for g in gold:
        hit = None
        for p in pred:
            if p[2] != g[2] or p in matched_p:
                continue
            if (p[0], p[1]) == (g[0], g[1]) or (lenient and _iou(p, g) >= 0.5):
                hit = p
                break
        if hit:
            matched_p.add(hit)
            out[g[2]][0] += 1
        else:
            out[g[2]][2] += 1
    for p in pred:
        if p not in matched_p and p[2] in out:
            out[p[2]][1] += 1
    return out


def aggregate(cases, system, lenient=False, types=TYPES):
    tot = {t: [0, 0, 0] for t in TYPES}
    shifted = 0
    for text, gold in cases:
        pred, proc, _ = system.run(text)
        if len(proc) != len(text):
            shifted += 1
        r = score_case(pred, gold, lenient)
        for t in TYPES:
            for i in range(3):
                tot[t][i] += r[t][i]
    return tot, shifted


def summarize(tot, types):
    tp = sum(tot[t][0] for t in types); fp = sum(tot[t][1] for t in types); fn = sum(tot[t][2] for t in types)
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    f1 = 2 * prec * rec / (prec + rec) if prec and rec else (0.0 if tp + fp + fn else None)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": prec, "recall": rec, "f1": f1,
            "recall_wilson95": wilson(tp, tp + fn), "precision_wilson95": wilson(tp, tp + fp)}


# --------------------------------------------------------------------------- relabelled challenge sets
_PHONE00 = re.compile(r"\b00(?:966|971|20|964|962|965|973)\d{7,10}\b")
_PHONE_PAREN = re.compile(r"\+\d{2,3} \(\d{2,3}\) [\d-]+")
_IBAN_ANY = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]{2}\d{2}(?: ?[A-Za-z0-9]{4}){2,7}(?: ?[A-Za-z0-9]{1,4})?")
_IBAN_LEN = {"SA": 24, "AE": 23, "EG": 29, "BH": 22, "IQ": 23, "JO": 30, "KW": 30}
_LOCAL_NUMBER = re.compile(r"[Ll]ocal [A-Za-z ]*number|local number|call me at \d{9}|without the country code")


def relabel(cases):
    """The first-round challenge sets labelled formats the v1 engine could not
    parse (00-prefixed phones, parenthesised phones, lowercase IBANs, IBANs
    printed in 4-character groups) as NEGATIVE. They are real identifiers, so
    here they are relabelled as positives. Bare local numbers without a country
    code are ambiguous (a 9-digit run without context is not reliably a phone
    number) and are returned separately, not scored."""
    scored, ambiguous, changed = [], [], []
    for text, gold in cases:
        gold = [tuple(g) for g in gold]
        if gold:
            scored.append((text, gold)); continue
        if _LOCAL_NUMBER.search(text) and not (_PHONE00.search(text) or _PHONE_PAREN.search(text)):
            ambiguous.append(text); continue
        new = []
        m = _PHONE00.search(text)
        if m: new.append((m.start(), m.end(), "PHONE"))
        m = _PHONE_PAREN.search(text)
        if m: new.append((m.start(), m.end(), "PHONE"))
        for m in re.finditer(r"(?<![A-Za-z0-9])[A-Za-z]{2}\d{2}", text):
            total = _IBAN_LEN.get(m.group(0)[:2].upper())
            if not total:
                continue
            i, got = m.start(), 0
            while i < len(text) and got < total:
                if text[i] == " " and got:
                    i += 1; continue
                if not (text[i].isascii() and text[i].isalnum()):
                    break
                got += 1; i += 1
            if got == total and not (i < len(text) and text[i].isascii() and text[i].isalnum()):
                new.append((m.start(), i, "IBAN"))
        if not new:
            m = re.search(r"\b(?:" + "|".join(k.lower() for k in _IBAN_LEN) + r")\d{2}[a-z0-9]{10,26}\b", text)
            if m and _IBAN_LEN.get(m.group(0)[:2].upper()) == len(m.group(0)):
                new.append((m.start(), m.end(), "IBAN"))
        if new:
            changed.append(text)
        scored.append((text, new))
    return scored, ambiguous, changed


# --------------------------------------------------------------------------- stratification
_CC = {"+966": "SA", "+971": "AE", "+20": "EG", "+964": "IQ", "+962": "JO", "+965": "KW", "+973": "BH"}


def _digit_script(s: str) -> str:
    kinds = set()
    for ch in s:
        if ch.isdigit():
            cp = ord(ch)
            kinds.add("western" if cp < 128 else "arabic_indic" if 0x660 <= cp <= 0x669 else
                      "ext_arabic_indic" if 0x6F0 <= cp <= 0x6F9 else "fullwidth" if 0xFF10 <= cp <= 0xFF19 else "other")
    if not kinds:
        return "none"
    return kinds.pop() if len(kinds) == 1 else "mixed"


def _ctx_lang(text: str) -> str:
    ar = sum(1 for c in text if "؀" <= c <= "ۿ")
    la = sum(1 for c in text if c.isascii() and c.isalpha())
    if ar and la and min(ar, la) / (ar + la) > 0.15:
        return "code_mixed"
    return "arabic" if ar > la else "english"


def stratum(text: str, g, meta=None):
    s, e, t = g
    val = text[s:e]
    country = (meta or {}).get("country")
    if not country:
        compact = unicodedata.normalize("NFKC", val).replace(" ", "")
        if t == "PHONE":
            if compact.startswith("00"): compact = "+" + compact[2:]
            country = next((v for k, v in _CC.items() if compact.startswith(k)), "other")
        elif t == "IBAN":
            country = compact[:2].upper()
        else:
            country = "n/a"
    fmt = (meta or {}).get("format")
    if not fmt:
        fmt = "spaced/grouped" if re.search(r"[ \-.()]", val) else "compact"
        if t == "IBAN" and val[:2].islower(): fmt = "lowercase"
    return {"type": t, "country": country, "digit_script": _digit_script(val),
            "context_language": _ctx_lang(text), "format": fmt}


# --------------------------------------------------------------------------- output leakage scoring
_CONF_ALL = getattr(prep, '_CONFUSABLE_MAP', {})  # noqa: SLF001 (absent in revision 1)
_EXTRA_CONF = str.maketrans({
    "Ꭺ": "A", "Ᏼ": "B", "Ꮯ": "C", "Ꭼ": "E", "Ꮪ": "S", "Ꮋ": "H",
    "ɑ": "a", "օ": "o", "ɡ": "g", "ı": "i", "ո": "n", "ս": "u",
    "ǀ": "l", "ƽ": "s"})


def canon(s: str) -> str:
    """Reader-equivalent canonical form used ONLY for scoring: what a human or
    a lenient parser would read. Strips format characters, folds compatibility
    forms, digits and all look-alikes (a superset of the defence), drops
    everything that is not a letter or digit."""
    s = unicodedata.normalize("NFKC", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Cf" and not (0xFE00 <= ord(c) <= 0xFE0F))
    s = s.translate(prep._DIGIT_TRANSLATION).translate(_CONF_ALL).translate(_EXTRA_CONF)  # noqa: SLF001
    return "".join(c.lower() for c in s if c.isalnum())


def _count(hay: str, needle: str) -> int:
    n, pos = 0, hay.find(needle)
    while pos != -1:
        n += 1
        pos = hay.find(needle, pos + 1)
    return n


def leaks_v1(identifier: str, redacted_output: str, k: int = 6) -> bool:
    """Revision-2 scorer (kept for the scorer-validation study): any k-character
    fragment of the canonical identifier occurs anywhere in the canonical output.
    Over-counts when the surrounding text shares fragments with the identifier."""
    ic, oc = canon(identifier), canon(redacted_output)
    if len(ic) < k:
        return ic in oc
    return any(ic[i:i + k] in oc for i in range(len(ic) - k + 1))


def leaks_v2a(identifier: str, redacted_output: str, k: int = 6, context: str | None = None) -> bool:
    """Intermediate rule kept for the validation study: output count > context count,
    WITHOUT removing other copies of the identifier from the context. Fails when the
    identifier is repeated and the scored copy survives."""
    ic, oc = canon(identifier), canon(redacted_output)
    cc = canon(context) if context is not None else ""
    frags = [ic] if len(ic) < k else {ic[i:i + k] for i in range(len(ic) - k + 1)}
    return any(_count(oc, f) > _count(cc, f) for f in frags)


K_FRAGMENT = int(os.environ.get("LEAK_K", "6"))  # fragment length; 6 in the paper, varied in the sensitivity study


def leaks(identifier: str, redacted_output: str, k: int = K_FRAGMENT, context: str | None = None) -> bool:
    """True if a k-character fragment of the identifier (canonical form) is
    readable in the redacted output MORE OFTEN than it is readable in the
    surrounding text alone. `context` is the input sentence with the
    identifier's span removed; fragments that the context already contains
    (coincidental overlap such as a shared domain name) cannot by themselves
    count as leakage. Other copies of the full identifier inside the context
    are removed from it first, so a surviving copy of the identifier anywhere
    in the output is counted, including when the identifier is repeated. Independent of span offsets, so length-changing
    attacks are scored correctly. Identifiers shorter than k are matched whole.
    Without `context` the function degrades to the v1 rule."""
    if os.environ.get("LEAK_SCORER") == "v1":  # sensitivity study only
        context = None
    ic, oc = canon(identifier), canon(redacted_output)
    cc = canon(context) if context is not None else ""
    if cc and ic:
        # other copies of the SAME identifier in the surrounding text are identifier
        # content, not coincidental text: remove them, so that a surviving copy
        # anywhere in the output is counted (repeated-identifier case)
        cc = cc.replace(ic, "")
    frags = [ic] if len(ic) < k else {ic[i:i + k] for i in range(len(ic) - k + 1)}
    return any(_count(oc, f) > _count(cc, f) for f in frags)


def eval_sha256() -> str:
    """SHA-256 over every script in scripts/ (scorer, attack procedure, Presidio
    configuration, datasets), so a result identifies the complete experiment and
    not only the detector package."""
    h = hashlib.sha256()
    root = Path(__file__).resolve().parent
    for p in sorted(root.glob("*.py")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()
