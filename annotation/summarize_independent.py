"""Summarise the independent annotation: agreement, adjudication, scoring errors.
usage: python annotation/summarize_independent.py   (run from the repository root, PYTHONPATH=src:.)
Reads data/independent/annotated_330/*, results/independent_annotation.json; writes
results/independent_annotation_summary.json. Does not re-run any change to the detector."""
import csv, hashlib, json, os, sys, unicodedata
from collections import Counter, defaultdict
sys.path.insert(0, "annotation"); sys.path.insert(0, "scripts")
import agreement as AG, eval_lib as L
D = "data/independent/annotated_330/"
texts = {r["item_id"]: r["text"] for r in csv.DictReader(open(D + "items.csv", encoding="utf-8-sig"))}
key = {r["item_id"]: r for r in csv.DictReader(open(D + "key.csv", encoding="utf-8-sig"))}
A, B = AG.read_spans(D + "spans_A.csv"), AG.read_spans(D + "spans_B.csv")
ag = AG.agreement(A, B, texts)
gold = defaultdict(set)
for r in csv.DictReader(open(D + "adjudicated.csv", encoding="utf8")):
    gold[r["sentence_id"]].add((int(r["start"]), int(r["end"]), r["label"]))
dis = ag["disagreements"]
changed_A = [k for k in dis if gold[k] != set(A.get(k, []))]; changed_B = [k for k in dis if gold[k] != set(B.get(k, []))]
S = L.OursSystem(None); err = {"missed": [], "extra": []}
for k, t in texts.items():
    P = set(S.run(t)[0])
    for s, e, l in gold[k] - P: err["missed"].append({"id": k, "type": l, "text": t[s:e]})
    for s, e, l in P - gold[k]: err["extra"].append({"id": k, "type": l, "text": t[s:e]})
def phrase(i):
    t = texts[i]
    for p, n in (("ID card number", "ID card number"), ("الرقم الوطني للمتقدم", "الرقم الوطني للمتقدم"), ("رقم هوية الطالب", "student ID (رقم هوية الطالب)"), ("The identity of the donor", "'identity of the donor' + count")):
        if p in t: return n
    return "other"
cat = Counter(); cat_fp = Counter()
for m in err["missed"]:
    if m["type"] == "NATIONAL_ID": cat["NID missed: " + phrase(m["id"])] += 1
    else: cat[m["type"] + " missed"] += 1
for m in err["extra"]:
    cat_fp[(m["type"], phrase(m["id"]) if m["type"] == "NATIONAL_ID" else "other")] += 1
sc = json.load(open("results/independent_annotation.json"))
summ = {"n_items": len(texts), "n_gold_spans": sum(len(v) for v in gold.values()), "gold_by_type": dict(Counter(l for v in gold.values() for *_, l in v)),
        "n_positive_sentences": sum(1 for v in gold.values() if v), "kappa_char_before_adjudication": ag["kappa_char"], "span_f1_A_vs_B": ag["span_f1"],
        "n_disagreeing_sentences": len(dis), "disagreements": dis, "changed_vs_A": len(changed_A), "changed_vs_B": len(changed_B),
        "spans_A": sum(len(v) for v in A.values()), "spans_B": sum(len(v) for v in B.values()),
        "adjudicated_sha256": hashlib.sha256(open(D + "adjudicated.csv", "rb").read()).hexdigest(),
        "scored_code_sha256": sc["code_sha256"], "scored_eval_sha256": sc["eval_sha256"],
        "ours_missed": err["missed"], "ours_extra": err["extra"], "missed_categories": dict(cat), "extra_categories": {f"{a}|{b}": v for (a, b), v in cat_fp.items()}}
json.dump(summ, open("results/independent_annotation_summary.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps({k: v for k, v in summ.items() if k not in ("ours_missed", "ours_extra", "disagreements")}, ensure_ascii=False, indent=1))
