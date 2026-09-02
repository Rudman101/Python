import pytest

from contracts.mlb_prospective_v1.capture import capture_decision
from contracts.mlb_prospective_v1.cohorts import CohortConflationError, validate_cohort_units
from contracts.mlb_prospective_v1.enrichment import enrich_with_outcome


def _base_payload(**overrides):
    base = {
        "decision_id": "dec_cohort_1",
        "event_id": "evt_1",
        "market": "team_total",
        "side": "over",
        "book": "circa",
        "cohort": "OFFICIAL_GOVERNOR_BET",
        "model_version": "gbm_v3.2",
        "odds_american": -110,
        "decision_ts_utc": "2026-09-01T17:00:00+00:00",
        "game_start_ts_utc": "2026-09-01T23:05:00+00:00",
        "final_funded_units": 1.0,
        "tracking_stake": 0.0,
    }
    base.update(overrides)
    return base


def test_manual_dollar_tracking_can_never_carry_official_units():
    with pytest.raises(CohortConflationError):
        validate_cohort_units(
            "MANUAL_$1_TRACKING", final_funded_units=1.0, tracking_stake=1.0, block_hold_reason=None
        )


def test_manual_dollar_tracking_requires_exactly_one_dollar_stake():
    with pytest.raises(CohortConflationError):
        validate_cohort_units(
            "MANUAL_$1_TRACKING", final_funded_units=0.0, tracking_stake=5.0, block_hold_reason=None
        )


def test_official_bet_cannot_carry_a_manual_tracking_stake():
    with pytest.raises(CohortConflationError):
        validate_cohort_units(
            "OFFICIAL_GOVERNOR_BET", final_funded_units=1.0, tracking_stake=1.0, block_hold_reason=None
        )


def test_official_bet_requires_positive_funded_units():
    with pytest.raises(CohortConflationError):
        validate_cohort_units(
            "OFFICIAL_GOVERNOR_BET", final_funded_units=0.0, tracking_stake=0.0, block_hold_reason=None
        )


def test_zero_unit_tracking_cannot_carry_funded_units():
    with pytest.raises(CohortConflationError):
        validate_cohort_units(
            "ZERO_UNIT_TRACKING", final_funded_units=1.0, tracking_stake=0.0, block_hold_reason=None
        )


def test_blocked_counterfactual_requires_a_reason_and_zero_units():
    with pytest.raises(CohortConflationError):
        validate_cohort_units(
            "BLOCKED_COUNTERFACTUAL", final_funded_units=0.0, tracking_stake=0.0, block_hold_reason=None
        )
    with pytest.raises(CohortConflationError):
        validate_cohort_units(
            "BLOCKED_COUNTERFACTUAL", final_funded_units=1.0, tracking_stake=0.0, block_hold_reason="exposure_cap"
        )
    # valid case does not raise
    validate_cohort_units(
        "BLOCKED_COUNTERFACTUAL", final_funded_units=0.0, tracking_stake=0.0, block_hold_reason="exposure_cap"
    )


def test_unknown_cohort_is_rejected():
    with pytest.raises(CohortConflationError):
        validate_cohort_units("SOME_OTHER_COHORT", 0.0, 0.0, None)


def test_capture_rejects_conflated_manual_tracking_payload():
    payload = _base_payload(
        decision_id="dec_cohort_2",
        cohort="MANUAL_$1_TRACKING",
        final_funded_units=1.0,  # conflated with official units -- must reject
        tracking_stake=1.0,
    )
    with pytest.raises(CohortConflationError):
        capture_decision(payload, writer_id="mlb_manual_tracking_v1")


def test_blocked_counterfactual_decision_still_receives_eventual_outcome_evidence():
    payload = _base_payload(
        decision_id="dec_blocked_1",
        cohort="BLOCKED_COUNTERFACTUAL",
        final_funded_units=0.0,
        tracking_stake=0.0,
        block_hold_reason="GOVERNOR_HELD_EXPOSURE_CAP",
    )
    decision = capture_decision(payload, writer_id="mlb_governor_v1")
    assert decision.cohort == "BLOCKED_COUNTERFACTUAL"
    assert decision.final_funded_units == 0.0

    outcome = enrich_with_outcome(
        decision,
        {
            "result": "win",
            "closing_odds": -105,
            "closing_price_provenance": "book_snapshot",
            "settlement_route": "counterfactual_grading",
        },
    )
    assert outcome.decision_id == decision.decision_id
    assert outcome.result == "win"
    assert outcome.clv_usable is True
