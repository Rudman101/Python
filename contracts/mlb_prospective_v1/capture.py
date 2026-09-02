"""Prospective MLB decision capture — the shadow-writer chokepoint.

capture_decision() is the single entrypoint every MLB scanner/governor/
tracking writer must call to record a decision from this point forward.
It never fabricates missing evidence (Phase 0 evidence-contract
Principle 8: unknown provenance stays unknown rather than reconstructed),
never blocks on incomplete evidence (capture is not a betting-policy gate;
the governor already decided funded units before this is called), and
always fires an evidence-quality alert for a gap in the four required
signals: model_version, decision reason, decision timestamp, usable price.

Eligibility-tier classification is not re-derived here: it reuses
contracts.mlb_replay_v1.tiers.classify_tier verbatim, because the
integrity/eligibility flags it operates on (decision_time_valid,
sportsbook_price_valid, result_valid, model_attributable,
rationale_traceable, clv_usable, ...) are generic to any MLB decision
record, not specific to replay.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from contracts.mlb_replay_v1.tiers import classify_tier

from contracts.mlb_prospective_v1 import alerts as alerts_mod
from contracts.mlb_prospective_v1.cohorts import validate_cohort_units
from contracts.mlb_prospective_v1.price_validation import (
    is_dfs_placeholder_book,
    is_valid_sportsbook_price,
)
from contracts.mlb_prospective_v1.rationale_registry import normalize_rationale
from contracts.mlb_prospective_v1.writer_registry import is_registered_writer

REQUIRED_IDENTITY_FIELDS = ("decision_id", "event_id", "market", "side", "book", "cohort")


class CaptureValidationError(ValueError):
    """Raised when a decision cannot even be structurally addressed/stored.

    This is distinct from an evidence-quality gap: it means the payload is
    missing the bare minimum needed to identify and store a row at all.
    """


def _parse_ts(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _compute_decision_time_valid(decision_ts, game_start_ts) -> bool:
    if decision_ts is None or game_start_ts is None:
        return False
    return decision_ts <= game_start_ts


def _compute_minutes_to_start(decision_ts, game_start_ts) -> Optional[float]:
    if decision_ts is None or game_start_ts is None:
        return None
    return (game_start_ts - decision_ts).total_seconds() / 60.0


@dataclass(frozen=True)
class ProspectiveMLBDecision:
    """One immutable prospective MLB decision, captured once at decision time.

    Frozen by design: settlement/CLV/closing-price enrichment must never be
    able to rewrite a field here. See contracts.mlb_prospective_v1.enrichment
    for how later outcome evidence is layered on without mutating this record.
    """

    # IDENTITY
    decision_id: str
    event_id: str
    market: str
    side: str
    book: str
    cohort: str
    player_id: Optional[str] = None
    team_id: Optional[str] = None
    line: Optional[float] = None

    # MODEL
    writer_id: str = "UNKNOWN_WRITER"
    model_version: Optional[str] = None
    model_probability: Optional[float] = None
    fair_odds: Optional[int] = None
    edge_probability: Optional[float] = None
    ev: Optional[float] = None
    confidence: Optional[Any] = None
    feature_versions: Tuple[str, ...] = field(default_factory=tuple)

    # MARKET
    odds_american: Optional[int] = None
    price_ts_utc: Optional[str] = None
    price_age_seconds: Optional[float] = None
    sharp_reference: Optional[Tuple[Tuple[str, Any], ...]] = None
    market_consensus: Optional[Any] = None
    price_provenance: Optional[str] = None

    # DECISION
    scanner_label: Optional[str] = None
    scanner_actionability_tier: Optional[str] = None
    resolver_reasons: Tuple[str, ...] = field(default_factory=tuple)
    policy_state: Optional[str] = None
    governor_decision: Optional[str] = None
    final_funded_units: float = 0.0
    tracking_stake: float = 0.0
    block_hold_reason: Optional[str] = None
    decision_ts_utc: Optional[str] = None
    original_rationale_raw: Optional[str] = None
    original_reason_dialect: Optional[str] = None
    canonical_reason_code: Optional[str] = None

    # TIMING
    game_start_ts_utc: Optional[str] = None
    minutes_to_start: Optional[float] = None

    # OUTCOME placeholder — never populated here; enrichment produces a
    # separate ProspectiveMLBOutcome instead of mutating this record.
    result: str = "unsettled"

    # INTEGRITY / ELIGIBILITY — Phase 0 contract fields, reused verbatim.
    decision_time_valid: bool = False
    sportsbook_price_valid: bool = False
    result_valid: bool = True
    model_attributable: bool = False
    rationale_traceable: bool = False
    clv_usable: bool = False
    known_provenance_damage: bool = False
    reconstructed_evidence: bool = False
    historical_missing_shadow: bool = False
    ambiguous_identity: bool = False
    conflicting_results: bool = False

    eligibility_tier: str = "TIER_C_FORENSIC_ONLY"
    exclusion_reasons: Tuple[str, ...] = field(default_factory=tuple)
    evidence_quality_warnings: Tuple[str, ...] = field(default_factory=tuple)
    captured_at_utc: str = ""


def capture_decision(
    payload: Dict[str, Any], *, writer_id: str, now: Optional[datetime] = None
) -> ProspectiveMLBDecision:
    """Capture one MLB decision at decision time. This is the only sanctioned
    entrypoint for writing a prospective MLB decision record."""
    missing = [f for f in REQUIRED_IDENTITY_FIELDS if not payload.get(f)]
    if missing:
        raise CaptureValidationError(
            f"Cannot capture MLB decision: missing structural identity fields {missing}"
        )

    now = now or datetime.now(timezone.utc)
    decision_id = payload["decision_id"]
    book = payload["book"]
    cohort = payload["cohort"]

    writer_registered = is_registered_writer(writer_id)
    raw_model_version = payload.get("model_version")
    # Unknown/unmapped writers never receive a fabricated model version,
    # even if the raw payload happens to carry a model_version string.
    model_version = raw_model_version if writer_registered else None
    model_attributable = bool(model_version) and writer_registered

    decision_ts = _parse_ts(payload.get("decision_ts_utc"))
    game_start_ts = _parse_ts(payload.get("game_start_ts_utc"))
    decision_time_valid = _compute_decision_time_valid(decision_ts, game_start_ts)
    minutes_to_start = _compute_minutes_to_start(decision_ts, game_start_ts)

    odds_american = payload.get("odds_american")
    sportsbook_price_valid = is_valid_sportsbook_price(odds_american, book)
    dfs_placeholder = is_dfs_placeholder_book(book)

    raw_reason = payload.get("original_rationale_raw")
    dialect = payload.get("original_reason_dialect")
    canonical_reason_code, rationale_traceable = normalize_rationale(dialect, raw_reason)

    final_funded_units = float(payload.get("final_funded_units", 0.0) or 0.0)
    tracking_stake = float(payload.get("tracking_stake", 0.0) or 0.0)
    block_hold_reason = payload.get("block_hold_reason")
    validate_cohort_units(cohort, final_funded_units, tracking_stake, block_hold_reason)

    flags = {
        "decision_time_valid": decision_time_valid,
        "sportsbook_price_valid": sportsbook_price_valid,
        "result_valid": True,  # "unsettled" is a valid state at capture time
        "model_attributable": model_attributable,
        "rationale_traceable": rationale_traceable,
        "clv_usable": False,  # no close exists yet at decision time
        "known_provenance_damage": False,
        "reconstructed_evidence": False,
        "historical_missing_shadow": False,
        "ambiguous_identity": False,
        "conflicting_results": False,
    }
    eligibility_tier, exclusion_reasons = classify_tier(flags)
    exclusion_reasons = list(exclusion_reasons)
    # Reuse the more specific, already-registered DFS-placeholder reason
    # code instead of the generic invalid-price code: no DFS placeholder
    # price may present as ordinary sportsbook evidence.
    if dfs_placeholder and "EXCL_INVALID_OR_PLACEHOLDER_PRICE" in exclusion_reasons:
        exclusion_reasons = [
            "EXCL_DFS_PLACEHOLDER_PRICE" if c == "EXCL_INVALID_OR_PLACEHOLDER_PRICE" else c
            for c in exclusion_reasons
        ]

    fired_alerts = alerts_mod.evaluate_decision_alerts(
        decision_id=decision_id,
        writer_registered=writer_registered,
        model_version=model_version,
        canonical_reason_code=canonical_reason_code,
        raw_reason=raw_reason,
        decision_time_valid=decision_time_valid,
        sportsbook_price_valid=sportsbook_price_valid,
    )
    alerts_mod.emit(fired_alerts)

    sharp_reference = payload.get("sharp_reference")
    sharp_reference_tuple = (
        tuple(sorted(sharp_reference.items())) if isinstance(sharp_reference, dict) else None
    )

    return ProspectiveMLBDecision(
        decision_id=decision_id,
        event_id=payload["event_id"],
        market=payload["market"],
        side=payload["side"],
        book=book,
        cohort=cohort,
        player_id=payload.get("player_id"),
        team_id=payload.get("team_id"),
        line=payload.get("line"),
        writer_id=writer_id,
        model_version=model_version,
        model_probability=payload.get("model_probability"),
        fair_odds=payload.get("fair_odds"),
        edge_probability=payload.get("edge_probability"),
        ev=payload.get("ev"),
        confidence=payload.get("confidence"),
        feature_versions=tuple(payload.get("feature_versions") or ()),
        odds_american=odds_american,
        price_ts_utc=payload.get("price_ts_utc"),
        price_age_seconds=payload.get("price_age_seconds"),
        sharp_reference=sharp_reference_tuple,
        market_consensus=payload.get("market_consensus"),
        price_provenance=payload.get("price_provenance"),
        scanner_label=payload.get("scanner_label"),
        scanner_actionability_tier=payload.get("scanner_actionability_tier"),
        resolver_reasons=tuple(payload.get("resolver_reasons") or ()),
        policy_state=payload.get("policy_state"),
        governor_decision=payload.get("governor_decision"),
        final_funded_units=final_funded_units,
        tracking_stake=tracking_stake,
        block_hold_reason=block_hold_reason,
        decision_ts_utc=payload.get("decision_ts_utc"),
        original_rationale_raw=raw_reason,
        original_reason_dialect=dialect,
        canonical_reason_code=canonical_reason_code,
        game_start_ts_utc=payload.get("game_start_ts_utc"),
        minutes_to_start=minutes_to_start,
        result="unsettled",
        decision_time_valid=decision_time_valid,
        sportsbook_price_valid=sportsbook_price_valid,
        result_valid=True,
        model_attributable=model_attributable,
        rationale_traceable=rationale_traceable,
        clv_usable=False,
        eligibility_tier=eligibility_tier,
        exclusion_reasons=tuple(exclusion_reasons),
        evidence_quality_warnings=tuple(a.code for a in fired_alerts),
        captured_at_utc=now.isoformat(),
    )
