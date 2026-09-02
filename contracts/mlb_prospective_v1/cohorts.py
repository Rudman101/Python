"""Prospective tracking-cohort separation for MLB Replay V1 Workstream C.

Four cohorts must stay structurally distinct so a $1 manual tracking stake
can never be recorded as an official governor-funded unit, and a blocked
counterfactual can never be recorded as if money was risked.
"""
from enum import Enum
from typing import Optional


class ProspectiveCohort(str, Enum):
    OFFICIAL_GOVERNOR_BET = "OFFICIAL_GOVERNOR_BET"
    ZERO_UNIT_TRACKING = "ZERO_UNIT_TRACKING"
    MANUAL_1_DOLLAR_TRACKING = "MANUAL_$1_TRACKING"
    BLOCKED_COUNTERFACTUAL = "BLOCKED_COUNTERFACTUAL"


ALL_COHORTS = frozenset(c.value for c in ProspectiveCohort)


class CohortConflationError(ValueError):
    """Raised when a decision's units are inconsistent with its declared cohort.

    This is the single gate that keeps official engine units, manual $1
    tracking dollars, zero-unit paper tracking, and blocked counterfactuals
    from ever being conflated with one another.
    """


def validate_cohort_units(
    cohort: str,
    final_funded_units: float,
    tracking_stake: float,
    block_hold_reason: Optional[str],
) -> None:
    if cohort not in ALL_COHORTS:
        raise CohortConflationError(f"Unknown prospective cohort: {cohort!r}")

    if cohort == ProspectiveCohort.OFFICIAL_GOVERNOR_BET.value:
        if final_funded_units <= 0:
            raise CohortConflationError(
                "OFFICIAL_GOVERNOR_BET requires final_funded_units > 0 "
                "(a real governor-funded stake)"
            )
        if tracking_stake:
            raise CohortConflationError(
                "OFFICIAL_GOVERNOR_BET must not carry a manual tracking_stake "
                "value; official units and tracking dollars are separate fields "
                "and separate cohorts"
            )

    elif cohort == ProspectiveCohort.ZERO_UNIT_TRACKING.value:
        if final_funded_units != 0:
            raise CohortConflationError(
                "ZERO_UNIT_TRACKING must have final_funded_units == 0"
            )

    elif cohort == ProspectiveCohort.MANUAL_1_DOLLAR_TRACKING.value:
        if final_funded_units != 0:
            raise CohortConflationError(
                "A $1 manual tracking stake must never be recorded as an "
                "official engine unit: MANUAL_$1_TRACKING requires "
                "final_funded_units == 0"
            )
        if tracking_stake != 1:
            raise CohortConflationError(
                "MANUAL_$1_TRACKING requires tracking_stake == 1"
            )

    elif cohort == ProspectiveCohort.BLOCKED_COUNTERFACTUAL.value:
        if final_funded_units != 0:
            raise CohortConflationError(
                "BLOCKED_COUNTERFACTUAL must have final_funded_units == 0 "
                "(no money was risked)"
            )
        if not block_hold_reason:
            raise CohortConflationError(
                "BLOCKED_COUNTERFACTUAL requires a block_hold_reason"
            )
