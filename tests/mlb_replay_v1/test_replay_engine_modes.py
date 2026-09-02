"""Proof that ORIGINAL_DECISION_REPLAY and POLICY_COUNTERFACTUAL are never
blended: distinct code paths, distinct payload shapes, and (per the spy
scanner below) the scanner port is only ever invoked in one of the two.
"""
from dataclasses import replace

from fixtures.mlb_replay_v1.validation_set import current_model_agrees_with_original_action
from replay_engine.engine import run_decision
from replay_engine.modes import ReplayMode
from replay_engine.pipeline import ScannerResult
from replay_engine.projection import HISTORICAL_BELIEF_FIELDS
from replay_engine.reference_pipeline import build_reference_pipeline


class SpyScanner:
    """Wraps a real scanner, recording every call and its payload."""

    def __init__(self, inner):
        self._inner = inner
        self.version = inner.version
        self.calls = []

    def scan(self, payload):
        self.calls.append(dict(payload))
        return self._inner.scan(payload)


def _pipeline_with_spy_scanner():
    pipeline = build_reference_pipeline()
    spy = SpyScanner(pipeline.scanner)
    return replace(pipeline, scanner=spy), spy


def test_policy_counterfactual_never_calls_the_scanner_port():
    pipeline, spy = _pipeline_with_spy_scanner()
    row = current_model_agrees_with_original_action()

    run_decision(row, ReplayMode.POLICY_COUNTERFACTUAL, pipeline, {"max_units": 2.0}, "POLICY_V1")

    assert spy.calls == []


def test_original_decision_replay_always_calls_the_scanner_port():
    pipeline, spy = _pipeline_with_spy_scanner()
    row = current_model_agrees_with_original_action()

    run_decision(row, ReplayMode.ORIGINAL_DECISION_REPLAY, pipeline, {"max_units": 2.0}, "POLICY_V1")

    assert len(spy.calls) == 1


def test_original_decision_replay_payload_never_contains_historical_belief_fields():
    pipeline, spy = _pipeline_with_spy_scanner()
    row = current_model_agrees_with_original_action()

    run_decision(row, ReplayMode.ORIGINAL_DECISION_REPLAY, pipeline, {"max_units": 2.0}, "POLICY_V1")

    (payload,) = spy.calls
    assert not (HISTORICAL_BELIEF_FIELDS & payload.keys())


def test_policy_counterfactual_scanner_result_is_marked_as_fixed_belief():
    pipeline = build_reference_pipeline()
    row = current_model_agrees_with_original_action()

    sealed = run_decision(row, ReplayMode.POLICY_COUNTERFACTUAL, pipeline, {"max_units": 2.0}, "POLICY_V1")

    assert isinstance(sealed.replay_scanner_result, ScannerResult)
    assert sealed.replay_scanner_result.historical_belief_fixed is True


def test_original_decision_replay_scanner_result_is_not_marked_as_fixed_belief():
    pipeline = build_reference_pipeline()
    row = current_model_agrees_with_original_action()

    sealed = run_decision(row, ReplayMode.ORIGINAL_DECISION_REPLAY, pipeline, {"max_units": 2.0}, "POLICY_V1")

    assert sealed.replay_scanner_result.historical_belief_fixed is False


def test_sealed_decision_records_which_mode_produced_it():
    pipeline = build_reference_pipeline()
    row = current_model_agrees_with_original_action()

    sealed_full = run_decision(row, ReplayMode.ORIGINAL_DECISION_REPLAY, pipeline, {"max_units": 2.0}, "POLICY_V1")
    sealed_counterfactual = run_decision(row, ReplayMode.POLICY_COUNTERFACTUAL, pipeline, {"max_units": 2.0}, "POLICY_V1")

    assert sealed_full.replay_mode == ReplayMode.ORIGINAL_DECISION_REPLAY.value
    assert sealed_counterfactual.replay_mode == ReplayMode.POLICY_COUNTERFACTUAL.value


def test_only_two_replay_modes_exist():
    assert {m.value for m in ReplayMode} == {"ORIGINAL_DECISION_REPLAY", "POLICY_COUNTERFACTUAL"}
