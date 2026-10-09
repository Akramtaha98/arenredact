"""Evaluation sets used by the round-4 analyses (S3, S4, independent set, original and corrected gold)."""
import csv, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import common as C
import stratified_holdout as S3m, stratified_holdout_s4 as S4m
def load_independent(version):
    D = os.path.join(C.ROOT, "data/independent/annotated_330/")
    T = {r["item_id"]: r["text"] for r in csv.DictReader(open(D + "items.csv", encoding="utf-8-sig"))}
    g = {k: [] for k in T}
    for r in csv.DictReader(open(D + ("adjudicated.csv" if version == "orig" else "adjudicated_v2.csv"), encoding="utf8")):
        g[r["sentence_id"]].append((int(r["start"]), int(r["end"]), r["label"]))
    return [(T[k], g[k]) for k in T]

def load_s5():
    D = os.path.join(C.ROOT, "data/independent/s5/")
    if not os.path.exists(D + "items.csv"): return None
    T = {r["sentence_id"]: r["text"] for r in csv.DictReader(open(D + "items.csv", encoding="utf8"))}
    g = {k: [] for k in T}
    for r in csv.DictReader(open(D + "gold.csv", encoding="utf8")): g[r["sentence_id"]].append((int(r["start"]), int(r["end"]), r["label"]))
    return [(T[k], g[k]) for k in T]

SETS = {"S3": [(t, [tuple(x) for x in g]) for t, g in S3m.CASES], "S4": [(t, [tuple(x) for x in g]) for t, g in S4m.CASES],
        "independent_original": load_independent("orig"), "independent_corrected": load_independent("corr")}
_s5 = load_s5()
if _s5: SETS["S5"] = _s5
