# Changelog

## 1.1.0 (independent annotation, round-4 analyses)
- S5 built from two non-author contributors' sentences (`data/independent/s5`, SHA-256 05a151ce…) and scored once (`results/s5_scored.json`); leakage-review sheet completed by one blind non-author reviewer (`results/leakage_review.json`, 120/120 agreement; scoring key released).
- `make independent` reproduces Table 15 (original and corrected gold) from the released files and checks it against the committed results.
- `analysis/` (outside `scripts/`, so `eval_sha256` is unchanged): `leakage_levels.py` (partial vs complete recovery, total leakage, common subset, span-vs-output disagreement), `bootstrap_ci.py` (cluster bootstrap and paired differences), `fp_negatives.py` (false positives on negatives), `common.py` (scrubadub comparator).
- Review kits (results now included, see next two lines): `analysis/leakage_review/` (blinded sheet of 120 attacked outputs + scoring script) and `analysis/s5_kit/` (context-writing sheets for non-author contributors, build and score-once pipeline).
- New result files: `results/leakage_levels.json`, `results/bootstrap_ci.json`, `results/fp_negatives.json`.
- Independent annotation executed: 330 items labelled by two non-author annotators (character-level kappa 0.955), 21 disagreements adjudicated by a third non-author; frozen detector and Presidio controls scored once (`results/independent_annotation.json`, `results/independent_annotation_summary.json`, `annotation/summarize_independent.py`).
- Data: `data/independent/annotated_330/` (items, key, both annotators' workbooks and spans, adjudication sheet, adjudicated gold).
- Detector source unchanged (same `code_sha256` and `eval_sha256` as 1.0.1).
- Gold corrected once (v2, `adjudicated_v2.csv`, six rows) after a blind second review: item I314 span and five bare local numbers; v1 kept; all systems rescored with unchanged detectors (`results/independent_annotation_v2.json`, `results/independent_annotation_v1_v2.json`, `annotation/rescore_corrected.py`).

## 1.0.1 (response to second review)
- Leakage scorer v2: a fragment counts only if it occurs more often in the redacted output than in the surrounding text alone (coincidental overlap such as a shared domain no longer counts); validated on 1,160 constructed cases (`scripts/validate_scorer.py`); threshold and v1/v2 sensitivity runs in `results/sensitivity/`. All attack results re-run (R1 and R3).
- Second frozen set S4 (new templates, new seed), scored once on the frozen R3 detector and Presidio configurations.
- `eval_sha256` (all scripts) stored next to `code_sha256` in every result file.
- Documented the reader model used for scoring.

## 1.0.0 (round-2 revision)
- Stage 1 gains step-wise switches (`steps=`), invisible-character stripping, bidi stripping before matching, Arabic mark stripping in context windows, and a conservative confusable fold (UTS #39 style, limited inventory).
- Pattern engine: phone numbers (+/00 prefix, `[\\s.-]` separators, parenthesised group), IBAN scanner (country-specific structure and length; no mod-97 check; spaced and lower-case forms), `@`-anchored e-mail scanner (the previous regex was quadratic in the local-part length), contextual 10-digit national ID with a trailing "(civil ID)" rule.
- Audit log: keyed HMAC-SHA256 digests, signed checkpoint (count + head hash) that detects tail truncation; offsets refer to the normalised text.
- New evaluation code: `eval_lib.py`, `run_clean_eval.py`, `run_attack_audit.py`, `stratified_holdout.py`, `redos_scaling.py`, `fetch_wikipedia_negatives.py`, `make_provenance.py`.
- Extended attack operators (`attacks/extended.py`): invisible, bidi, full-width/mathematical, digit scripts, separators, look-alikes, ID-context, combinations, black-box adaptive search.
- Evaluation integrity: mislabelled negatives in the challenge sets were relabelled (25 sentences in the extended set, 1 in the holdout; 8 and 1 ambiguous local numbers excluded); original-label results are reported alongside.
- Presidio controls: default, + Stage 1, + Stage 1 + regional recognisers.
- Annotation package for independent labelling (not executed).
- 122 tests.

## 0.1.0
- Initial release (first-round manuscript).
