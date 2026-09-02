"""Deterministic evidence-tier classification for MLB_REPLAY_EVIDENCE_V1.

classify_tier() is the single implementation of the tier rules described in
docs/MLB_REPLAY_V1_EVIDENCE_CONTRACT.md and evidence_contract.json. Every
workstream must call this rather than re-deriving tier logic independently.
"""
from typing import Dict, List, Tuple

# Row-level flags that, when true, force TIER_C_FORENSIC_ONLY regardless of
# every other flag. Order is deterministic (dict insertion order) so
# exclusion_reasons is reproducible.
_ROW_LEVEL_BOOLEAN_EXCLUSIONS = (
    ("ambiguous_identity", "EXCL_AMBIGUOUS_IDENTITY"),
    ("conflicting_results", "EXCL_CONFLICTING_RESULTS"),
    ("known_provenance_damage", "EXCL_KNOWN_PROVENANCE_CORRUPTION"),
    ("reconstructed_evidence", "EXCL_REPLAY_RECONSTRUCTED_TIMESTAMP"),
)

# Row-level "must be true" flags. False forces TIER_C.
_ROW_LEVEL_REQUIRED_TRUE = (
    ("decision_time_valid", "EXCL_POST_START_DECISION"),
    ("sportsbook_price_valid", "EXCL_INVALID_OR_PLACEHOLDER_PRICE"),
    ("result_valid", "EXCL_RESULT_INVALID"),
)

# Claim-level flags. False downgrades to TIER_B (never TIER_C by itself).
_CLAIM_LEVEL_REQUIRED_TRUE = (
    ("model_attributable", "DOWNGRADE_MISSING_MODEL_ATTRIBUTION"),
    ("rationale_traceable", "DOWNGRADE_MISSING_RATIONALE"),
    ("clv_usable", "DOWNGRADE_UNSUPPORTED_CLOSE_PROVENANCE"),
)

TIER_A = "TIER_A_FULL_REPLAY"
TIER_B = "TIER_B_PERFORMANCE_REPLAY"
TIER_C = "TIER_C_FORENSIC_ONLY"


def classify_tier(observation: Dict) -> Tuple[str, List[str]]:
    """Classify one replay observation's integrity/eligibility fields.

    `observation` must supply the boolean fields listed in the contract's
    integrity_eligibility schema section (missing keys are treated as
    False/failing, per Principle 8: unknown provenance stays unknown, it is
    never assumed clean).

    Returns (tier, reason_codes). reason_codes is empty only for a clean
    TIER_A row with historical_missing_shadow also false.
    """
    reasons: List[str] = []

    for flag, code in _ROW_LEVEL_BOOLEAN_EXCLUSIONS:
        if observation.get(flag, False):
            reasons.append(code)

    for flag, code in _ROW_LEVEL_REQUIRED_TRUE:
        if not observation.get(flag, False):
            reasons.append(code)

    if reasons:
        return TIER_C, reasons

    for flag, code in _CLAIM_LEVEL_REQUIRED_TRUE:
        if not observation.get(flag, False):
            reasons.append(code)

    if observation.get("historical_missing_shadow", False):
        reasons.append("INFO_MISSING_SHADOW_ROW")

    blocking_downgrade_codes = {code for _, code in _CLAIM_LEVEL_REQUIRED_TRUE}
    if blocking_downgrade_codes & set(reasons):
        return TIER_B, reasons

    return TIER_A, reasons
