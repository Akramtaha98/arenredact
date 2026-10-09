"""Frozen holdout challenge set (Section 6.1 addendum, test-set-adaptation check).

Provenance and timeline (read before citing this as evidence — this section
exists specifically to answer a test-set-adaptation concern raised in review):

  1. `noisy_challenge_set.py`'s original 28 cases (the "development set") were
     written first and used to discover two real pattern-engine bugs: the
     phone/national-ID digit-run ambiguity and the all-digit-only Bahrain IBAN
     pattern. Both bugs were then fixed in `pattern_engine.py`.
  2. `noisy_challenge_set.py`'s remaining 140 cases (the "extended set",
     7-country coverage) were written and added AFTER those fixes were
     already in place, specifically to broaden country/format coverage. They
     are a regression/coverage check, not blind holdout evidence for the two
     fixed bugs specifically — the author knew the fix existed while writing
     them, which is a real source of potential test-set adaptation bias.
  3. THIS file's cases were written after (1) and (2) were both finalized and
     frozen, using a different deterministic fake-digit source (digits of e,
     not pi, so no value overlaps the development or extended sets) and
     templates/scenarios not reused from either. It was run exactly once,
     and the result recorded here (see results/noisy_challenge_set_holdout.json)
     is reported as-is, whatever it turned out to be — this file is not
     iterated on in response to its own pass/fail output. If a future
     revision adds cases to this file in response to an error it produced,
     that will be disclosed explicitly rather than silently.

This is still author-constructed, not independently human-annotated — it
reduces (does not eliminate) test-set-adaptation risk for the specific two
bugs found in the development set, and says nothing about generalization
beyond the formatting variation this author thought to construct. Independent
human-annotated holdout data remains future work (Section 8.5).
"""

from __future__ import annotations

# Digits of e (2.718281828...), distinct from the pi-based pool used by
# noisy_challenge_set.py, so no fake identifier value overlaps that file.
_E_DIGITS = (
    "718281828459045235360287471352662497757247093699959574966967627724076"
    "630353547594571382178525166427427466391932003059921817413596629043572"
)


def _digits(n: int, offset: int) -> str:
    pool = _E_DIGITS * 3
    return pool[offset: offset + n]


_RAW_CASES: list[tuple[str, list[tuple[str, str]]]] = [
    # ---- Phone: one positive per country, new sentence frames ----
    (f"They asked me to phone +966{_digits(9, 0)} once the shipment clears customs.",
     [(f"+966{_digits(9, 0)}", "PHONE")]),
    (f"Could you try +971 {_digits(2,9)} {_digits(3,11)} {_digits(4,14)} if the office line is busy?",
     [(f"+971 {_digits(2,9)} {_digits(3,11)} {_digits(4,14)}", "PHONE")]),
    (f"His WhatsApp is +20-{_digits(3,18)}-{_digits(3,21)}-{_digits(3,24)}, not the landline.",
     [(f"+20-{_digits(3,18)}-{_digits(3,21)}-{_digits(3,24)}", "PHONE")]),
    (f"إذا احتجت مساعدة اتصل على +964{_digits(9,27)} بعد الظهر.",
     [(f"+964{_digits(9,27)}", "PHONE")]),
    (f"Reception in Amman answers at +962{_digits(9,36)} during business hours.",
     [(f"+962{_digits(9,36)}", "PHONE")]),
    (f"For Kuwait deliveries, coordinate via +965{_digits(9,45)} before noon.",
     [(f"+965{_digits(9,45)}", "PHONE")]),
    (f"Bahrain support line: +973{_digits(9,54)}, available Sunday to Thursday.",
     [(f"+973{_digits(9,54)}", "PHONE")]),

    # ---- Phone negatives: new near-miss shapes not used in dev/extended ----
    (f"He just said \"call me at {_digits(9,63)}\" without giving the country code.", []),
    (f"The internal extension is 4{_digits(3,72)}, that's not a full external number.", []),

    # ---- IBAN: subset of countries, new sentence frames ----
    (f"SA{_digits(22,0)} is the account we used last quarter.",
     [(f"SA{_digits(22,0)}", "IBAN")]),
    (f"Bahrain settlement account: BH{_digits(2,22)}BMAG{_digits(14,24)}.",
     [(f"BH{_digits(2,22)}BMAG{_digits(14,24)}", "IBAN")]),
    (f"حساب الفرع في العراق هو IQ{_digits(2,38)}RAFB{_digits(15,40)}.",
     [(f"IQ{_digits(2,38)}RAFB{_digits(15,40)}", "IBAN")]),
    (f"EG{_digits(27,55)} was flagged for review this morning.",
     [(f"EG{_digits(27,55)}", "IBAN")]),
    (f"Wire instructions list sa{_digits(22,0)} in lowercase — please recheck before sending.", []),

    # ---- National ID: new context phrasing, EN and AR ----
    (f"His civil registry number, {_digits(10,82)}, needs to be updated on file.",
     [(f"{_digits(10,82)}", "NATIONAL_ID")]),
    (f"سجّل الموظف رقم هويته {_digits(10,92)} في الاستمارة الجديدة.",
     [(f"{_digits(10,92)}", "NATIONAL_ID")]),

    # ---- National ID negatives: new near-miss shapes ----
    (f"Invoice reference {_digits(10,102)} does not correspond to any person.", []),
    (f"The warehouse barcode reads {_digits(10,112)} on the outer carton.", []),

    # ---- Email: new formats ----
    (f"Reply-to address for the ticket is support+case{_digits(4,0)}@helpdesk-mena.io.",
     [(f"support+case{_digits(4,0)}@helpdesk-mena.io", "EMAIL")]),
    (f"شارك الملف مع reviewer.team@arenredact-project.dev قبل الاجتماع.",
     [("reviewer.team@arenredact-project.dev", "EMAIL")]),

    # ---- Free-form / code-switched, new phrasing ----
    (f"يا ريت تبعتلي IBAN بتاعك على الايميل، أو حتى ابعته على +20{_digits(9,18)}.",
     [(f"+20{_digits(9,18)}", "PHONE")]),
    (f"Please confirm the civil ID {_digits(10,122)} matches what's on the Kuwait residency card, لو سمحت.",
     [(f"{_digits(10,122)}", "NATIONAL_ID")]),

    # ---- Pure distractors ----
    (f"Order quantity for this batch was {_digits(10,132)} units, not a document number.", []),
    ("Meeting moved to 09:45 on the fourteenth, same room as last time.", []),

    # ---- Combo sentences: multiple entity types ----
    (f"Jordan branch contact: {_digits(10,142)} (civil ID), call +962{_digits(9,36)}, or email reviewer.team@arenredact-project.dev.",
     [(f"{_digits(10,142)}", "NATIONAL_ID"), (f"+962{_digits(9,36)}", "PHONE"),
      ("reviewer.team@arenredact-project.dev", "EMAIL")]),
]


def _resolve_gold(text: str, entries: list[tuple[str, str]]) -> list[tuple[int, int, str]]:
    resolved = []
    for substring, entity_type in entries:
        start = text.index(substring)
        resolved.append((start, start + len(substring), entity_type))
    return resolved


CASES: list[tuple[str, list[tuple[int, int, str]]]] = [
    (text, _resolve_gold(text, entries)) for text, entries in _RAW_CASES
]


def run_holdout() -> dict:
    from arenredact.pipeline import ArEnRedactPipeline

    pipeline = ArEnRedactPipeline()
    tp = fp = fn = 0
    per_item = []

    entity_types = ("PHONE", "EMAIL", "IBAN", "NATIONAL_ID")
    per_type = {et: {"tp": 0, "fp": 0, "fn": 0, "gold": 0} for et in entity_types}

    for text, gold in CASES:
        result = pipeline.redact(text, record_audit=False)
        gold_set = {(s, e, t) for s, e, t in gold}
        pred_set = {(s.start, s.end, s.entity_type) for s in result.spans}

        item_tp = gold_set & pred_set
        item_fp = pred_set - gold_set
        item_fn = gold_set - pred_set
        tp += len(item_tp)
        fp += len(item_fp)
        fn += len(item_fn)

        for (_, _, t) in gold_set:
            if t in per_type:
                per_type[t]["gold"] += 1
        for (_, _, t) in item_tp:
            if t in per_type:
                per_type[t]["tp"] += 1
        for (_, _, t) in item_fp:
            if t in per_type:
                per_type[t]["fp"] += 1
        for (_, _, t) in item_fn:
            if t in per_type:
                per_type[t]["fn"] += 1

        per_item.append({
            "text": text,
            "gold": sorted(gold_set),
            "predicted": sorted(pred_set),
            "correct": sorted(item_tp),
            "false_positives": sorted(item_fp),
            "false_negatives": sorted(item_fn),
        })

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    n_positive_identifiers = sum(len(gold) for _, gold in CASES)

    return {
        "n_cases": len(CASES),
        "n_positive_identifiers": n_positive_identifiers,
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "per_type": {
            et: {**c, **({
                "precision": c["tp"] / (c["tp"] + c["fp"]) if (c["tp"] + c["fp"]) else 0.0,
                "recall": c["tp"] / (c["tp"] + c["fn"]) if (c["tp"] + c["fn"]) else 0.0,
            })}
            for et, c in per_type.items()
        },
        "per_item": per_item,
    }


if __name__ == "__main__":
    import json
    import os

    results = run_holdout()
    out_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "results",
        "noisy_challenge_set_holdout.json",
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"n_cases={results['n_cases']}  n_positive_identifiers={results['n_positive_identifiers']}")
    print(f"P={results['precision']:.3f}  R={results['recall']:.3f}  F1={results['f1']:.3f}")
    print(f"TP={results['true_positives']}  FP={results['false_positives']}  FN={results['false_negatives']}")
    print(f"Wrote {out_path}")
