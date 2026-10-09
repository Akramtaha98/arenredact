"""Validation of the output-leakage scorer on constructed cases with known
ground truth (the label follows from how the case is built, not from the
scorer): whether any part of the identifier remains in the output beyond what
the surrounding text already contains.

Case kinds (identifier id, sentence template with context words, output):
  fully_redacted_plain      identifier replaced by a tag                       -> no leak
  fully_redacted_shared     as above, context shares >=6-char fragments with
                            the identifier (e.g. the e-mail domain is named)   -> no leak
  repeated_context          the same identifier appears a second time in the
                            context and is redacted in both places              -> no leak
  partial_prefix/suffix     >=8 characters of the identifier survive            -> leak
  partial_lookalike         surviving part written with look-alike characters   -> leak
  second_copy_unredacted    one copy redacted, a second copy left in place      -> leak
  repeat_second_survives    identifier occurs twice in the input, the scored
                            (second) occurrence survives, the first is redacted -> leak
  repeat_first_survives     same, with the first occurrence surviving            -> leak
  repeat_both_redacted      both occurrences redacted                            -> no leak
  short_fragment            only 4 characters survive (below threshold)         -> no leak
Reports accuracy / false positives / false negatives for the v1 scorer
(any fragment anywhere) and the v2 scorer (context-aware) at k = 6. Sensitivity to k is
measured on the attack results instead (results/sensitivity/). Writes results/scorer_validation.json."""
import json, os, random, sys
sys.path.insert(0, os.path.dirname(__file__))
import eval_lib as L

rng = random.Random(7)
DOMAINS = ["example.com", "corp-demo.net", "mailhost.org", "bankofdemo.com", "contoso.co"]
WORDS_SHARED = ["Example company", "corp-demo network", "Mailhost support", "Bank of Demo"]


def ident(kind):
    if kind == "EMAIL":
        d = rng.choice(DOMAINS); return f"user{rng.randint(100, 999)}@{d}", d.split(".")[0]
    if kind == "PHONE":
        return "+966" + "".join(rng.choice("0123456789") for _ in range(9)), None
    if kind == "IBAN":
        return "SA" + "".join(rng.choice("0123456789") for _ in range(22)), None
    return "".join(rng.choice("0123456789") for _ in range(10)), None


def cases():
    out = []
    for n in range(40):
        for kind in ("EMAIL", "PHONE", "IBAN", "NATIONAL_ID"):
            v, dom = ident(kind); tag = f"[{kind}]"
            shared = (dom.capitalize() + " company") if dom else "the customer"
            ctx_l, ctx_r = f"Please contact {shared} at ", f". Thanks, {shared}."
            ctx = ctx_l + ctx_r
            out.append(("fully_redacted_plain", kind, v, ctx, ctx_l + tag + ctx_r, False))
            if dom:
                out.append(("fully_redacted_shared", kind, v, ctx, ctx_l + tag + ctx_r, False))
            out.append(("repeated_context", kind, v, f"{ctx_l}{v}{ctx_r} Again: {v}.", f"{ctx_l}{tag}{ctx_r} Again: {tag}.", False))
            # note: for repeated_context the scored occurrence is the first; context = text without it still holds the 2nd copy
            keep = v[: max(8, len(v) // 2)]
            out.append(("partial_prefix", kind, v, ctx, ctx_l + keep + tag + ctx_r, True))
            out.append(("partial_suffix", kind, v, ctx, ctx_l + tag + v[-max(8, len(v) // 2):] + ctx_r, True))
            lk = keep.translate(str.maketrans("0123456789oae", "٠١٢٣٤٥٦٧٨٩оае")) if kind != "EMAIL" else keep.replace("e", "е").replace("a", "а")
            out.append(("partial_lookalike", kind, v, ctx, ctx_l + lk + tag + ctx_r, True))
            out.append(("second_copy_unredacted", kind, v, ctx, ctx_l + tag + ctx_r + " (cc: " + v + ")", True))
            out.append(("repeat_second_survives", kind, v, None, f"ID {tag}; repeat {v}.", True))
            out.append(("repeat_first_survives", kind, v, None, f"ID {v}; repeat {tag}.", True))
            out.append(("repeat_both_redacted", kind, v, None, f"ID {tag}; repeat {tag}.", False))
            out.append(("short_fragment", kind, v, ctx, ctx_l + tag + v[-4:] + ctx_r, False))
    return out


def run(k):
    res = {}
    for kindcase, kind, v, ctx, outp, truth in cases():
        # context for the scorer = input sentence with THIS identifier occurrence removed
        context = ctx if kindcase != "repeated_context" else f"Please contact the customer at . Thanks, the customer. Again: {v}."
        if kindcase == "repeated_context":
            context = ctx.split(" Again:")[0] + f" Again: {v}."
        if kindcase == "second_copy_unredacted":
            context = ctx
        if kindcase == "repeat_second_survives":      # scored occurrence = the second; first copy stays in the context
            context = f"ID {v}; repeat ."
        if kindcase in ("repeat_first_survives", "repeat_both_redacted"):
            context = f"ID ; repeat {v}." if kindcase == "repeat_first_survives" else f"ID {v}; repeat ."
        r = res.setdefault(kindcase, {"n": 0, "v1_correct": 0, "v2a_correct": 0, "v2_correct": 0, "v2a_fp": 0, "v2a_fn": 0, "v1_fp": 0, "v1_fn": 0, "v2_fp": 0, "v2_fn": 0})
        a, b, c2 = L.leaks_v1(v, outp, k), L.leaks(v, outp, k, context=context), L.leaks_v2a(v, outp, k, context=context)
        r["n"] += 1
        r["v2a_correct"] += c2 == truth; r["v2a_fp"] += (c2 and not truth); r["v2a_fn"] += (not c2 and truth)
        r["v1_correct"] += a == truth; r["v2_correct"] += b == truth
        r["v1_fp"] += (a and not truth); r["v1_fn"] += (not a and truth)
        r["v2_fp"] += (b and not truth); r["v2_fn"] += (not b and truth)
    return res


def main():
    out = {"k6": run(6)}
    # the example raised in review
    out["review_example"] = {"identifier": "user123@example.com", "output": "Contact [EMAIL]. Example company.",
                             "v1": L.leaks_v1("user123@example.com", "Contact [EMAIL]. Example company."),
                             "v2": L.leaks("user123@example.com", "Contact [EMAIL]. Example company.", context="Contact . Example company.")}
    out["note"] = "Ground truth follows from construction (author-built), not from independent human judgement."
    json.dump(out, open("results/scorer_validation.json", "w"), indent=1, ensure_ascii=False)
    n = sum(x["n"] for x in out["k6"].values())
    for name in ("v1", "v2a", "v2"):
        print(name, "accuracy", sum(x[name + "_correct"] for x in out["k6"].values()) / n,
              "FP", sum(x[name + "_fp"] for x in out["k6"].values()), "FN", sum(x[name + "_fn"] for x in out["k6"].values()), "of", n)
    print(out["review_example"])


if __name__ == "__main__":
    main()
