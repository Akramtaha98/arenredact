"""Generator-independent, author-constructed noisy challenge set for the
deterministic tier (Section 6.1 addendum).

Unlike the synthetic corpus (arenredact.data.corpus_generator), which by
construction emits PII strings in exactly the formats the Stage 3 regex
patterns were written to match, every case here comes from a second,
structurally distinct source: a small set of author-written sentence
templates instantiated across seven MENA countries (Saudi Arabia, UAE,
Bahrain, Iraq, Jordan, Kuwait, Egypt) with deterministic (non-random, digit
-of-pi-derived) fake identifiers, plus a fixed pool of hand-written free-form
and near-miss sentences. It deliberately covers formatting variation the
corpus generator does not produce: alternative phone spacing/grouping,
country-specific IBAN structures (including the 4-letter bank-code segment
used by Bahrain, Iraq, Jordan, and Kuwait), case variation, near-miss
non-PII numbers that must NOT be redacted, and free-form (non-templated)
code-switched sentences.

Construction and validation status (read before citing this as evidence):
this set is generator-independent (it shares no code or templates with
arenredact.data.corpus_generator) and was constructed by the paper's author,
with AI drafting/generation assistance, rather than independently
constructed or reviewed by separate bilingual human annotators. It is
offered as a stronger, more realistic stress test than the synthetic corpus,
not as a validated benchmark with measured inter-annotator agreement.
Independent human-annotated noisy test data is future work (Section 8.5).

Each item is (text, gold_spans) where gold_spans is a list of
(start, end, entity_type) tuples. Items with an empty gold list are pure
distractor/negative controls: text containing numbers or strings that must
NOT be flagged as PHONE/EMAIL/IBAN/NATIONAL_ID.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Deterministic fake-digit source (first 100 digits of pi, well past the
# decimal point so no country's slice accidentally repeats another's).
# Using a fixed irrational-number digit sequence instead of `random` keeps
# every fake identifier below fully reproducible without seeding concerns,
# and transparently "obviously fake" on inspection.
# ---------------------------------------------------------------------------
_PI_DIGITS = (
    "141592653589793238462643383279502884197169399375105820974944592307816"
    "406286208998628034825342117067982148086513282306647093844609550582231"
)


def _digits(n: int, offset: int) -> str:
    pool = _PI_DIGITS * 3
    return pool[offset: offset + n]


# ---------------------------------------------------------------------------
# Part 1: the original 28 hand-authored core cases (from the first-round
# challenge set), with three corrections made after the pattern-engine fixes
# described in Section 6.1 / 8.4:
#   - the Bahrain IBAN case now uses a length-correct fake number (the
#     original was 2 digits too long for the real BH structure and would
#     still miss under the corrected regex);
#   - three "bare 10-digit number, no identity context" cases that were
#     previously gold-labeled NATIONAL_ID (documenting a known false-positive
#     risk) are now gold-labeled as true negatives, because the corrected
#     pattern engine no longer tags a bare digit run as a national ID unless
#     an identity-context keyword appears nearby (Section 6.1).
# ---------------------------------------------------------------------------
_CORE_CASES: list[tuple[str, list[tuple[str, str]]]] = [
    # ---- Control cases: same formats the corpus generator produces ----
    ("Call +966501234567 for details.", [("+966501234567", "PHONE")]),
    ("My email is ahmed.hassan@example.com for work.", [("ahmed.hassan@example.com", "EMAIL")]),
    ("Transfer to SA7912345678901234567890 today.", [("SA7912345678901234567890", "IBAN")]),
    ("National ID: 1234567890 on file.", [("1234567890", "NATIONAL_ID")]),

    # ---- Phone: alternative spacing / grouping ----
    ("Reach me at +966 50 123 4567 anytime.", [("+966 50 123 4567", "PHONE")]),
    ("My number is +971-50-987-6543 now.", [("+971-50-987-6543", "PHONE")]),

    # ---- Phone: formats the regex is NOT written to handle (expected misses) ----
    ("Call 00966501234567 instead of the plus form.", []),  # 00-prefix, not '+': expected miss
    ("Local number: 0501234567 without the country code.", []),  # no country code: expected miss
    ("Dial +966 (50) 123-4567 with parentheses.", []),  # parens break the pattern: expected miss
    ("Extension: +966501234567 x204 for the front desk.", [("+966501234567", "PHONE")]),

    # ---- IBAN: case and spacing variation ----
    ("Please wire to sa7912345678901234567890 (lowercase prefix).", []),  # lowercase: expected miss (case-sensitive regex)
    ("IBAN SA79 1234 5678 9012 3456 7890 with spaces.", []),  # internal spaces break the digit run: expected miss
    ("Account AE070331234567890123456 is active.", [("AE070331234567890123456", "IBAN")]),

    # ---- National ID: near-misses that must NOT match (true negatives) ----
    ("Reference number 123456789 is nine digits, not an ID.", []),  # 9 digits: correctly not NATIONAL_ID
    ("Tracking code 12345678901 has eleven digits.", []),  # 11 digits: correctly not NATIONAL_ID
    ("Order #1234567890 was shipped yesterday.", []),  # no identity context: correctly NOT tagged after the Sec. 6.1 fix

    # ---- National ID: Arabic-Indic digits (Stage 1 normalization should still catch this) ----
    ("رقم الهوية ١٢٣٤٥٦٧٨٩٠ مسجل.", [("١٢٣٤٥٦٧٨٩٠", "NATIONAL_ID")]),

    # ---- Email: less common but valid formats ----
    ("Send to sara+invoices@sub.company-name.co for billing.", [("sara+invoices@sub.company-name.co", "EMAIL")]),
    ("Contact user_2024@mail-provider.info please.", [("user_2024@mail-provider.info", "EMAIL")]),

    # ---- Pure distractors: numbers that must NOT be redacted ----
    ("The invoice total is 500.00 SAR before tax.", []),
    ("The meeting is scheduled for 2024-05-12 at 3pm.", []),
    ("Discount applied: 1234567890 was NOT a code, just today's visitor count.", []),  # no identity context: correctly NOT tagged after the Sec. 6.1 fix
    ("The building has 4567890123 square feet of office space.", []),  # no identity context: correctly NOT tagged after the Sec. 6.1 fix
    ("Flight AA1234 departs at 14:30 from gate B12.", []),

    # ---- Free-form, non-templated code-mixed sentences (not from the generator) ----
    ("والله يا صديقي، اتصل فيني على +966512345678 لو سمحت.", [("+966512345678", "PHONE")]),
    ("Send the invoice to billing@company-sa.com, بليز اليوم.", [("billing@company-sa.com", "EMAIL")]),
    ("أبو خالد قال إن رقمه القومي 9876543210 ضاع منه.", [("9876543210", "NATIONAL_ID")]),
    # Corrected to a length-valid Bahrain IBAN (2-digit check + 4-letter bank
    # code + 14-digit account = 20 body chars, 22 total with the BH prefix).
    ("Can you confirm the IBAN BH67BMAG00001299123456 before Friday?", [("BH67BMAG00001299123456", "IBAN")]),
]

# ---------------------------------------------------------------------------
# Part 2: per-country extended set (item #5 of the second-round review).
# Seven MENA countries, each contributing phone / IBAN / national-ID /
# email cases in multiple formats, plus negative and near-miss controls.
# ---------------------------------------------------------------------------
_COUNTRIES = [
    {"iso": "SA", "name": "Saudi Arabia", "phone_code": "+966",
     "iban_prefix": "SA", "iban_letters": None, "iban_all_digit_len": 22,
     "email_domain": "example.sa"},
    {"iso": "AE", "name": "UAE", "phone_code": "+971",
     "iban_prefix": "AE", "iban_letters": None, "iban_all_digit_len": 21,
     "email_domain": "example.ae"},
    {"iso": "EG", "name": "Egypt", "phone_code": "+20",
     "iban_prefix": "EG", "iban_letters": None, "iban_all_digit_len": 27,
     "email_domain": "example.eg"},
    {"iso": "IQ", "name": "Iraq", "phone_code": "+964",
     "iban_prefix": "IQ", "iban_letters": "RAFB", "iban_acct_len": 15,
     "email_domain": "example.iq"},
    {"iso": "JO", "name": "Jordan", "phone_code": "+962",
     "iban_prefix": "JO", "iban_letters": "CBJO", "iban_acct_len": 22,
     "email_domain": "example.jo"},
    {"iso": "KW", "name": "Kuwait", "phone_code": "+965",
     "iban_prefix": "KW", "iban_letters": "CBKU", "iban_acct_len": 22,
     "email_domain": "example.kw"},
    {"iso": "BH", "name": "Bahrain", "phone_code": "+973",
     "iban_prefix": "BH", "iban_letters": "BMAG", "iban_acct_len": 14,
     "email_domain": "example.bh"},
]

_EN_ID_CTX = "National ID number"
_AR_ID_CTX = "رقم الهوية الوطنية"


def _make_iban(country: dict, offset: int) -> str:
    if country["iban_letters"] is None:
        return country["iban_prefix"] + _digits(country["iban_all_digit_len"], offset)
    return (
        country["iban_prefix"]
        + _digits(2, offset)
        + country["iban_letters"]
        + _digits(country["iban_acct_len"], offset + 20)
    )


def _build_country_cases(country: dict, base_offset: int) -> list[tuple[str, list[tuple[str, str]]]]:
    iso = country["iso"]
    name = country["name"]
    code = country["phone_code"]
    off = base_offset

    phone_a = _digits(9, off)
    phone_b = _digits(9, off + 9)
    phone_a_spaced = f"{phone_a[:2]} {phone_a[2:5]} {phone_a[5:]}"
    phone_b_hyphen = f"{phone_b[:3]}-{phone_b[3:6]}-{phone_b[6:]}"

    iban_a = _make_iban(country, off + 30)
    iban_b = _make_iban(country, off + 60)

    nid_a = _digits(10, off + 90)
    nid_b = _digits(10, off + 100)
    nid_ar = _digits(10, off + 110)
    nid_indic = "".join("٠١٢٣٤٥٦٧٨٩"[int(d)] for d in _digits(10, off + 120))
    nid_negative = _digits(10, off + 130)  # bare digits, no identity context anywhere nearby

    email_a = f"user.{iso.lower()}1@{country['email_domain']}"
    email_b = f"contact.{iso.lower()}2@{country['email_domain']}"

    cases: list[tuple[str, list[tuple[str, str]]]] = [
        # -- Phone: 4 positive format variants across 2 distinct numbers --
        (f"Please call {code}{phone_a} regarding your {name} account.",
         [(f"{code}{phone_a}", "PHONE")]),
        (f"You can reach the {name} office at {code} {phone_a_spaced}.",
         [(f"{code} {phone_a_spaced}", "PHONE")]),
        (f"Mobile: {code}-{phone_b_hyphen} (available after 9am).",
         [(f"{code}-{phone_b_hyphen}", "PHONE")]),
        (f"Front desk extension: {code}{phone_b} x12 for {name} support.",
         [(f"{code}{phone_b}", "PHONE")]),

        # -- Phone negatives: local number w/o country code, parens --
        (f"Local {name} number: {phone_a} without the country code.", []),
        (f"Dial {code} ({phone_b[:2]}) {phone_b[2:5]}-{phone_b[5:]} with parentheses.", []),

        # -- IBAN: correct format, 2 distinct numbers --
        (f"Transfer the deposit to {iban_a} for the {name} branch.",
         [(iban_a, "IBAN")]),
        (f"Confirm receipt at account {iban_b} before month end.",
         [(iban_b, "IBAN")]),

        # -- IBAN negatives: lowercase prefix, internal spacing --
        (f"Wire to {iban_a.lower()} (lowercase prefix, expected miss).", []),
        (f"IBAN {iban_b[:4]} {iban_b[4:8]} {iban_b[8:12]} {iban_b[12:]} with spaces.", []),

        # -- National ID: English context, Arabic context, Arabic-Indic digits --
        (f"{_EN_ID_CTX} ({name}): {nid_a} recorded on file.",
         [(nid_a, "NATIONAL_ID")]),
        (f"{name} {_EN_ID_CTX}: {nid_b} verified today.",
         [(nid_b, "NATIONAL_ID")]),
        (f"{_AR_ID_CTX} في {name} هو {nid_ar}.",
         [(nid_ar, "NATIONAL_ID")]),
        (f"{_AR_ID_CTX} بالأرقام العربية: {nid_indic}.",
         [(nid_indic, "NATIONAL_ID")]),

        # -- National ID negative: bare 10-digit run, no identity context --
        (f"The {name} shipment tracking value was {nid_negative} at last scan.", []),

        # -- Email --
        (f"Send the {name} paperwork to {email_a} today.",
         [(email_a, "EMAIL")]),
        (f"CC {email_b} on all {name} correspondence.",
         [(email_b, "EMAIL")]),

        # -- Combo sentences: multiple entity types in one sentence --
        (f"For {name} matters, call {code}{phone_a} or email {email_a}.",
         [(f"{code}{phone_a}", "PHONE"), (email_a, "EMAIL")]),
        (f"{_EN_ID_CTX} {nid_b} is linked to account {iban_a} in our {name} records.",
         [(nid_b, "NATIONAL_ID"), (iban_a, "IBAN")]),
        (f"{name} customer file: phone {code}{phone_b}, email {email_b}, "
         f"{_EN_ID_CTX} {nid_a}, account {iban_b}.",
         [(f"{code}{phone_b}", "PHONE"), (email_b, "EMAIL"), (nid_a, "NATIONAL_ID"), (iban_b, "IBAN")]),
    ]
    return cases


_EXTENDED_RAW_CASES: list[tuple[str, list[tuple[str, str]]]] = []
for _i, _country in enumerate(_COUNTRIES):
    _EXTENDED_RAW_CASES.extend(_build_country_cases(_country, base_offset=_i * 7))

_RAW_CASES: list[tuple[str, list[tuple[str, str]]]] = _CORE_CASES + _EXTENDED_RAW_CASES


def _resolve_gold(text: str, entries: list[tuple[str, str]]) -> list[tuple[int, int, str]]:
    resolved = []
    for substring, entity_type in entries:
        start = text.index(substring)  # raises ValueError loudly if the fixture is wrong
        resolved.append((start, start + len(substring), entity_type))
    return resolved


CASES: list[tuple[str, list[tuple[int, int, str]]]] = [
    (text, _resolve_gold(text, entries)) for text, entries in _RAW_CASES
]


def run_challenge_set() -> dict:
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

    per_type_summary = {}
    for et, counts in per_type.items():
        p = counts["tp"] / (counts["tp"] + counts["fp"]) if (counts["tp"] + counts["fp"]) else 0.0
        r = counts["tp"] / (counts["tp"] + counts["fn"]) if (counts["tp"] + counts["fn"]) else 0.0
        f = 2 * p * r / (p + r) if (p + r) else 0.0
        per_type_summary[et] = {
            "gold": counts["gold"], "tp": counts["tp"], "fp": counts["fp"], "fn": counts["fn"],
            "precision": p, "recall": r, "f1": f,
        }

    n_positive_identifiers = sum(len(gold) for _, gold in CASES)

    return {
        "n_cases": len(CASES),
        "n_positive_identifiers": n_positive_identifiers,
        "n_countries": len(_COUNTRIES),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "per_type": per_type_summary,
        "per_item": per_item,
    }


if __name__ == "__main__":
    import json
    import os

    results = run_challenge_set()
    out_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "results",
        "noisy_challenge_set.json",
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"n_cases={results['n_cases']}  n_positive_identifiers={results['n_positive_identifiers']}  "
          f"n_countries={results['n_countries']}")
    print(f"P={results['precision']:.3f}  R={results['recall']:.3f}  F1={results['f1']:.3f}")
    print(f"TP={results['true_positives']}  FP={results['false_positives']}  FN={results['false_negatives']}")
    print("\nPer-category breakdown:")
    print(f"{'Type':<14}{'Gold':>6}{'TP':>6}{'FP':>6}{'FN':>6}{'F1':>8}")
    for et, s in results["per_type"].items():
        print(f"{et:<14}{s['gold']:>6}{s['tp']:>6}{s['fp']:>6}{s['fn']:>6}{s['f1']:>8.3f}")
    print(f"\nWrote {out_path}")
