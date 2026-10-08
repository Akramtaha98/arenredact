"""Sanity tests for the validity-realistic comparison set and the attack
operators' effect on structured identifiers (supports Section 6.2 audit)."""

import random

import pytest

phonenumbers = pytest.importorskip("phonenumbers")

import sys, os  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import validity_realistic_set as vr  # noqa: E402

from arenredact.attacks.operators import apply_homoglyph_substitution  # noqa: E402
from arenredact.pattern_engine import PatternEngine  # noqa: E402
from arenredact.preprocessing import normalize  # noqa: E402


def _mod97_valid(iban: str) -> bool:
    r = iban[4:] + iban[:4]
    return int("".join(str(int(c, 36)) for c in r)) % 97 == 1


def test_all_generated_ibans_are_checksum_valid():
    for text, gold in vr.CASES:
        for s, e, t in gold:
            if t == "IBAN":
                assert _mod97_valid(text[s:e])


def test_all_generated_phones_are_libphonenumber_valid():
    for text, gold in vr.CASES:
        for s, e, t in gold:
            if t == "PHONE":
                assert phonenumbers.is_valid_number(phonenumbers.parse(text[s:e], None))


def test_full_homoglyph_attack_changes_every_phone_and_stage1_restores_detection():
    engine = PatternEngine()
    for text, gold in vr.CASES:
        for s, e, t in gold:
            if t != "PHONE":
                continue
            attacked = apply_homoglyph_substitution(text, [(s, e)], budget=1.0, rng=random.Random(0))
            assert attacked[s:e] != text[s:e]
            assert (s, e, "PHONE") in {(x.start, x.end, x.entity_type) for x in engine.detect(normalize(attacked))}
            assert (s, e, "PHONE") not in {(x.start, x.end, x.entity_type) for x in engine.detect(attacked)}
