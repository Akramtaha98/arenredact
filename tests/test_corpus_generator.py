"""Tests for arenredact.data.corpus_generator — Section 5.1."""

import json

from arenredact.data.corpus_generator import generate_corpus, generate_record, write_jsonl
import random


def test_generate_record_entities_within_text_bounds():
    rng = random.Random(42)
    record = generate_record(rng)
    for entity in record.entities:
        assert 0 <= entity.start < entity.end <= len(record.text)


def test_generate_record_entity_text_matches_type_pattern():
    rng = random.Random(42)
    record = generate_record(rng)
    for entity in record.entities:
        substring = record.text[entity.start : entity.end]
        assert len(substring) > 0


def test_generate_corpus_deterministic_with_seed():
    corpus1 = generate_corpus(n_sentences=10, seed=123)
    corpus2 = generate_corpus(n_sentences=10, seed=123)
    assert [r.text for r in corpus1] == [r.text for r in corpus2]


def test_generate_corpus_different_seeds_differ():
    corpus1 = generate_corpus(n_sentences=10, seed=1)
    corpus2 = generate_corpus(n_sentences=10, seed=2)
    assert [r.text for r in corpus1] != [r.text for r in corpus2]


def test_generate_corpus_produces_requested_count():
    corpus = generate_corpus(n_sentences=25, seed=1)
    assert len(corpus) == 25


def test_write_jsonl_round_trips(tmp_path):
    corpus = generate_corpus(n_sentences=5, seed=1)
    out_path = tmp_path / "corpus.jsonl"
    write_jsonl(corpus, str(out_path))

    lines = out_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 5
    first = json.loads(lines[0])
    assert "text" in first and "entities" in first
    assert first["text"] == corpus[0].text
