"""Real, executed evaluation of the DETERMINISTIC tier of the ArEnRedact
pipeline (Stages 1, 3, 4, 5 -- normalization, regex PII engine, span fusion,
audit log). Stage 2 (LoRA neural NER) is NOT included: it requires GPU
training that is not available in this environment, so PERSON/ORGANIZATION/
LOCATION/DATE_OF_BIRTH entities (which only the neural stage can detect) are
excluded from the measured numbers below and reported separately as
"not evaluated in this run".

Every number this script prints is computed by actually executing the
arenredact package end-to-end against a freshly generated synthetic corpus.
Nothing here is hand-typed or illustrative.
"""

import json
import platform
import statistics
import time

from arenredact.attacks.operators import OPERATOR_FUNCS, AttackOperator
from arenredact.data.corpus_generator import generate_corpus
from arenredact.evaluation.metrics import attack_success_rate, bootstrap_ci, precision_recall_f1
from arenredact.evaluation.reidentification import LexicalOverlapAdversary, RedactedRecord, compute_prir
from arenredact.pipeline import ArEnRedactPipeline
from arenredact.span_fusion import Span, SpanOrigin

REGEX_DETECTABLE_TYPES = {"PHONE", "EMAIL", "IBAN", "NATIONAL_ID", "URL", "IP_ADDRESS"}
NEURAL_ONLY_TYPES = {"PERSON", "ORGANIZATION", "LOCATION", "DATE_OF_BIRTH"}

SEED = 42
N_SENTENCES = 8970  # matches the corpus size the manuscript already describes
ARABIZI_RATE = 0.30


def gold_spans(record) -> list[Span]:
    return [
        Span(start=e.start, end=e.end, entity_type=e.entity_type, origin=SpanOrigin.REGEX)
        for e in record.entities
    ]


def gold_spans_regex_subset(record) -> list[Span]:
    return [s for s in gold_spans(record) if s.entity_type in REGEX_DETECTABLE_TYPES]


def main():
    results = {}

    results["environment"] = {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "note": (
            "4-vCPU ARM64 containerized sandbox, no GPU, single-process. "
            "Latency figures reflect only the relative cost of Stages 1/3/4/5 "
            "on this hardware and should NOT be read as a production SLA; "
            "they are reported for architectural transparency, not deployment "
            "sizing."
        ),
    }

    # ---- 1. Generate the corpus (same seed/size the manuscript describes) ----
    corpus = generate_corpus(n_sentences=N_SENTENCES, seed=SEED, arabizi_rate=ARABIZI_RATE)
    n_train = int(0.80 * N_SENTENCES)
    n_dev = int(0.10 * N_SENTENCES)
    train = corpus[:n_train]
    dev = corpus[n_train : n_train + n_dev]
    test = corpus[n_train + n_dev :]

    def entity_count(split):
        return sum(len(r.entities) for r in split)

    def entity_type_breakdown(split):
        counts = {}
        for r in split:
            for e in r.entities:
                counts[e.entity_type] = counts.get(e.entity_type, 0) + 1
        return counts

    results["corpus"] = {
        "n_sentences_total": len(corpus),
        "n_sentences_train": len(train),
        "n_sentences_dev": len(dev),
        "n_sentences_test": len(test),
        "n_entities_total": entity_count(corpus),
        "n_entities_train": entity_count(train),
        "n_entities_dev": entity_count(dev),
        "n_entities_test": entity_count(test),
        "entity_type_breakdown_total": entity_type_breakdown(corpus),
    }

    # ---- 2. Clean-input detection performance (regex-only pipeline) ----
    pipeline = ArEnRedactPipeline()  # no neural_ner -> Stage 2 skipped entirely
    per_sentence_f1_clean = []
    tp_total = fp_total = fn_total = 0
    per_type_tp = {}
    per_type_fp = {}
    per_type_fn = {}

    clean_pred_cache = []  # keep for reuse in latency + adversarial sections
    for rec in test:
        result = pipeline.redact(rec.text, record_audit=False)
        clean_pred_cache.append(result)
        gold = gold_spans_regex_subset(rec)
        prf1 = precision_recall_f1(gold, result.spans)
        per_sentence_f1_clean.append(prf1.f1)
        tp_total += prf1.true_positives
        fp_total += prf1.false_positives
        fn_total += prf1.false_negatives

        gold_types = {(s.start, s.end, s.entity_type) for s in gold}
        pred_types = {(s.start, s.end, s.entity_type) for s in result.spans}
        for key in gold_types & pred_types:
            per_type_tp[key[2]] = per_type_tp.get(key[2], 0) + 1
        for key in pred_types - gold_types:
            per_type_fp[key[2]] = per_type_fp.get(key[2], 0) + 1
        for key in gold_types - pred_types:
            per_type_fn[key[2]] = per_type_fn.get(key[2], 0) + 1

    precision = tp_total / (tp_total + fp_total) if (tp_total + fp_total) else 0.0
    recall = tp_total / (tp_total + fn_total) if (tp_total + fn_total) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    results["clean_performance_regex_only"] = {
        "scope_note": "Measured over the REGEX_DETECTABLE_TYPES subset only "
                       "(PHONE, EMAIL, IBAN, NATIONAL_ID, URL, IP_ADDRESS). "
                       "PERSON/ORGANIZATION/LOCATION/DATE_OF_BIRTH require the "
                       "neural NER stage (Stage 2), which was not executed.",
        "n_test_sentences": len(test),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "true_positives": tp_total,
        "false_positives": fp_total,
        "false_negatives": fn_total,
        "per_type_true_positives": per_type_tp,
        "per_type_false_positives": per_type_fp,
        "per_type_false_negatives": per_type_fn,
    }

    # ---- 3. Adversarial robustness (attacks applied to regex-detectable spans) ----
    adversarial_results = {}
    for op_name in ["arz", "tat", "dia", "hgl", "cmb"]:
        op = AttackOperator(op_name)
        op_func = OPERATOR_FUNCS[op]
        per_sentence_f1_adv = []
        tp_adv_total = 0
        for rec in test:
            attackable_spans = [(e.start, e.end) for e in rec.entities if e.entity_type in REGEX_DETECTABLE_TYPES]
            if not attackable_spans:
                perturbed_text = rec.text
            else:
                perturbed_text = op_func(rec.text, spans=attackable_spans, rng=__import__("random").Random(SEED))
            adv_result = pipeline.redact(perturbed_text, record_audit=False)
            gold = gold_spans_regex_subset(rec)
            prf1 = precision_recall_f1(gold, adv_result.spans)
            per_sentence_f1_adv.append(prf1.f1)
            tp_adv_total += prf1.true_positives

        asr = attack_success_rate(tp_total, tp_adv_total)
        ci = bootstrap_ci(per_sentence_f1_clean, per_sentence_f1_adv, n_resamples=10000, confidence=0.95, seed=SEED)
        adversarial_results[op_name] = {
            "tp_adversarial": tp_adv_total,
            "attack_success_rate": asr,
            "f1_mean_adversarial": statistics.mean(per_sentence_f1_adv),
            "bootstrap_ci_vs_clean": ci,
        }

    results["adversarial_regex_only"] = {
        "scope_note": "ARZ/TAT/DIA target Arabic-script PERSON-name characters, "
                       "which the regex-only pipeline never detects in the first "
                       "place (TP_clean=0 for that entity type here), so their "
                       "ASR against this deterministic baseline is not a "
                       "meaningful robustness signal -- it reflects Stage 1 "
                       "normalization's effect on the PHONE/IBAN/NATIONAL_ID/ "
                       "EMAIL/URL/IP entities that are actually detectable "
                       "without Stage 2.",
        "operators": adversarial_results,
    }

    # ---- 4. PRIR with the weak lexical-overlap adversary ----
    # Build a background corpus from the DEV split (disjoint from TEST) so the
    # adversary isn't trivially matching against the exact same records it's
    # attacking.
    background_entities = []
    for rec in dev:
        for e in rec.entities:
            context = rec.text[max(0, e.start - 30) : e.end + 30]
            value = rec.text[e.start : e.end]
            background_entities.append((context, value))

    redacted_records = []
    for rec, cached_result in zip(test, clean_pred_cache):
        redacted_records.append(
            RedactedRecord(
                redacted_text=cached_result.redacted_text,
                original_text=cached_result.normalized_text,
                redacted_spans=cached_result.spans,
            )
        )
    adversary = LexicalOverlapAdversary(background_entities=background_entities)
    prir_result = compute_prir(redacted_records, adversary)
    results["prir_lexical_overlap_adversary"] = {
        "scope_note": "Weak, fully offline n-gram-overlap adversary (see "
                       "reidentification.py docstring) -- a conservative LOWER "
                       "BOUND on re-identification risk, not the paper's "
                       "originally specified RAG-augmented infilling adversary "
                       "(which requires an LM and is not executed here).",
        **prir_result,
    }

    # ---- 5. Latency: real wall-clock measurement of Stages 1+3+4+5 ----
    warmup = test[:20]
    for rec in warmup:
        pipeline.redact(rec.text, record_audit=False)

    timing_pipeline = ArEnRedactPipeline()  # fresh audit log so chain length doesn't affect timing
    n_timed = min(500, len(test))
    per_sentence_ms = []
    for rec in test[:n_timed]:
        start = time.perf_counter()
        timing_pipeline.redact(rec.text, record_audit=True)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        per_sentence_ms.append(elapsed_ms)

    results["latency_stages_1_3_4_5"] = {
        "n_sentences_timed": n_timed,
        "mean_ms": statistics.mean(per_sentence_ms),
        "std_ms": statistics.stdev(per_sentence_ms) if len(per_sentence_ms) > 1 else 0.0,
        "median_ms": statistics.median(per_sentence_ms),
        "p95_ms": sorted(per_sentence_ms)[int(0.95 * len(per_sentence_ms)) - 1],
        "min_ms": min(per_sentence_ms),
        "max_ms": max(per_sentence_ms),
    }

    # ---- 6. What was NOT run, explicitly ----
    results["not_executed_in_this_run"] = [
        "Stage 2 neural NER (LoRA-adapted XLM-RoBERTa) training and inference "
        "-- requires GPU and multi-hour training.",
        "Full fine-tuning baseline for memorization comparison.",
        "DP-SGD comparison baseline.",
        "LiRA membership-inference attack with shadow models (harness exists "
        "and is unit-tested in evaluation/membership_inference.py, but "
        "training 128 shadow models is a multi-GPU-day workload).",
        "Human bilingual annotator review / inter-annotator agreement on the "
        "synthetic corpus.",
        "RAG-augmented autoregressive-infilling PRIR adversary (only the weak "
        "offline lexical-overlap adversary was run).",
        "Component ablation study (requires the trained neural model).",
    ]

    import os
    out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results", "deterministic_tier_baseline.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)

    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
