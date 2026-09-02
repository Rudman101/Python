import pytest

from contracts.mlb_prospective_v1.capture import capture_decision
from contracts.mlb_prospective_v1.enrichment import (
    CLOSE_PROVENANCE_BOOK_SNAPSHOT,
    CLOSE_PROVENANCE_ENTRY_FALLBACK,
    CLOSE_PROVENANCE_MISSING,
    CLOSE_PROVENANCE_STALE_REFERENCE,
    ClosePriceProvenanceError,
    enrich_with_outcome,
)


def _decision(**overrides):
    payload = {
        "decision_id": "dec_close_1",
        "event_id": "evt_1",
        "market": "moneyline",
        "side": "away",
        "book": "circa",
        "cohort": "OFFICIAL_GOVERNOR_BET",
        "model_version": "gbm_v3.2",
        "odds_american": -120,
        "decision_ts_utc": "2026-09-01T17:00:00+00:00",
        "game_start_ts_utc": "2026-09-01T23:05:00+00:00",
        "final_funded_units": 1.0,
        "tracking_stake": 0.0,
    }
    payload.update(overrides)
    return capture_decision(payload, writer_id="mlb_scanner_v1")


def test_genuine_book_snapshot_close_makes_clv_usable():
    decision = _decision()
    outcome = enrich_with_outcome(
        decision,
        {"result": "win", "closing_odds": -105, "closing_price_provenance": CLOSE_PROVENANCE_BOOK_SNAPSHOT},
    )
    assert outcome.closing_price_provenance == CLOSE_PROVENANCE_BOOK_SNAPSHOT
    assert outcome.clv_usable is True
    assert outcome.clv is not None


def test_entry_fallback_is_never_treated_as_a_real_close():
    decision = _decision(decision_id="dec_close_2")
    outcome = enrich_with_outcome(
        decision,
        {
            "result": "win",
            "closing_odds": -120,  # identical to entry price, as a fallback would produce
            "closing_price_provenance": CLOSE_PROVENANCE_ENTRY_FALLBACK,
        },
    )
    # The label stays entry_fallback -- it is never silently relabeled or
    # upgraded to book_snapshot -- and CLV is not computed from it.
    assert outcome.closing_price_provenance == CLOSE_PROVENANCE_ENTRY_FALLBACK
    assert outcome.closing_price_provenance != CLOSE_PROVENANCE_BOOK_SNAPSHOT
    assert outcome.clv_usable is False
    assert outcome.clv is None


def test_stale_reference_does_not_make_clv_usable():
    decision = _decision(decision_id="dec_close_3")
    outcome = enrich_with_outcome(
        decision,
        {"result": "loss", "closing_odds": -118, "closing_price_provenance": CLOSE_PROVENANCE_STALE_REFERENCE},
    )
    assert outcome.closing_price_provenance == CLOSE_PROVENANCE_STALE_REFERENCE
    assert outcome.clv_usable is False
    assert outcome.clv is None


def test_missing_close_defaults_to_missing_provenance_not_book_snapshot():
    decision = _decision(decision_id="dec_close_4")
    outcome = enrich_with_outcome(decision, {"result": "win"})
    assert outcome.closing_price_provenance == CLOSE_PROVENANCE_MISSING
    assert outcome.clv_usable is False


def test_unregistered_close_provenance_string_is_rejected_not_silently_accepted():
    decision = _decision(decision_id="dec_close_5")
    with pytest.raises(ClosePriceProvenanceError):
        enrich_with_outcome(
            decision,
            {"result": "win", "closing_odds": -110, "closing_price_provenance": "made_up_provenance"},
        )


def test_book_snapshot_without_closing_odds_does_not_fabricate_clv():
    decision = _decision(decision_id="dec_close_6")
    outcome = enrich_with_outcome(
        decision,
        {"result": "win", "closing_price_provenance": CLOSE_PROVENANCE_BOOK_SNAPSHOT, "closing_odds": None},
    )
    assert outcome.clv_usable is False
    assert outcome.clv is None
