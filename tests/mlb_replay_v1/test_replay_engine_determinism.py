"""Determinism proofs: identical (input, code version, policy version,
configuration) must yield byte-for-byte identical replay output, captured
via input-evidence/output/policy-config hashes.
"""
from fixtures.mlb_replay_v1.validation_set import current_model_agrees_with_original_action
from replay_engine.engine import run_decision
from replay_engine.modes import ReplayMode
from replay_engine.reference_pipeline import build_reference_pipeline


def test_output_hash_is_byte_identical_across_repeated_runs():
    row = current_model_agrees_with_original_action()
    pipeline = build_reference_pipeline()
    policy_config = {"max_units": 2.0}

    sealed1 = run_decision(row, ReplayMode.ORIGINAL_DECISION_REPLAY, pipeline, policy_config, "POLICY_V1")
    sealed2 = run_decision(row, ReplayMode.ORIGINAL_DECISION_REPLAY, pipeline, policy_config, "POLICY_V1")

    assert sealed1.output_hash == sealed2.output_hash
    assert sealed1.input_evidence_hash == sealed2.input_evidence_hash
    assert sealed1.replay_proposed_action == sealed2.replay_proposed_action
    assert sealed1.replay_units == sealed2.replay_units
    assert sealed1.replay_reason == sealed2.replay_reason


def test_output_hash_survives_different_observation_id_and_replay_ts():
    # replay_observation_id and replay_ts_utc vary every real run (fresh
    # uuid, wall clock) and must not affect the decision's own hash.
    row = current_model_agrees_with_original_action()
    pipeline = build_reference_pipeline()
    policy_config = {"max_units": 2.0}

    sealed1 = run_decision(
        row, ReplayMode.ORIGINAL_DECISION_REPLAY, pipeline, policy_config, "POLICY_V1",
        replay_observation_id="obs-a", replay_ts_utc="2026-09-02T00:00:00+00:00",
    )
    sealed2 = run_decision(
        row, ReplayMode.ORIGINAL_DECISION_REPLAY, pipeline, policy_config, "POLICY_V1",
        replay_observation_id="obs-b", replay_ts_utc="2026-09-02T12:00:00+00:00",
    )

    assert sealed1.replay_observation_id != sealed2.replay_observation_id
    assert sealed1.replay_ts_utc != sealed2.replay_ts_utc
    assert sealed1.output_hash == sealed2.output_hash


def test_output_hash_changes_when_policy_config_changes():
    row = current_model_agrees_with_original_action()
    pipeline = build_reference_pipeline()

    sealed_small_cap = run_decision(row, ReplayMode.ORIGINAL_DECISION_REPLAY, pipeline, {"max_units": 0.1}, "POLICY_V1")
    sealed_large_cap = run_decision(row, ReplayMode.ORIGINAL_DECISION_REPLAY, pipeline, {"max_units": 5.0}, "POLICY_V1")

    assert sealed_small_cap.policy_config_hash != sealed_large_cap.policy_config_hash
    assert sealed_small_cap.output_hash != sealed_large_cap.output_hash
    assert sealed_small_cap.replay_units != sealed_large_cap.replay_units


def test_output_hash_differs_between_modes_when_belief_and_features_disagree():
    # Historical belief (edge_probability=0.0451, i.e. BET-worthy) disagrees
    # with a deliberately flat current-model signal (NO_BET-worthy): the two
    # modes must diverge, proving they are not silently blended.
    row = current_model_agrees_with_original_action()
    row = dict(row)
    row["features"] = {"current_model_edge_signal": 0.0, "current_model_confidence": "low"}
    pipeline = build_reference_pipeline()
    policy_config = {"max_units": 2.0}

    sealed_full = run_decision(row, ReplayMode.ORIGINAL_DECISION_REPLAY, pipeline, policy_config, "POLICY_V1")
    sealed_counterfactual = run_decision(row, ReplayMode.POLICY_COUNTERFACTUAL, pipeline, policy_config, "POLICY_V1")

    assert sealed_full.output_hash != sealed_counterfactual.output_hash
    assert sealed_full.replay_proposed_action == "NO_BET"  # flat current-model signal
    assert sealed_counterfactual.replay_proposed_action == "BET"  # fixed historical belief still has edge


def test_input_evidence_hash_reflects_only_the_whitelisted_payload():
    row = current_model_agrees_with_original_action()
    row_with_noise = dict(row)
    row_with_noise["some_unrelated_bookkeeping_field"] = "irrelevant"
    pipeline = build_reference_pipeline()
    policy_config = {"max_units": 2.0}

    sealed1 = run_decision(row, ReplayMode.ORIGINAL_DECISION_REPLAY, pipeline, policy_config, "POLICY_V1")
    sealed2 = run_decision(row_with_noise, ReplayMode.ORIGINAL_DECISION_REPLAY, pipeline, policy_config, "POLICY_V1")

    assert sealed1.input_evidence_hash == sealed2.input_evidence_hash
    assert sealed1.output_hash == sealed2.output_hash
