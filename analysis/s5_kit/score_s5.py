"""Score the frozen systems on S5 ONCE. Refuses to run if results/s5_scored.json exists, if the set hash changed,
or if the detector/scoring hashes differ from results/provenance.json.
usage: python analysis/s5_kit/score_s5.py data/independent/s5"""
import csv, hashlib, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, ".."))
import common as C
L = C.L; d = sys.argv[1]; outp = os.environ.get("S5_RESULT", os.path.join(C.ROOT, "results", "s5_scored.json"))
if os.path.exists(outp): sys.exit("S5 already scored once; refusing (freeze rule)")
h = hashlib.sha256(open(d + "/items.csv", "rb").read() + open(d + "/gold.csv", "rb").read()).hexdigest()
assert h + "\n" == open(d + "/SHA256.txt").read(), "set changed after freezing"
prov = json.load(open(os.path.join(C.ROOT, "results", "provenance.json")))
assert L.code_sha256() == prov["current_code_sha256"], "detector differs from the frozen one"
T = {r["sentence_id"]: r for r in csv.DictReader(open(d + "/items.csv", encoding="utf8"))}
g = {k: set() for k in T}
for r in csv.DictReader(open(d + "/gold.csv", encoding="utf8")): g[r["sentence_id"]].add((int(r["start"]), int(r["end"]), r["label"]))
systems = C.make_systems(); cases = [(T[k]["text"], g[k]) for k in T]
res = {"set_sha256": h, "code_sha256": L.code_sha256(), "eval_sha256": L.eval_sha256(), "n_sentences": len(cases), "n_gold": sum(len(v) for v in g.values()), "systems": {}}
for n, s in systems.items():
    e = {}
    for mode in ("strict", "lenient"):
        tot, _ = L.aggregate(cases, s, lenient=(mode == "lenient"))
        e[mode] = {"all_types": L.summarize(tot, L.TYPES), "shared_types": L.summarize(tot, L.SHARED), "national_id": L.summarize(tot, ("NATIONAL_ID",)), "phone_email": L.summarize(tot, ("PHONE", "EMAIL")),
                   "per_type": {t: L.summarize(tot, (t,)) for t in L.TYPES}}
    res["systems"][n] = e
json.dump(res, open(outp, "w"), indent=1, default=list); print("scored once ->", outp)
