"""Cluster bootstrap (resampling templates, not sentences) and paired intervals for system differences.
Cluster key = sentence text with every gold span and every digit run masked (so sentences from one template
form one cluster). Sets: S3, S4, independent annotated set (original and corrected gold).
usage: python analysis/bootstrap_ci.py [B=4000]  -> results/bootstrap_ci.json"""
import csv, json, os, random, re, sys
sys.path.insert(0, os.path.dirname(__file__))
import common as C
L = C.L
B = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
import bootstrap_ci_sets as BS
SETS = BS.SETS

def key(text, gold):
    t = text
    for s, e, _ in sorted(gold, reverse=True): t = t[:s] + "§" + t[e:]
    return re.sub(r"\d+", "0", t)

SYS = {"ours": "ours_full", "presidio": "presidio_default", "presidio_S1_reg": "presidio_norm_regional", "scrubadub": "scrubadub"}
systems = C.make_systems(); systems = {k: systems[v] for k, v in SYS.items()}
GROUPS = {"all": L.TYPES, "shared": L.SHARED, "phone_email": ("PHONE", "EMAIL")}

def per_sentence(cases, sysobj):
    rows = []
    for t, g in cases:
        pred, _, _ = sysobj.run(t); r = L.score_case(pred, g)
        rows.append({k: [sum(r[ty][i] for ty in v) for i in range(3)] for k, v in GROUPS.items()})
    return rows

def f1(tp, fp, fn): d = 2 * tp + fp + fn; return (2 * tp / d) if d else float("nan")
def pct(xs, q): xs = sorted(x for x in xs if x == x); return xs[int(q * (len(xs) - 1))]

out = {"B": B, "code_sha256": L.code_sha256(), "eval_sha256": L.eval_sha256(), "sets": {}}
for sname, cases in SETS.items():
    ps = {n: per_sentence(cases, s) for n, s in systems.items()}
    clusters = {}
    for i, (t, g) in enumerate(cases): clusters.setdefault(key(t, g), []).append(i)
    cl = list(clusters.values()); rng = random.Random(20261011)
    pairs = [("ours", "presidio_S1_reg", "all"), ("ours", "presidio_S1_reg", "shared"), ("ours", "presidio", "all"), ("ours", "scrubadub", "phone_email")]
    boots = {n: {g: [] for g in GROUPS} for n in ps}; diffs = {p: [] for p in pairs}
    sums = lambda n, grp, idxs: [sum(ps[n][i][grp][c] for i in idxs) for c in range(3)]
    for _ in range(B):
        idxs = [i for c in (rng.choice(cl) for _ in cl) for i in c]
        v = {}
        for n in ps:
            for grp in GROUPS: v[(n, grp)] = f1(*sums(n, grp, idxs))
        for n in ps:
            for grp in GROUPS: boots[n][grp].append(v[(n, grp)])
        for a, b, grp in pairs: diffs[(a, b, grp)].append(v[(a, grp)] - v[(b, grp)])
    allidx = list(range(len(cases)))
    res = {"n_sentences": len(cases), "n_clusters": len(cl), "systems": {}, "paired": {}}
    for n in ps:
        res["systems"][n] = {grp: {"f1": f1(*sums(n, grp, allidx)), "ci95": [pct(boots[n][grp], .025), pct(boots[n][grp], .975)]} for grp in GROUPS}
    for (a, b, grp), d in diffs.items():
        pt = f1(*sums(a, grp, allidx)) - f1(*sums(b, grp, allidx))
        lo, hi = pct(d, .025), pct(d, .975)
        res["paired"][f"{a} - {b} [{grp}]"] = {"diff": pt, "ci95": [lo, hi], "excludes_zero": bool(lo > 0 or hi < 0)}
    out["sets"][sname] = res
    print(sname, len(cases), "sentences", len(cl), "clusters", flush=True)
json.dump(out, open(os.path.join(C.ROOT, "results", "bootstrap_ci.json"), "w"), indent=1)
print("written")
