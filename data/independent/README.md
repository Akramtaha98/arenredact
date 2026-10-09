# Independent text for false-positive measurement

`wikipedia_ar.jsonl` (294 pages) and `wikipedia_en.jsonl` (156 pages) were fetched with
`scripts/fetch_wikipedia_negatives.py` from the MediaWiki API (plain-text extracts of
randomly sampled articles). Text is © its Wikipedia contributors and licensed
CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/); page ids and titles in each
record identify the source article and revision date. The files are used only to count
detections on text that was not written by the authors; they are **not** annotated for PII, so
any detection there is reviewed by hand (see `results/revision2_clean.json` -> `wikipedia_fp`).
These extracts are not an annotated benchmark. The independently annotated 330-sentence set is in
`annotated_330/` (items, key, both annotators' workbooks and span files, the adjudication sheet and
the adjudicated gold; see `results/independent_annotation_summary.json`). It contains 120 Wikipedia
sentences (CC BY-SA 4.0) and 210 author-written synthetic sentences.

`adjudicated.csv` is the original gold (v1); `adjudicated_v2.csv` is the corrected gold (six rows changed after a blind second review, see `annotation/gold_review/`). Both are scored; see `results/independent_annotation_v1_v2.json`.
