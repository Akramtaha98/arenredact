"""Second frozen stratified set "S4" (round-2 follow-up).

Written after the R3 detector and the Presidio control configurations were
frozen, with NEW templates (chat messages, form fields, table rows, Arabic
free text, first-person statements), a new seed, new negative types, and
natural phrasings of the identity keyword that were written WITHOUT consulting
the detector's keyword list. Scored once; no change to any system was made
afterwards. Same honest status as S3: written by the detector's authors with
generative-AI assistance, so it is a second frozen stratified test and NOT an
independent annotated benchmark."""
from __future__ import annotations
import random
from stratified_holdout import _fmt_phone, _fmt_iban, _script
from validity_realistic_set import _COUNTRIES, make_email, make_nid

SEED = 20261009
PHONE_T = {
    "english": ["WhatsApp me on {v} if the delivery is late.", "Mobile: {v}", "| Contact | {v} | after 5pm |", "She gave her number as {v} and hung up."],
    "arabic": ["تواصل معي على الرقم {v} في أي وقت.", "الجوال: {v}", "هاتفه {v} وهو متاح يوميًا."],
    "code_mixed": ["ابعت لي message على {v} please.", "Customer mobile (جوال): {v}"],
}
IBAN_T = {
    "english": ["Beneficiary IBAN: {v}", "Please wire the deposit to {v} before Sunday.", "| IBAN | {v} |"],
    "arabic": ["حوّل المبلغ على {v} من فضلك.", "الآيبان: {v}"],
    "code_mixed": ["الحساب البنكي IBAN {v} للمستفيد."],
}
EMAIL_T = {
    "english": ["Email: {v}", "cc {v} on the thread.", "Send the invoice to {v}, thanks."],
    "arabic": ["البريد الإلكتروني: {v}", "راسلونا عبر {v} لأي استفسار."],
    "code_mixed": ["ارسل الـ report إلى {v} اليوم."],
}
NID_T = {
    "english": ["Resident ID: {v}", "Citizen ID {v} was found in the registry.", "ID number {v} belongs to the account holder.", "Please confirm iqama no. {v} before travel."],
    "arabic": ["رقم المقيم {v} منتهي.", "السجل المدني رقم {v}", "هويته الوطنية رقم {v} مسجلة لدينا.", "رقم بطاقة الأحوال {v}"],
    "code_mixed": ["العميل صاحب الـ national ID {v} اتصل اليوم.", "رقم الـ iqama {v} لازم يتجدد."],
}
NEG = [
    "Shipment {n10} cleared customs on Tuesday.", "Seat {n3}{L} on flight SV{n3} departs at 18:45.", "Total due: {n4}.50 SAR.",
    "Meeting room 4B, floor {n2}, building {n3}.", "Tracking ID {n10} was updated at 09:12.", "Case file {n9} has been archived.",
    "The warehouse holds {n10} units of stock.", "Page {n3} of {n4} was scanned.", "Order #{n9} contains 3 items.",
    "Latitude 24.{n4}, longitude 46.{n4}.", "Invoice INV-{n6} was approved by finance.", "Phone support is open 08:00-16:00 daily.",
    "رقم الطلب {n10} قيد المعالجة.", "رقم التذكرة {n9} تم إغلاقه.", "الإجمالي {n4} ريال سعودي شامل الضريبة.",
    "الشحنة {n10} وصلت إلى المستودع.", "عدد المشاهدات هو {n10} حتى الآن.", "الاجتماع في الطابق {n2} الساعة 10:30.",
    "Please keep your identity documents ready; counter {n3} is open.", "Identity checks were completed for {n3} visitors.",
    "National holiday dates: 2026-09-23 and 2026-09-24.", "ISBN 978-1-4028-9462-6 is out of print.",
]

def build():
    rng = random.Random(SEED); cases, meta = [], []
    ccs = list(_COUNTRIES); langs = ["english", "arabic", "code_mixed"]
    def add(t, v, ty, **m):
        text = t.format(v=v); s = text.index(v); cases.append((text, [(s, s + len(v), ty)])); meta.append({"type": ty, **m})
    pv = ["e164", "spaced", "hyphen", "dots", "zero_zero", "parens"]
    for i in range(60):
        cc, var, lang = ccs[(i * 3) % 7], pv[i % 6], langs[(i // 2) % 3]
        script = "western" if i % 5 else rng.choice(["arabic_indic", "ext_arabic_indic", "fullwidth"])
        v = _script(_fmt_phone(rng, cc, var), "" if script == "western" else script)
        add(rng.choice(PHONE_T[lang]), v, "PHONE", country=cc, format=var, script=script, context=lang)
    for i in range(42):
        cc, var, lang = ccs[(i * 2) % 7], ["upper", "lower", "grouped"][i % 3], langs[i % 3]
        add(rng.choice(IBAN_T[lang]), _fmt_iban(rng, cc, var), "IBAN", country=cc, format=var, script="western", context=lang)
    for i in range(36):
        lang = langs[i % 3]; e = make_email(rng)
        if i % 4 == 1: e = e.replace("@", ".x@", 1)
        add(rng.choice(EMAIL_T[lang]), e, "EMAIL", country="n/a", format="plain", script="western", context=lang)
    for i in range(60):
        lang = langs[i % 3]; t = rng.choice(NID_T[lang])
        script = "western" if i % 4 else rng.choice(["arabic_indic", "ext_arabic_indic", "fullwidth"])
        v = _script(make_nid(rng), "" if script == "western" else script)
        add(t, v, "NATIONAL_ID", country=ccs[i % 7], format=t.split("{v}")[0].strip()[:20] or "bare", script=script, context=lang)
    def digs(n): return "".join(rng.choice("0123456789") for _ in range(n))
    for i in range(100):
        t = NEG[i % len(NEG)]
        cases.append((t.format(n2=digs(2), n3=digs(3), n4=digs(4), n6=digs(6), n9=digs(9), n10=digs(10), L=rng.choice("ABCDEF")), []))
        meta.append({"type": "NEGATIVE"})
    return cases, meta

CASES, META = build()
if __name__ == "__main__":
    from collections import Counter
    print(len(CASES), Counter(m["type"] for m in META))
    for c, m in list(zip(CASES, META))[::45]: print(c, m)
