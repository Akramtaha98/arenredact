"""Fill the returned contribution sheets with generated identifiers, freeze the set, record hashes.
usage: python analysis/s5_kit/build_s5.py S5_A.xlsx S5_B.xlsx --out data/independent/s5   (refuses to overwrite)
Validations: exactly one slot per sentence, no other digits/@ in positives, no duplicate sentences.
Identifier values come from the repository generators (same value generators as S3/S4); labels follow by construction."""
import csv, hashlib, os, random, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for p in (os.path.join(ROOT, "scripts"), os.path.join(ROOT, "src"), ROOT):
    sys.path.insert(0, p)
import openpyxl
from stratified_holdout import _fmt_phone, _fmt_iban, _script
from validity_realistic_set import _COUNTRIES, make_email, make_nid
SEED = 20261013
out = sys.argv[sys.argv.index("--out") + 1]; files = [a for a in sys.argv[1:] if a.endswith(".xlsx")]
if os.path.exists(os.path.join(out, "items.csv")): sys.exit("S5 already built; refusing to overwrite (freeze rule)")
rows = []
for f in files:
    for r in openpyxl.load_workbook(f).worksheets[0].iter_rows(min_row=2, values_only=True):
        if r[5] and str(r[5]).strip(): rows.append((r[0], r[1], r[2], r[3], str(r[5]).strip()))
probs = []; seen = set()
for rid, kind, ty, lang, text in rows:
    slot = "{ID}" if kind == "positive" else "{NUM}"
    if text.count(slot) != 1 or ("{ID}" in text and "{NUM}" in text): probs.append((rid, "slot count"))
    if text in seen: probs.append((rid, "duplicate"))
    seen.add(text)
    rest = text.replace(slot, "")
    if kind == "positive" and (re.search(r"\d{4,}|@", rest)): probs.append((rid, "extra identifier-like content"))
if probs: sys.exit("PROBLEMS (ask the contributor): " + str(probs))
rng = random.Random(SEED); ccs = list(_COUNTRIES); items = []; gold = []
pv = ["e164", "spaced", "hyphen", "dots", "zero_zero", "parens"]
def digs(n): return "".join(rng.choice("0123456789") for _ in range(n))
for k, (rid, kind, ty, lang, text) in enumerate(rows):
    if kind == "positive":
        script = "western" if k % 5 else rng.choice(["arabic_indic", "ext_arabic_indic", "fullwidth"])
        if ty == "PHONE": v = _script(_fmt_phone(rng, ccs[k % 7], pv[k % 6]), "" if script == "western" else script)
        elif ty == "IBAN": v = _fmt_iban(rng, ccs[k % 7], ["upper", "lower", "grouped"][k % 3]); script = "western"
        elif ty == "EMAIL": v = make_email(rng); script = "western"
        else: v = _script(make_nid(rng), "" if script == "western" else script)
        s = text.index("{ID}"); full = text.replace("{ID}", v); items.append((rid, full, ty, lang, script)); gold.append((rid, s, s + len(v), ty))
    else:
        full = text.replace("{NUM}", digs(rng.choice([3, 4, 6, 9, 10]))); items.append((rid, full, "NEGATIVE", lang, "western"))
os.makedirs(out, exist_ok=True)
with open(os.path.join(out, "items.csv"), "w", newline="", encoding="utf8") as f:
    w = csv.writer(f); w.writerow(["sentence_id", "text", "type", "language", "script"]); w.writerows(items)
with open(os.path.join(out, "gold.csv"), "w", newline="", encoding="utf8") as f:
    w = csv.writer(f); w.writerow(["sentence_id", "start", "end", "label"]); w.writerows(gold)
h = hashlib.sha256(open(os.path.join(out, "items.csv"), "rb").read() + open(os.path.join(out, "gold.csv"), "rb").read()).hexdigest()
open(os.path.join(out, "SHA256.txt"), "w").write(h + "\n"); print(len(items), "items,", len(gold), "gold spans, sha", h[:16])
