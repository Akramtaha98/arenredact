"""Revision-2 clean-detection evaluation: ours (full and Stage-1 ablations),
Presidio (default / +Stage 1 / +Stage 1 + regional recognizers), on the
synthetic test split, the relabelled extended set, the frozen holdout (original
and relabelled gold), the validity-realistic set and the stratified holdout S3,
plus a false-positive scan over independent Wikipedia text.

Writes results/revision2_clean.json (every entry carries the SHA-256 of the
detector source that produced it). Usage:  python scripts/run_clean_eval.py
"""
import json, os, sys, time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
import eval_lib as L
import noisy_challenge_set as ext
import noisy_challenge_set_holdout as hold
import validity_realistic_set as valid
import stratified_holdout as s3
import stratified_holdout_s4 as s4
from arenredact.data.corpus_generator import generate_corpus

SEED = 42
N = 8970

ABLATIONS = {
    "ours_full": None,
    "ours_no_stage1": (),
    "ours_nfkc_only": ("nfkc",),
    "ours_digits_only": ("digits",),
    "ours_bidi_only": ("bidi",),
    "ours_invisible_only": ("invisible",),
    "ours_tatweel_only": ("tatweel",),
    "ours_confusables_only": ("confusables",),
    "ours_nfkc_plus_digits": ("nfkc", "digits"),
    "ours_all_but_digits": ("nfkc", "bidi", "invisible", "tatweel", "confusables"),
    "ours_all_but_nfkc": ("bidi", "invisible", "digits", "tatweel", "confusables"),
    "ours_all_but_invisible": ("nfkc", "bidi", "digits", "tatweel", "confusables"),
    "ours_all_but_confusables": ("nfkc", "bidi", "invisible", "digits", "tatweel"),
}


def build_systems(with_presidio=True):
    systems = {k: L.OursSystem(v) for k, v in ABLATIONS.items()}
    if with_presidio:
        systems["presidio_default"] = L.PresidioSystem("default")
        systems["presidio_norm"] = L.PresidioSystem("norm")
        systems["presidio_norm_regional"] = L.PresidioSystem("norm_regional")
    return systems


def load_sets():
    corpus = generate_corpus(n_sentences=N, seed=SEED, arabizi_rate=0.30)
    test = corpus[int(0.8 * N) + int(0.1 * N):]
    synth = [(r.text, {(e.start, e.end, e.entity_type) for e in r.entities if e.entity_type in L.TYPES}) for r in test]
    ext_scored, ext_amb, ext_changed = L.relabel(ext.CASES)
    hold_orig = [(t, [tuple(g) for g in gold]) for t, gold in hold.CASES]
    hold_rel, hold_amb, hold_changed = L.relabel(hold.CASES)
    sets = {
        "synthetic_test_897": synth,
        "extended_168_relabelled": [(t, set(map(tuple, g))) for t, g in ext_scored],
        "extended_168_original_labels": [(t, set(map(tuple, g))) for t, g in ext.CASES],
        "holdout_25_original_labels": [(t, set(g)) for t, g in hold_orig],
        "holdout_25_relabelled": [(t, set(g)) for t, g in hold_rel],
        "validity_realistic_112": [(t, set(map(tuple, g))) for t, g in valid.CASES],
        "stratified_S3": [(t, set(map(tuple, g))) for t, g in s3.CASES],
        "stratified_S4": [(t, set(map(tuple, g))) for t, g in s4.CASES],
    }
    info = {"extended_relabelled_cases": len(ext_changed), "extended_ambiguous_excluded": len(ext_amb),
            "holdout_relabelled_cases": len(hold_changed), "holdout_ambiguous_excluded": len(hold_amb)}
    return sets, info


def score_all(sets, systems):
    out = {}
    for sname, cases in sets.items():
        out[sname] = {}
        n_gold = sum(len(g) for _, g in cases)
        for name, sysobj in systems.items():
            entry = {}
            for mode in ("strict", "lenient"):
                tot, shifted = L.aggregate(cases, sysobj, lenient=(mode == "lenient"))
                entry[mode] = {
                    "all_types": L.summarize(tot, L.TYPES),
                    "shared_types": L.summarize(tot, L.SHARED),
                    "national_id": L.summarize(tot, ("NATIONAL_ID",)),
                    "per_type": {t: L.summarize(tot, (t,)) for t in L.TYPES},
                }
            entry["offset_shifted_sentences"] = shifted
            out[sname][name] = entry
        out[sname]["_n_sentences"] = len(cases)
        out[sname]["_n_gold"] = n_gold
        print("scored", sname, flush=True)
    return out


def stratified(systems_subset, systems):
    """Recall (lenient match) by stratum on the pooled positives of the
    relabelled extended set, validity set and S3."""
    pooled = []
    ext_scored, _, _ = L.relabel(ext.CASES)
    for t, g in ext_scored:
        for x in g:
            pooled.append((t, x, "extended", None))
    for t, g in valid.CASES:
        for x in g:
            pooled.append((t, tuple(x), "validity", None))
    for (t, g), m in zip(s3.CASES, s3.META):
        for x in g:
            pooled.append((t, tuple(x), "S3", {"country": m["country"], "format": m["format"]}))
    res = {}
    for dim in ("type", "country", "digit_script", "context_language", "format"):
        res[dim] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    cache = {}
    for t, g, src, meta in pooled:
        st = L.stratum(t, g, meta)
        for name in systems_subset:
            key = (name, t)
            if key not in cache:
                cache[key] = systems[name].run(t)[0]
            pred = cache[key]
            hit = any(p[2] == g[2] and L._iou(p, g) >= 0.5 for p in pred)
            for dim in res:
                cell = res[dim][st[dim]][name]
                cell[0] += hit; cell[1] += 1
    return {d: {v: {n: {"tp": c[0], "n": c[1], "recall": c[0] / c[1], "wilson95": L.wilson(c[0], c[1])}
                    for n, c in per.items()} for v, per in vals.items()} for d, vals in res.items()}


def wikipedia_fp(systems):
    pages = []
    for lang in ("ar", "en"):
        p = f"data/independent/wikipedia_{lang}.jsonl"
        pages += [json.loads(l) for l in open(p, encoding="utf8")]
    chars = {"ar": 0, "en": 0}
    for p in pages:
        chars[p["lang"]] += len(p["text"])
    res = {"pages": {l: sum(1 for p in pages if p["lang"] == l) for l in chars}, "chars": chars, "systems": {}}
    for name, sysobj in systems.items():
        flagged = []
        for p in pages:
            pred = sysobj.run(p["text"])[0]
            proc = sysobj.run(p["text"])[1]
            for (s, e, t) in sorted(pred):
                flagged.append({"pageid": p["pageid"], "lang": p["lang"], "type": t,
                                "text": proc[s:e], "context": proc[max(0, s - 25): e + 25]})
        res["systems"][name] = {"n_flagged": len(flagged), "by_type": {t: sum(1 for f in flagged if f["type"] == t) for t in L.TYPES},
                                "flagged": flagged}
        print("wiki", name, len(flagged), flush=True)
    return res


def main():
    t0 = time.time()
    systems = build_systems()
    sets, info = load_sets()
    out = {"code_sha256": L.code_sha256(), "eval_sha256": L.eval_sha256(), "seed": SEED, "set_info": info,
           "dataset_sha256": {
               "extended": L.file_sha256("scripts/noisy_challenge_set.py"),
               "holdout": L.file_sha256("scripts/noisy_challenge_set_holdout.py"),
               "validity": L.file_sha256("scripts/validity_realistic_set.py"),
               "stratified_S3": L.file_sha256("scripts/stratified_holdout.py"),
               "stratified_S4": L.file_sha256("scripts/stratified_holdout_s4.py"),
               "wikipedia_ar": L.file_sha256("data/independent/wikipedia_ar.jsonl"),
               "wikipedia_en": L.file_sha256("data/independent/wikipedia_en.jsonl")}}
    out["clean"] = score_all(sets, systems)
    keep = ["ours_full", "ours_no_stage1", "ours_nfkc_only", "ours_digits_only", "presidio_default", "presidio_norm", "presidio_norm_regional"]
    out["strata"] = stratified(keep, systems)
    out["wikipedia_fp"] = wikipedia_fp({k: systems[k] for k in ("ours_full", "ours_no_stage1", "presidio_default", "presidio_norm", "presidio_norm_regional")})
    out["seconds"] = round(time.time() - t0, 1)
    json.dump(out, open(os.environ.get("CLEAN_OUT", "results/revision2_clean.json"), "w"), indent=1, ensure_ascii=False, default=list)
    print("done", out["seconds"], "s")


if __name__ == "__main__":
    main()
