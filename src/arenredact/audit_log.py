"""Stage 5 — Cryptographic Audit Logging.

Implements the single-node hash-chained, Ed25519-signed append-only log
entry format described in Section 4.5 / 7.3 of the paper. Each entry
contains: transaction ID, SHA-256 hash of the NFKC-normalized input, redaction
output hash, entity type labels and span offsets, model version hash, TLS
client certificate fingerprint of the submitting principal, and the hash of
the preceding log entry (hash chaining).

Threat model and limits (revision 2):

* What is protected. Signatures give authenticity and per-entry integrity;
  hash chaining detects deletion or reordering of entries in the MIDDLE of
  the log.
* Linkability / guessing. Plain SHA-256 of a low-entropy input (a phone
  number, a short sentence) can be confirmed by anyone who guesses the input.
  Input and output digests are therefore HMAC-SHA256 values under a secret
  `hash_key` (random per log unless supplied), so a log reader without the key
  cannot confirm guesses or link records across logs. Whoever holds the key
  can still test guesses; the key must be kept in a KMS/HSM. Entity offsets
  and types are stored in clear and still reveal where PII sat.
* Tail truncation. A hash chain cannot show that the last entries were
  deleted. `checkpoint()` returns a signed (entry count, head hash) record;
  a verifier that stores the latest checkpoint out of band can detect
  truncation with `verify_checkpoint()`.
* Confidentiality. Nothing here encrypts the log; signatures do not provide
  secrecy.
* Offsets. Offsets and hashes refer to the Stage 1 NORMALIZED text, which can
  differ in length from the submitted text (NFKC expands some characters).
  The redacted output returned to callers is likewise a redaction of the
  normalized text.

Scope note: this module implements the single-node log format and signing
scheme only. The Byzantine-fault-tolerant PBFT replication across n=4 nodes
(tolerating f=1 Byzantine fault) described in Section 7.3 of the paper is
**not** implemented here — see the paper's Section 8.4 (Limitations), which
identifies formal verification of the PBFT layer as a prerequisite for
production deployment. This module is the building block that a PBFT
replication layer would sit on top of.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization

from arenredact.span_fusion import Span


def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


@dataclass
class AuditLogEntry:
    transaction_id: str
    timestamp: float
    input_hash: str
    output_hash: str
    entity_labels: list[dict]  # [{"entity_type": ..., "start": ..., "end": ...}, ...]
    model_version_hash: str
    client_cert_fingerprint: str
    previous_entry_hash: str
    signature: str = field(default="", compare=False)

    def canonical_bytes(self) -> bytes:
        """Deterministic serialization for hashing/signing — excludes the
        signature field itself (a signature cannot sign over itself)."""
        payload = asdict(self)
        payload.pop("signature", None)
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def entry_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


class AuditLog:
    """A single-node, hash-chained, Ed25519-signed append-only redaction log.

    Example:
        log = AuditLog(private_key=Ed25519PrivateKey.generate())
        entry = log.append(
            input_text=normalized_input,
            output_text=redacted_output,
            spans=fused_spans,
            model_version_hash="xlmr-lora-r8-v3",
            client_cert_fingerprint="sha256:ab12...",
        )
        assert log.verify_chain()
    """

    #: Genesis hash — the "previous_entry_hash" for the first entry in a chain.
    GENESIS_HASH = "0" * 64

    def __init__(
        self,
        private_key: Ed25519PrivateKey | None = None,
        hash_key: bytes | None = None,
    ):
        self.hash_key = hash_key if hash_key is not None else os.urandom(32)
        self.private_key = private_key or Ed25519PrivateKey.generate()
        self.public_key: Ed25519PublicKey = self.private_key.public_key()
        self._entries: list[AuditLogEntry] = []

    @property
    def entries(self) -> list[AuditLogEntry]:
        return list(self._entries)

    def keyed_digest(self, data: str) -> str:
        """HMAC-SHA256 under the log's secret hash key (see threat model)."""
        return hmac.new(self.hash_key, data.encode("utf-8"), hashlib.sha256).hexdigest()

    def _last_hash(self) -> str:
        return self._entries[-1].entry_hash() if self._entries else self.GENESIS_HASH

    def append(
        self,
        input_text: str,
        output_text: str,
        spans: list[Span],
        model_version_hash: str,
        client_cert_fingerprint: str,
    ) -> AuditLogEntry:
        """Append a new signed, hash-chained entry recording one redaction
        decision. Per Section 4.3 / LINDDUN Data Disclosure mitigation, only
        *hashes* of input/output are logged — never raw text — and entity
        spans are logged as offsets/types only, never the underlying PII
        substrings."""
        entry = AuditLogEntry(
            transaction_id=str(uuid.uuid4()),
            timestamp=time.time(),
            input_hash=self.keyed_digest(input_text),
            output_hash=self.keyed_digest(output_text),
            entity_labels=[
                {"entity_type": s.entity_type, "start": s.start, "end": s.end}
                for s in spans
            ],
            model_version_hash=model_version_hash,
            client_cert_fingerprint=client_cert_fingerprint,
            previous_entry_hash=self._last_hash(),
        )
        signature = self.private_key.sign(entry.canonical_bytes())
        entry.signature = signature.hex()

        self._entries.append(entry)
        return entry

    def verify_chain(self) -> bool:
        """Verify hash chaining (Repudiation mitigation) and Ed25519
        signatures (Tampering mitigation) across the full log."""
        expected_prev = self.GENESIS_HASH
        for entry in self._entries:
            if entry.previous_entry_hash != expected_prev:
                return False
            try:
                self.public_key.verify(bytes.fromhex(entry.signature), entry.canonical_bytes())
            except Exception:
                return False
            expected_prev = entry.entry_hash()
        return True

    def checkpoint(self) -> dict:
        """Signed statement of how many entries exist and the head hash."""
        body = {"count": len(self._entries), "head_hash": self._last_hash()}
        payload = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return {**body, "signature": self.private_key.sign(payload).hex()}

    def verify_checkpoint(self, checkpoint: dict) -> bool:
        """True if `checkpoint` is validly signed AND the current log still
        contains at least that many entries whose head at that count matches.
        A log truncated below the checkpoint count fails."""
        body = {"count": checkpoint["count"], "head_hash": checkpoint["head_hash"]}
        payload = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        try:
            self.public_key.verify(bytes.fromhex(checkpoint["signature"]), payload)
        except Exception:
            return False
        n = checkpoint["count"]
        if len(self._entries) < n:
            return False
        head = self._entries[n - 1].entry_hash() if n else self.GENESIS_HASH
        return head == checkpoint["head_hash"]

    def public_key_bytes(self) -> bytes:
        """Raw public key bytes, for distribution to auditors / other PBFT
        replica nodes in a multi-node deployment (see module docstring)."""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
