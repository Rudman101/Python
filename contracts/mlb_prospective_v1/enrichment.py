"""Outcome enrichment for prospective MLB decisions.

Later settlement, closing price, and CLV data is layered onto a decision
strictly as a separate, independently-keyed ProspectiveMLBOutcome record.
enrich_with_outcome() never touches the original ProspectiveMLBDecision:
the decision dataclass is frozen, this function never assigns to it, and
the enrichment payload is rejected outright if it tries to carry any
decision-time field — so later settlement can never overwrite decision-time
evidence.

Applies to every cohort, including BLOCKED_COUNTERFACTUAL: a blocked
decision still gets to accumulate eventual outcome evidence (what would
have happened), it just never carries funded units.
"""
from dataclasses import dataclass, fields as dataclass_fields
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from contracts.mlb_prospective_v1.capture import ProspectiveMLBDecision

CLOSE_PROVENANCE_BOOK_SNAPSHOT = "book_snapshot"
CLOSE_PROVENANCE_ENTRY_FALLBACK = "entry_fallback"
CLOSE_PROVENANCE_STALE_REFERENCE = "stale_reference"
CLOSE_PROVENANCE_MISSING = "missing"

VALID_CLOSE_PROVENANCE = frozenset(
    {
        CLOSE_PROVENANCE_BOOK_SNAPSHOT,
        CLOSE_PROVENANCE_ENTRY_FALLBACK,
        CLOSE_PROVENANCE_STALE_REFERENCE,
        CLOSE_PROVENANCE_MISSING,
    }
)

VALID_RESULTS = frozenset({"win", "loss", "push", "void", "unsettled"})
SETTLED_RESULTS = frozenset({"win", "loss", "push", "void"})

# Decision-time-only field names. An enrichment payload must never carry
# any of these: that would be an attempt to alter decision-time evidence
# after the fact rather than layer outcome evidence alongside it.
_DECISION_TIME_ONLY_FIELDS = frozenset(
    f.name for f in dataclass_fields(ProspectiveMLBDecision)
) - {"result", "decision_id"}


class EnrichmentLeakageError(ValueError):
    """Raised when an enrichment payload attempts to overwrite decision-time evidence."""


class ClosePriceProvenanceError(ValueError):
    """Raised when closing-price provenance is missing or not a registered state."""


@dataclass(frozen=True)
class ProspectiveMLBOutcome:
    decision_id: str
    result: str
    profit_units: Optional[float]
    result_provenance: Optional[str]
    closing_odds: Optional[int]
    closing_price_provenance: str
    clv: Optional[float]
    clv_usable: bool
    settlement_route: Optional[str]
    settlement_ts_utc: Optional[str]
    enriched_at_utc: str


def _assert_no_decision_time_leakage(outcome_payload: Dict[str, Any]) -> None:
    leaked = _DECISION_TIME_ONLY_FIELDS & outcome_payload.keys()
    if leaked:
        raise EnrichmentLeakageError(
            f"Outcome enrichment payload must not carry decision-time fields: {sorted(leaked)}"
        )


def _implied_probability(odds_american: int) -> float:
    if odds_american > 0:
        return 100.0 / (odds_american + 100.0)
    return -odds_american / (-odds_american + 100.0)


def _compute_clv(entry_odds: Optional[int], closing_odds: Optional[int]) -> Optional[float]:
    if entry_odds is None or closing_odds is None:
        return None
    return _implied_probability(closing_odds) - _implied_probability(entry_odds)


def enrich_with_outcome(
    decision: ProspectiveMLBDecision,
    outcome_payload: Dict[str, Any],
    *,
    now: Optional[datetime] = None,
) -> ProspectiveMLBOutcome:
    """Layer later outcome evidence onto `decision` without mutating it.

    `decision` is read-only input; the return value is a brand-new,
    independently-keyed ProspectiveMLBOutcome joined by decision_id.
    """
    _assert_no_decision_time_leakage(outcome_payload)

    result = outcome_payload.get("result", "unsettled")
    if result not in VALID_RESULTS:
        raise ValueError(f"Unknown result state: {result!r}")

    closing_price_provenance = outcome_payload.get(
        "closing_price_provenance", CLOSE_PROVENANCE_MISSING
    )
    if closing_price_provenance not in VALID_CLOSE_PROVENANCE:
        raise ClosePriceProvenanceError(
            f"closing_price_provenance must be one of {sorted(VALID_CLOSE_PROVENANCE)}, "
            f"got {closing_price_provenance!r}"
        )

    closing_odds = outcome_payload.get("closing_odds")
    # Only a genuine book_snapshot close makes CLV usable. entry_fallback
    # and stale_reference can never silently present as a real close.
    clv_usable = closing_price_provenance == CLOSE_PROVENANCE_BOOK_SNAPSHOT and closing_odds is not None
    clv = _compute_clv(decision.odds_american, closing_odds) if clv_usable else None

    now = now or datetime.now(timezone.utc)

    return ProspectiveMLBOutcome(
        decision_id=decision.decision_id,
        result=result,
        profit_units=outcome_payload.get("profit_units"),
        result_provenance=outcome_payload.get("result_provenance"),
        closing_odds=closing_odds,
        closing_price_provenance=closing_price_provenance,
        clv=clv,
        clv_usable=clv_usable,
        settlement_route=outcome_payload.get("settlement_route"),
        settlement_ts_utc=outcome_payload.get("settlement_ts_utc"),
        enriched_at_utc=now.isoformat(),
    )
