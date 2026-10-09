# data/lexicons/

Reserved for plaintext lexicon exports (one entry per line) if you want to
version-control lexicon edits separately from code, e.g. for review by a
non-engineer domain expert. The lexicons that ship with this repository are
defined directly in `src/arenredact/data/lexicons.py` — that module is the
source of truth. If you add `.txt` files here, wire them up by editing
`lexicons.py` to load from this directory instead of using the inline
Python literals.
