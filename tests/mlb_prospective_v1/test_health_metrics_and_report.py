import dataclasses
import shutil
import tempfile
from pathlib import Path

import pytest

from contracts.mlb_prospective_v1.capture import capture_decision
from contracts.mlb_prospective_v1.daily_report import build_daily_report, render_markdown
from contracts.mlb_prospective_v1.enrichment import enrich_with_outcome
from contracts.mlb_prospective_v1.health_metrics import compute_coverage
from contracts.mlb_prospective_v1.store import DuplicateDecisionError, ProspectiveMLBStore


def _payload(decision_id, **overrides):
    base = {
        "decision_id": decision_id,
        "event_id": "evt_1",
        "market": "moneyline",
        "side": "home",
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


@pytest.fixture()
def tmp_store():
    tmp_dir = tempfile.mkdtemp(prefix="mlb_prospective_store_")
    yield ProspectiveMLBStore(tmp_dir)
    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_compute_coverage_on_empty_list_is_all_none():
    coverage = compute_coverage([], {})
    assert coverage["total_decisions"] == 0
    assert coverage["pct_model_version_attributable"] is None


def test_compute_coverage_percentages():
    clean = capture_decision(_payload("dec_h1"), writer_id="mlb_scanner_v1")
    unattributed = capture_decision(
        _payload("dec_h2", model_version=None), writer_id="mlb_scanner_v1"
    )
    decisions = [dataclasses.asdict(clean), dataclasses.asdict(unattributed)]

    outcome = enrich_with_outcome(
        clean, {"result": "win", "closing_odds": -108, "closing_price_provenance": "book_snapshot"}
    )
    outcomes_by_decision = {outcome.decision_id: dataclasses.asdict(outcome)}

    coverage = compute_coverage(decisions, outcomes_by_decision)
    assert coverage["total_decisions"] == 2
    assert coverage["pct_model_version_attributable"] == 50.0
    assert coverage["pct_settled"] == 50.0
    assert coverage["pct_eventual_valid_close"] == 50.0


def test_store_append_and_duplicate_rejection(tmp_store):
    decision = capture_decision(_payload("dec_store_1"), writer_id="mlb_scanner_v1")
    tmp_store.append_decision(decision)
    with pytest.raises(DuplicateDecisionError):
        tmp_store.append_decision(decision)

    stored = list(tmp_store.iter_decisions())
    assert len(stored) == 1
    assert stored[0]["decision_id"] == "dec_store_1"


def test_store_outcomes_latest_line_wins(tmp_store):
    decision = capture_decision(_payload("dec_store_2"), writer_id="mlb_scanner_v1")
    tmp_store.append_decision(decision)

    outcome_1 = enrich_with_outcome(decision, {"result": "unsettled"})
    tmp_store.append_outcome(outcome_1)
    outcome_2 = enrich_with_outcome(
        decision, {"result": "win", "closing_odds": -108, "closing_price_provenance": "book_snapshot"}
    )
    tmp_store.append_outcome(outcome_2)

    latest = tmp_store.latest_outcomes_by_decision()
    assert latest["dec_store_2"]["result"] == "win"
    # both lines remain on disk -- audit trail, never overwritten in place
    assert len(list(tmp_store.iter_outcomes())) == 2


def test_daily_report_and_markdown_rendering(tmp_store):
    decision = capture_decision(_payload("dec_report_1"), writer_id="mlb_scanner_v1")
    tmp_store.append_decision(decision)
    outcome = enrich_with_outcome(
        decision, {"result": "win", "closing_odds": -108, "closing_price_provenance": "book_snapshot"}
    )
    tmp_store.append_outcome(outcome)

    report = build_daily_report(tmp_store, report_date="2026-09-01")
    assert report["today"]["total_decisions"] == 1
    assert report["today"]["pct_model_version_attributable"] == 100.0
    assert report["cohort_counts_today"] == {"OFFICIAL_GOVERNOR_BET": 1}
    assert report["eligibility_tier_counts_today"] == {"TIER_A_FULL_REPLAY": 1}

    markdown = render_markdown(report)
    assert "MLB Prospective Evidence-Health Report" in markdown
    assert "Model-version attributable: 100.0%" in markdown
