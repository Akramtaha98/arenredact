"""Synthetic code-mixed Arabic-English PII corpus generator (Section 5.1).

Generates sentences containing annotated PII entities via three augmentation
strategies:

1. Intra-sentential entity substitution — Arabic/English entity swaps at a
   configurable probability (paper default: 40%).
2. Discourse marker injection — English connectors spliced into Arabic
   sentence frames (paper default: 25% rate).
3. Arabizi transliteration — applied to a configurable fraction of Arabic
   entity instances using the Da3i mapping (paper default: 30%).

This generator produces entirely synthetic entities (fictitious names,
algorithmically-valid-but-fake phone/IBAN numbers) — no real PII is
generated or required. Output is JSONL, one record per line:

    {"text": "...", "entities": [{"start": 0, "end": 8, "entity_type": "PERSON"}, ...]}
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass

from arenredact.attacks.operators import arabizi_substitution
from arenredact.data.lexicons import KUNYA_PREFIXES, MENA_COUNTRY_CODES, NISBAH_SUFFIXES

# Fictitious given names for entity generation (Arabic + transliterated English form).
_ARABIC_GIVEN_NAMES = ["محمد", "أحمد", "علي", "فاطمة", "سارة", "خالد", "نورة", "عبدالله", "مريم", "يوسف"]
_ENGLISH_GIVEN_NAMES = ["Mohamed", "Ahmed", "Ali", "Fatima", "Sara", "Khaled", "Noura", "Abdullah", "Mariam", "Yousef"]

_ORG_NAMES_AR = ["شركة الاتصالات السعودية", "بنك الرياض", "مؤسسة الخليج للتقنية"]
_ORG_NAMES_EN = ["Saudi Telecom Company", "Riyadh Bank", "Gulf Tech Foundation"]

_LOCATIONS_AR = ["الرياض", "جدة", "دبي", "بغداد", "عمّان", "الكويت"]
_LOCATIONS_EN = ["Riyadh", "Jeddah", "Dubai", "Baghdad", "Amman", "Kuwait City"]

# English discourse connectors spliced into Arabic frames (augmentation strategy 2).
_DISCOURSE_MARKERS = ["by the way", "actually", "for example", "so", "anyway", "you know"]

_ARABIC_SENTENCE_TEMPLATES = [
    "تواصل مع {person} على الرقم {phone} بخصوص الحجز.",
    "الرجاء إرسال البيانات إلى {email} في أقرب وقت.",
    "قام {person} بتحويل المبلغ إلى الحساب {iban}.",
    "يعمل {person} في {org} بمدينة {location}.",
    "رقم الهوية الوطنية الخاص بـ {person} هو {national_id}.",
]


@dataclass
class GeneratedEntity:
    start: int
    end: int
    entity_type: str


@dataclass
class GeneratedRecord:
    text: str
    entities: list[GeneratedEntity]


def _fake_phone(rng: random.Random) -> str:
    code = rng.choice(list(MENA_COUNTRY_CODES.keys()))
    digits = "".join(str(rng.randint(0, 9)) for _ in range(9))
    return f"{code}{digits}"


def _fake_national_id(rng: random.Random) -> str:
    return "".join(str(rng.randint(0, 9)) for _ in range(10))


def _fake_iban(rng: random.Random, prefix: str = "SA", length: int = 22) -> str:
    return prefix + "".join(str(rng.randint(0, 9)) for _ in range(length))


def _fake_email(name_en: str, rng: random.Random) -> str:
    domain = rng.choice(["example.com", "mail.test", "corp-demo.net"])
    return f"{name_en.lower()}{rng.randint(1, 999)}@{domain}"


def _person_with_quasi_identifiers(rng: random.Random, arabic: bool) -> str:
    """Occasionally attach a kunya prefix or nisbah suffix, matching the
    quasi-identifier expansion surface that Stage 4 (Algorithm 1) targets."""
    idx = rng.randrange(len(_ARABIC_GIVEN_NAMES))
    name = _ARABIC_GIVEN_NAMES[idx] if arabic else _ENGLISH_GIVEN_NAMES[idx]
    if arabic and rng.random() < 0.3:
        name = f"{rng.choice(KUNYA_PREFIXES)} {name}"
    if arabic and rng.random() < 0.3:
        name = f"{name} {rng.choice(NISBAH_SUFFIXES)}"
    return name


def generate_record(rng: random.Random, arabizi_rate: float = 0.30) -> GeneratedRecord:
    """Generate one synthetic sentence with annotated entity spans, applying
    the three augmentation strategies from Section 5.1."""
    template = rng.choice(_ARABIC_SENTENCE_TEMPLATES)

    # Strategy 1: intra-sentential entity substitution (Arabic<->English, 40%).
    use_arabic_entities = rng.random() > 0.40
    idx = rng.randrange(len(_ARABIC_GIVEN_NAMES))
    person = _person_with_quasi_identifiers(rng, arabic=use_arabic_entities)

    # Strategy 3: Arabizi transliteration applied to a fraction of Arabic entities.
    if use_arabic_entities and rng.random() < arabizi_rate:
        person = arabizi_substitution(person, rng=rng)

    org = _ORG_NAMES_AR[0] if use_arabic_entities else _ORG_NAMES_EN[0]
    location = rng.choice(_LOCATIONS_AR if use_arabic_entities else _LOCATIONS_EN)

    fill_values = {
        "person": person,
        "phone": _fake_phone(rng),
        "email": _fake_email(_ENGLISH_GIVEN_NAMES[idx], rng),
        "iban": _fake_iban(rng),
        "org": org,
        "location": location,
        "national_id": _fake_national_id(rng),
    }

    # Build text and track entity offsets by locating each placeholder's
    # rendered value as we substitute left-to-right.
    text = template
    entities: list[GeneratedEntity] = []
    entity_type_map = {
        "person": "PERSON", "phone": "PHONE", "email": "EMAIL", "iban": "IBAN",
        "org": "ORGANIZATION", "location": "LOCATION", "national_id": "NATIONAL_ID",
    }
    for key, value in fill_values.items():
        placeholder = "{" + key + "}"
        if placeholder not in text:
            continue
        start = text.index(placeholder)
        text = text.replace(placeholder, value, 1)
        entities.append(GeneratedEntity(start=start, end=start + len(value), entity_type=entity_type_map[key]))

    # Strategy 2: discourse marker injection (English connector into Arabic frame, 25%).
    if use_arabic_entities and rng.random() < 0.25:
        marker = rng.choice(_DISCOURSE_MARKERS)
        insertion_point = len(text)
        text = f"{text} {marker}."
        # No entity at the marker itself; offsets before it are unaffected
        # since we append at the end.
        _ = insertion_point

    entities.sort(key=lambda e: e.start)
    return GeneratedRecord(text=text, entities=entities)


def generate_corpus(n_sentences: int, seed: int = 42, arabizi_rate: float = 0.30) -> list[GeneratedRecord]:
    rng = random.Random(seed)
    return [generate_record(rng, arabizi_rate=arabizi_rate) for _ in range(n_sentences)]


def write_jsonl(records: list[GeneratedRecord], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(
                json.dumps(
                    {
                        "text": rec.text,
                        "entities": [
                            {"start": e.start, "end": e.end, "entity_type": e.entity_type}
                            for e in rec.entities
                        ],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="Output JSONL path.")
    parser.add_argument("--n-sentences", type=int, default=8970,
                         help="Number of sentences to generate (paper default: 8970).")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--arabizi-rate", type=float, default=0.30)
    args = parser.parse_args(argv)

    records = generate_corpus(args.n_sentences, seed=args.seed, arabizi_rate=args.arabizi_rate)
    write_jsonl(records, args.out)
    print(f"Wrote {len(records)} synthetic records to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
