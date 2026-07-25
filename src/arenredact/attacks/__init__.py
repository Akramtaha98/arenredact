"""Adversarial perturbation operators used to construct the adversarial test
set (Section 5.2) and to augment training data (Section 4.2, Stage 2)."""

from arenredact.attacks.operators import (
    AttackOperator,
    apply_combined_attack,
    apply_diacritization_attack,
    apply_homoglyph_substitution,
    apply_tatweel_injection,
    arabizi_substitution,
)

__all__ = [
    "AttackOperator",
    "arabizi_substitution",
    "apply_tatweel_injection",
    "apply_diacritization_attack",
    "apply_homoglyph_substitution",
    "apply_combined_attack",
]
