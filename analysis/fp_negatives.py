"""False positives on sentences with no gold identifier (negative sentences), per system, including
detectors with and without our Stage 1 (so the cost of preprocessing on look-alike numbers is visible).
usage: python analysis/fp_negatives.py  -> results/fp_negatives.json"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import common as C
L = C.L
sys.path.insert(0, os.path.dirname(__file__))
import bootstrap_ci_sets as BS   # noqa

systems = C.make_systems()
out = {"code_sha256": L.code_sha256(), "eval_sha256": L.eval_sha256(), "sets": {}}
for sname in ("S3", "S4", "independent_corrected", "S5"):
    cases = BS.SETS[sname]; neg = [t for t, g in cases if not g]
    out["sets"][sname] = {"n_negative_sentences": len(neg), "systems": {}}
    for n, s in systems.items():
        fp_sent = fp_spans = 0
        for t in neg:
            pred = s.run(t)[0]
            if pred: fp_sent += 1; fp_spans += len(pred)
        out["sets"][sname]["systems"][n] = {"sentences_with_false_positive": fp_sent, "false_positive_spans": fp_spans}
    print(sname, len(neg), {n: v["false_positive_spans"] for n, v in out["sets"][sname]["systems"].items()}, flush=True)
json.dump(out, open(os.path.join(C.ROOT, "results", "fp_negatives.json"), "w"), indent=1)
