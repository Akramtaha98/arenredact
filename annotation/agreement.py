"""Inter-annotator agreement for span annotations.

usage: python annotation/agreement.py A.csv B.csv sample.csv
A.csv / B.csv: sentence_id,start,end,label,note ; sample.csv: sentence_id,text,...
Reports character-level Cohen's kappa over the label set {O, PHONE, EMAIL,
IBAN, NATIONAL_ID}, exact-span F1 of B against A per type, and every
disagreement for adjudication.
"""
import csv, sys
from collections import Counter, defaultdict

LABELS = ["O", "PHONE", "EMAIL", "IBAN", "NATIONAL_ID"]


def read_spans(path):
    spans = defaultdict(list)
    with open(path, encoding="utf8", newline="") as f:
        for r in csv.DictReader(f):
            if r.get("label") in LABELS[1:]:
                spans[r["sentence_id"]].append((int(r["start"]), int(r["end"]), r["label"]))
    return spans


def read_texts(path):
    with open(path, encoding="utf8", newline="") as f:
        return {r["sentence_id"]: r["text"] for r in csv.DictReader(f)}


def char_labels(n, spans):
    lab = ["O"] * n
    for s, e, t in spans:
        for i in range(max(0, s), min(n, e)):
            lab[i] = t
    return lab


def cohen_kappa(pairs):
    n = len(pairs)
    if n == 0:
        return None
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[l] * cb[l] for l in LABELS) / (n * n)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def span_f1(a_spans, b_spans, texts):
    out = {}
    for t in LABELS[1:]:
        tp = fp = fn = 0
        for sid in texts:
            A = {s for s in a_spans.get(sid, []) if s[2] == t}
            B = {s for s in b_spans.get(sid, []) if s[2] == t}
            tp += len(A & B); fp += len(B - A); fn += len(A - B)
        d = 2 * tp + fp + fn
        out[t] = {"tp": tp, "fp": fp, "fn": fn, "f1": (2 * tp / d) if d else None}
    return out


def agreement(a_spans, b_spans, texts):
    pairs = []
    for sid, text in texts.items():
        la, lb = char_labels(len(text), a_spans.get(sid, [])), char_labels(len(text), b_spans.get(sid, []))
        pairs += list(zip(la, lb))
    dis = [sid for sid in texts if set(a_spans.get(sid, [])) != set(b_spans.get(sid, []))]
    return {"kappa_char": cohen_kappa(pairs), "span_f1": span_f1(a_spans, b_spans, texts), "n_disagreeing_sentences": len(dis),
            "disagreements": dis}


if __name__ == "__main__":
    A, B, S = sys.argv[1:4]
    res = agreement(read_spans(A), read_spans(B), read_texts(S))
    print("character-level Cohen kappa:", res["kappa_char"])
    for t, v in res["span_f1"].items():
        print(f"  {t:12s} F1={v['f1']}  (tp {v['tp']}, fp {v['fp']}, fn {v['fn']})")
    print("sentences needing adjudication:", res["n_disagreeing_sentences"])
    print(*res["disagreements"], sep="\n")
