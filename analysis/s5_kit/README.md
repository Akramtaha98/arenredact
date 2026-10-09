# S5: independently written positive contexts

1. Send `S5_Writing_Sheet_A.xlsx` / `_B.xlsx` to two non-author contributors (about 45 minutes each).
2. `python analysis/s5_kit/build_s5.py A_done.xlsx B_done.xlsx --out data/independent/s5` validates the slots, inserts generated
   identifiers (labels by construction), writes `items.csv`, `gold.csv` and `SHA256.txt`, and refuses to overwrite.
3. Freeze (tag the release), then `python analysis/s5_kit/score_s5.py data/independent/s5`. It checks the set hash and the
   detector hash and refuses to run twice. Report the scores once, with the cluster bootstrap of `analysis/bootstrap_ci.py`.
