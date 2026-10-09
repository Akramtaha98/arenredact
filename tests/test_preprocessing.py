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


# ---------------------------------------------------------------------------
# NFKC (not NFC) is required to fold compatibility characters. These tests
# document the distinction raised in peer review of the manuscript.
# ---------------------------------------------------------------------------

import unicodedata


def test_nfc_alone_does_not_fold_arabic_presentation_forms():
    isolated_beh = "ﺏ"  # ARABIC LETTER BEH ISOLATED FORM
    assert unicodedata.normalize("NFC", isolated_beh) == isolated_beh


def test_stage1_folds_arabic_presentation_forms_to_base_letters():
    from arenredact.preprocessing import normalize

    assert normalize("ﺏ") == "ب"  # BEH


def test_stage1_folds_fullwidth_digits_to_ascii():
    from arenredact.preprocessing import normalize

    assert normalize("１２３") == "123"


from arenredact.preprocessing import normalize as _norm, ALL_STEPS as _ALL


def test_invisible_characters_removed_inside_identifier():
    assert _norm("+966\u200b50\u200d123\u20614567") == "+966501234567"


def test_confusables_folded_only_in_mixed_tokens():
    assert _norm("\u0421\u041079 1234") == "CA79 1234"        # Cyrillic C, A inside an alphanumeric token
    assert _norm("\u043f\u0440\u0438\u0432\u0435\u0442") == "\u043f\u0440\u0438\u0432\u0435\u0442"  # pure Cyrillic word untouched


def test_nfkc_alone_does_not_fold_arabic_indic_digits_but_digit_step_does():
    ai = "\u0661\u0662\u0663"
    assert _norm(ai, ("nfkc",)) == ai
    assert _norm(ai, ("digits",)) == "123"
    assert _norm("\uff11\uff12\uff13", ("nfkc",)) == "123"
    assert _norm("\uff11\uff12\uff13", ("digits",)) == "\uff11\uff12\uff13"


def test_unknown_step_rejected_and_steps_independent():
    import pytest as _pt
    with _pt.raises(ValueError):
        _norm("x", ("nope",))
    assert _norm("a\u200bb", ("digits",)) == "a\u200bb"
