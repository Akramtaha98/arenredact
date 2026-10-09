.PHONY: test all provenance independent analysis
test:
	PYTHONPATH=src:scripts python -m pytest -q
all:
	bash scripts/reproduce_all.sh
provenance:
	PYTHONPATH=src:scripts python scripts/make_provenance.py
independent:
	PYTHONPATH=src:scripts python annotation/reproduce_independent.py
analysis:
	PYTHONPATH=src:scripts python analysis/leakage_levels.py
	PYTHONPATH=src:scripts python analysis/bootstrap_ci.py 4000
	PYTHONPATH=src:scripts python analysis/fp_negatives.py
