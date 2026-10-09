"""Post-Redaction Re-Identification Rate (PRIR) evaluation harness (Section 5.3, 6.3).

Implements the Motivated Bilingual Intruder (MBI) adversary from Section 3.4:
given a redacted record, attempt to recover at least one redacted PII entity
using the surrounding unredacted context as a query against a background
corpus, following the autoregressive-infilling methodology of Charpentier &
Lison (2025).

This module provides the *harness* (scoring loop, PRIR aggregation) and a
pluggable `InfillingAdversary` protocol. A production adversary would wrap a
fine-tuned masked/causal LM over Arabic Wikipedia + social media + news
background corpora, as described in Section 5.3; this repository ships a
`NullAdversary` (always fails to recover) and a `LexicalOverlapAdversary`
(a weak, fully-offline baseline using n-gram overlap against the background
corpus) so the harness is testable without any GPU or external API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from arenredact.span_fusion import Span


@dataclass
class RedactedRecord:
    redacted_text: str
    original_text: str
    redacted_spans: list[Span]  # spans in `original_text` coordinates


class InfillingAdversary(Protocol):
    """A re-identification adversary: given redacted text and the mask
    positions, propose a candidate string for each masked span."""

    def infill(self, redacted_text: str, mask_spans: list[Span]) -> list[str]:
        ...


class NullAdversary:
    """Baseline adversary that never recovers anything — useful as a sanity
    floor (PRIR should be 0.0 against this adversary for any system)."""

    def infill(self, redacted_text: str, mask_spans: list[Span]) -> list[str]:
        return ["" for _ in mask_spans]


class LexicalOverlapAdversary:
    """A weak, fully offline re-identification baseline: for each masked
    span, search a background corpus for entities whose surrounding context
    has the highest n-gram overlap with the redacted record's local context.

    This is intentionally much weaker than the RAG-augmented autoregressive
    infilling adversary described in Section 5.3 (which requires a language
    model and real background corpora) — it exists so the PRIR harness below
    is exercised and testable in CI without external dependencies. Treat its
    PRIR output as a conservative lower bound, not the paper's reported
    figure.
    """

    def __init__(self, background_entities: list[tuple[str, str]]):
        """`background_entities`: list of (context, entity_value) pairs
        drawn from a background corpus."""
        self.background = background_entities

    @staticmethod
    def _ngram_overlap(a: str, b: str, n: int = 3) -> float:
        def ngrams(s: str) -> set[str]:
            return {s[i : i + n] for i in range(max(len(s) - n + 1, 0))}

        ga, gb = ngrams(a), ngrams(b)
        if not ga or not gb:
            return 0.0
        return len(ga & gb) / len(ga | gb)

    def infill(self, redacted_text: str, mask_spans: list[Span]) -> list[str]:
        guesses = []
        for span in mask_spans:
            local_context = redacted_text[max(0, span.start - 30) : span.end + 30]
            best_entity, best_score = "", 0.0
            for context, entity_value in self.background:
                score = self._ngram_overlap(local_context, context)
                if score > best_score:
                    best_entity, best_score = entity_value, score
            guesses.append(best_entity)
        return guesses


def compute_prir(
    records: list[RedactedRecord],
    adversary: InfillingAdversary,
) -> dict:
    """Compute the Post-Redaction Re-Identification Rate: the fraction of
    records for which the adversary correctly recovers *at least one*
    redacted entity from its surrounding context (Section 5.3)."""
    n_reidentified = 0

    for record in records:
        mask_spans = record.redacted_spans
        if not mask_spans:
            continue
        guesses = adversary.infill(record.redacted_text, mask_spans)
        gold_values = [record.original_text[s.start : s.end] for s in mask_spans]

        if any(guess.strip() and guess.strip() == gold.strip() for guess, gold in zip(guesses, gold_values)):
            n_reidentified += 1

    prir = n_reidentified / len(records) if records else 0.0
    return {
        "prir": prir,
        "n_records": len(records),
        "n_reidentified": n_reidentified,
    }
