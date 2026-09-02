from contracts.mlb_prospective_v1 import alerts as alerts_mod
from contracts.mlb_prospective_v1.capture import capture_decision
from contracts.mlb_prospective_v1.writer_registry import REGISTERED_WRITERS, is_registered_writer


def _base_payload(**overrides):
    base = {
        "decision_id": "dec_writer_1",
        "event_id": "evt_1",
        "market": "moneyline",
        "side": "home",
        "book": "draftkings",
        "cohort": "ZERO_UNIT_TRACKING",
        "model_version": "gbm_v3.2",
        "odds_american": -130,
        "decision_ts_utc": "2026-09-01T17:00:00+00:00",
        "game_start_ts_utc": "2026-09-01T23:05:00+00:00",
        "final_funded_units": 0.0,
        "tracking_stake": 0.0,
    }
    base.update(overrides)
    return base


def test_registered_writer_is_attributed():
    decision = capture_decision(_base_payload(), writer_id="mlb_scanner_v1")
    assert decision.model_version == "gbm_v3.2"
    assert decision.model_attributable is True


def test_unmapped_writer_never_receives_fake_model_version():
    assert not is_registered_writer("some_new_untracked_writer")
    decision = capture_decision(_base_payload(), writer_id="some_new_untracked_writer")
    assert decision.model_version is None
    assert decision.model_attributable is False
    assert "ALERT_UNMAPPED_WRITER" in decision.evidence_quality_warnings
    # missing-model-version alert is not double-fired on top of the more
    # specific unmapped-writer alert
    assert "ALERT_MISSING_MODEL_VERSION" not in decision.evidence_quality_warnings


def test_unmapped_writer_alert_is_emitted_to_the_alert_log():
    alerts_mod.clear_alert_log()
    capture_decision(_base_payload(decision_id="dec_writer_2"), writer_id="totally_unknown_writer")
    codes = [a.code for a in alerts_mod.ALERT_LOG]
    assert "ALERT_UNMAPPED_WRITER" in codes


def test_model_version_change_produces_different_attribution():
    decision_a = capture_decision(
        _base_payload(decision_id="dec_model_a", model_version="gbm_v3.2"),
        writer_id="mlb_scanner_v1",
    )
    decision_b = capture_decision(
        _base_payload(decision_id="dec_model_b", model_version="gbm_v4.0"),
        writer_id="mlb_scanner_v1",
    )
    assert decision_a.model_version != decision_b.model_version
    assert decision_a.model_attributable is True
    assert decision_b.model_attributable is True


def test_registered_writers_set_is_nonempty():
    assert REGISTERED_WRITERS
