#!/usr/bin/env python
"""CLI wrapper around arenredact.data.corpus_generator (Section 5.1).

Example:
    python scripts/generate_corpus.py --out data/synthetic/train.jsonl --n-sentences 8970
"""

from __future__ import annotations

import sys

from arenredact.data.corpus_generator import _cli

if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
