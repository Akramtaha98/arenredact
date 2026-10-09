"""ArEnRedact — adversarially hardened PII redaction for Arabic-English code-mixed text.

Reference implementation of the five-stage pipeline described in Section 4 of
"Adversarial Resilience and Privacy-Preserving PII Redaction in Arabic-English
Code-Mixed Network Traffic: A Threat-Driven Hybrid Architecture."
"""

from arenredact.span_fusion import Span, fuse_spans
from arenredact.pattern_engine import PatternEngine
from arenredact.preprocessing import normalize

__version__ = "0.1.0"

__all__ = ["Span", "fuse_spans", "PatternEngine", "normalize", "__version__"]
