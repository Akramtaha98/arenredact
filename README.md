# ArEnRedact

**Adversarially hardened, threat-model-driven PII redaction for Arabic–English code-mixed network traffic.**

Reference implementation accompanying the paper *"ArEnRedact: A Threat-Driven Methodology and Reproducible Evaluation Framework for Arabic–English PII Redaction."*

> **Status note (read before running).** The paper distinguishes two classes of result — see Section 5.5. **Measured** (Tables 4–6): the deterministic tier (Stages 1, 3, 4, 5 — no neural NER) was executed end-to-end against the synthetic corpus in this repository (seed = 42) and every number in those tables is a real, reproducible output of that run; see `results/deterministic_tier_baseline.json` for the raw output. It was also run against an independent, hand-authored noisy challenge set (`scripts/noisy_challenge_set.py`) covering formatting variation the corpus generator does not produce — P=R=F1=0.944 (17 TP, 1 FP, 1 FN across 28 cases), with two concrete pattern-engine limitations surfaced and documented rather than silently patched; see `results/noisy_challenge_set.json`. **Specified, not executed**: the neural NER tier (Stage 2), the LoRA-vs-full-fine-tuning membership-inference comparison, the DP-SGD frontier, the component ablation, and the AraBERT/GPT-4o/Llama-3.1 comparison baselines require GPU training (and, for two baselines, external API access) not available in the environment used to prepare the paper. The code for all of it is here and unit-tested (see `evaluation/membership_inference.py`), but no neural-tier numbers are reported as findings anywhere in the manuscript. Running `scripts/train_lora.py` and the `scripts/run_*_eval.py` scripts against a GPU is how those numbers get produced.

## What this is

A five-stage hybrid pipeline for detecting and redacting Personally Identifiable Information (PII) in Arabic–English code-mixed text, hardened against script-evasion adversarial attacks (Arabizi substitution, Tatweel injection, Arabic diacritization, Unicode homoglyphs):

```
raw text -> [1] Unicode normalization -> [2] LoRA NER  \
                                       -> [3] regex PII  -> [4] span fusion -> [5] audit log -> redacted text
```

| Stage | Module | What it does |
|---|---|---|
| 1 | `arenredact.preprocessing` | NFC normalization, bidi control-character stripping, Arabic–Indic digit folding, Tatweel capping |
| 2 | `arenredact.neural_ner` | LoRA-adapted XLM-RoBERTa token classifier |
| 3 | `arenredact.pattern_engine` | Deterministic regex detectors for MENA phone numbers, IBANs, emails, national IDs |
| 4 | `arenredact.span_fusion` | Union-fusion + kunya/nisbah/laqab quasi-identifier expansion (Algorithm 1 in the paper) |
| 5 | `arenredact.audit_log` | Hash-chained, Ed25519-signed append-only redaction log |

Plus:

- `arenredact.attacks` — the five adversarial perturbation operators (ARZ, TAT, DIA, HGL, CMB) used for the security evaluation
- `arenredact.data` — synthetic code-mixed PII corpus generator
- `arenredact.evaluation` — ASR, PRIR, and MIA (LiRA) evaluation harnesses

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
git clone https://github.com/<author-org>/arenredact.git
cd arenredact
pip install -e ".[dev]"
```

Python 3.10+. Core deterministic modules (`preprocessing`, `pattern_engine`, `span_fusion`, `attacks`, `data.corpus_generator`) have **no GPU dependency** and run anywhere. `neural_ner.py` and the MIA harness require `torch`, `transformers`, and `peft`; `train_lora.py` expects a CUDA GPU for realistic training times.

## Quickstart — deterministic pipeline only (no GPU required)

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

Each script writes a JSON results file. The deterministic-tier scripts reproduce Tables 4–6 exactly (see `results/deterministic_tier_baseline.json` for the committed reference output); the neural-tier scripts (`run_mia_eval.py`, and `run_*_eval.py` once pointed at a trained checkpoint) produce the numbers the paper explicitly does not yet report — running them and reporting the output is the paper's stated next step (Section 8.5).

## Testing

```bash
pytest tests/ -v
```

The test suite covers the deterministic components only (preprocessing, pattern engine, span fusion, attack operators) since these require no trained model or GPU and are fully reproducible in CI. See `.github/workflows/tests.yml`.

To reproduce the independent noisy challenge set result (P=R=F1=0.944):

```bash
python scripts/noisy_challenge_set.py
```

## Security notes

- The pattern engine is written against Python's built-in `re` module for portability. The paper specifies Google's RE2 for its linear-time (ReDoS-proof) guarantee; swap in the `google-re2` bindings (`pip install google-re2`) for production deployment — `pattern_engine.py` isolates all regex compilation behind a single `_compile()` call so the swap is a one-line change (see the comment in that file).
- `audit_log.py` implements the hash-chaining and Ed25519 signing logic described in Section 7.3. The Byzantine-fault-tolerant replication (PBFT, n=4, f=1) across multiple nodes is **not** implemented here — this repository provides the single-node log format; multi-node consensus is future work per the paper's Section 8.3 (Limitations).
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

MIT — see `LICENSE`.
