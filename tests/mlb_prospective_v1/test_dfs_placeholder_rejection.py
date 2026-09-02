from contracts.mlb_prospective_v1.capture import capture_decision
from contracts.mlb_prospective_v1.price_validation import (
    is_dfs_placeholder_book,
    is_valid_sportsbook_price,
)


def _base_payload(**overrides):
    base = {
        "decision_id": "dec_dfs_1",
        "event_id": "evt_1",
        "market": "player_hits",
        "side": "over",
        "line": 1.5,
        "book": "prizepicks",
        "cohort": "ZERO_UNIT_TRACKING",
        "model_version": "gbm_v3.2",
        "odds_american": -119,
        "decision_ts_utc": "2026-09-01T17:00:00+00:00",
        "game_start_ts_utc": "2026-09-01T23:05:00+00:00",
        "final_funded_units": 0.0,
        "tracking_stake": 0.0,
    }
    base.update(overrides)
    return base


def test_dfs_placeholder_book_is_never_a_valid_sportsbook_price():
    assert is_dfs_placeholder_book("prizepicks") is True
    assert is_valid_sportsbook_price(-115, "prizepicks") is False


def test_real_sportsbook_is_not_flagged_as_dfs_placeholder():
    assert is_dfs_placeholder_book("draftkings") is False
    assert is_valid_sportsbook_price(-115, "draftkings") is True


def test_dfs_placeholder_price_forces_tier_c_with_specific_reason_code():
    decision = capture_decision(_base_payload(), writer_id="mlb_scanner_v1")
    assert decision.sportsbook_price_valid is False
    assert decision.eligibility_tier == "TIER_C_FORENSIC_ONLY"
    assert "EXCL_DFS_PLACEHOLDER_PRICE" in decision.exclusion_reasons
    # The generic invalid-price code must not also appear alongside the
    # more specific DFS code for the same underlying cause.
    assert "EXCL_INVALID_OR_PLACEHOLDER_PRICE" not in decision.exclusion_reasons


def test_dfs_placeholder_price_fires_unusable_price_alert():
    decision = capture_decision(_base_payload(decision_id="dec_dfs_2"), writer_id="mlb_scanner_v1")
    assert "ALERT_UNUSABLE_PRICE" in decision.evidence_quality_warnings


def test_non_dfs_invalid_price_keeps_generic_reason_code():
    decision = capture_decision(
        _base_payload(decision_id="dec_dfs_3", book="draftkings", odds_american=0),
        writer_id="mlb_scanner_v1",
    )
    assert "EXCL_INVALID_OR_PLACEHOLDER_PRICE" in decision.exclusion_reasons
    assert "EXCL_DFS_PLACEHOLDER_PRICE" not in decision.exclusion_reasons
