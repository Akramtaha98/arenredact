# Changelog

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
