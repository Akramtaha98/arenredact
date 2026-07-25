"""Tests for Stage 5 (arenredact.audit_log) — Section 4.5 / 7.3."""

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from arenredact.audit_log import AuditLog, sha256_hex
from arenredact.span_fusion import Span, SpanOrigin


def test_sha256_hex_deterministic():
    assert sha256_hex("hello") == sha256_hex("hello")
    assert sha256_hex("hello") != sha256_hex("world")


def test_append_returns_entry_with_expected_fields():
    log = AuditLog()
    spans = [Span(start=0, end=4, entity_type="PERSON", origin=SpanOrigin.NEURAL)]
    entry = log.append(
        input_text="محمد قال",
        output_text="[PERSON] قال",
        spans=spans,
        model_version_hash="test-v1",
        client_cert_fingerprint="sha256:abc",
    )
    assert entry.model_version_hash == "test-v1"
    assert entry.entity_labels == [{"entity_type": "PERSON", "start": 0, "end": 4}]
    assert entry.previous_entry_hash == AuditLog.GENESIS_HASH
    assert entry.signature != ""


def test_verify_chain_true_for_untampered_log():
    log = AuditLog()
    for i in range(5):
        log.append(
            input_text=f"input {i}",
            output_text=f"output {i}",
            spans=[],
            model_version_hash="v1",
            client_cert_fingerprint="sha256:abc",
        )
    assert log.verify_chain() is True


def test_verify_chain_false_if_entry_tampered():
    log = AuditLog()
    log.append("in1", "out1", [], "v1", "sha256:abc")
    log.append("in2", "out2", [], "v1", "sha256:abc")

    # Tamper with the first entry's recorded output hash after the fact.
    log._entries[0].output_hash = "0" * 64
    assert log.verify_chain() is False


def test_verify_chain_false_if_signature_invalid():
    log = AuditLog()
    log.append("in1", "out1", [], "v1", "sha256:abc")
    log._entries[0].signature = "00" * 64  # corrupt signature, still valid hex
    assert log.verify_chain() is False


def test_hash_chaining_links_entries():
    log = AuditLog()
    e1 = log.append("in1", "out1", [], "v1", "sha256:abc")
    e2 = log.append("in2", "out2", [], "v1", "sha256:abc")
    assert e2.previous_entry_hash == e1.entry_hash()


def test_public_key_bytes_length_matches_ed25519():
    log = AuditLog(private_key=Ed25519PrivateKey.generate())
    assert len(log.public_key_bytes()) == 32


def test_no_raw_text_stored_only_hashes():
    """LINDDUN Data Disclosure mitigation: entries must never contain the raw
    input/output text, only hashes and offset/type metadata."""
    log = AuditLog()
    secret_text = "محمد رقمه +966501234567"
    entry = log.append(secret_text, "[REDACTED]", [], "v1", "sha256:abc")
    serialized = str(entry.canonical_bytes())
    assert secret_text not in serialized
