"""Experiment infrastructure — A/B testing with proper assignment, exposure logging,
guardrail metrics, and sequential testing.

This package replaces the monolithic experiments.py module.  All public names
are re-exported here for backward compatibility.
"""

from .registry import (
    create_experiment,
    start_experiment,
    pause_experiment,
    conclude_experiment,
    list_experiments,
    get_experiment,
    validate_pre_registration,
    freeze_config,
)
from .assignment import get_variant
from .exposure import log_exposure
from .analysis import get_experiment_results
from .guardrails import check_guardrails, DEFAULT_GUARDRAILS, GUARDRAIL_DEGRADATION_THRESHOLD
from .sequential import sequential_test
from .eligibility import check_eligibility
from .stratification import compute_stratum
from .balance import check_srm, check_covariate_balance
from .audit import log_audit_event, get_audit_log

__all__ = [
    # Registry / lifecycle
    "create_experiment",
    "start_experiment",
    "pause_experiment",
    "conclude_experiment",
    "list_experiments",
    "get_experiment",
    "validate_pre_registration",
    "freeze_config",
    # Assignment
    "get_variant",
    # Exposure
    "log_exposure",
    # Analysis
    "get_experiment_results",
    # Guardrails
    "check_guardrails",
    "DEFAULT_GUARDRAILS",
    "GUARDRAIL_DEGRADATION_THRESHOLD",
    # Sequential
    "sequential_test",
    # Eligibility
    "check_eligibility",
    # Stratification
    "compute_stratum",
    # Balance
    "check_srm",
    "check_covariate_balance",
    # Audit
    "log_audit_event",
    "get_audit_log",
]
