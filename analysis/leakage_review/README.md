# Blinded human review of the leakage scorer

`Leakage_Review_Sheet.xlsx` has 120 real attacked outputs (S3; two systems and ten attacks, all hidden) with the original
identifier and the redacted output. A reviewer answers Q1 (can the complete identifier be reconstructed?) and Q2 (is it a
privacy leak?). Reviewers must not be authors and work alone. `_private/AUTHORS_ONLY_key.csv` (git-ignored, not in the release zip) holds the scorer verdicts; keep it away
from reviewers. Score with `python analysis/score_leakage_review.py completed_A.xlsx [completed_B.xlsx]`
(agreement, Cohen's kappa, scorer false alarms and misses, every disagreement; two reviewers also give inter-reviewer kappa).
No human result is reported in the paper until this has been done.
