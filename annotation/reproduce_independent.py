"""Reproduce Table 15 (independent annotated set) from the released files and check it against the committed results.
usage (repository root): PYTHONPATH=src:scripts python annotation/reproduce_independent.py
Steps: (1) agreement from the two annotators' span files; (2) score every frozen system on the ORIGINAL gold and on the
CORRECTED gold into a temporary folder; (3) compare with results/independent_annotation*.json; (4) print the table.
Exit status 1 on any mismatch."""
import csv, json, os, subprocess, sys, tempfile, hashlib
sys.path.insert(0, "annotation"); sys.path.insert(0, "scripts")
import agreement as AG
D = "data/independent/annotated_330/"
ok = True
T = {r["item_id"]: r["text"] for r in csv.DictReader(open(D + "items.csv", encoding="utf-8-sig"))}
ag = AG.agreement(AG.read_spans(D + "spans_A.csv"), AG.read_spans(D + "spans_B.csv"), T)
summ = json.load(open("results/independent_annotation_summary.json"))
print("kappa (char) = %.3f ; sentences needing adjudication = %d" % (ag["kappa_char"], ag["n_disagreeing_sentences"]))
ok &= abs(ag["kappa_char"] - summ["kappa_char_before_adjudication"]) < 1e-12 and ag["n_disagreeing_sentences"] == 21
for tag, gold, ref in (("original", "adjudicated.csv", "results/independent_annotation.json"), ("corrected", "adjudicated_v2.csv", "results/independent_annotation_v2.json")):
    assert hashlib.sha256(open(D + gold, "rb").read()).hexdigest() in json.dumps(summ) or tag == "corrected"
    tmp = os.path.join(tempfile.mkdtemp(), f"{tag}.json")
    subprocess.check_call([sys.executable, "annotation/score_adjudicated.py", D + gold, D + "sample.csv", D + "key.csv", tmp], stdout=subprocess.DEVNULL)
    new, old = json.load(open(tmp)), json.load(open(ref))
    same = new["groups"] == old["groups"]; ok &= same
    print(f"[{tag}] gold={gold} matches committed {ref}: {same}")
    print("  system            TP/FP/FN       P      R      F1")
    for s, e in new["groups"]["all"]["systems"].items():
        a = e["strict"]["all_types"]; print(f"  {s:16s} {a['tp']:3d}/{a['fp']:2d}/{a['fn']:2d}   {a['precision']:.3f}  {a['recall']:.3f}  {a['f1']:.3f}")
print("REPRODUCED" if ok else "MISMATCH"); sys.exit(0 if ok else 1)
