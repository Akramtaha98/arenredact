"""Stage 4 — Span Fusion with Conflict Resolution.

Implements Algorithm 1 from the paper (Section 4.4):

    Input:  S_NER (spans from neural NER engine), S_Regex (spans from
            pattern engine), text T
    Output: S_fused (final redaction spans)
     1: S_fused <- S_NER U S_Regex
     2: sort S_fused by start offset
     3: for each pair of overlapping spans (s_i, s_j) in S_fused do
     4:     if type(s_i) != type(s_j) then
     5:         retain s_i if origin(s_i) = Regex, else retain s_j
     6:     end if
     7: end for
     8: for each span s of type PERSON in S_fused do
     9:     while adjacent_token(s) in {kunya, nisbah, laqab lexicon} do
    10:         expand s to include adjacent_token(s)
    11:     end while
    12: end for
    13: return S_fused

Complexity: sorting is O(n log n) in the number of candidate spans n; the
overlap-resolution pass is a single left-to-right sweep, O(n); and the
quasi-identifier expansion is O(n) lexicon lookups. Stage 4 therefore runs in
O(n log n) overall, dominated by the sort.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from arenredact.data.lexicons import QUASI_IDENTIFIER_LEXICON


class SpanOrigin(str, Enum):
    NEURAL = "neural"
    REGEX = "regex"
    FUSED = "fused"


@dataclass
class Span:
    """A single detected PII span over the (already Stage-1-normalized) text."""

    start: int
    end: int
    entity_type: str
    origin: SpanOrigin
    score: float = 1.0
    # Populated after quasi-identifier expansion (Algorithm 1, lines 8-12).
    expanded: bool = field(default=False, compare=False)

    def overlaps(self, other: "Span") -> bool:
        return self.start < other.end and other.start < self.end

    def __len__(self) -> int:
        return self.end - self.start


def _resolve_overlaps(spans: list[Span]) -> list[Span]:
    """Algorithm 1, lines 3-7: for overlapping spans of differing type,
    deterministic (regex-origin) spans take priority over neural spans,
    reflecting the lower false-positive rate of structured-identifier
    regexes noted in Section 4.4."""
    if not spans:
        return []

    spans = sorted(spans, key=lambda s: (s.start, -len(s)))
    resolved: list[Span] = [spans[0]]

    for candidate in spans[1:]:
        kept = resolved[-1]
        if candidate.overlaps(kept):
            if candidate.entity_type == kept.entity_type:
                # Same type: keep the higher-confidence / longer span.
                if candidate.score > kept.score or (
                    candidate.score == kept.score and len(candidate) > len(kept)
                ):
                    resolved[-1] = candidate
                continue
            # Differing type: regex origin wins per Algorithm 1 line 5.
            if candidate.origin == SpanOrigin.REGEX and kept.origin != SpanOrigin.REGEX:
                resolved[-1] = candidate
            elif kept.origin == SpanOrigin.REGEX:
                pass  # keep existing regex-origin span
            else:
                # Neither is regex-origin (both neural): keep higher score.
                if candidate.score > kept.score:
                    resolved[-1] = candidate
        else:
            resolved.append(candidate)

    return resolved


def _expand_quasi_identifiers(spans: list[Span], text: str) -> list[Span]:
    """Algorithm 1, lines 8-12: expand PERSON spans left/right while the
    adjacent whitespace-delimited token is a kunya prefix, nisbah suffix, or
    laqab honorific, so the fused span covers the full quasi-identifier
    rather than just the bare given name."""
    expanded_spans: list[Span] = []

    for span in spans:
        if span.entity_type != "PERSON":
            expanded_spans.append(span)
            continue

        start, end = span.start, span.end

        # Expand left.
        while True:
            left_boundary = text.rfind(" ", 0, start - 1) + 1 if start > 0 else 0
            if left_boundary >= start:
                break
            token = text[left_boundary : start].strip()
            if token and token in QUASI_IDENTIFIER_LEXICON:
                start = left_boundary
            else:
                break

        # Expand right.
        while True:
            right_boundary = text.find(" ", end + 1)
            right_boundary = right_boundary if right_boundary != -1 else len(text)
            token = text[end:right_boundary].strip()
            if token and token in QUASI_IDENTIFIER_LEXICON:
                end = right_boundary
            else:
                break

        expanded_spans.append(
            Span(
                start=start,
                end=end,
                entity_type=span.entity_type,
                origin=span.origin,
                score=span.score,
                expanded=(start, end) != (span.start, span.end),
            )
        )

    return expanded_spans


def fuse_spans(
    neural_spans: list[Span],
    regex_spans: list[Span],
    text: str,
    expand_quasi_identifiers: bool = True,
) -> list[Span]:
    """Run the full Stage 4 pipeline: union -> sort -> overlap resolution ->
    (optional) quasi-identifier expansion. See module docstring for
    Algorithm 1's pseudocode and complexity analysis."""
    union = list(neural_spans) + list(regex_spans)
    union.sort(key=lambda s: s.start)  # Algorithm 1, line 2

    resolved = _resolve_overlaps(union)  # Algorithm 1, lines 3-7

    if expand_quasi_identifiers:
        resolved = _expand_quasi_identifiers(resolved, text)  # lines 8-12

    return sorted(resolved, key=lambda s: s.start)


def redact(text: str, spans: list[Span], mask_fmt: str = "[{entity_type}]") -> str:
    """Apply redaction masks to `text` given a fused span list, replacing each
    span right-to-left so earlier offsets remain valid during substitution."""
    out = text
    for span in sorted(spans, key=lambda s: s.start, reverse=True):
        mask = mask_fmt.format(entity_type=span.entity_type)
        out = out[: span.start] + mask + out[span.end :]
    return out
