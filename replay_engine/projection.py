"""Structural anti-leakage input projection.

This is the primary anti-leakage control (the contract calls for enforcing
anti-leakage "structurally, not just by convention"). Both projection
functions below are strict *whitelists*: they copy only named fields out of
a historical row into a brand-new dict. A forbidden field can never reach
the pipeline through these functions no matter what else the historical row
contains, because nothing is copied unless it is explicitly named here.

contracts.mlb_replay_v1.anti_leakage.assert_no_leakage() is still run on the
projected payload afterward as a second, independent gate (belt-and-suspenders):
test_projection_whitelists_are_leakage_clean pins that the whitelists below
share zero fields with the contract's forbidden-field sets, so the two
controls can never silently drift apart.
"""
from typing import Any, Dict, List

from contracts.mlb_replay_v1.anti_leakage import assert_no_leakage
from contracts.mlb_replay_v1.contract import ANTI_LEAKAGE

FUTURE_OUTCOME_FIELDS = frozenset(ANTI_LEAKAGE["future_outcome_fields"])
ORIGINAL_DECISION_OUTPUT_FIELDS = frozenset(ANTI_LEAKAGE["original_decision_output_fields"])

#: Raw, decision-time-only market/event/context fields. Available in BOTH
#: replay modes. Deliberately excludes model_probability/edge_probability/
#: ev/confidence/model_version: those are the ORIGINAL model's belief
#: output, and ORIGINAL_DECISION_REPLAY must derive its own belief from raw
#: features rather than being handed the original model's answer.
RAW_DECISION_TIME_FIELDS: frozenset = frozenset(
    {
        "event_id",
        "game_date",
        "market",
        "side",
        "line",
        "player_id",
        "team_id",
        "book",
        "decision_ts_utc",
        "game_start_ts_utc",
        "minutes_to_start",
        "odds_american",
        "implied_probability",
        "consensus_state",
        "concurrent_decision_context",
        "governor_context",
        "features",
        "market_snapshots",
    }
)

#: The historical model's own belief output. Only ever projected under
#: POLICY_COUNTERFACTUAL, where it is used to build a *fixed* ScannerResult
#: without calling the scanner port at all.
HISTORICAL_BELIEF_FIELDS: frozenset = frozenset(
    {
        "model_probability",
        "edge_probability",
        "ev",
        "confidence",
        "model_version",
    }
)


def _filter_past_snapshots(payload: Dict[str, Any], decision_ts_utc: Any) -> None:
    """Drop any market_snapshots entry timestamped after decision_ts_utc.

    Structural belt-and-suspenders alongside assert_no_leakage's own
    snapshot check: even a malformed/extra-future snapshot never reaches the
    pipeline, it is simply not copied into the payload in the first place.
    """
    snapshots = payload.get("market_snapshots")
    if not snapshots:
        return
    from contracts.mlb_replay_v1.anti_leakage import _to_comparable

    cutoff = _to_comparable(decision_ts_utc)
    payload["market_snapshots"] = [
        snap
        for snap in snapshots
        if not (isinstance(snap, dict) and snap.get("snapshot_ts_utc") and _to_comparable(snap["snapshot_ts_utc"]) > cutoff)
    ]


def project_raw_replay_payload(historical_row: Dict[str, Any]) -> Dict[str, Any]:
    """Whitelist projection for ORIGINAL_DECISION_REPLAY: raw features only."""
    payload = {k: historical_row[k] for k in RAW_DECISION_TIME_FIELDS if k in historical_row}
    if "decision_ts_utc" in payload:
        _filter_past_snapshots(payload, payload["decision_ts_utc"])
    assert_no_leakage(payload, decision_ts_utc=payload.get("decision_ts_utc"))
    return payload


def project_policy_counterfactual_payload(historical_row: Dict[str, Any]) -> Dict[str, Any]:
    """Whitelist projection for POLICY_COUNTERFACTUAL: raw features + fixed historical belief."""
    payload = project_raw_replay_payload(historical_row)
    for k in HISTORICAL_BELIEF_FIELDS:
        if k in historical_row:
            payload[k] = historical_row[k]
    assert_no_leakage(payload, decision_ts_utc=payload.get("decision_ts_utc"))
    return payload


def whitelist_fields_for_mode(mode_name: str) -> List[str]:
    """The set of historical-row field names a given mode's payload may draw from."""
    if mode_name == "POLICY_COUNTERFACTUAL":
        return sorted(RAW_DECISION_TIME_FIELDS | HISTORICAL_BELIEF_FIELDS)
    return sorted(RAW_DECISION_TIME_FIELDS)
