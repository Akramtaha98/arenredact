"""Score the FROZEN detector and the Presidio controls against the adjudicated gold.
usage: python annotation/score_adjudicated.py adjudicated.csv sample.csv key.csv out.json
adjudicated.csv: sentence_id,start,end,label,note (types PHONE/EMAIL/IBAN/NATIONAL_ID; OTHER_PII ignored)
key.csv (authors only) supplies origin/subtype for breakdowns. Run exactly once, after freezing."""
import csv, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import eval_lib as L
adj, sample, key, out = sys.argv[1:5]
texts = {r["sentence_id"]: r["text"] for r in csv.DictReader(open(sample, encoding="utf8"))}
gold = {k: set() for k in texts}
for r in csv.DictReader(open(adj, encoding="utf8")):
    if r["label"] in L.TYPES: gold[r["sentence_id"]].add((int(r["start"]), int(r["end"]), r["label"]))
meta = {r["item_id"]: r for r in csv.DictReader(open(key, encoding="utf-8-sig"))}
systems = {"ours": L.OursSystem(None), "presidio": L.PresidioSystem("default"), "presidio_S1": L.PresidioSystem("norm"), "presidio_S1_reg": L.PresidioSystem("norm_regional")}
def subset(f): return [(texts[k], gold[k]) for k in texts if f(meta.get(k, {}))]
groups = {"all": lambda m: True, "synthetic": lambda m: m.get("origin", "").startswith("synthetic"), "wikipedia": lambda m: m.get("origin") == "wikipedia",
          "local_phone": lambda m: "local" in m.get("subtype", ""), "not_local_phone": lambda m: "local" not in m.get("subtype", "")}
res = {"code_sha256": L.code_sha256(), "eval_sha256": L.eval_sha256(), "n_items": len(texts), "n_gold": sum(len(g) for g in gold.values()), "groups": {}}
for gname, f in groups.items():
    cases = subset(f); res["groups"][gname] = {"n_items": len(cases), "n_gold": sum(len(g) for _, g in cases), "systems": {}}
    for sname, sysobj in systems.items():
        e = {}
        for mode in ("strict", "lenient"):
            tot, _ = L.aggregate(cases, sysobj, lenient=(mode == "lenient"))
            e[mode] = {"all_types": L.summarize(tot, L.TYPES), "shared_types": L.summarize(tot, L.SHARED), "national_id": L.summarize(tot, ("NATIONAL_ID",)),
                       "per_type": {t: L.summarize(tot, (t,)) for t in L.TYPES}}
        res["groups"][gname]["systems"][sname] = e
json.dump(res, open(out, "w"), indent=1, default=list)
print("scored", len(texts), "items ->", out)
