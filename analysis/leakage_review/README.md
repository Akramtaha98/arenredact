# Blinded human review of the leakage scorer

`Leakage_Review_Sheet.xlsx` has 120 real attacked outputs (S3; two systems and ten attacks, all hidden) with the original
identifier and the redacted output. A reviewer answers Q1 (can the complete identifier be reconstructed?) and Q2 (is it a
privacy leak?). Reviewers must not be authors and work alone. `Leakage_Review_KEY.csv` holds the scorer verdicts and is released so the agreement can be recomputed; give a new reviewer only the blinded sheet, not this folder. Score with `python analysis/score_leakage_review.py completed_A.xlsx [completed_B.xlsx]`
(agreement, Cohen's kappa, scorer false alarms and misses, every disagreement; two reviewers also give inter-reviewer kappa).
Reviewer 1 (`Leakage_Review_Sheet_completed.xlsx`, one non-author working blind): 120/120 agreement on both questions, see `results/leakage_review.json`.
