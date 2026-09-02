"""Behavioral coverage of the Workstream B validation set: every scenario
required by the spec, exercised end-to-end through ReplayEngine."""
import pytest

from contracts.mlb_replay_v1.tiers import TIER_A, TIER_B, TIER_C
from fixtures.mlb_replay_v1.validation_set import VALIDATION_SET
from replay_engine.engine import ReplayEngine
from replay_engine.modes import ReplayMode
from replay_engine.reference_pipeline import build_reference_pipeline


@pytest.fixture
def engine():
    pipeline = build_reference_pipeline()
    return ReplayEngine(pipeline, policy_config={"max_units": 2.0}, replay_policy_version="POLICY_VALIDATION_V1")


EXPECTED = {
    "current model agrees with original action": {"tier": TIER_A, "action": "BET"},
    "current model rejects historical bet": {"tier": TIER_A, "action": "NO_BET"},
    "current governor blocks scanner BET": {"tier": TIER_A, "action": "NO_BET"},
    "historical block current system would accept": {"tier": TIER_A, "action": "BET"},
    "missing model version": {"tier": TIER_B, "action": "BET"},
    "missing rationale": {"tier": TIER_B, "action": "BET"},
    "Tier B row": {"tier": TIER_B, "action": "BET"},
    "Tier C rejection": {"tier": TIER_C, "action": "BET"},
    "contradictory side": {"tier": TIER_A, "action": "NO_BET"},
    "post-start exclusion": {"tier": TIER_C, "action": "NO_BET"},
    "DFS invalid-price exclusion": {"tier": TIER_C, "action": "NO_BET"},
}


@pytest.mark.parametrize("scenario_name", sorted(VALIDATION_SET))
def test_validation_set_scenario_matches_expected_tier_and_action(engine, scenario_name):
    row = VALIDATION_SET[scenario_name]
    observation = engine.replay(row, ReplayMode.ORIGINAL_DECISION_REPLAY)
    expected = EXPECTED[scenario_name]
    assert observation.replay_eligibility_tier == expected["tier"], scenario_name
    assert observation.sealed.replay_proposed_action == expected["action"], scenario_name


def test_all_eleven_required_scenarios_are_present():
    required = {
        "current model agrees with original action",
        "current model rejects historical bet",
        "current governor blocks scanner BET",
        "historical block current system would accept",
        "missing model version",
        "missing rationale",
        "Tier B row",
        "Tier C rejection",
        "contradictory side",
        "post-start exclusion",
        "DFS invalid-price exclusion",
    }
    assert required == set(VALIDATION_SET)


def test_current_model_agrees_shows_no_action_level_difference(engine):
    observation = engine.replay(
        VALIDATION_SET["current model agrees with original action"], ReplayMode.ORIGINAL_DECISION_REPLAY
    )
    assert not any(d.startswith("action_changed") for d in observation.sealed.differences_from_original)


def test_current_model_rejects_shows_action_level_difference(engine):
    observation = engine.replay(
        VALIDATION_SET["current model rejects historical bet"], ReplayMode.ORIGINAL_DECISION_REPLAY
    )
    assert any(d.startswith("action_changed:BET->NO_BET") for d in observation.sealed.differences_from_original)


def test_governor_block_reason_is_traceable(engine):
    observation = engine.replay(
        VALIDATION_SET["current governor blocks scanner BET"], ReplayMode.ORIGINAL_DECISION_REPLAY
    )
    assert observation.sealed.replay_governor_result.decision == "BLOCK"
    assert "exposure_cap_hit" in observation.sealed.replay_governor_result.reasons


def test_historical_block_now_accept_upgrades_action(engine):
    observation = engine.replay(
        VALIDATION_SET["historical block current system would accept"], ReplayMode.ORIGINAL_DECISION_REPLAY
    )
    assert observation.sealed.historical_original_action == "NO_BET"
    assert observation.sealed.replay_proposed_action == "BET"


def test_missing_model_version_still_replays_but_is_capped_at_tier_b(engine):
    observation = engine.replay(VALIDATION_SET["missing model version"], ReplayMode.ORIGINAL_DECISION_REPLAY)
    assert observation.sealed.ORIGINAL_MODEL_VERSION is None
    assert observation.replay_eligibility_tier == TIER_B
    assert "DOWNGRADE_MISSING_MODEL_ATTRIBUTION" in observation.exclusion_reasons


def test_missing_rationale_does_not_change_the_replay_decision_itself(engine):
    with_rationale = VALIDATION_SET["current model agrees with original action"]
    without_rationale = VALIDATION_SET["missing rationale"]
    obs_with = engine.replay(with_rationale, ReplayMode.ORIGINAL_DECISION_REPLAY)
    obs_without = engine.replay(without_rationale, ReplayMode.ORIGINAL_DECISION_REPLAY)
    # original_rationale is forbidden pipeline input either way, so its
    # presence/absence must not change the decision the pipeline reaches.
    assert obs_with.sealed.replay_proposed_action == obs_without.sealed.replay_proposed_action
    assert obs_without.replay_eligibility_tier == TIER_B
    assert "DOWNGRADE_MISSING_RATIONALE" in obs_without.exclusion_reasons


def test_contradictory_side_is_rejected_by_resolver_not_governor(engine):
    observation = engine.replay(VALIDATION_SET["contradictory side"], ReplayMode.ORIGINAL_DECISION_REPLAY)
    assert observation.sealed.replay_resolver_result.decision == "REJECTED"
    assert "contradictory_side" in observation.sealed.replay_resolver_result.reasons


def test_post_start_exclusion_is_rejected_by_resolver_and_tier_c(engine):
    observation = engine.replay(VALIDATION_SET["post-start exclusion"], ReplayMode.ORIGINAL_DECISION_REPLAY)
    assert "post_start_exclusion" in observation.sealed.replay_resolver_result.reasons
    assert "EXCL_POST_START_DECISION" in observation.exclusion_reasons


def test_dfs_invalid_price_is_rejected_by_resolver_and_tier_c(engine):
    observation = engine.replay(VALIDATION_SET["DFS invalid-price exclusion"], ReplayMode.ORIGINAL_DECISION_REPLAY)
    assert "invalid_price_source" in observation.sealed.replay_resolver_result.reasons
    assert "EXCL_INVALID_OR_PLACEHOLDER_PRICE" in observation.exclusion_reasons


def test_tier_c_rows_are_still_replayed_for_forensic_value(engine):
    # Tier C excludes a row from performance claims, it does not stop the
    # replay engine from producing a decision to inspect (contract:
    # "Retained for defect analysis").
    observation = engine.replay(VALIDATION_SET["Tier C rejection"], ReplayMode.ORIGINAL_DECISION_REPLAY)
    assert observation.replay_eligibility_tier == TIER_C
    assert observation.sealed.replay_proposed_action in ("BET", "NO_BET")
