"""Write results/provenance.json: code hashes of every recorded revision,
SHA-256 of every dataset file, package versions, interpreter and platform."""
import hashlib, json, os, platform, sys
from importlib import metadata
sys.path.insert(0, os.path.dirname(__file__))
import eval_lib as L

PK = ["regex", "pydantic", "PyYAML", "cryptography", "tqdm", "numpy", "pandas", "scipy",
      "phonenumbers", "matplotlib", "presidio-analyzer", "spacy", "pytest"]
DATA = ["scripts/noisy_challenge_set.py", "scripts/noisy_challenge_set_holdout.py",
        "scripts/validity_realistic_set.py", "scripts/stratified_holdout.py", "scripts/stratified_holdout_s4.py",
        "data/independent/wikipedia_ar.jsonl", "data/independent/wikipedia_en.jsonl",
        "annotation/sample_for_annotation.csv"]


def ver(p):
    try:
        return metadata.version(p)
    except metadata.PackageNotFoundError:
        return None


def main():
    res = {"python": sys.version.split()[0], "platform": platform.platform(),
           "packages": {p: ver(p) for p in PK},
           "datasets_sha256": {p: L.file_sha256(p) for p in DATA if os.path.exists(p)},
           "current_code_sha256": L.code_sha256(), "current_eval_sha256": L.eval_sha256(), "recorded_revisions": {}}
    for tag, f in [("R1 (first-round code), attack audit re-run with the final scripts", "results/attack_audit_r1.json"),
                   ("R2 (frozen before S3 was scored)", "results/frozen/revision2_clean_firstrun.json"),
                   ("R3 (final, = current): clean evaluation", "results/revision2_clean.json"),
                   ("R3 (final, = current): attack audit", "results/attack_audit_r2.json")]:
        d = json.load(open(f)); res["recorded_revisions"][tag] = {"results_file": f, "code_sha256": d["code_sha256"], "eval_sha256": d.get("eval_sha256")}
    res["note"] = ("eval_sha256 hashes every script in scripts/ (scorer, attack procedure, Presidio configuration, datasets). The R2 frozen first-run file predates it and stores only the package hash. R1 source is archived in results/frozen/r1_src; R2 is identified by hash only "
                   "(its sole difference to R3 is the phone-parentheses fix; see CHANGELOG).")
    json.dump(res, open("results/provenance.json", "w"), indent=1)
    print(json.dumps(res["recorded_revisions"], indent=1))


if __name__ == "__main__":
    main()
