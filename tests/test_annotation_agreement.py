import importlib.util, pathlib

spec = importlib.util.spec_from_file_location("agreement", pathlib.Path(__file__).resolve().parent.parent / "annotation" / "agreement.py")
agr = importlib.util.module_from_spec(spec); spec.loader.exec_module(agr)


def test_perfect_agreement_kappa_one():
    texts = {"s1": "call +966501234567 now", "s2": "nothing here"}
    spans = {"s1": [(5, 18, "PHONE")]}
    r = agr.agreement(spans, spans, texts)
    assert r["kappa_char"] == 1.0 and r["n_disagreeing_sentences"] == 0


def test_disagreement_lowers_kappa_and_is_listed():
    texts = {"s1": "call +966501234567 now", "s2": "id 1234567890 here"}
    a = {"s1": [(5, 18, "PHONE")], "s2": [(3, 13, "NATIONAL_ID")]}
    b = {"s1": [(5, 18, "PHONE")]}
    r = agr.agreement(a, b, texts)
    assert 0 < r["kappa_char"] < 1 and r["disagreements"] == ["s2"]
    assert r["span_f1"]["NATIONAL_ID"]["fn"] == 1
