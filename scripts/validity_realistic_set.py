"""Validity-realistic comparison set (used for the external-baseline comparison).

Why this set exists: the synthetic corpus and the challenge sets use fake
identifiers that are format-correct but NOT checksum-valid (IBAN mod-97) or
numbering-plan-valid (libphonenumber). Validation-based detectors such as
Microsoft Presidio correctly reject such strings, so scoring them on
format-only fakes would be an unfair (strawman) comparison. This set
therefore generates identifiers that pass the same validators a real
deployment would face:

  * IBANs with correct ISO 13616 mod-97 check digits for SA, AE, EG, BH, IQ,
    JO and KW (letter bank codes for BH/IQ/JO/KW, as in the real structures);
  * phone numbers accepted by `phonenumbers.is_valid_number` for the same
    seven countries, written in E.164 or international spaced format;
  * e-mail addresses on public-looking domains;
  * 10-digit national IDs with an identity-context phrase (English/Arabic).

All values are produced from a fixed seed, so the set is reproducible. The
identifiers are algorithmically generated and may coincide with real ones by
chance; they are not drawn from any real person's data. This set was written
after all pattern-engine changes were frozen and was scored once; results
are reported as first-run numbers.
"""

from __future__ import annotations

import random

import phonenumbers

_SEED = 2026

# country -> (iban prefix, bank-code kind, BBAN length excluding bank letters,
#             phone region, mobile prefixes)
_COUNTRIES = {
    "SA": dict(iban="SA", letters=0, bban_digits=22 - 2 + 0, region="SA", mob=["50", "53", "55", "56", "59"], cc="+966"),
    "AE": dict(iban="AE", letters=0, bban_digits=19, region="AE", mob=["50", "52", "54", "55", "56"], cc="+971"),
    "EG": dict(iban="EG", letters=0, bban_digits=25, region="EG", mob=["10", "11", "12", "15"], cc="+20"),
    "BH": dict(iban="BH", letters=4, acct_alnum=14, region="BH", mob=["36", "37", "38", "39"], cc="+973"),
    "IQ": dict(iban="IQ", letters=4, acct_digits=15, region="IQ", mob=["770", "771", "750", "780"], cc="+964"),
    "JO": dict(iban="JO", letters=4, acct_digits=22, region="JO", mob=["79", "78", "77"], cc="+962"),
    "KW": dict(iban="KW", letters=4, acct_alnum=22, region="KW", mob=["50", "51", "55", "60", "65"], cc="+965"),
}
_NATIONAL_LEN = {"SA": 9, "AE": 9, "EG": 10, "BH": 8, "IQ": 10, "JO": 9, "KW": 8}
_BANK_LETTERS = ["BMAG", "RAFB", "NBOK", "CBJO", "ARAB", "NBOB", "BBME", "CIBE"]


def _iban_check_digits(country: str, bban: str) -> str:
    rearranged = bban + country + "00"
    numeric = "".join(str(int(c, 36)) for c in rearranged)
    return f"{98 - (int(numeric) % 97):02d}"


def make_iban(rng: random.Random, cc: str) -> str:
    spec = _COUNTRIES[cc]
    if spec["letters"] == 0:
        if cc == "SA":
            bban = "".join(rng.choice("0123456789") for _ in range(20))
            # SA total length 24 => 2 check digits + 20-digit BBAN
        elif cc == "AE":
            bban = "".join(rng.choice("0123456789") for _ in range(19))
        else:  # EG: 25 digits BBAN (total 29)
            bban = "".join(rng.choice("0123456789") for _ in range(25))
    else:
        letters = rng.choice(_BANK_LETTERS)
        if "acct_digits" in spec:
            tail = "".join(rng.choice("0123456789") for _ in range(spec["acct_digits"]))
        else:
            tail = "".join(rng.choice("0123456789") for _ in range(spec["acct_alnum"]))
        bban = letters + tail
    return cc + _iban_check_digits(cc, bban) + bban


def make_phone(rng: random.Random, cc: str, spaced: bool) -> str:
    spec = _COUNTRIES[cc]
    for _ in range(2000):
        prefix = rng.choice(spec["mob"])
        rest_len = _NATIONAL_LEN[cc] - len(prefix)
        digits = prefix + "".join(rng.choice("0123456789") for _ in range(rest_len))
        try:
            num = phonenumbers.parse(spec["cc"] + digits, None)
        except phonenumbers.NumberParseException:
            continue
        if phonenumbers.is_valid_number(num):
            fmt = phonenumbers.PhoneNumberFormat.INTERNATIONAL if spaced else phonenumbers.PhoneNumberFormat.E164
            return phonenumbers.format_number(num, fmt)
    raise RuntimeError(f"no valid number for {cc}")


_NAMES = ["ahmed", "fatima", "yousef", "layla", "omar", "noor", "hassan", "mariam"]
_DOMAINS = ["gmail.com", "outlook.com", "yahoo.com", "company.com", "uotechnology.edu.iq"]


def make_email(rng: random.Random) -> str:
    return f"{rng.choice(_NAMES)}.{rng.choice(_NAMES)}{rng.randint(1, 99)}@{rng.choice(_DOMAINS)}"


def make_nid(rng: random.Random) -> str:
    return rng.choice("12") + "".join(rng.choice("0123456789") for _ in range(9))


_TEMPLATES = {
    "PHONE": [
        "Please call me on {v} after the meeting.",
        "رقم التواصل الجديد هو {v} فاحفظه عندك.",
        "Reach the finance team at {v} before Thursday.",
    ],
    "IBAN": [
        "Transfer the amount to IBAN {v} today.",
        "حوّل المبلغ إلى الحساب {v} من فضلك.",
        "The supplier's account is {v}, please confirm.",
    ],
    "EMAIL": [
        "Send the signed form to {v} by Friday.",
        "راسلني على {v} إذا احتجت أي شيء.",
        "Contact: {v} (reply within 24 hours).",
    ],
    "NATIONAL_ID": [
        "The applicant's national ID: {v} was verified.",
        "رقم الهوية الوطنية {v} مسجل في النظام.",
        "Iqama number {v} must be renewed this month.",
    ],
}


def _build():
    rng = random.Random(_SEED)
    cases = []
    ccs = list(_COUNTRIES)
    for i in range(7 * 4):  # 28 sentences per type
        cc = ccs[i % 7]
        # PHONE
        v = make_phone(rng, cc, spaced=(i % 2 == 0))
        cases.append((rng.choice(_TEMPLATES["PHONE"]), "PHONE", v))
        # IBAN
        v = make_iban(rng, cc)
        cases.append((rng.choice(_TEMPLATES["IBAN"]), "IBAN", v))
        # EMAIL
        cases.append((rng.choice(_TEMPLATES["EMAIL"]), "EMAIL", make_email(rng)))
        # NATIONAL_ID
        cases.append((rng.choice(_TEMPLATES["NATIONAL_ID"]), "NATIONAL_ID", make_nid(rng)))
    out = []
    for tpl, etype, value in cases:
        text = tpl.format(v=value)
        start = text.index(value)
        out.append((text, [(start, start + len(value), etype)]))
    return out


CASES = _build()

if __name__ == "__main__":
    print(len(CASES), "cases")
    for t, g in CASES[:8]:
        print(t, g)
