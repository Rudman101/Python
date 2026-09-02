import pytest

from contracts.mlb_prospective_v1.capture import CaptureValidationError, capture_decision


def _base_payload(**overrides):
    base = {
        "decision_id": "dec_1",
        "event_id": "evt_1",
        "market": "player_strikeouts",
        "side": "over",
        "line": 6.5,
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
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    "field", ["decision_id", "event_id", "market", "side", "book", "cohort"]
)
def test_missing_structural_identity_field_raises(field):
    payload = _base_payload()
    del payload[field]
    with pytest.raises(CaptureValidationError):
        capture_decision(payload, writer_id="mlb_scanner_v1")


def test_fully_clean_decision_captures_as_tier_b_pending_close():
    # A decision can never be TIER_A at capture time: no closing price
    # exists yet, so clv_usable is correctly False until enrichment runs.
    # This caps every freshly-captured decision at TIER_B, never TIER_A.
    decision = capture_decision(_base_payload(), writer_id="mlb_scanner_v1")
    assert decision.eligibility_tier == "TIER_B_PERFORMANCE_REPLAY"
    assert decision.exclusion_reasons == ("DOWNGRADE_UNSUPPORTED_CLOSE_PROVENANCE",)
    assert decision.evidence_quality_warnings == ()
    assert decision.model_attributable is True
    assert decision.rationale_traceable is True
    assert decision.decision_time_valid is True
    assert decision.sportsbook_price_valid is True
    assert decision.result == "unsettled"
    assert decision.result_valid is True


def test_minutes_to_start_is_derived():
    decision = capture_decision(_base_payload(), writer_id="mlb_scanner_v1")
    assert decision.minutes_to_start == pytest.approx(365.0)


def test_capture_never_raises_for_incomplete_evidence_only_alerts():
    # Missing model_version/rationale/price/timestamp must not block capture
    # itself -- only structural identity fields do that.
    payload = _base_payload(
        model_version=None,
        original_rationale_raw=None,
        original_reason_dialect=None,
        odds_american=None,
        decision_ts_utc=None,
    )
    decision = capture_decision(payload, writer_id="mlb_scanner_v1")
    assert decision.eligibility_tier == "TIER_C_FORENSIC_ONLY"
    assert "ALERT_MISSING_MODEL_VERSION" in decision.evidence_quality_warnings
    assert "ALERT_MISSING_DECISION_REASON" in decision.evidence_quality_warnings
    assert "ALERT_INVALID_DECISION_TIMESTAMP" in decision.evidence_quality_warnings
    assert "ALERT_UNUSABLE_PRICE" in decision.evidence_quality_warnings
