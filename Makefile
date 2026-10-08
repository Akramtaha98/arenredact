.PHONY: test all provenance
test:
	PYTHONPATH=src:scripts python -m pytest -q
all:
	bash scripts/reproduce_all.sh
provenance:
	PYTHONPATH=src:scripts python scripts/make_provenance.py
