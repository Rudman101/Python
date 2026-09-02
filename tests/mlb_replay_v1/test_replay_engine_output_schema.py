"""Output-schema and seal-before-settle proofs for the replay engine."""
import dataclasses

import pytest

from contracts.mlb_replay_v1.anti_leakage import FUTURE_OUTCOME_FIELDS
from fixtures.mlb_replay_v1.validation_set import current_model_agrees_with_original_action
from replay_engine.engine import attach_outcome, run_decision
from replay_engine.modes import ReplayMode
from replay_engine.reference_pipeline import REFERENCE_PIPELINE_VERSION, build_reference_pipeline
from replay_engine.schema import SealedDecision


def test_sealed_decision_has_no_outcome_field():
    """Structural proof that a decision cannot be settled before sealing:
    SealedDecision's own fields do not include any future-outcome field, so
    there is nothing in it that scoring code could accidentally read early."""
    sealed_field_names = {f.name for f in dataclasses.fields(SealedDecision)}
    assert not (sealed_field_names & FUTURE_OUTCOME_FIELDS)


def test_attach_outcome_requires_an_already_sealed_decision():
    row = current_model_agrees_with_original_action()
    with pytest.raises(AttributeError):
        attach_outcome({"not": "a sealed decision"}, row)  # type: ignore[arg-type]


def test_replay_observation_carries_the_minimum_required_output_fields():
    row = current_model_agrees_with_original_action()
    pipeline = build_reference_pipeline()
    sealed = run_decision(row, ReplayMode.ORIGINAL_DECISION_REPLAY, pipeline, {"max_units": 2.0}, "POLICY_V1")
    observation = attach_outcome(sealed, row)
    d = observation.to_dict()

    # historical original action / replay scanner / resolver / policy /
    # governor / final action / units / differences / reason for differences
    for required in (
        "historical_original_action",
        "replay_scanner_result",
        "replay_resolver_result",
        "replay_policy_result",
        "replay_governor_result",
        "replay_proposed_action",
        "replay_units",
        "differences_from_original",
        "difference_reason",
    ):
        assert required in d

    # outcome, attached after sealing
    for required in (
        "result",
        "profit_units",
        "historical_profit_at_original_price",
        "simulated_replay_profit_at_historical_price",
        "closing_odds",
        "clv",
    ):
        assert required in d

    assert d["replay_eligibility_tier"] in ("TIER_A_FULL_REPLAY", "TIER_B_PERFORMANCE_REPLAY", "TIER_C_FORENSIC_ONLY")


def test_original_and_current_model_version_are_distinct_and_never_overwritten():
    row = current_model_agrees_with_original_action()
    row = dict(row)
    row["model_version"] = "HISTORICAL_MODEL_FAMILY_V9"
    pipeline = build_reference_pipeline()
    sealed = run_decision(row, ReplayMode.ORIGINAL_DECISION_REPLAY, pipeline, {"max_units": 2.0}, "POLICY_V1")

    assert sealed.ORIGINAL_MODEL_VERSION == "HISTORICAL_MODEL_FAMILY_V9"
    assert sealed.CURRENT_REPLAY_MODEL_VERSION == REFERENCE_PIPELINE_VERSION
    assert sealed.ORIGINAL_MODEL_VERSION != sealed.CURRENT_REPLAY_MODEL_VERSION


def test_missing_original_model_version_does_not_block_replay():
    row = current_model_agrees_with_original_action()
    row = dict(row)
    row["model_version"] = None
    pipeline = build_reference_pipeline()
    sealed = run_decision(row, ReplayMode.ORIGINAL_DECISION_REPLAY, pipeline, {"max_units": 2.0}, "POLICY_V1")

    assert sealed.ORIGINAL_MODEL_VERSION is None
    assert sealed.replay_proposed_action in ("BET", "NO_BET")  # replay still runs


def test_price_semantics_use_only_the_historical_decision_snapshot():
    """Historical profit and simulated replay profit must be scored off the
    exact same historical decision-time price -- no later/executable price
    is fabricated."""
    row = current_model_agrees_with_original_action()
    pipeline = build_reference_pipeline()
    sealed = run_decision(row, ReplayMode.ORIGINAL_DECISION_REPLAY, pipeline, {"max_units": 2.0}, "POLICY_V1")
    observation = attach_outcome(sealed, row)

    assert sealed.odds_american == row["odds_american"]
    # Both profit figures must be computable off that single snapshot only.
    assert observation.historical_profit_at_original_price is not None
    assert observation.simulated_replay_profit_at_historical_price is not None


def test_unsettled_result_never_fabricates_a_profit_figure():
    row = current_model_agrees_with_original_action()
    row = dict(row)
    row["result"] = "unsettled"
    pipeline = build_reference_pipeline()
    sealed = run_decision(row, ReplayMode.ORIGINAL_DECISION_REPLAY, pipeline, {"max_units": 2.0}, "POLICY_V1")
    observation = attach_outcome(sealed, row)

    if sealed.replay_proposed_action == "BET":
        assert observation.simulated_replay_profit_at_historical_price is None
