"""Builds the blind annotation set (set "S5") and the authors-only key.

Run ONCE, before anyone runs any detector on it:
  python annotation/build_annotation_set.py --out ../annotation_package --private ../annotation_PRIVATE_authors_only
Outputs
  <out>/items.csv            item_id,text            (what annotators see)
  <private>/key.csv          item_id,origin,subtype,gold_json   (NEVER shared with annotators)
Mix (shuffled, origin hidden): synthetic positives of the four types in new templates,
synthetic hard negatives (number-like text, card/passport numbers), and sentences from the
independent Wikipedia extracts (data/independent). Local phone numbers without a country
code are included as positives on purpose (annotators mark them; the detector does not cover them)."""
import argparse, csv, json, os, random, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from stratified_holdout import _fmt_phone, _fmt_iban, _script
from validity_realistic_set import _COUNTRIES, make_email, make_nid

SEED = 20261010
EN = {
 "PHONE": ["Hi Sara, the courier will call you on {v} tomorrow morning.", "Contact the pharmacy: {v} (open 9-5).", "Reach our branch on {v} for appointments.", "My number changed to {v}, please update your records.", "Emergency contact: Mr. Khalid, tel. {v}."],
 "EMAIL": ["For complaints write to {v} and quote your reference.", "Applicants should send CVs to {v} before the deadline.", "Her work address is {v}; she checks it daily.", "Subscribe by emailing {v} with the word JOIN."],
 "IBAN": ["The salary is paid into {v} on the 25th of each month.", "Transfer the registration fee to account {v} and attach the receipt.", "Our bank details: IBAN {v}, beneficiary Al-Noor Trading."],
 "NATIONAL_ID": ["The visa application lists national ID {v} for the main applicant.", "Mr. Yusuf's civil ID is {v}, issued in 2019.", "Employee file: iqama {v}, expires next year.", "Please bring the ID card number {v} to the counter."],
}
AR = {
 "PHONE": ["اتصل بالمستشفى على {v} للحجز.", "رقم هاتف المدير {v} ويمكنك مراسلته أيضًا.", "للاستفسار يرجى الاتصال بالرقم {v} خلال ساعات الدوام."],
 "EMAIL": ["يرجى إرسال الطلب إلى {v} قبل نهاية الأسبوع.", "عنوان المراسلة الخاص بالقسم هو {v}."],
 "IBAN": ["يُودع الراتب في الحساب {v} في نهاية الشهر.", "رقم الآيبان الخاص بالجمعية هو {v}."],
 "NATIONAL_ID": ["الرقم الوطني للمتقدم {v} وقد تم التحقق منه.", "رقم هوية الطالب {v} مسجل في الجامعة.", "رقم الإقامة الخاص بالموظف {v}."],
}
MIX = {
 "PHONE": ["كلمني على {v} when you land."], "EMAIL": ["بعت الملف على {v} please check."],
 "IBAN": ["الـ IBAN الخاص بي {v} حول عليه."], "NATIONAL_ID": ["الـ national ID بتاعه {v} مسجل عندنا."],
}
NEG = [
 "Order {n10} shipped on 12 March and should arrive within {n1} days.", "The report has {n3} pages and was printed in {n4} copies.",
 "Flight SV{n3} leaves from gate {n2}A at 14:05.", "The ticket number is {n9}; keep it for the refund.", "Parcel tracking code {n10} is not yet active.",
 "Population: {n10} (2020 estimate).", "Reference no. {n9} refers to the 2021 audit.", "Version 3.{n2}.{n1} was released on 2025-11-30.",
 "رقم الطلب {n10} قيد التجهيز.", "الفاتورة رقم {n6} بقيمة {n4} ريال.", "عدد الزوار بلغ {n10} زائرًا هذا العام.", "افتح الباب رقم {n2} في الطابق {n1}.",
 "Visit us at building {n3}, street {n2}, from 08:00 to 16:00.", "Card ending {n4} was charged; full number 4{n3}{n4}{n4}{n4} (do not store).",
 "Passport no. A{n8} was renewed last spring.", "Her student number is {n8}.", "The identity of the donor remains confidential; {n10} donations were received.",
 "Account balance: {n6}.75 SAR as of yesterday.", "Dial *{n3}# to check your balance.", "الشحنة {n9} وصلت إلى الميناء.",
]
def digs(r, n): return "".join(r.choice("0123456789") for _ in range(n))
def local_phone(r, cc):
    p = {"SA": "05", "AE": "05", "EG": "01", "IQ": "07", "JO": "07", "KW": "5", "BH": "3"}[cc]
    return p + digs(r, 8 if cc in ("SA", "AE", "IQ", "JO") else 7)
def sentences_from_wiki(r):
    out = {"ar": [], "en": []}
    for lang in ("ar", "en"):
        for l in open(os.path.join(os.path.dirname(__file__), "..", "data", "independent", f"wikipedia_{lang}.jsonl"), encoding="utf8"):
            d = json.loads(l)
            for s in re.split(r"(?<=[.؟!])\s+", d["text"]):
                if 25 <= len(s) <= 260: out[lang].append((s.strip(), f"{lang}.wikipedia:{d['pageid']}"))
    return out
def build():
    r = random.Random(SEED); items = []
    ccs = list(_COUNTRIES)
    def add(text, origin, subtype, gold): items.append((text, origin, subtype, gold))
    def pos(etype, n):
        for i in range(n):
            lang = ["en", "ar", "mix"][i % 3]
            pool = {"en": EN, "ar": AR, "mix": MIX}[lang][etype]; t = r.choice(pool); cc = ccs[r.randrange(7)]
            script = "western" if i % 6 else r.choice(["arabic_indic", "ext_arabic_indic", "fullwidth"])
            sub = f"{lang}|{cc}|{script}"
            if etype == "PHONE":
                if i % 7 == 3: v = local_phone(r, cc); sub += "|local"
                else: v = _fmt_phone(r, cc, r.choice(["e164", "spaced", "hyphen", "dots", "zero_zero", "parens"]))
                v = _script(v, "" if script == "western" else script)
            elif etype == "EMAIL": v = make_email(r); script = "western"; sub = f"{lang}|-|western"
            elif etype == "IBAN": v = _fmt_iban(r, cc, r.choice(["upper", "lower", "grouped"])); sub = f"{lang}|{cc}|western"
            else: v = _script(make_nid(r), "" if script == "western" else script)
            text = t.format(v=v); s = text.index(v)
            add(text, "synthetic_positive", sub + "|" + etype, [[s, s + len(v), etype]])
    for et, n in (("PHONE", 35), ("EMAIL", 25), ("IBAN", 25), ("NATIONAL_ID", 35)): pos(et, n)
    # two-identifier sentences
    for i in range(10):
        cc = ccs[r.randrange(7)]; p = _fmt_phone(r, cc, "spaced"); e = make_email(r)
        text = f"Call {p} or write to {e} to reschedule."; a = text.index(p); b = text.index(e)
        add(text, "synthetic_positive", "en|multi", [[a, a + len(p), "PHONE"], [b, b + len(e), "EMAIL"]])
    for i in range(80):
        t = NEG[i % len(NEG)]
        add(t.format(n1=digs(r, 1), n2=digs(r, 2), n3=digs(r, 3), n4=digs(r, 4), n6=digs(r, 6), n8=digs(r, 8), n9=digs(r, 9), n10=digs(r, 10)), "synthetic_negative", "number-like", [])
    wk = sentences_from_wiki(r)
    digit_s = {l: [x for x in wk[l] if re.search(r"\d{4,}", x[0])] for l in wk}
    plain = {l: [x for x in wk[l] if not re.search(r"\d", x[0])] for l in wk}
    for l, nd, npn in (("ar", 40, 20), ("en", 40, 20)):
        for x in r.sample(digit_s[l], min(nd, len(digit_s[l]))): add(x[0], "wikipedia", x[1] + "|digits", None)
        for x in r.sample(plain[l], npn): add(x[0], "wikipedia", x[1] + "|plain", None)
    r.shuffle(items)
    return items
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); ap.add_argument("--private", required=True); a = ap.parse_args()
    items = build(); os.makedirs(a.out, exist_ok=True); os.makedirs(a.private, exist_ok=True)
    with open(os.path.join(a.out, "items.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(["item_id", "text"])
        for i, it in enumerate(items): w.writerow([f"I{i+1:03d}", it[0]])
    with open(os.path.join(a.private, "key.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(["item_id", "origin", "subtype", "gold_json"])
        for i, it in enumerate(items): w.writerow([f"I{i+1:03d}", it[1], it[2], json.dumps(it[3])])
    from collections import Counter
    print(len(items), Counter(it[1] for it in items))
if __name__ == "__main__": main()
