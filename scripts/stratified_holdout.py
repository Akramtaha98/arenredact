"""Stratified frozen holdout "S3" (revision 2).

Written after the revision-2 detector was frozen (the SHA-256 of the package
is recorded in results/stratified_holdout.json) and scored once. Positives
are balanced over identifier type, country, digit script, format variant and
context language; negatives are ordinary text with confusing digit strings.
Identifiers are algorithmically generated (IBAN mod-97 valid, phone numbers
valid under libphonenumber), so a validating comparison system is not
penalised for rejecting fakes.

Honest status: this set is written by the detector's authors with
generative-AI assistance. It is a frozen, stratified, held-back test, NOT an
independent annotated benchmark. Independent bilingual annotation is
specified in annotation/ and has not been performed.
"""

from __future__ import annotations

import random

import phonenumbers

from validity_realistic_set import _COUNTRIES, _NATIONAL_LEN, make_email, make_iban, make_nid

SEED = 20261008
AR = "٠١٢٣٤٥٦٧٨٩"
EXT = "۰۱۲۳۴۵۶۷۸۹"
FW = "".join(chr(0xFF10 + i) for i in range(10))


def _script(s: str, kind: str) -> str:
    tab = {"arabic_indic": AR, "ext_arabic_indic": EXT, "fullwidth": FW}.get(kind)
    return s.translate(str.maketrans("0123456789", tab)) if tab else s


PHONE_T = {
    "english": ["Please ring the front desk on {v} before noon.", "My new mobile is {v}, save it.",
                "You can reach the branch manager at {v} until Thursday."],
    "arabic": ["للتواصل اتصل على {v} مساءً.",
               "رقم جوالي الجديد {v} من فضلك."],
    "code_mixed": ["اتصل بالمندوب on {v} لو التوصيل تأخر.",
                   "Call me على {v} ASAP لو سمحت."],
}
IBAN_T = {
    "english": ["Kindly settle the invoice by transfer to {v} this week.", "Refund will be sent to the account {v}."],
    "arabic": ["يرجى التحويل إلى الحساب {v} قبل نهاية الشهر.",
               "رقم الآيبان هو {v} للمستفيد."],
    "code_mixed": ["حول المبلغ to {v} بعد التأكيد."],
}
EMAIL_T = {
    "english": ["Forward the signed contract to {v} when ready.", "Questions? Write to {v} and we will reply."],
    "arabic": ["أرسل الملف إلى {v} من فضلك.", "بريدي الإلكتروني هو {v} للمراسلة."],
    "code_mixed": ["راسلني on {v} لأي استفسار."],
}
NID_T = {  # (template, keyword class)
    "english": [("Applicant national ID {v} has been verified.", "national id"),
                ("The Iqama number {v} expires next month.", "iqama"),
                ("Civil ID: {v} was used at registration.", "civil id"),
                ("Record {v} (civil ID) was matched to the file.", "after")],
    "arabic": [("رقم الهوية الوطنية {v} مسجل لدينا.", "hawiya"),
               ("رقم الإقامة {v} ساري حتى العام القادم.", "iqama_ar"),
               ("رقمه القومي {v} موجود في السجل.", "qawmi")],
    "code_mixed": [("تم التحقق من national ID {v} اليوم.", "national id"),
                   ("العميل صاحب الهوية {v} طلب تحديث.", "hawiya")],
}

NEGATIVES = [
    "Order {n10} left the warehouse on Monday.", "Invoice total was 1,250.75 SAR including VAT.",
    "The conference runs from 2026-03-14 to 2026-03-16 in Riyadh.", "Tracking number {n10} shows the parcel in transit.",
    "Server 192.168.10.45 restarted at 03:15.", "The firmware version is 4.12.7 build 20260314.",
    "Reference {n9} was assigned to the ticket.", "Batch {n11} contains 3,000 units.",
    "الطلب رقم {n10} تم شحنه أمس.",
    "المبلغ الإجمالي 4500 ريال شامل الضريبة.",
    "الاجتماع يوم 14/03/2026 الساعة 10:30.",
    "رقم الشحنة {n10} قيد التوصيل.",
    "ISBN 978-3-16-148410-0 is listed in the catalogue.", "The coordinates 24.7136, 46.6753 mark the site.",
    "The identity of the sender remains unknown; {n10} messages were blocked.",
    "National statistics show {n10} transactions were processed last year.",
    "Document ID {n9} is nine digits and not a national ID.", "SA{n20} is not a valid-length IBAN.",
    "Please keep extension 4421 for internal calls.", "Use promo code SAVE{n4} at checkout.",
    "The population was estimated at {n10} in the 2022 census.", "Ticket {n10} escalated; identity verification pending.",
    "التحقق من الهوية مطلوب قبل الدخول.",
]


def _fmt_phone(rng, cc, variant):
    spec = _COUNTRIES[cc]
    for _ in range(3000):
        pre = rng.choice(spec["mob"])
        rest = "".join(rng.choice("0123456789") for _ in range(_NATIONAL_LEN[cc] - len(pre)))
        digits = pre + rest
        num = phonenumbers.parse(spec["cc"] + digits, None)
        if phonenumbers.is_valid_number(num):
            break
    e164 = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
    intl = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
    if variant == "e164": return e164
    if variant == "spaced": return intl
    if variant == "hyphen": return intl.replace(" ", "-")
    if variant == "dots": return intl.replace(" ", ".")
    if variant == "zero_zero": return "00" + e164[1:]
    if variant == "parens":
        ccs = spec["cc"]; nat = digits
        return f"{ccs} ({nat[:2]}) {nat[2:5]} {nat[5:]}"
    raise ValueError(variant)


def _fmt_iban(rng, cc, variant):
    iban = make_iban(rng, cc)
    if variant == "upper": return iban
    if variant == "lower": return iban.lower()
    if variant == "grouped": return " ".join(iban[i:i + 4] for i in range(0, len(iban), 4))
    raise ValueError(variant)


def build():
    rng = random.Random(SEED)
    cases, meta = [], []
    ccs = list(_COUNTRIES)
    langs = ["english", "arabic", "code_mixed"]

    def add(text_t, value, etype, **m):
        text = text_t.format(v=value)
        s = text.index(value)
        cases.append((text, [(s, s + len(value), etype)]))
        meta.append({"type": etype, **m})

    # PHONE: 7 countries x 6 formats x ~2 = 84 -> keep 70 via rotation
    pv = ["e164", "spaced", "hyphen", "dots", "zero_zero", "parens"]
    for i in range(70):
        cc, var, lang = ccs[i % 7], pv[i % 6], langs[i % 3]
        script = "western" if i % 5 else rng.choice(["arabic_indic", "ext_arabic_indic", "fullwidth"])
        v = _script(_fmt_phone(rng, cc, var), script if script != "western" else "")
        add(rng.choice(PHONE_T[lang]), v, "PHONE", country=cc, format=var, script=script, context=lang)
    iv = ["upper", "lower", "grouped"]
    for i in range(56):
        cc, var, lang = ccs[i % 7], iv[i % 3], langs[i % 3]
        add(rng.choice(IBAN_T[lang]), _fmt_iban(rng, cc, var), "IBAN", country=cc, format=var, script="western", context=lang)
    for i in range(42):
        lang = langs[i % 3]
        e = make_email(rng)
        if i % 4 == 1: e = e.replace("@", "+tag@", 1)
        if i % 4 == 2: e = e.upper().replace("@", "@", 1) if False else e
        add(rng.choice(EMAIL_T[lang]), e, "EMAIL", country="n/a", format="plain" if i % 4 != 1 else "plus_tag", script="western", context=lang)
    for i in range(70):
        lang = ["english", "arabic", "code_mixed"][i % 3]
        t, kw = rng.choice(NID_T[lang])
        script = "western" if i % 4 else rng.choice(["arabic_indic", "ext_arabic_indic", "fullwidth"])
        v = _script(make_nid(rng), script if script != "western" else "")
        add(t, v, "NATIONAL_ID", country=ccs[i % 7], format=kw, script=script, context=lang)
    # NEGATIVES
    for i in range(110):
        t = NEGATIVES[i % len(NEGATIVES)]
        f = {"n10": "".join(rng.choice("0123456789") for _ in range(10)),
             "n9": "".join(rng.choice("0123456789") for _ in range(9)),
             "n11": "".join(rng.choice("0123456789") for _ in range(11)),
             "n20": "".join(rng.choice("0123456789") for _ in range(20)),
             "n4": "".join(rng.choice("0123456789") for _ in range(4))}
        cases.append((t.format(**f), []))
        meta.append({"type": "NEGATIVE"})
    return cases, meta


CASES, META = build()

if __name__ == "__main__":
    from collections import Counter
    print(len(CASES), Counter(m["type"] for m in META))
    for c, m in list(zip(CASES, META))[::40]:
        print(c, m)
