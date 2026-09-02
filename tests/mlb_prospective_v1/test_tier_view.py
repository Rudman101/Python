import dataclasses

from contracts.mlb_prospective_v1.capture import capture_decision
from contracts.mlb_prospective_v1.enrichment import enrich_with_outcome
from contracts.mlb_prospective_v1.tier_view import current_eligibility


def _decision(**overrides):
    payload = {
        "decision_id": "dec_tv_1",
        "event_id": "evt_1",
        "market": "moneyline",
        "side": "home",
        "book": "draftkings",
        "cohort": "OFFICIAL_GOVERNOR_BET",
        "model_version": "gbm_v3.2",
        "odds_american": -115,
        "decision_ts_utc": "2026-09-01T17:00:00+00:00",
        "game_start_ts_utc": "2026-09-01T23:05:00+00:00",
        "original_rationale_raw": "edge_above_threshold",
        "original_reason_dialect": "scanner_v1",
        "final_funded_units": 1.0,
        "tracking_stake": 0.0,
    }
    payload.update(overrides)
    return capture_decision(payload, writer_id="mlb_scanner_v1")


def test_no_outcome_yet_stays_tier_b():
    decision = _decision()
    tier, reasons = current_eligibility(dataclasses.asdict(decision), None)
    assert tier == "TIER_B_PERFORMANCE_REPLAY"
    assert reasons == ["DOWNGRADE_UNSUPPORTED_CLOSE_PROVENANCE"]


def test_genuine_close_promotes_combined_view_to_tier_a():
    decision = _decision(decision_id="dec_tv_2")
    outcome = enrich_with_outcome(
        decision, {"result": "win", "closing_odds": -108, "closing_price_provenance": "book_snapshot"}
    )
    tier, reasons = current_eligibility(dataclasses.asdict(decision), dataclasses.asdict(outcome))
    assert tier == "TIER_A_FULL_REPLAY"
    assert reasons == []
    # the underlying decision record's own frozen tier is untouched
    assert decision.eligibility_tier == "TIER_B_PERFORMANCE_REPLAY"


def test_entry_fallback_close_keeps_combined_view_at_tier_b():
    decision = _decision(decision_id="dec_tv_3")
    outcome = enrich_with_outcome(
        decision, {"result": "win", "closing_odds": -115, "closing_price_provenance": "entry_fallback"}
    )
    tier, reasons = current_eligibility(dataclasses.asdict(decision), dataclasses.asdict(outcome))
    assert tier == "TIER_B_PERFORMANCE_REPLAY"
    assert "DOWNGRADE_UNSUPPORTED_CLOSE_PROVENANCE" in reasons
