<div align="center">

# ArEnRedact

**A threat-driven evaluation framework and deterministic baseline for Arabic–English PII redaction**

![version](https://img.shields.io/badge/version-1.1.0-blue)
![python](https://img.shields.io/badge/python-3.10%2B-3776AB)
![tests](https://img.shields.io/badge/tests-122%20passing-brightgreen)
![license](https://img.shields.io/badge/license-MIT-lightgrey)
![status](https://img.shields.io/badge/status-research%20code-orange)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23268049.svg)](https://doi.org/10.5281/zenodo.23268049)

Does your redactor still work when someone hides a phone number behind zero-width characters, Arabic-Indic digits or look-alike letters? ArEnRedact measures that, and ships a small deterministic redactor to demonstrate it.

</div>

---

## Why this exists

Personal-data redaction for Arabic–English text is usually scored on clean, template-like data. Accuracy there says little about **evasion** through Unicode and script tricks. This repository provides:

- **An attack-audit framework**: invisible and bidirectional characters, fullwidth forms, digit scripts, separators, look-alike letters, altered ID keywords, stacked combinations and a budgeted adaptive search, scored by whether identifier content survives in the *redacted output*.
- **A validated leakage scorer**: ignores matches that the surrounding text already contains and still counts repeated identifiers (validated on 1,640 constructed cases).
- **Component attribution**: every Stage 1 step switched on and off on identical code, so you can see *which* step defends *which* attack family.
- **Fair controls**: Presidio as shipped, behind our normalisation, and behind normalisation plus regional recognisers.
- **An integrity record**: source hashes in every result file, frozen stratified test sets scored once, an independent Wikipedia scan, and an independently labelled 330-sentence set (two non-author annotators, adjudicated, scored once).

## What the deterministic baseline does

```
raw text ─► [1] Unicode normalisation ─► [3] pattern engine ─► [4] span fusion ─► [5] keyed audit log ─► redacted text
                                     └► [2] neural NER (specified, not evaluated)
```

| Stage | Module | Role |
|---|---|---|
| 1 | `preprocessing.py` | NFKC, bidi and invisible-character stripping, digit folding, Tatweel cap, confusable folding (each step switchable) |
| 3 | `pattern_engine.py` | Phone numbers, IBANs, e-mail addresses and context-gated national IDs for 7 countries (SA, AE, EG, IQ, JO, KW, BH) |
| 4 | `span_fusion.py` | Union of spans with type priority |
| 5 | `audit_log.py` | HMAC-keyed digests, hash chain, Ed25519 signatures, signed checkpoint against tail truncation |

## Headline results

| | Ours | Presidio + our normalisation + regional recognisers | Presidio (stock) |
|---|---|---|---|
| **S3** frozen stratified set (F1, scored once at revision R2) | 0.983 | 0.950 | 0.665 |
| **S4** new templates (F1, scored once) | 0.966 | 0.941 | 0.665 |

- NFKC alone leaves Arabic-Indic digits unfolded (92% leakage); digit folding alone leaves fullwidth digits (91%); the full combination achieves the lowest leakage under stacked attacks (35% at two stacked operators against 90% for the best single step).
- Presidio behind the same normalisation behaves like our detector on these families: the protection comes from the **front end**, not the matcher.
- Robustness is **inventory-relative**: separator insertion and look-alikes outside the folded set evade every system, and a 50-query adaptive search evades essentially all identifiers in the open setting.

- On the independently labelled set (330 sentences, 133 gold identifiers, kappa 0.955 before adjudication, frozen detector scored once) our detector reaches **F1 0.905** on the corrected labels (0.908 on the original) against 0.685 for stock Presidio and 0.926 for Presidio behind our normalisation, regional phone recognisers and national-ID rule; our loss comes from the national-ID keyword rule and from local numbers.

> **Honest scope.** The deterministic tier is the only thing measured. Most sets are author-written; the 330-sentence set has independent labels but author-written synthetic text, 136 identifiers (labels corrected once after a blind second review: I314 and local numbers). The neural tier, DP training, membership inference and re-identification are specified but not executed.

## Quick start

```bash
git clone https://github.com/Akramtaha98/arenredact.git && cd arenredact
python -m pip install -r requirements-lock.txt
export PYTHONPATH=src:scripts
python -m pytest -q                      # 122 tests, under a second
```

```python
from arenredact.pipeline import ArEnRedactPipeline

pipe = ArEnRedactPipeline()
print(pipe.redact("اتصل على ‎+966 55 123 4567 أو راسل ahmed@corp.com").redacted_text)
```

(The pipeline returns the redacted **normalised** text; offsets refer to the normalised text.)

## Reproduce the paper

```bash
bash scripts/reproduce_all.sh            # about 6 minutes on 4 vCPUs
```

| Output | Command | Result file |
|---|---|---|
| Corpus statistics, latency | `scripts/reproduce_deterministic_tier_baseline.py` | `results/deterministic_tier_baseline.json` |
| Clean detection, controls, ablation, strata, Wikipedia scan, S3, S4 | `scripts/run_clean_eval.py` | `results/revision2_clean.json` |
| Attacks, adaptive search, component attribution | `scripts/run_attack_audit.py --revision r2` | `results/attack_audit_r2.json` |
| Scorer validation and sensitivity | `scripts/validate_scorer.py`, `LEAK_K=…`, `LEAK_SCORER=v1` | `results/scorer_validation.json`, `results/sensitivity/` |
| Length-scaling test | `scripts/redos_scaling.py` | `results/redos_scaling.json` |
| Hashes and versions | `scripts/make_provenance.py` | `results/provenance.json` |

Every result file stores `code_sha256` (detector package) and `eval_sha256` (all evaluation scripts, including the scorer and Presidio configuration).

## Repository layout

```
src/arenredact/     detector, attacks (operators.py, extended.py), audit log, data generator, metrics
scripts/            evaluation, attack audit, scorer validation, evaluation sets (S3, S4, validity, challenge)
results/            all result JSON, frozen first-run files, archived first-round package
annotation/         independent-annotation protocol, blind-set builder, agreement and scoring tools
data/independent/   Wikipedia lead extracts (CC BY-SA 4.0) and the annotated 330-sentence set
tests/              122 unit tests
```

## Reproduce the independent-set and round-4 results

```
make independent     # Table 15 from the released annotation files (original and corrected gold), checked against results/
make analysis        # complete-recovery / total-leakage / common-subset, cluster bootstrap, false positives (scrubadub needs: pip install scrubadub)
```

Human checks: `analysis/leakage_review/` (120 attacked outputs judged blind by one non-author reviewer: 120/120 agreement with the scorer, `results/leakage_review.json`) and `analysis/s5_kit/` with `data/independent/s5/` (180 sentences whose contexts two non-author contributors wrote; scored once, `results/s5_scored.json`: F1 0.970 ours, 0.988 Presidio+S1+reg, 0.732 Presidio).

## Independent annotation

`annotation/` contains the guidelines, the set builder, the workbook collector, the Cohen's κ script, the one-shot scoring script and `summarize_independent.py`. The executed annotation (both annotators' workbooks, adjudication sheet, adjudicated gold and key) is in `data/independent/annotated_330/`; reproduce the numbers with `python annotation/score_adjudicated.py` and `python annotation/summarize_independent.py`.

## Limitations

Synthetic and author-written evaluation sets; one generic 10-digit national-ID rule for all countries; no local phone numbers without a country code; English and Arabic keywords only; no names, addresses or quasi-identifiers; Python's backtracking regex engine (linear on the tested inputs, not guaranteed in general).

## Cite

```bibtex
@software{arenredact2026,
  author  = {Raheema, Alaa Q. and Tarish, Hiba A. and Salman, Aymen D. and Humaidi, Amjad J.},
  title   = {ArEnRedact: A Threat-Driven Evaluation Framework and Deterministic Baseline for Arabic--English PII Redaction},
  year    = {2026},
  version = {1.1.0},
  doi     = {10.5281/zenodo.23268049},
  url     = {https://github.com/Akramtaha98/arenredact}
}
```

## License

MIT for the code (see `LICENSE`). Wikipedia text in `data/independent/` is CC BY-SA 4.0. Generative-AI assistance (Claude, Anthropic) was used to write code, evaluation sets and text; see the manuscript's declaration.
