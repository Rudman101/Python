import dataclasses

import pytest

from contracts.mlb_prospective_v1.capture import capture_decision
from contracts.mlb_prospective_v1.enrichment import EnrichmentLeakageError, enrich_with_outcome


def _base_payload(**overrides):
    base = {
        "decision_id": "dec_immut_1",
        "event_id": "evt_1",
        "market": "player_strikeouts",
        "side": "over",
        "line": 6.5,
        "book": "pinnacle",
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


def test_decision_record_is_frozen():
    decision = capture_decision(_base_payload(), writer_id="mlb_scanner_v1")
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.model_version = "some_other_model"
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.final_funded_units = 999.0
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.original_rationale_raw = "tampered"


def test_outcome_record_is_frozen():
    decision = capture_decision(_base_payload(), writer_id="mlb_scanner_v1")
    outcome = enrich_with_outcome(
        decision,
        {"result": "win", "closing_odds": -108, "closing_price_provenance": "book_snapshot"},
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        outcome.result = "loss"


def test_enrichment_payload_cannot_carry_decision_time_fields():
    decision = capture_decision(_base_payload(), writer_id="mlb_scanner_v1")
    with pytest.raises(EnrichmentLeakageError):
        enrich_with_outcome(
            decision,
            {
                "result": "win",
                "closing_odds": -108,
                "closing_price_provenance": "book_snapshot",
                "model_version": "tampered_model",  # attempted overwrite
            },
        )


def test_enrichment_payload_cannot_carry_original_rationale():
    decision = capture_decision(_base_payload(), writer_id="mlb_scanner_v1")
    with pytest.raises(EnrichmentLeakageError):
        enrich_with_outcome(
            decision,
            {
                "result": "win",
                "closing_odds": -108,
                "closing_price_provenance": "book_snapshot",
                "original_rationale_raw": "rewritten after the fact",
            },
        )


def test_enrichment_never_mutates_the_original_decision_object():
    decision = capture_decision(_base_payload(), writer_id="mlb_scanner_v1")
    original_snapshot = dataclasses.replace(decision)  # independent copy for comparison
    enrich_with_outcome(
        decision,
        {"result": "loss", "closing_odds": -120, "closing_price_provenance": "book_snapshot"},
    )
    assert decision == original_snapshot
    assert decision.result == "unsettled"  # decision-time placeholder untouched


def test_settlement_cannot_overwrite_decision_time_evidence_across_multiple_enrichments():
    decision = capture_decision(_base_payload(), writer_id="mlb_scanner_v1")
    before = dataclasses.replace(decision)

    enrich_with_outcome(
        decision, {"result": "unsettled", "closing_price_provenance": "missing"}
    )
    enrich_with_outcome(
        decision,
        {"result": "win", "closing_odds": -105, "closing_price_provenance": "book_snapshot"},
    )

    assert decision == before
