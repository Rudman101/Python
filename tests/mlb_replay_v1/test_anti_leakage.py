import pytest

from contracts.mlb_replay_v1.anti_leakage import (
    FORBIDDEN_REPLAY_INPUT_FIELDS,
    FUTURE_OUTCOME_FIELDS,
    ORIGINAL_DECISION_OUTPUT_FIELDS,
    LeakageError,
    assert_no_leakage,
)


def _clean_payload():
    return {
        "historical_decision_id": "hd_1",
        "event_id": "evt_1",
        "market": "player_strikeouts",
        "side": "over",
        "line": 6.5,
        "odds_american": -115,
        "decision_ts_utc": "2026-08-01T17:00:00+00:00",
        "game_start_ts_utc": "2026-08-01T23:05:00+00:00",
    }


def test_clean_payload_passes():
    assert_no_leakage(_clean_payload())  # should not raise


@pytest.mark.parametrize("field", sorted(FUTURE_OUTCOME_FIELDS))
def test_future_outcome_fields_are_rejected(field):
    payload = _clean_payload()
    payload[field] = "leaked-value"
    with pytest.raises(LeakageError):
        assert_no_leakage(payload)


@pytest.mark.parametrize("field", sorted(ORIGINAL_DECISION_OUTPUT_FIELDS))
def test_original_decision_output_fields_are_rejected(field):
    payload = _clean_payload()
    payload[field] = "leaked-value"
    with pytest.raises(LeakageError):
        assert_no_leakage(payload)


def test_forbidden_field_set_is_union_of_both_categories():
    assert FORBIDDEN_REPLAY_INPUT_FIELDS == FUTURE_OUTCOME_FIELDS | ORIGINAL_DECISION_OUTPUT_FIELDS
    assert len(FORBIDDEN_REPLAY_INPUT_FIELDS) >= 8


def test_future_market_snapshot_is_rejected():
    payload = _clean_payload()
    payload["market_snapshots"] = [
        {"snapshot_ts_utc": "2026-08-01T16:00:00+00:00"},  # before decision, fine
        {"snapshot_ts_utc": "2026-08-01T18:00:00+00:00"},  # after decision, leak
    ]
    with pytest.raises(LeakageError):
        assert_no_leakage(payload, decision_ts_utc=payload["decision_ts_utc"])


def test_past_market_snapshots_are_allowed():
    payload = _clean_payload()
    payload["market_snapshots"] = [
        {"snapshot_ts_utc": "2026-08-01T15:00:00+00:00"},
        {"snapshot_ts_utc": "2026-08-01T16:59:00+00:00"},
    ]
    assert_no_leakage(payload, decision_ts_utc=payload["decision_ts_utc"])  # should not raise


def test_postgame_stats_field_is_rejected():
    payload = _clean_payload()
    payload["postgame_stats"] = {"final_score": "4-2"}
    with pytest.raises(LeakageError):
        assert_no_leakage(payload)


def test_snapshot_check_is_skipped_without_decision_ts():
    payload = _clean_payload()
    payload["market_snapshots"] = [{"snapshot_ts_utc": "2099-01-01T00:00:00+00:00"}]
    # No decision_ts_utc supplied: the structural future-snapshot check is a
    # no-op, but this does not clear the caller of supplying decision_ts_utc
    # in real replay code paths (see docs contract, ANTI-LEAKAGE section).
    assert_no_leakage(payload)  # should not raise
