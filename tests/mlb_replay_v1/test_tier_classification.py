from contracts.mlb_replay_v1.tiers import TIER_A, TIER_B, TIER_C, classify_tier


def _clean_observation(**overrides):
    base = {
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
    base.update(overrides)
    return base


def test_fully_clean_row_is_tier_a_with_no_reasons():
    tier, reasons = classify_tier(_clean_observation())
    assert tier == TIER_A
    assert reasons == []


def test_missing_model_attribution_alone_downgrades_to_tier_b_not_excluded():
    # Explicit contract requirement: do not exclude a legitimate settled row
    # merely because model version is absent.
    tier, reasons = classify_tier(_clean_observation(model_attributable=False))
    assert tier == TIER_B
    assert reasons == ["DOWNGRADE_MISSING_MODEL_ATTRIBUTION"]


def test_missing_rationale_alone_downgrades_to_tier_b():
    tier, reasons = classify_tier(_clean_observation(rationale_traceable=False))
    assert tier == TIER_B
    assert reasons == ["DOWNGRADE_MISSING_RATIONALE"]


def test_unsupported_close_provenance_alone_downgrades_to_tier_b():
    tier, reasons = classify_tier(_clean_observation(clv_usable=False))
    assert tier == TIER_B
    assert reasons == ["DOWNGRADE_UNSUPPORTED_CLOSE_PROVENANCE"]


def test_multiple_claim_level_downgrades_still_tier_b():
    tier, reasons = classify_tier(
        _clean_observation(model_attributable=False, rationale_traceable=False)
    )
    assert tier == TIER_B
    assert set(reasons) == {
        "DOWNGRADE_MISSING_MODEL_ATTRIBUTION",
        "DOWNGRADE_MISSING_RATIONALE",
    }


def test_missing_shadow_row_is_informational_only_stays_tier_a():
    tier, reasons = classify_tier(_clean_observation(historical_missing_shadow=True))
    assert tier == TIER_A
    assert reasons == ["INFO_MISSING_SHADOW_ROW"]


def test_missing_shadow_row_combines_with_downgrade_and_stays_tier_b():
    tier, reasons = classify_tier(
        _clean_observation(historical_missing_shadow=True, model_attributable=False)
    )
    assert tier == TIER_B
    assert "INFO_MISSING_SHADOW_ROW" in reasons
    assert "DOWNGRADE_MISSING_MODEL_ATTRIBUTION" in reasons


def test_dfs_placeholder_price_forces_tier_c():
    tier, reasons = classify_tier(_clean_observation(sportsbook_price_valid=False))
    assert tier == TIER_C
    assert reasons == ["EXCL_INVALID_OR_PLACEHOLDER_PRICE"]


def test_post_start_decision_forces_tier_c():
    tier, reasons = classify_tier(_clean_observation(decision_time_valid=False))
    assert tier == TIER_C
    assert reasons == ["EXCL_POST_START_DECISION"]


def test_invalid_result_forces_tier_c():
    tier, reasons = classify_tier(_clean_observation(result_valid=False))
    assert tier == TIER_C
    assert reasons == ["EXCL_RESULT_INVALID"]


def test_ambiguous_identity_forces_tier_c():
    tier, reasons = classify_tier(_clean_observation(ambiguous_identity=True))
    assert tier == TIER_C
    assert "EXCL_AMBIGUOUS_IDENTITY" in reasons


def test_conflicting_results_forces_tier_c():
    tier, reasons = classify_tier(_clean_observation(conflicting_results=True))
    assert tier == TIER_C
    assert "EXCL_CONFLICTING_RESULTS" in reasons


def test_known_provenance_damage_forces_tier_c():
    tier, reasons = classify_tier(_clean_observation(known_provenance_damage=True))
    assert tier == TIER_C
    assert "EXCL_KNOWN_PROVENANCE_CORRUPTION" in reasons


def test_reconstructed_evidence_forces_tier_c():
    tier, reasons = classify_tier(_clean_observation(reconstructed_evidence=True))
    assert tier == TIER_C
    assert "EXCL_REPLAY_RECONSTRUCTED_TIMESTAMP" in reasons


def test_row_level_exclusion_overrides_claim_level_downgrade():
    # Even if model/rationale/clv are also missing, a row-level exclusion
    # wins and the row lands in Tier C, not Tier B.
    tier, reasons = classify_tier(
        _clean_observation(
            known_provenance_damage=True,
            model_attributable=False,
            rationale_traceable=False,
            clv_usable=False,
        )
    )
    assert tier == TIER_C
    assert reasons == ["EXCL_KNOWN_PROVENANCE_CORRUPTION"]
    assert "DOWNGRADE_MISSING_MODEL_ATTRIBUTION" not in reasons


def test_missing_flags_default_to_failing_not_clean():
    # Principle 8: unknown provenance stays unknown; an observation missing
    # its integrity booleans must not be treated as a clean Tier A row.
    tier, reasons = classify_tier({})
    assert tier == TIER_C
    assert reasons  # at least one exclusion reason present
