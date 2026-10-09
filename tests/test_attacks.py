"""Tests for adversarial attack operators (Section 3.5 / 5.2)."""

import random

from arenredact.attacks.operators import (
    apply_combined_attack,
    apply_diacritization_attack,
    apply_homoglyph_substitution,
    apply_tatweel_injection,
    arabizi_substitution,
)


def test_arabizi_substitution_is_deterministic_with_seed():
    text = "عبدالله"
    rng1 = random.Random(42)
    rng2 = random.Random(42)
    out1 = arabizi_substitution(text, rng=rng1)
    out2 = arabizi_substitution(text, rng=rng2)
    assert out1 == out2


def test_arabizi_substitution_changes_text_when_eligible_chars_present():
    text = "عبدالله"  # contains ع which maps to '3'
    rng = random.Random(1)
    out = arabizi_substitution(text, budget=1.0, rng=rng)
    assert out != text


def test_arabizi_substitution_noop_on_no_eligible_chars():
    text = "hello world"
    rng = random.Random(1)
    out = arabizi_substitution(text, rng=rng)
    assert out == text


def test_tatweel_injection_inserts_kashida():
    text = "محمد"
    rng = random.Random(1)
    out = apply_tatweel_injection(text, rng=rng)
    assert "ـ" in out
    assert len(out) > len(text)


def test_diacritization_attack_inserts_tashkeel():
    text = "كتاب"
    rng = random.Random(1)
    out = apply_diacritization_attack(text, rng=rng)
    assert len(out) > len(text)


def test_homoglyph_substitution_respects_budget_zero():
    text = "0123456789"
    rng = random.Random(1)
    out = apply_homoglyph_substitution(text, budget=0.0, rng=rng)
    assert out == text


def test_homoglyph_substitution_full_budget_changes_digits():
    text = "0123456789"
    rng = random.Random(1)
    out = apply_homoglyph_substitution(text, budget=1.0, rng=rng)
    assert out != text
    assert len(out) == len(text)


def test_combined_attack_deterministic_with_same_seed():
    text = "عبدالله محمد ٠١٢٣"
    rng1 = random.Random(7)
    rng2 = random.Random(7)
    out1 = apply_combined_attack(text, rng=rng1)
    out2 = apply_combined_attack(text, rng=rng2)
    assert out1 == out2


def test_operators_respect_explicit_spans():
    text = "prefix محمد suffix"
    start = text.index("محمد")
    end = start + len("محمد")
    rng = random.Random(1)
    out = apply_tatweel_injection(text, spans=[(start, end)], rng=rng)
    assert out.startswith("prefix ")
    assert out.endswith(" suffix")
