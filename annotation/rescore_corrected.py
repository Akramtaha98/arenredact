"""Build corrected gold v2 from the completed gold-review sheet and rescore ALL frozen systems (detectors unchanged).
usage: python annotation/rescore_corrected.py annotation/gold_review/Gold_Review_Sheet_completed.xlsx
Keeps v1 (adjudicated.csv, results/independent_annotation.json) untouched; writes adjudicated_v2.csv,
results/independent_annotation_v2.json and results/independent_annotation_v1_v2.json (side-by-side)."""
import csv, hashlib, json, os, subprocess, sys
import openpyxl
D = "data/independent/annotated_330/"
sheet = sys.argv[1]
T = {r["item_id"]: r["text"] for r in csv.DictReader(open(D + "items.csv", encoding="utf-8-sig"))}
rows = list(csv.DictReader(open(D + "adjudicated.csv", encoding="utf8")))
ws = openpyxl.load_workbook(sheet).worksheets[0]
changed = {}
for r in ws.iter_rows(min_row=2, values_only=True):
    iid, no, ident, typ = r[0], r[4], r[5], r[6]
    if iid not in T: continue
    if ident:
        st = T[iid].find(ident); assert st >= 0 and typ, (iid, ident, typ)
        changed[iid] = [(st, st + len(ident), typ)]
    else:
        assert str(no).strip().lower() == "yes", f"{iid}: row not filled"
        changed[iid] = []
out = [r for r in rows if r["sentence_id"] not in changed]
for iid, sp in changed.items():
    for s, e, t in sp: out.append({"sentence_id": iid, "start": s, "end": e, "label": t, "note": "gold_v2"})
out.sort(key=lambda r: (r["sentence_id"], int(r["start"])))
with open(D + "adjudicated_v2.csv", "w", encoding="utf8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["sentence_id", "start", "end", "label", "note"]); w.writeheader(); w.writerows(out)
sha = hashlib.sha256(open(D + "adjudicated_v2.csv", "rb").read()).hexdigest()
subprocess.check_call([sys.executable, "annotation/score_adjudicated.py", D + "adjudicated_v2.csv", D + "sample.csv", D + "key.csv", "results/independent_annotation_v2.json"])
v1 = json.load(open("results/independent_annotation.json")); v2 = json.load(open("results/independent_annotation_v2.json"))
assert v1["code_sha256"] == v2["code_sha256"] and v1["eval_sha256"] == v2["eval_sha256"], "detector or scripts changed"
cmp = {"gold_v1_sha256": hashlib.sha256(open(D + "adjudicated.csv", "rb").read()).hexdigest(), "gold_v2_sha256": sha, "changed_items": sorted(changed),
       "n_gold_v1": v1["n_gold"], "n_gold_v2": v2["n_gold"], "systems": {}}
for s in v1["groups"]["all"]["systems"]:
    cmp["systems"][s] = {m: {g: {"v1": v1["groups"]["all"]["systems"][s][m][g], "v2": v2["groups"]["all"]["systems"][s][m][g]} for g in ("all_types", "shared_types", "national_id")} for m in ("strict", "lenient")}
json.dump(cmp, open("results/independent_annotation_v1_v2.json", "w"), indent=1, default=list)
for s, e in cmp["systems"].items():
    a, b = e["strict"]["all_types"]["v1"], e["strict"]["all_types"]["v2"]
    print(f"{s:16s} v1 {a['tp']}/{a['fp']}/{a['fn']} F1 {a['f1']:.3f} | v2 {b['tp']}/{b['fp']}/{b['fn']} F1 {b['f1']:.3f}")
