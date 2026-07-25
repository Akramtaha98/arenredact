"""Integration tests for the regex-only pipeline (Stages 1, 3, 4, 5 — no
trained checkpoint required, so these run without the `ml` extra)."""

from arenredact.pipeline import ArEnRedactPipeline


def test_pipeline_redacts_email_and_phone():
    pipeline = ArEnRedactPipeline()
    result = pipeline.redact("Contact ahmed@example.com or +966501234567.")
    assert "[EMAIL]" in result.redacted_text
    assert "[PHONE]" in result.redacted_text
    assert "ahmed@example.com" not in result.redacted_text


def test_pipeline_records_audit_entry_by_default():
    pipeline = ArEnRedactPipeline()
    result = pipeline.redact("test@example.com")
    assert result.audit_entry is not None
    assert pipeline.audit_log.verify_chain() is True


def test_pipeline_can_skip_audit_recording():
    pipeline = ArEnRedactPipeline()
    result = pipeline.redact("test@example.com", record_audit=False)
    assert result.audit_entry is None
    assert len(pipeline.audit_log.entries) == 0


def test_pipeline_normalizes_before_detection():
    """A bidi-control-character-laden email should still be detected after
    Stage 1 normalization strips the control chars."""
    pipeline = ArEnRedactPipeline()
    result = pipeline.redact("‮test@example.com")
    assert "[EMAIL]" in result.redacted_text
    assert result.normalization_report.bidi_chars_stripped == 1


def test_pipeline_handles_clean_text_with_no_pii():
    pipeline = ArEnRedactPipeline()
    result = pipeline.redact("This sentence has no PII whatsoever.")
    assert result.redacted_text == result.normalized_text
    assert result.spans == []


def test_pipeline_multiple_redactions_chain_audit_log():
    pipeline = ArEnRedactPipeline()
    pipeline.redact("a@b.com")
    pipeline.redact("c@d.com")
    pipeline.redact("e@f.com")
    assert len(pipeline.audit_log.entries) == 3
    assert pipeline.audit_log.verify_chain() is True
