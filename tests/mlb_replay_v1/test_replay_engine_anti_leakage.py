"""Structural anti-leakage proofs for the Workstream B replay engine.

These tests deliberately insert future/original-output information into a
historical row and prove the replay engine's decision cannot see it or
depend on it -- not just that a hand-written payload happens to omit it.
"""
import copy

import pytest

from contracts.mlb_replay_v1.anti_leakage import (
    FUTURE_OUTCOME_FIELDS,
    ORIGINAL_DECISION_OUTPUT_FIELDS,
    LeakageError,
)
from fixtures.mlb_replay_v1.validation_set import current_model_agrees_with_original_action
from replay_engine.engine import run_decision
from replay_engine.modes import ReplayMode
from replay_engine.projection import (
    HISTORICAL_BELIEF_FIELDS,
    RAW_DECISION_TIME_FIELDS,
    project_policy_counterfactual_payload,
    project_raw_replay_payload,
)
from replay_engine.reference_pipeline import build_reference_pipeline

ALL_FORBIDDEN_FIELDS = FUTURE_OUTCOME_FIELDS | ORIGINAL_DECISION_OUTPUT_FIELDS


_NUMERIC_FORBIDDEN_FIELDS = {
    "original_recommended_units",
    "original_shadow_units",
    "profit_units",
    "clv",
    "closing_odds",
}


def _leaked_value_for(field):
    # Type-appropriate poison values: run_decision legitimately reads a few
    # of these ORIGINAL_DECISION_OUTPUT_FIELDS post-hoc (for the
    # differences-from-original comparison, never as pipeline input), so
    # the poison must be a value that code path can still parse -- the
    # point of this test is proving the *pipeline decision* is unaffected,
    # not crashing unrelated comparison code with a type mismatch.
    if field in _NUMERIC_FORBIDDEN_FIELDS:
        return 999.0
    return "LEAKED_FUTURE_VALUE"


def _row_with_every_forbidden_field_poisoned():
    row = current_model_agrees_with_original_action()
    poisoned = copy.deepcopy(row)
    for field in ALL_FORBIDDEN_FIELDS:
        poisoned[field] = _leaked_value_for(field)
    return row, poisoned


def test_raw_projection_whitelist_shares_no_fields_with_forbidden_sets():
    assert not (RAW_DECISION_TIME_FIELDS & ALL_FORBIDDEN_FIELDS)


def test_policy_counterfactual_whitelist_shares_no_fields_with_forbidden_sets():
    assert not ((RAW_DECISION_TIME_FIELDS | HISTORICAL_BELIEF_FIELDS) & ALL_FORBIDDEN_FIELDS)


@pytest.mark.parametrize("field", sorted(ALL_FORBIDDEN_FIELDS))
def test_raw_projection_never_carries_a_forbidden_field(field):
    row = current_model_agrees_with_original_action()
    row = dict(row)
    row[field] = "LEAKED_FUTURE_VALUE"
    payload = project_raw_replay_payload(row)
    assert field not in payload


@pytest.mark.parametrize("field", sorted(ALL_FORBIDDEN_FIELDS))
def test_policy_counterfactual_projection_never_carries_a_forbidden_field(field):
    row = current_model_agrees_with_original_action()
    row = dict(row)
    row[field] = "LEAKED_FUTURE_VALUE"
    payload = project_policy_counterfactual_payload(row)
    assert field not in payload


def test_replay_decision_is_byte_identical_whether_or_not_future_fields_are_present():
    """The core anti-leakage proof: inserting future/original-output data
    into the historical row must not change the replay engine's decision
    at all -- not the action, not the units, not the output hash."""
    clean_row, poisoned_row = _row_with_every_forbidden_field_poisoned()
    pipeline = build_reference_pipeline()
    policy_config = {"max_units": 2.0}

    sealed_clean = run_decision(
        clean_row, ReplayMode.ORIGINAL_DECISION_REPLAY, pipeline, policy_config, "POLICY_V1",
        replay_observation_id="x", replay_ts_utc="2026-09-02T00:00:00+00:00",
    )
    sealed_poisoned = run_decision(
        poisoned_row, ReplayMode.ORIGINAL_DECISION_REPLAY, pipeline, policy_config, "POLICY_V1",
        replay_observation_id="x", replay_ts_utc="2026-09-02T00:00:00+00:00",
    )

    assert sealed_clean.output_hash == sealed_poisoned.output_hash
    assert sealed_clean.replay_proposed_action == sealed_poisoned.replay_proposed_action
    assert sealed_clean.replay_units == sealed_poisoned.replay_units


def test_replay_decision_is_byte_identical_under_policy_counterfactual_too():
    clean_row, poisoned_row = _row_with_every_forbidden_field_poisoned()
    pipeline = build_reference_pipeline()
    policy_config = {"max_units": 2.0}

    sealed_clean = run_decision(
        clean_row, ReplayMode.POLICY_COUNTERFACTUAL, pipeline, policy_config, "POLICY_V1",
        replay_observation_id="x", replay_ts_utc="2026-09-02T00:00:00+00:00",
    )
    sealed_poisoned = run_decision(
        poisoned_row, ReplayMode.POLICY_COUNTERFACTUAL, pipeline, policy_config, "POLICY_V1",
        replay_observation_id="x", replay_ts_utc="2026-09-02T00:00:00+00:00",
    )
    assert sealed_clean.output_hash == sealed_poisoned.output_hash


def test_future_market_snapshot_is_dropped_before_reaching_the_pipeline():
    row = current_model_agrees_with_original_action()
    row = dict(row)
    row["market_snapshots"] = [
        {"snapshot_ts_utc": "2026-08-01T16:00:00+00:00", "odds_american": -110},  # before decision: kept
        {"snapshot_ts_utc": "2026-08-02T00:00:00+00:00", "odds_american": -300},  # after decision: leak
    ]
    payload = project_raw_replay_payload(row)
    kept = payload["market_snapshots"]
    assert len(kept) == 1
    assert kept[0]["snapshot_ts_utc"] == "2026-08-01T16:00:00+00:00"


def test_postgame_stats_are_never_projected():
    row = current_model_agrees_with_original_action()
    row = dict(row)
    row["postgame_stats"] = {"final_score": "4-2"}
    payload = project_raw_replay_payload(row)
    assert "postgame_stats" not in payload


def test_direct_leakage_attempt_via_hand_built_payload_still_raises():
    # Defense-in-depth: even bypassing the whitelist projection entirely,
    # the contract's own gate still catches a forbidden field.
    from contracts.mlb_replay_v1.anti_leakage import assert_no_leakage

    payload = {"event_id": "evt_1", "decision_ts_utc": "2026-08-01T17:00:00+00:00", "result": "win"}
    with pytest.raises(LeakageError):
        assert_no_leakage(payload, decision_ts_utc=payload["decision_ts_utc"])


def test_historical_decision_id_is_not_projected_as_a_feature():
    row = current_model_agrees_with_original_action()
    payload = project_raw_replay_payload(row)
    assert "historical_decision_id" not in payload
