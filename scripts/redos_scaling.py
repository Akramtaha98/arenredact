"""Measure Stage 1 + Stage 3 matching time on adversarial inputs of growing
length, to check the denial-of-service claim empirically instead of asserting
linear-time behaviour from the regex flags. Writes results/redos_scaling.json.
"""
import json, math, statistics, sys, time
from arenredact.pipeline import ArEnRedactPipeline

INPUTS = {
    "digit_run": lambda n: "1" * n,
    "phone_prefix_repeat": lambda n: "+966 " * (n // 5),
    "plus966_digits_no_boundary": lambda n: "+966" + "5 " * (n // 2),
    "iban_prefix_repeat": lambda n: "SA79 " * (n // 5),
    "iban_near_miss": lambda n: ("SA79" + "1234 " * 5) * (n // 29),
    "email_local_part": lambda n: "a" * n + "@",
    "email_dots": lambda n: "a." * (n // 2) + "@b",
    "tatweel_run": lambda n: "م" + "ـ" * n,
    "invisible_run": lambda n: "1​" * (n // 2),
    "id_keyword_then_digits": lambda n: "national id " + "1234567890 " * (n // 11),
    "url_repeat": lambda n: "http://" + "a" * n,
    "www_repeat": lambda n: "www." * (n // 4),
    "ip_dots": lambda n: "1." * (n // 2),
    "mixed_script_tokens": lambda n: "СA79" * (n // 5),
}
SIZES = [2000, 8000, 32000, 128000]


def best_time(pipe, text, reps=3):
    ts = []
    for _ in range(reps):
        t0 = time.perf_counter()
        pipe.redact(text, record_audit=False)
        ts.append(time.perf_counter() - t0)
    return min(ts)


def main():
    pipe = ArEnRedactPipeline()
    out = {}
    for name, gen in INPUTS.items():
        rows = []
        for n in SIZES:
            rows.append({"n": n, "seconds": best_time(pipe, gen(n))})
        xs = [math.log(r["n"]) for r in rows]
        ys = [math.log(max(r["seconds"], 1e-9)) for r in rows]
        mx, my = statistics.mean(xs), statistics.mean(ys)
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
        out[name] = {"timings": rows, "loglog_slope": slope}
        print(f"{name:28s} slope={slope:5.2f}  t({SIZES[-1]})={rows[-1]['seconds']*1000:8.1f} ms")
    json.dump({"sizes": SIZES, "inputs": out,
               "note": "slope ~1 means linear growth; ~2 would indicate quadratic behaviour"},
              open(__import__("os").environ.get("REDOS_OUT","results/redos_scaling.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
