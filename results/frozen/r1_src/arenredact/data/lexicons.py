"""Static lexicons used by the pattern engine (Stage 3) and span fusion (Stage 4):
MENA country calling codes, Arabic kunya/nisbah/laqab quasi-identifier
components (Section 4.4), and the Da3i Arabizi phoneme-to-Latin mapping
(Darwish, 2014) used by the ARZ adversarial attack operator.
"""

from __future__ import annotations

# International calling codes for the countries named in Section 4.3.
MENA_COUNTRY_CODES: dict[str, str] = {
    "+966": "SA",  # Saudi Arabia
    "+971": "AE",  # UAE
    "+20": "EG",  # Egypt
    "+964": "IQ",  # Iraq
    "+962": "JO",  # Jordan
    "+965": "KW",  # Kuwait
    "+973": "BH",  # Bahrain
}

# IBAN prefixes and total digit lengths for MENA countries whose real IBAN
# body (everything after the 2-letter country code) is entirely numeric
# (Section 4.3).
MENA_IBAN_DIGIT_LENGTHS: dict[str, int] = {
    "SA": 22,  # SA + 2-digit check + 20-digit bank/account, all numeric
    "AE": 21,  # AE + 2-digit check + 19-digit bank/account, all numeric
    "EG": 27,  # EG + 2-digit check + 25-digit bank/branch/account, all numeric
}

# IBAN prefixes for MENA countries whose real IBAN structure embeds a
# 4-LETTER bank code between the 2-digit check digits and the numeric
# account segment (registry-published formats). An all-digit pattern
# systematically misses every real IBAN from these countries — this is the
# concrete limitation the independent noisy challenge set (Section 6.1)
# surfaced for Bahrain; the same structural issue affects Iraq, Jordan, and
# Kuwait, so all four get the letter-aware pattern.
# Format: prefix -> number of digits in the account segment AFTER the
# 4-letter bank code.
MENA_IBAN_LETTER_BANK_ACCOUNT_DIGITS: dict[str, int] = {
    "BH": 14,  # BH + 2-digit check + 4-letter bank + 14-char account
    "IQ": 15,  # IQ + 2-digit check + 4-letter bank + 15-digit branch/account
    "JO": 22,  # JO + 2-digit check + 4-letter bank + 22-char branch/account
    "KW": 22,  # KW + 2-digit check + 4-letter bank + 22-char account
}

# Kunya (teknonymic prefixes: "father of" / "mother of").
KUNYA_PREFIXES: tuple[str, ...] = (
    "أبو",
    "ابو",
    "أم",
    "ام",
)

# Representative nisbah (tribal / geographic nationhood suffixes). Not
# exhaustive — extend this list from a validated gazetteer before production
# use; see Section 8.3 (Threats to Validity, external validity) regarding
# generalization beyond the dialects represented in the training mixture.
NISBAH_SUFFIXES: tuple[str, ...] = (
    "الدوسري",
    "العتيبي",
    "القحطاني",
    "الحربي",
    "الشمري",
    "المطيري",
    "الغامدي",
    "الزهراني",
    "العنزي",
    "السبيعي",
)

# Representative laqab (honorific / nickname components).
LAQAB_HONORIFICS: tuple[str, ...] = (
    "الحاج",
    "الشيخ",
    "الأستاذ",
    "الدكتور",
    "المهندس",
)

#: Union of all quasi-identifier expansion trigger tokens (Algorithm 1, line 9).
QUASI_IDENTIFIER_LEXICON: frozenset[str] = frozenset(
    KUNYA_PREFIXES + NISBAH_SUFFIXES + LAQAB_HONORIFICS
)

# Da3i phoneme -> Latin/digit surrogate mapping (Darwish, 2014), used by the
# ARZ (Arabizi Substitution) adversarial attack operator. Not exhaustive —
# covers the phonemes most commonly transliterated informally.
DA3I_MAPPING: dict[str, str] = {
    "ء": "2",
    "ع": "3",
    "ح": "7",
    "خ": "5",  # or "kh"
    "ص": "9",
    "ض": "9'",
    "ط": "6",
    "ظ": "6'",
    "ق": "8",  # or "2" in some dialects
    "غ": "3'",  # or "gh"
    "ث": "th",
    "ذ": "th",  # or "z"
    "ش": "sh",
    "ة": "a",
}
