"""Convert a returned annotator workbook into the span CSV used by agreement.py.
usage: python annotation/collect.py Annotator_A.xlsx items.csv out_A.csv
Also writes sample.csv (sentence_id,text) next to out_A.csv when --sample is given.
Reports rows that are unfilled, identifiers not found in the text, invalid types."""
import csv, sys, unicodedata
from openpyxl import load_workbook
TYPES = {"PHONE", "EMAIL", "IBAN", "NATIONAL_ID", "OTHER_PII"}

def main(xlsx, items_csv, out):
    items = {r["item_id"]: r["text"] for r in csv.DictReader(open(items_csv, encoding="utf-8-sig"))}
    ws = load_workbook(xlsx, data_only=True).active
    rows, problems = [], []
    seen = set()
    for r in ws.iter_rows(min_row=2, values_only=True):
        iid, text, none = r[0], r[1], (r[2] or "")
        if iid not in items: continue
        seen.add(iid)
        if text != items[iid]: problems.append((iid, "text column was edited"))
        ids = [(r[3], r[4]), (r[5], r[6]), (r[7], r[8])]
        ids = [(str(a).strip(), str(b).strip()) for a, b in ids if a not in (None, "")]
        if not ids and str(none).strip().lower() != "yes":
            problems.append((iid, "row not filled (neither identifier nor no_identifier=yes)")); continue
        used = []
        for ident, typ in ids:
            if typ not in TYPES: problems.append((iid, f"invalid or missing type for '{ident}': {typ}")); continue
            s = -1; pos = 0
            while True:
                s = items[iid].find(ident, pos)
                if s == -1 or all(not (s < e and b < s + len(ident)) for b, e in used): break
                pos = s + 1
            if s == -1: problems.append((iid, f"identifier text not found in sentence: {ident!r}")); continue
            used.append((s, s + len(ident))); rows.append((iid, s, s + len(ident), typ, ""))
    for iid in items:
        if iid not in seen: problems.append((iid, "item missing from workbook"))
    with open(out, "w", encoding="utf8", newline="") as f:
        w = csv.writer(f); w.writerow(["sentence_id", "start", "end", "label", "note"]); w.writerows(rows)
    with open(out.replace(".csv", "_sample.csv"), "w", encoding="utf8", newline="") as f:
        w = csv.writer(f); w.writerow(["sentence_id", "text"]); [w.writerow([k, v]) for k, v in items.items()]
    print(len(rows), "spans;", len(problems), "problems")
    for p in problems: print("  ", p)

if __name__ == "__main__": main(*sys.argv[1:4])
