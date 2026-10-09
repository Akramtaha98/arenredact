"""Revision-2 attack audit.

For each attack configuration and system we report (per evaluation set):
  n_ids            gold identifiers in the set
  n_altered        identifiers whose text the attack actually changed
  n_protected_alt  altered identifiers that the system already protected on
                   clean text (the only ones an attack can "defeat")
  n_leaked         of those, identifiers with a >=6-character fragment still
                   readable in the redacted OUTPUT (reader-canonical form)
  asr_alt          n_leaked / n_protected_alt          (primary measure)
  asr_all          n_leaked / n_protected_clean        (over all clean-protected ids)
Output-based scoring is used so length-changing attacks (separators, expanded
forms) are included; transformed gold spans are also tracked for a secondary
span-based miss count. Adaptive search: random compositions of operators with
random parameters, budget Q queries per identifier, success = first leak.

usage: python scripts/run_attack_audit.py [--revision r1|r2] [--budget 50]
"""
import argparse, json, os, random, sys, time, zlib

sys.path.insert(0, os.path.dirname(__file__))
import eval_lib as L
from arenredact.attacks import extended as X
from arenredact.attacks.operators import apply_homoglyph_substitution
import validity_realistic_set as valid
import stratified_holdout as s3
from arenredact.data.corpus_generator import generate_corpus
from run_clean_eval import ABLATIONS


def seeded(*parts):
    return random.Random(zlib.crc32("|".join(map(str, parts)).encode()))


def load_sets():
    corpus = generate_corpus(n_sentences=8970, seed=42, arabizi_rate=0.30)
    test = corpus[int(0.8 * 8970) + int(0.1 * 8970):]
    synth = [(r.text, [tuple(e[:3]) if isinstance(e, tuple) else (e.start, e.end, e.entity_type) for e in r.entities if e.entity_type in L.TYPES]) for r in test]
    synth = [(t, g) for t, g in synth if g]
    v = [(t, [tuple(x) for x in g]) for t, g in valid.CASES]
    s = [(t, [tuple(x) for x in g]) for t, g in s3.CASES if g]
    return {"synthetic_test": synth, "validity_realistic": v, "stratified_S3": s}


def ident_fn(op, held, rng):
    f = X.IDENT_OPS[op]
    return lambda ident, t: f(ident, rng, held) if X.eligible(op, t, ident) else ident


def hgl_fn(rate, rng):
    def fn(ident, t):
        return apply_homoglyph_substitution(ident, [(0, len(ident))], budget=rate, rng=rng)
    return fn


FIXED = [
    ("HGL 20%", "hgl", 0.20), ("HGL 100%", "hgl", 1.0),
    ("INV (dev chars)", "INV", False), ("INV (held-out chars)", "INV", True),
    ("BIDI controls", "BIDI", False), ("Fullwidth/math forms", "FW", False),
    ("Arabic-Indic digits", "DIG", False),
    ("SEP (dev separators)", "SEP", False), ("SEP (held-out separators)", "SEP", True),
    ("CONF (folded set)", "CONF", False), ("CONF (held-out set)", "CONF", True),
    ("CTX zero-width", "CTX", "zw"), ("CTX diacritics", "CTX", "tashkeel"),
    ("CTX look-alike", "CTX", "conf"), ("CTX synonym", "CTX", "synonym"),
    ("COMBO-2", "combo", 2), ("COMBO-3", "combo", 3),
]


def attack_sentence(text, gold, cfg, seed_parts):
    name, kind, par = cfg
    rng = seeded(*seed_parts)
    if kind == "hgl":
        return X.apply_to_spans(text, gold, hgl_fn(par, rng)), text
    if kind in X.IDENT_OPS:
        return X.apply_to_spans(text, gold, ident_fn(kind, par, rng)), text
    if kind == "combo":
        return X.apply_to_spans(text, gold, lambda i, t: X.random_combo(i, t, rng, par)), text
    if kind == "CTX":
        new = text
        alt = []
        # shift handled by working right to left
        for (s, e, t) in sorted(gold, reverse=True):
            if t == "NATIONAL_ID":
                new = X.op_ctx(new, s, rng, par)
        ok = new != text
        # gold offsets move if the keyword text changed length: recompute by locating each identifier string
        gnew = []
        for (s, e, t) in sorted(gold):
            val = text[s:e]
            k = new.find(val)
            gnew.append((k, k + len(val), t))
        return X.AppliedAttack(new, gnew, [ok if g[2] == "NATIONAL_ID" else False for g in sorted(gold)]), text
    raise ValueError(kind)


def run_fixed(sets, systems, cfgs):
    out = {}
    for sname, cases in sets.items():
        out[sname] = {}
        # clean protection status per (system, sentence, identifier)
        clean = {}
        for name, sysobj in systems.items():
            for i, (t, g) in enumerate(cases):
                _, _, red = sysobj.run(t)
                for j, (s, e, ty) in enumerate(sorted(g)):
                    clean[(name, i, j)] = not L.leaks(t[s:e], red, context=t[:s] + t[e:])
        for cfg in cfgs:
            cname = cfg[0]
            res = {n: dict(n_ids=0, n_altered=0, n_protected_alt=0, n_leaked=0, n_protected_clean=0, n_span_miss=0) for n in systems}
            atk = {}
            for i, (t, g) in enumerate(cases):
                atk[i] = attack_sentence(t, sorted(g), cfg, (cname, sname, i))[0]
            for name, sysobj in systems.items():
                r = res[name]
                for i, (t, g) in enumerate(cases):
                    a = atk[i]
                    pred, _, red = sysobj.run(a.text)
                    og = sorted(g)
                    for j, (s, e, ty) in enumerate(og):
                        r["n_ids"] += 1
                        prot = clean[(name, i, j)]
                        r["n_protected_clean"] += prot
                        if not a.altered[j]:
                            continue
                        r["n_altered"] += 1
                        if not prot:
                            continue
                        r["n_protected_alt"] += 1
                        gs = a.gold[j]
                        if L.leaks(t[s:e], red, context=a.text[:gs[0]] + a.text[gs[1]:]):
                            r["n_leaked"] += 1
                        if not any(p[2] == gs[2] and L._iou(p, gs) >= 0.5 for p in pred):
                            r["n_span_miss"] += 1
            for name, r in res.items():
                n, k = r["n_protected_alt"], r["n_leaked"]
                r["asr_alt"] = k / n if n else None
                r["asr_all"] = k / r["n_protected_clean"] if r["n_protected_clean"] else None
                r["wilson95_alt"] = L.wilson(k, n) if n else None
                r["upper95_if_zero"] = L.clopper_pearson_upper_zero(n) if (n and k == 0) else None
            out[sname][cname] = res
        print("fixed done", sname, flush=True)
    return out


CLOSED_OPS = ["INV", "BIDI", "FW", "DIG", "CONF"]


def adaptive_query(ident, etype, rng, mode="open"):
    """open: any operator, any inventory (includes separator insertion and
    look-alikes outside the folded set). closed: only the operator families
    Stage 1 is designed to normalise (invisible, bidi, fullwidth, digit
    script, folded look-alike set)."""
    k = rng.choice([1, 2, 3])
    if mode == "open":
        return X.random_combo(ident, etype, rng, k, held_prob=0.5)
    ops = [o for o in CLOSED_OPS if X.eligible(o, etype, ident)]
    for o in rng.sample(ops, min(k, len(ops))):
        held = False if o == "CONF" else rng.random() < 0.5
        ident = X.IDENT_OPS[o](ident, rng, held)
    return ident


def run_adaptive(sets, systems, budget, per_set_cap, mode="open"):
    out = {}
    for sname, cases in sets.items():
        items = [(i, j, t, sorted(g)[j]) for i, (t, g) in enumerate(cases) for j in range(len(g))]
        rng0 = seeded("subsample", sname)
        if len(items) > per_set_cap:
            items = rng0.sample(items, per_set_cap)
        out[sname] = {}
        for name, sysobj in systems.items():
            prot = alt = succ = 0
            q_to = []
            examples = []
            for (i, j, t, (s, e, ty)) in items:
                _, _, red0 = sysobj.run(t)
                if L.leaks(t[s:e], red0, context=t[:s] + t[e:]):
                    continue
                prot += 1
                rng = seeded("adaptive", mode, sname, i, j)
                ident = t[s:e]
                for q in range(1, budget + 1):
                    new_ident = adaptive_query(ident, ty, rng, mode)
                    if new_ident == ident:
                        continue
                    text2 = t[:s] + new_ident + t[e:]
                    _, _, red = sysobj.run(text2)
                    if L.leaks(ident, red, context=t[:s] + t[e:]):
                        succ += 1; q_to.append(q)
                        if len(examples) < 3:
                            examples.append({"type": ty, "perturbed": new_ident.encode("unicode_escape").decode()})
                        break
            out[sname][name] = {"identifiers_tried": prot, "evaded": succ, "success_rate": succ / prot if prot else None,
                                "wilson95": L.wilson(succ, prot) if prot else None,
                                "upper95_if_zero": L.clopper_pearson_upper_zero(prot) if (prot and succ == 0) else None,
                                "median_queries_to_success": (sorted(q_to)[len(q_to) // 2] if q_to else None),
                                "examples": examples, "budget": budget}
        print("adaptive done", sname, flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--revision", default="r2")
    ap.add_argument("--budget", type=int, default=50)
    ap.add_argument("--cap", type=int, default=150)
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-presidio", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    sets = load_sets()
    if a.revision == "r1":
        systems = {"ours_full": L.OursSystem(None), "ours_no_stage1": L.OursSystem(())}
    else:
        systems = {k: L.OursSystem(v) for k, v in ABLATIONS.items()}
        if not a.no_presidio:
            for v in ("default", "norm", "norm_regional"):
                systems["presidio_" + v] = L.PresidioSystem(v)
    fixed = run_fixed(sets, systems, FIXED)
    ad_sys = {k: v for k, v in systems.items() if k in ("ours_full", "ours_no_stage1", "ours_nfkc_only", "ours_digits_only", "ours_nfkc_plus_digits",
                                                        "presidio_default", "presidio_norm", "presidio_norm_regional")}
    adaptive = run_adaptive(sets, ad_sys, a.budget, a.cap, "open")
    adaptive_closed = run_adaptive(sets, ad_sys, a.budget, a.cap, "closed")
    res = {"revision": a.revision, "code_sha256": L.code_sha256(), "eval_sha256": L.eval_sha256(), "scorer": "leaks v2 (context-aware, k=6)", "budget": a.budget, "adaptive_cap_per_set": a.cap,
           "n_ids": {k: sum(len(g) for _, g in v) for k, v in sets.items()},
           "fixed": fixed, "adaptive": adaptive, "adaptive_closed": adaptive_closed, "seconds": round(time.time() - t0, 1),
           "definitions": "success = a >=6-char fragment of the identifier (reader-canonical form) occurs in the redacted output more often than in the surrounding text alone"}
    out = a.out or f"results/attack_audit_{a.revision}.json"
    json.dump(res, open(out, "w"), indent=1, default=list)
    print("done", res["seconds"], "s ->", out)


if __name__ == "__main__":
    main()
