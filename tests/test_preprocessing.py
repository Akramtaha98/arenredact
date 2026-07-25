"""Tests for Stage 1 (arenredact.preprocessing) — Section 4.1."""

from arenredact.preprocessing import (
    cap_tatweel,
    normalize,
    normalize_digits,
    normalize_with_report,
    strip_bidi_controls,
)


def test_strip_bidi_controls_removes_all_control_chars():
    text = "hello‮world⁦test"
    clean, count = strip_bidi_controls(text)
    assert clean == "helloworldtest"
    assert count == 2


def test_strip_bidi_controls_noop_on_clean_text():
    text = "لا توجد رموز اتجاه هنا"
    clean, count = strip_bidi_controls(text)
    assert clean == text
    assert count == 0


def test_normalize_digits_converts_arabic_indic():
    text = "٠١٢٣٤٥٦٧٨٩"
    converted, count = normalize_digits(text)
    assert converted == "0123456789"
    assert count == 10


def test_normalize_digits_converts_extended_arabic_indic():
    text = "۰۱۲۳"
    converted, count = normalize_digits(text)
    assert converted == "0123"
    assert count == 4


def test_normalize_digits_leaves_western_digits_unchanged():
    text = "already 12345"
    converted, count = normalize_digits(text)
    assert converted == text
    assert count == 0


def test_cap_tatweel_collapses_runs():
    text = "مـــرحبا"  # tatweel run of 3
    collapsed, runs = cap_tatweel(text)
    assert "ـــ" not in collapsed
    assert runs == 1


def test_cap_tatweel_ignores_single_occurrence():
    text = "مـرحبا"  # single tatweel, not a run
    collapsed, runs = cap_tatweel(text)
    assert collapsed == text
    assert runs == 0


def test_normalize_full_chain():
    text = "‮محمد ٠١٢٣ مـــرحبا"
    result = normalize(text)
    assert "‮" not in result
    assert "0123" in result
    assert "ـــ" not in result


def test_normalize_with_report_flags_adversarial_signal():
    text = "‮malicious"
    _, report = normalize_with_report(text)
    assert report.bidi_chars_stripped == 1
    assert report.any_adversarial_signal is True


def test_normalize_with_report_clean_input_no_signal():
    text = "normal clean text with no tricks"
    _, report = normalize_with_report(text)
    assert report.any_adversarial_signal is False
