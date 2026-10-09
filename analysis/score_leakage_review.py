"""Compare blinded human leakage judgements with the automatic scorer.
usage: python analysis/score_leakage_review.py Leakage_Review_Sheet_completed.xlsx [second_reviewer.xlsx]
Writes results/leakage_review.json. Q2 (counts as a leak) is compared with the scorer's partial rule (k=6);
Q1 (complete identifier reconstructable) with the whole-identifier rule. Reports agreement, Cohen's kappa,
false alarms / misses of the scorer, and every disagreement for inspection."""
import csv, json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import openpyxl
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
key = {r["item_id"]: r for r in csv.DictReader(open(os.path.join(ROOT, "analysis/leakage_review/Leakage_Review_KEY.csv"), encoding="utf8"))}

def load(path):
    ws = openpyxl.load_workbook(path).worksheets[0]; d = {}
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[0] in key:
            q1, q2 = (str(r[4]).strip().lower() if r[4] else ""), (str(r[5]).strip().lower() if r[5] else "")
            assert q1 in ("yes", "no") and q2 in ("yes", "no"), f"{r[0]}: unanswered or invalid"
            d[r[0]] = (q1 == "yes", q2 == "yes", r[3], r[2])
    assert len(d) == len(key), "missing items"
    return d

def kappa(a, b):
    n = len(a); po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n; pe = pa * pb + (1 - pa) * (1 - pb)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)

def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** .5)
    return [(c - h) / d, (c + h) / d]

def compare(h, name):
    ids = sorted(h); out = {}
    for q, idx, col in (("Q2_leak_vs_scorer_partial_k6", 1, "scorer_partial_k6"), ("Q1_complete_vs_scorer_full", 0, "scorer_full")):
        hv = [h[i][idx] for i in ids]; sv = [bool(int(key[i][col])) for i in ids]
        agree = sum(a == b for a, b in zip(hv, sv)); tp = sum(a and b for a, b in zip(hv, sv)); fp = sum((not a) and b for a, b in zip(hv, sv)); fn = sum(a and (not b) for a, b in zip(hv, sv))
        out[q] = {"n": len(ids), "agreement": agree / len(ids), "agreement_wilson95": wilson(agree, len(ids)), "kappa": kappa(hv, sv),
                  "human_leak_scorer_leak": tp, "scorer_false_alarm": fp, "scorer_miss": fn, "human_no_scorer_no": len(ids) - tp - fp - fn,
                  "disagreements": [{"id": i, "human": h[i][idx], "scorer": bool(int(key[i][col])), "attack": key[i]["attack"], "output": h[i][2], "identifier": h[i][3]} for i in ids if h[i][idx] != bool(int(key[i][col]))]}
    return out

paths = sys.argv[1:]; res = {"reviewers": {}}
hs = [load(p) for p in paths]
for p, h in zip(paths, hs): res["reviewers"][os.path.basename(p)] = compare(h, p)
if len(hs) == 2:
    ids = sorted(hs[0]); res["inter_reviewer_kappa_Q2"] = kappa([hs[0][i][1] for i in ids], [hs[1][i][1] for i in ids]); res["inter_reviewer_kappa_Q1"] = kappa([hs[0][i][0] for i in ids], [hs[1][i][0] for i in ids])
json.dump(res, open(os.path.join(ROOT, "results", "leakage_review.json"), "w"), indent=1, ensure_ascii=False)
for n, r in res["reviewers"].items():
    for q, v in r.items(): print(n, q, "agree %.3f kappa %.3f falsealarm %d miss %d" % (v["agreement"], v["kappa"], v["scorer_false_alarm"], v["scorer_miss"]))
