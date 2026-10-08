#!/usr/bin/env bash
# Regenerates every number, table and figure input used in the manuscript.
# Usage: bash scripts/reproduce_all.sh   (about 3 minutes on 4 vCPUs)
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="src:scripts:${PYTHONPATH:-}"
python -m pytest -q                                         # 122 unit tests
python scripts/reproduce_deterministic_tier_baseline.py     # corpus statistics, latency  -> results/deterministic_tier_baseline.json
python scripts/run_clean_eval.py                            # Tables (clean incl. frozen S3 and S4, ablation, strata, Wikipedia scan) -> results/revision2_clean.json
python scripts/run_attack_audit.py --revision r2            # attack tables, adaptive search  -> results/attack_audit_r2.json
python scripts/validate_scorer.py                          # scorer validation table -> results/scorer_validation.json
for k in 4 8 10; do LEAK_K=$k python scripts/run_attack_audit.py --revision r2 --out results/sensitivity/attack_audit_k$k.json; done
LEAK_SCORER=v1 python scripts/run_attack_audit.py --revision r2 --out results/sensitivity/attack_audit_scorer_v1.json   # scorer/threshold sensitivity
python scripts/redos_scaling.py                             # scaling table  -> results/redos_scaling.json
PYTHONPATH="results/frozen/r1_src:scripts" python scripts/run_attack_audit.py --revision r1   # first-round detector under the same attacks
python scripts/make_provenance.py                           # -> results/provenance.json
