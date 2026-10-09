"""Shared helpers for the round-4 analyses. These files live outside scripts/ on purpose: they
import the frozen detector and the frozen scorer unchanged and do not alter eval_sha256."""
import os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for p in (os.path.join(ROOT, "scripts"), os.path.join(ROOT, "src"), ROOT):
    if p not in sys.path: sys.path.insert(0, p)
for extra in ("/tmp/pylib2", "/tmp/pylib"):
    if os.path.isdir(extra) and extra not in sys.path: sys.path.append(extra)
import eval_lib as L  # noqa: E402


class ScrubadubSystem:
    """scrubadub 2.x (independent open-source rule-based scrubber) with its default detectors.
    It has no IBAN or national-ID detector, so it is scored on PHONE and EMAIL only."""
    types = ("PHONE", "EMAIL")
    MAP = {"phone": "PHONE", "email": "EMAIL"}

    def __init__(self):
        import scrubadub
        self.s = scrubadub.Scrubber()

    def run(self, text):
        spans = set()
        for f in self.s.iter_filth(text):
            t = self.MAP.get(f.type)
            if t: spans.add((f.beg, f.end, t))
        spans = L._resolve(sorted(spans))
        red = text
        for s, e, t in sorted(spans, reverse=True):
            red = red[:s] + f"[{t}]" + red[e:]
        return set(spans), text, red


def make_systems(include_scrubadub=True):
    from run_clean_eval import ABLATIONS
    sy = {"ours_full": L.OursSystem(ABLATIONS["ours_full"]), "ours_no_stage1": L.OursSystem(ABLATIONS["ours_no_stage1"]),
          "presidio_default": L.PresidioSystem("default"), "presidio_norm": L.PresidioSystem("norm"),
          "presidio_norm_regional": L.PresidioSystem("norm_regional")}
    if include_scrubadub: sy["scrubadub"] = ScrubadubSystem()
    return sy
