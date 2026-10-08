# Independent text for false-positive measurement

`wikipedia_ar.jsonl` (294 pages) and `wikipedia_en.jsonl` (156 pages) were fetched with
`scripts/fetch_wikipedia_negatives.py` from the MediaWiki API (plain-text extracts of
randomly sampled articles). Text is © its Wikipedia contributors and licensed
CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/); page ids and titles in each
record identify the source article and revision date. The files are used only to count
detections on text that was not written by the authors; they are **not** annotated for PII, so
any detection there is reviewed by hand (see `results/revision2_clean.json` -> `wikipedia_fp`).
This is not an independent annotated benchmark: independent bilingual annotation is specified
in `annotation/` and has not been performed.
