#!/usr/bin/env python
"""Comparative evaluation and attack audit for the DETERMINISTIC tier.

Produces results/evaluation_suite.json, the single source for the
comparison, ablation and attack-audit tables in the manuscript (Tables 5-9).
No neural component is involved; every number is computed by executing code
in this repository (and, for the external baseline, the open-source
Microsoft Presidio analyzer) on CPU.

Systems compared
----------------
  ours_full        ArEnRedact deterministic tier: Stage 1 (NFKC, bidi strip,
                   digit folding, Tatweel cap) + Stage 3 pattern engine.
  ours_no_stage1   Same pattern engine WITHOUT Stage 1 (normalization
                   ablation).
  presidio         Presidio AnalyzerEngine (pattern recognizers only; a blank
                   spaCy pipeline is used so no statistical NER model is
                   involved) restricted to EMAIL_ADDRESS, IBAN_CODE and
                   PHONE_NUMBER, mapped to EMAIL, IBAN, PHONE. Presidio ships
                   no recognizer for the Gulf 10-digit national ID, so that
                   type is out of its scope by design (reported as such).

Evaluation sets
---------------
  synthetic test split (generator-compatible, 897 sentences), the 168-sentence
  extended challenge set, and the frozen 25-sentence holdout. The holdout is
  scored here only for systems other than ours_full's originally recorded
  run; the original ours_full holdout result stays in
  results/noisy_challenge_set_holdout.json and is NOT overwritten.

Attack audit
------------
For each operator the script reports how many in-scope structured entities
were actually altered (changed input), and detection with and without Stage 1.
ARZ, TAT and DIA act on Arabic-script letters; the audit counts how many
structured identifiers they alter (expected: none), and separately how many
PERSON-name spans they alter (these cannot be scored here because no
name detector is executed in the deterministic tier).

Usage:
    pip install presidio-analyzer spacy      # optional baseline
    python scripts/evaluation_suite.py
"""

from __future__ import annotations

import json
import math
import os
import platform
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from arenredact.attacks.operators import (  # noqa: E402
    OPERATOR_FUNCS,
    AttackOperator,
    apply_homoglyph_substitution,
)
from arenredact.data.corpus_generator import generate_corpus  # noqa: E402
from arenredact.pattern_engine import PatternEngine  # noqa: E402
from arenredact.pipeline import ArEnRedactPipeline  # noqa: E402
from arenredact.preprocessing import normalize  # noqa: E402

SEED = 42
N_SENTENCES = 8970
IN_SCOPE = ("PHONE", "EMAIL", "IBAN", "NATIONAL_ID")
PRESIDIO_MAP = {"EMAIL_ADDRESS": "EMAIL", "IBAN_CODE": "IBAN", "PHONE_NUMBER": "PHONE"}


# ----------------------------------------------------------------------------
# Systems: raw text -> set of (start, end, type)
# ----------------------------------------------------------------------------
def build_systems():
    pipe = ArEnRedactPipeline()
    engine = PatternEngine()
    systems = {
        "ours_full": lambda t: {
            (s.start, s.end, s.entity_type) for s in pipe.redact(t, record_audit=False).spans
        },
        "ours_no_stage1": lambda t: {(s.start, s.end, s.entity_type) for s in engine.detect(t)},
    }
    meta = {}
    try:
        import presidio_analyzer
        import spacy
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider

        blank_dir = os.path.join(os.environ.get("TMPDIR", "/tmp"), "arenredact_blank_en")
        spacy.blank("en").to_disk(blank_dir)
        provider = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": blank_dir}],
            }
        )
        analyzer = AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["en"])

        def presidio(t):
            out = set()
            for r in analyzer.analyze(text=t, language="en", entities=list(PRESIDIO_MAP)):
                out.add((r.start, r.end, PRESIDIO_MAP[r.entity_type]))
            return out

        systems["presidio"] = presidio
        import importlib.metadata as _md
        meta["presidio_version"] = _md.version("presidio-analyzer")
    except Exception as exc:  # pragma: no cover - optional dependency
        meta["presidio_error"] = repr(exc)
    return systems, meta


# ----------------------------------------------------------------------------
# Scoring helpers
# ----------------------------------------------------------------------------
def score(cases, predict):
    """cases: list of (text, set[(s,e,type)]). Returns overall + per-type."""
    per = {t: {"gold": 0, "tp": 0, "fp": 0, "fn": 0} for t in IN_SCOPE}
    for text, gold in cases:
        pred = {p for p in predict(text) if p[2] in IN_SCOPE}
        gold = {g for g in gold if g[2] in IN_SCOPE}
        for g in gold:
            per[g[2]]["gold"] += 1
        for g in gold & pred:
            per[g[2]]["tp"] += 1
        for p in pred - gold:
            per[p[2]]["fp"] += 1
        for g in gold - pred:
            per[g[2]]["fn"] += 1
    tp = sum(v["tp"] for v in per.values())
    fp = sum(v["fp"] for v in per.values())
    fn = sum(v["fn"] for v in per.values())
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    for v in per.values():
        v["recall"] = v["tp"] / v["gold"] if v["gold"] else None
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f1, "per_type": per}


def clopper_pearson_upper(k, n, alpha=0.05):
    """One-sided exact upper bound; for k=0 this is 1-alpha^(1/n)."""
    if n == 0:
        return None
    if k == 0:
        return 1 - alpha ** (1 / n)
    from scipy.stats import beta

    return float(beta.ppf(1 - alpha, k + 1, n - k))


def wilson(k, n, z=1.96):
    if n == 0:
        return (None, None)
    ph = k / n
    d = 1 + z * z / n
    c = ph + z * z / (2 * n)
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


# ----------------------------------------------------------------------------
def main():
    systems, meta = build_systems()
    results = {
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "seed": SEED,
            **meta,
        },
        "systems": list(systems),
    }

    corpus = generate_corpus(n_sentences=N_SENTENCES, seed=SEED, arabizi_rate=0.30)
    test = corpus[int(0.8 * N_SENTENCES) + int(0.1 * N_SENTENCES):]

    # ---- 1. clean detection on three evaluation sets ----
    synth_cases = [
        (r.text, {(e.start, e.end, e.entity_type) for e in r.entities if e.entity_type in IN_SCOPE})
        for r in test
    ]
    import noisy_challenge_set as ext
    import noisy_challenge_set_holdout as hold
    import validity_realistic_set as valid

    ext_cases = [(t, {tuple(g) for g in gold}) for t, gold in ext.CASES]
    hold_cases = [(t, {tuple(g) for g in gold}) for t, gold in hold.CASES]
    valid_cases = [(t, {tuple(g) for g in gold}) for t, gold in valid.CASES]
    sets = {
        "synthetic_test_897": synth_cases,
        "extended_challenge_168": ext_cases,
        "frozen_holdout_25": hold_cases,
        "validity_realistic_112": valid_cases,
    }
    clean = {}
    for sname, cases in sets.items():
        clean[sname] = {name: score(cases, fn) for name, fn in systems.items()}
        clean[sname]["n_cases"] = len(cases)
        clean[sname]["n_gold"] = sum(len(g) for _, g in cases)
    results["clean_detection"] = clean

    # ---- 2. attack audit on the synthetic test split ----
    def perturb(op, budget, text, spans, seed):
        rng = random.Random(seed)
        if op == "hgl":
            return apply_homoglyph_substitution(text, spans, budget=budget, rng=rng)
        return OPERATOR_FUNCS[AttackOperator(op)](text, spans=spans, rng=rng)

    configs = [
        ("arz", None, "ARZ"),
        ("tat", None, "TAT"),
        ("dia", None, "DIA"),
        ("hgl", 0.20, "HGL (paper default, 20% of digits)"),
        ("hgl", 1.00, "HGL (worst case, 100% of digits)"),
        ("cmb", None, "CMB (stochastic composition)"),
    ]
    from collections import namedtuple

    Ent = namedtuple("Ent", "start end entity_type")

    def run_audit(records):
        """records: list of (text, [Ent in scope], [Ent PERSON])."""
        audit = []
        for op, budget, label in configs:
            row = {"operator": label, "n_in_scope": 0, "n_changed": 0, "length_changed_sentences": 0}
            per_sys = {n: {"clean_tp": 0, "adv_tp_all": 0, "changed_clean_tp": 0, "changed_adv_tp": 0}
                       for n in systems}
            n_person, n_person_changed = 0, 0
            for ridx, (text, ents, names) in enumerate(records):
                if names:
                    pt_names = perturb(op, budget, text, [(e.start, e.end) for e in names], SEED + ridx)
                    n_person += len(names)
                    if len(pt_names) == len(text):
                        n_person_changed += sum(pt_names[e.start:e.end] != text[e.start:e.end] for e in names)
                    else:  # length-changing operators: the sentence's names were altered
                        n_person_changed += len(names)
                if not ents:
                    continue
                spans = [(e.start, e.end) for e in ents]
                pt = perturb(op, budget, text, spans, SEED + ridx)
                if len(pt) != len(text):
                    row["length_changed_sentences"] += 1
                    continue  # offset-based scoring invalid; counted and reported
                changed = {(e.start, e.end, e.entity_type): pt[e.start:e.end] != text[e.start:e.end] for e in ents}
                row["n_in_scope"] += len(ents)
                row["n_changed"] += sum(changed.values())
                for name, fn in systems.items():
                    clean_pred = fn(text)
                    adv_pred = fn(pt)
                    for e in ents:
                        key = (e.start, e.end, e.entity_type)
                        c_ok = key in clean_pred
                        a_ok = key in adv_pred
                        per_sys[name]["clean_tp"] += c_ok
                        per_sys[name]["adv_tp_all"] += (c_ok and a_ok)
                        if changed[key] and c_ok:
                            per_sys[name]["changed_clean_tp"] += 1
                            per_sys[name]["changed_adv_tp"] += a_ok
            row["person_spans_in_test"] = n_person
            row["person_spans_changed"] = n_person_changed
            row["systems"] = {}
            for name, v in per_sys.items():
                asr_all = (v["clean_tp"] - v["adv_tp_all"]) / v["clean_tp"] if v["clean_tp"] else None
                n_c = v["changed_clean_tp"]
                k_missed = n_c - v["changed_adv_tp"]
                lo, hi = wilson(k_missed, n_c)
                row["systems"][name] = {
                    **v,
                    "asr_over_all_clean_tp": asr_all,
                    "asr_over_changed": (k_missed / n_c) if n_c else None,
                    "changed_missed": k_missed,
                    "changed_asr_wilson95": [lo, hi],
                    "changed_asr_exact_upper95_if_zero": clopper_pearson_upper(0, n_c) if k_missed == 0 else None,
                }
            audit.append(row)
        return audit

    synth_records = [
        (r.text,
         [Ent(e.start, e.end, e.entity_type) for e in r.entities if e.entity_type in IN_SCOPE],
         [Ent(e.start, e.end, e.entity_type) for e in r.entities if e.entity_type == "PERSON"])
        for r in test
    ]
    valid_records = [(t, [Ent(*g) for g in sorted(gold)], []) for t, gold in valid_cases]
    audit = run_audit(synth_records)
    results["attack_audit_validity_realistic"] = run_audit(valid_records)
    results["attack_audit_synthetic_test"] = audit

    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results", "evaluation_suite.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # ---- human-readable summary ----
    for sname, d in clean.items():
        print(f"\n[{sname}] cases={d['n_cases']} gold={d['n_gold']}")
        for name in systems:
            s = d[name]
            print(f"  {name:15s} P={s['precision']:.3f} R={s['recall']:.3f} F1={s['f1']:.3f} "
                  f"(TP={s['tp']} FP={s['fp']} FN={s['fn']})")
    print("\n[attack audit]")
    for row in audit:
        print(f"  {row['operator']}: in-scope={row['n_in_scope']} changed={row['n_changed']} "
              f"person={row['person_spans_in_test']} person_changed={row['person_spans_changed']} "
              f"len_changed_sent={row['length_changed_sentences']}")
        for name, v in row["systems"].items():
            print(f"     {name:15s} cleanTP={v['clean_tp']} advTP={v['adv_tp_all']} "
                  f"ASR_all={v['asr_over_all_clean_tp']} ASR_changed={v['asr_over_changed']} "
                  f"(missed {v['changed_missed']}/{v['changed_clean_tp']})")
    print("\nWrote", out)


if __name__ == "__main__":
    main()
