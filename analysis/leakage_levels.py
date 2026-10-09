"""Round-4 analysis of the fixed attacks (same sets, attacks and seeds as scripts/run_attack_audit.py):
  * partial exposure (k=6 fragment, the paper's rule) AND complete-identifier recovery (whole canonical identifier),
  * total leakage over ALL altered identifiers (clean misses included),
  * conditional ASR (altered and protected on clean text, as in the paper),
  * ASR on the common subset protected on clean text by every system of the comparison group.
usage: python analysis/leakage_levels.py   -> results/leakage_levels.json"""
import json, sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
import common as C
L = C.L
import run_attack_audit as RA

FULL_K = 10 ** 6   # fragment longer than any identifier => whole canonical identifier
GROUP_A = ["ours_full", "presidio_default", "presidio_norm", "presidio_norm_regional"]
SHARED2 = ("PHONE", "EMAIL")

def rate(k, n): return (k / n) if n else None

def main():
    t0 = time.time()
    sets = RA.load_sets(); systems = C.make_systems()
    out = {"code_sha256": L.code_sha256(), "eval_sha256": L.eval_sha256(), "scorer": "leaks v2, k=6 (partial) and whole-identifier (full)", "sets": {}}
    for sname, cases in sets.items():
        out["sets"][sname] = {}
        clean = {}
        for name, sysobj in systems.items():
            for i, (t, g) in enumerate(cases):
                _, _, red = sysobj.run(t)
                for j, (s, e, ty) in enumerate(sorted(g)):
                    clean[(name, i, j)] = not L.leaks(t[s:e], red, context=t[:s] + t[e:])
        for cfg in RA.FIXED:
            cname = cfg[0]
            atk = {i: RA.attack_sentence(t, sorted(g), cfg, (cname, sname, i))[0] for i, (t, g) in enumerate(cases)}
            rec = {n: [] for n in systems}   # per identifier: dict
            for name, sysobj in systems.items():
                for i, (t, g) in enumerate(cases):
                    a = atk[i]; pred, _, red = sysobj.run(a.text); og = sorted(g)
                    for j, (s, e, ty) in enumerate(og):
                        if name == "scrubadub" and ty not in SHARED2: continue
                        ctx = a.text[:a.gold[j][0]] + a.text[a.gold[j][1]:]
                        gs = a.gold[j]
                        hit = any(p[2] == gs[2] and L._iou(p, gs) >= 0.5 for p in pred)
                        rec[name].append({"key": (i, j), "ty": ty, "hit": hit, "alt": bool(a.altered[j]), "cp": clean[(name, i, j)],
                                          "lp": L.leaks(t[s:e], red, context=ctx), "lf": L.leaks(t[s:e], red, k=FULL_K, context=ctx)})
            # common subsets
            def common(group, types=None):
                ks = None
                for n in group:
                    S = {r["key"] for r in rec[n] if r["alt"] and r["cp"] and (types is None or r["ty"] in types)}
                    ks = S if ks is None else ks & S
                return ks or set()
            cA = common(GROUP_A); cB = common(GROUP_A + ["scrubadub"], SHARED2)
            res = {}
            for n, rs in rec.items():
                alt = [r for r in rs if r["alt"]]; prot = [r for r in alt if r["cp"]]
                d = {"n_applicable": len(rs), "n_altered": len(alt), "n_clean_missed_altered": len(alt) - len(prot), "n_protected_alt": len(prot),
                     "asr_alt_partial": rate(sum(r["lp"] for r in prot), len(prot)), "asr_alt_full": rate(sum(r["lf"] for r in prot), len(prot)),
                     "k_partial": sum(r["lp"] for r in prot), "k_full": sum(r["lf"] for r in prot),
                     "total_leak_partial": rate(sum(r["lp"] for r in alt), len(alt)), "total_leak_full": rate(sum(r["lf"] for r in alt), len(alt)),
                     "k_total_partial": sum(r["lp"] for r in alt), "k_total_full": sum(r["lf"] for r in alt),
                     "span_hit_but_partial_leak": sum(r["hit"] and r["lp"] for r in prot), "span_hit_but_full_leak": sum(r["hit"] and r["lf"] for r in prot),
                     "span_hit": sum(r["hit"] for r in prot), "span_miss_no_leak": sum((not r["hit"]) and (not r["lp"]) for r in prot)}
                for tag, cs in (("A", cA), ("B", cB)):
                    if tag == "B" and n not in GROUP_A + ["scrubadub"]: continue
                    if tag == "A" and n == "scrubadub": continue
                    sub = [r for r in alt if r["key"] in cs and r["cp"]]
                    d[f"common_{tag}_n"] = len(sub); d[f"common_{tag}_partial"] = sum(r["lp"] for r in sub); d[f"common_{tag}_full"] = sum(r["lf"] for r in sub)
                res[n] = d
            out["sets"][sname][cname] = res
        print("done", sname, round(time.time() - t0), "s", flush=True)
    json.dump(out, open(os.path.join(C.ROOT, "results", "leakage_levels.json"), "w"), indent=1, default=list)
    print("written", round(time.time() - t0), "s")

if __name__ == "__main__":
    main()
