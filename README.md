# ArEnRedact

**A threat-driven evaluation framework and deterministic baseline for Arabic-English PII redaction.**

Reference implementation and reproduction package for the manuscript submitted to the *Journal of Information Security and Applications* (version 1.0.0).

> **Scope and status (read first).** Every number in the manuscript comes from the **deterministic tier** (Stage 1 normalisation, Stage 3 regex engine, Stage 4 fusion, Stage 5 audit log). Stage 2 (LoRA XLM-RoBERTa), DP-SGD, LiRA membership inference and re-identification with a strong adversary are specified and unit-tested but **not executed** (no GPU) and are future work. The evaluation sets are synthetic or author-constructed; **no independent human annotation has been performed**. `annotation/` contains the protocol, blind sample and agreement tooling for that step.

## Reproduce

```
pip install -r requirements-lock.txt && pip install -e .
bash scripts/reproduce_all.sh        # or: make all
```

| Output in the paper | Command | Result file |
|---|---|---|
| Corpus statistics, latency | `scripts/reproduce_deterministic_tier_baseline.py` | `results/deterministic_tier_baseline.json` |
| Clean detection, Presidio controls, ablation, strata, Wikipedia false positives | `scripts/run_clean_eval.py` | `results/revision2_clean.json` |
| Frozen S3 score at revision R2 (scored once) | `scripts/run_clean_eval.py` at R2 | `results/frozen/revision2_clean_firstrun.json` |
| Fixed and adaptive attacks, component attribution | `scripts/run_attack_audit.py --revision r2` | `results/attack_audit_r2.json` |
| First-round detector under the same attacks | `PYTHONPATH=results/frozen/r1_src:scripts python scripts/run_attack_audit.py --revision r1` | `results/attack_audit_r1.json` |
| Complexity (length scaling) | `scripts/redos_scaling.py` | `results/redos_scaling.json` |
| Hashes, versions | `scripts/make_provenance.py` | `results/provenance.json` |

Each result file records `code_sha256`, the SHA-256 of the detector source that produced it. Dataset hashes are in `results/provenance.json`. Python 3.10, versions in `requirements-lock.txt`. The unit tests (`pytest`, 122 tests) run in under a second.

## Revision history of the detector (why three hashes)

- **R1**: first-round detector (source archived in `results/frozen/r1_src`).
- **R2**: Stage 1 extended (invisible, confusable and mark stripping), phone/IBAN/e-mail/ID rules rewritten. Frozen, then the stratified holdout S3 was scored once on it.
- **R3** (final): one post hoc fix to phone numbers with a parenthesised group. S3 scores at R2 and R3 are both reported.

See `CHANGELOG.md`.

## What this is

A five-stage hybrid pipeline for detecting and redacting Personally Identifiable Information (PII) in Arabic–English code-mixed text, hardened against script-evasion adversarial attacks (Arabizi substitution, Tatweel injection, Arabic diacritization, Unicode homoglyphs):

```
raw text -> [1] Unicode normalization -> [2] LoRA NER  \
                                       -> [3] regex PII  -> [4] span fusion -> [5] audit log -> redacted text
```

| Stage | Module | What it does |
|---|---|---|
| 1 | `arenredact.preprocessing` | NFKC normalization, bidi control-character stripping, Arabic–Indic digit folding, Tatweel capping |
| 2 | `arenredact.neural_ner` | LoRA-adapted XLM-RoBERTa token classifier |
| 3 | `arenredact.pattern_engine` | Deterministic regex detectors for MENA phone numbers, IBANs, emails, national IDs |
| 4 | `arenredact.span_fusion` | Union-fusion + kunya/nisbah/laqab quasi-identifier expansion (Algorithm 1 in the paper) |
| 5 | `arenredact.audit_log` | Hash-chained, Ed25519-signed append-only redaction log |

Plus:

- `arenredact.attacks`: the five adversarial perturbation operators (ARZ, TAT, DIA, HGL, CMB) used for the security evaluation
- `arenredact.data`: synthetic code-mixed PII corpus generator
- `arenredact.evaluation`: ASR, PRIR, and MIA (LiRA) evaluation harnesses

## Repository layout

```
arenredact/
├── src/arenredact/
│   ├── preprocessing.py         Stage 1
│   ├── neural_ner.py            Stage 2 (LoRA wrapper)
│   ├── pattern_engine.py        Stage 3
│   ├── span_fusion.py           Stage 4 (Algorithm 1)
│   ├── audit_log.py             Stage 5
│   ├── pipeline.py              orchestrates all 5 stages
│   ├── attacks/operators.py     ARZ / TAT / DIA / HGL / CMB
│   ├── data/corpus_generator.py synthetic corpus generation
│   ├── data/lexicons.py         kunya/nisbah/laqab lists, Da3i mapping, MENA phone codes
│   └── evaluation/              metrics.py, reidentification.py, membership_inference.py
├── scripts/                     CLI entry points (train, generate corpus, run evals)
├── tests/                       unit tests for the deterministic components
├── configs/                     LoRA + pipeline YAML configs
└── data/lexicons/               plaintext lexicon files
```

## Installation

```bash
git clone https://github.com/Akramtaha98/arenredact.git
cd arenredact
pip install -e ".[dev]"
```

Python 3.10+. Core deterministic modules (`preprocessing`, `pattern_engine`, `span_fusion`, `attacks`, `data.corpus_generator`) have **no GPU dependency** and run anywhere. `neural_ner.py` and the MIA harness require `torch`, `transformers`, and `peft`; `train_lora.py` expects a CUDA GPU for realistic training times.

## Quickstart - deterministic pipeline only (no GPU required)

```python
from arenredact.preprocessing import normalize
from arenredact.pattern_engine import PatternEngine
from arenredact.span_fusion import fuse_spans

text = "تواصل مع محمد العتيبي أبو سالم على +966501234567 أو محمد@example.com"

normalized = normalize(text)
regex_spans = PatternEngine().detect(normalized)
# neural_spans would come from arenredact.neural_ner.LoraNER (requires a trained checkpoint)
fused = fuse_spans(neural_spans=[], regex_spans=regex_spans, text=normalized)

for span in fused:
    print(span.entity_type, normalized[span.start:span.end])
```

## Running the full pipeline (requires a trained LoRA checkpoint)

```bash
python scripts/generate_corpus.py --out data/synthetic_corpus.jsonl --n-sentences 8970
python scripts/train_lora.py --config configs/lora_config.yaml
python -m arenredact.pipeline --checkpoint runs/lora_xlmr/checkpoint-best --input examples/sample.txt
```

## Reproducing the security evaluation (Sections 5–6 of the paper)

```bash
# Adversarial Success Rate (Table 5) across the five perturbation operators
python scripts/run_adversarial_eval.py --checkpoint runs/lora_xlmr/checkpoint-best \
    --test-set data/synthetic_corpus_test.jsonl --operators arz tat dia hgl cmb

# Post-Redaction Re-Identification Rate (Table 7)
python scripts/run_reidentification_eval.py --redacted-output outputs/redacted_test.jsonl \
    --background-corpus data/background/ --n-records 200

# Membership Inference AUC, LoRA vs. full fine-tuning (Table 7)
python scripts/run_mia_eval.py --target-checkpoint runs/lora_xlmr/checkpoint-best \
    --n-shadow-models 128 --fpr-threshold 0.01
```

Each script writes a JSON results file. The deterministic-tier scripts reproduce Tables 4–6 exactly (see `results/deterministic_tier_baseline.json` for the committed reference output); the neural-tier scripts (`run_mia_eval.py`, and `run_*_eval.py` once pointed at a trained checkpoint) produce the numbers the paper explicitly does not yet report, running them and reporting the output is the paper's stated next step (Section 8.5).

## Testing

```bash
pytest tests/ -v
```

The test suite covers the deterministic components only (preprocessing, pattern engine, span fusion, attack operators) since these require no trained model or GPU and are fully reproducible in CI. See `.github/workflows/tests.yml`.

To reproduce the extended 168-sentence challenge set result (P=R=F1=1.000, post-fix):

```bash
python scripts/noisy_challenge_set.py
```

The frozen holdout (`scripts/noisy_challenge_set_holdout.py`) was run exactly once and its recorded result (`results/noisy_challenge_set_holdout.json`, P=1.000, R=0.800, F1=0.889) is reported as-is; re-running it is possible but re-scoring it against the post-holdout keyword-list fix would defeat the purpose of freezing it (see the module docstring for the full rationale).

## Security notes

- The pattern engine is written against Python's built-in `re` module for portability. The paper specifies Google's RE2 for its linear-time (ReDoS-proof) guarantee; swap in the `google-re2` bindings (`pip install google-re2`) for production deployment; `pattern_engine.py` isolates all regex compilation behind a single `_compile()` call so the swap is a one-line change (see the comment in that file).
- `audit_log.py` implements the hash-chaining and Ed25519 signing logic described in Section 7.3. The Byzantine-fault-tolerant replication (PBFT, n=4, f=1) across multiple nodes is **not** implemented here; this repository provides the single-node log format; multi-node consensus is future work per the paper's Section 8.3 (Limitations).
- No real PII is included anywhere in this repository. `corpus_generator.py` produces synthetic entities only.

## Citation

```bibtex
@article{raheema2026arenredact,
  title   = {ArEnRedact: A Threat-Driven Methodology and Reproducible
             Evaluation Framework for Arabic--English PII Redaction},
  author  = {Raheema, Alaa Q.},
  journal = {Discover Artificial Intelligence},
  year    = {2026}
}
```

## License

MIT - see `LICENSE`.
