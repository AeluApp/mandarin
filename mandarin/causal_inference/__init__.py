"""Causal inference toolkit — DAG documentation, sensitivity analysis, mediation."""

from .dag import CausalDAG, document_confounders, check_backdoor_criterion, suggest_controls
from .sensitivity import compute_sensitivity
from .mediation import test_mediation

__all__ = [
    # DAG
    "CausalDAG",
    "document_confounders",
    "check_backdoor_criterion",
    "suggest_controls",
    # Sensitivity
    "compute_sensitivity",
    # Mediation
    "test_mediation",
]
