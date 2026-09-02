"""Synthetic + small known-good historical rows for the Workstream B
validation set.

Every row is shaped like a canonical replay_observation input per
contracts/mlb_replay_v1/evidence_contract.json's identity/decision_time_evidence/
outcome sections, plus the extra decision-time-only context fields the
reference pipeline consumes (features, governor_context,
concurrent_decision_context — all legitimately available at decision time,
never future information) and an integrity_eligibility block consumed by
contracts.mlb_replay_v1.tiers.classify_tier.

VALIDATION_SET maps a required scenario name (matching the Workstream B
spec's validation-set list verbatim) to its historical row, so tests and the
benchmark script can iterate the whole set without re-deriving it.
"""
import copy
from typing import Any, Dict

_CLEAN_INTEGRITY: Dict[str, bool] = {
    "decision_time_valid": True,
    "sportsbook_price_valid": True,
    "result_valid": True,
    "model_attributable": True,
    "rationale_traceable": True,
    "clv_usable": True,
    "known_provenance_damage": False,
    "reconstructed_evidence": False,
    "historical_missing_shadow": False,
    "ambiguous_identity": False,
    "conflicting_results": False,
}


def make_base_row(**overrides: Any) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "historical_decision_id": "hd_default",
        "source_identity": "src_default",
        "source_table": "historical_mlb_decisions",
        "shadow_bet_id": "shadow_default",
        "event_id": "evt_default",
        "game_date": "2026-08-01",
        "market": "player_strikeouts",
        "side": "over",
        "line": 6.5,
        "player_id": "player_1",
        "team_id": None,
        "book": "consensus_book",
        "sport": "MLB",
        "decision_ts_utc": "2026-08-01T17:00:00+00:00",
        "game_start_ts_utc": "2026-08-01T23:05:00+00:00",
        "minutes_to_start": 365.0,
        "odds_american": -115,
        "implied_probability": 0.5349,
        "model_probability": 0.58,
        "edge_probability": 0.0451,
        "ev": 0.0451,
        "confidence": "high",
        "consensus_state": "consensus",
        "original_rationale": "Historical model liked the over based on recent K rate.",
        "original_reason_dialect": "legacy_v3",
        "policy_state": "ALLOWED",
        "governor_state": "APPROVED",
        "original_recommended_units": 1.0,
        "original_shadow_units": 1.0,
        "model_version": "MODELFAM1.3.2",
        "result": "win",
        "profit_units": 0.87,
        "result_provenance": "settlement_service",
        "closing_odds": -120,
        "closing_price_provenance": "book_snapshot",
        "clv": 0.02,
        "settlement_route": "auto_settlement",
        "features": {"current_model_edge_signal": 0.05, "current_model_confidence": "high"},
        "governor_context": {"exposure_cap_hit": False},
        "concurrent_decision_context": [],
        "integrity_eligibility": dict(_CLEAN_INTEGRITY),
    }
    for k, v in overrides.items():
        row[k] = v
    return row


def with_integrity(row: Dict[str, Any], **flags: bool) -> Dict[str, Any]:
    row = copy.deepcopy(row)
    row["integrity_eligibility"] = {**row["integrity_eligibility"], **flags}
    return row


def current_model_agrees_with_original_action() -> Dict[str, Any]:
    # Both the historical decision and today's pipeline land on BET.
    return make_base_row(
        historical_decision_id="hd_agrees",
        features={"current_model_edge_signal": 0.05, "current_model_confidence": "high"},
    )


def current_model_rejects_historical_bet() -> Dict[str, Any]:
    # Historical action was BET; today's model sees no edge.
    return make_base_row(
        historical_decision_id="hd_model_rejects",
        features={"current_model_edge_signal": 0.0, "current_model_confidence": "low"},
    )


def current_governor_blocks_scanner_bet() -> Dict[str, Any]:
    # Scanner/resolver still confirm BET, but governor exposure context (a
    # legitimate decision-time signal) blocks it today.
    return make_base_row(
        historical_decision_id="hd_governor_blocks",
        features={"current_model_edge_signal": 0.05, "current_model_confidence": "high"},
        governor_context={"exposure_cap_hit": True},
    )


def historical_block_current_system_would_accept() -> Dict[str, Any]:
    # Original decision was blocked/no-action; today's pipeline would BET.
    return make_base_row(
        historical_decision_id="hd_historical_block_now_accepts",
        original_recommended_units=0.0,
        original_shadow_units=0.0,
        governor_state="BLOCKED",
        policy_state="BLOCKED",
        features={"current_model_edge_signal": 0.05, "current_model_confidence": "high"},
        governor_context={"exposure_cap_hit": False},
    )


def missing_model_version() -> Dict[str, Any]:
    row = make_base_row(
        historical_decision_id="hd_missing_model_version",
        model_version=None,
        model_probability=None,
        edge_probability=None,
        ev=None,
        confidence=None,
    )
    return with_integrity(row, model_attributable=False)


def missing_rationale() -> Dict[str, Any]:
    row = make_base_row(historical_decision_id="hd_missing_rationale", original_rationale=None)
    return with_integrity(row, rationale_traceable=False)


def tier_b_row() -> Dict[str, Any]:
    # Unsupported close provenance downgrades to Tier B without excluding
    # the row (contract: claim-level downgrade, not a row-level exclusion).
    row = make_base_row(
        historical_decision_id="hd_tier_b_unsupported_close",
        closing_price_provenance="entry_fallback",
    )
    return with_integrity(row, clv_usable=False)


def tier_c_rejection() -> Dict[str, Any]:
    # Known provenance corruption forces Tier C regardless of everything else.
    row = make_base_row(historical_decision_id="hd_tier_c_known_provenance_damage")
    return with_integrity(row, known_provenance_damage=True)


def contradictory_side() -> Dict[str, Any]:
    # A decision already exists on the opposite side of the same
    # market/event at decision time -- known before T, not leakage.
    return make_base_row(
        historical_decision_id="hd_contradictory_side",
        concurrent_decision_context=[
            {
                "market": "player_strikeouts",
                "event_id": "evt_default",
                "side": "under",
                "decision_ts_utc": "2026-08-01T16:55:00+00:00",
            }
        ],
    )


def post_start_exclusion() -> Dict[str, Any]:
    row = make_base_row(
        historical_decision_id="hd_post_start_exclusion",
        decision_ts_utc="2026-08-01T23:10:00+00:00",
        minutes_to_start=-5.0,
    )
    return with_integrity(row, decision_time_valid=False)


def dfs_invalid_price_exclusion() -> Dict[str, Any]:
    row = make_base_row(
        historical_decision_id="hd_dfs_invalid_price",
        book="dfs_placeholder_book",
    )
    return with_integrity(row, sportsbook_price_valid=False)


VALIDATION_SET: Dict[str, Dict[str, Any]] = {
    "current model agrees with original action": current_model_agrees_with_original_action(),
    "current model rejects historical bet": current_model_rejects_historical_bet(),
    "current governor blocks scanner BET": current_governor_blocks_scanner_bet(),
    "historical block current system would accept": historical_block_current_system_would_accept(),
    "missing model version": missing_model_version(),
    "missing rationale": missing_rationale(),
    "Tier B row": tier_b_row(),
    "Tier C rejection": tier_c_rejection(),
    "contradictory side": contradictory_side(),
    "post-start exclusion": post_start_exclusion(),
    "DFS invalid-price exclusion": dfs_invalid_price_exclusion(),
}
