"""Append-only replay result store: no overwrite of original tables, no
mutation of inputs, provenance always linked back to historical identity.
"""
import copy
import json

import pytest

from fixtures.mlb_replay_v1.validation_set import current_model_agrees_with_original_action
from replay_engine.engine import ReplayEngine
from replay_engine.modes import ReplayMode
from replay_engine.reference_pipeline import build_reference_pipeline
from replay_engine.store import AppendOnlyReplayStore, ReplayStoreError


@pytest.fixture
def engine():
    pipeline = build_reference_pipeline()
    return ReplayEngine(pipeline, policy_config={"max_units": 2.0}, replay_policy_version="POLICY_V1")


def test_append_writes_one_json_object_per_line_with_provenance(tmp_path, engine):
    store = AppendOnlyReplayStore(tmp_path / "replay_results.jsonl")
    row1 = current_model_agrees_with_original_action()
    row2 = dict(row1)
    row2["historical_decision_id"] = "hd_other"

    store.append(engine.replay(row1, ReplayMode.ORIGINAL_DECISION_REPLAY))
    store.append(engine.replay(row2, ReplayMode.ORIGINAL_DECISION_REPLAY))

    records = list(store.read_all())
    assert len(records) == 2
    assert {r["historical_decision_id"] for r in records} == {"hd_agrees", "hd_other"}
    # every stored line is independently valid JSON (append-only, line-delimited)
    with open(store.path, "r", encoding="utf-8") as f:
        lines = [line for line in f if line.strip()]
    assert len(lines) == 2
    for line in lines:
        json.loads(line)


def test_store_refuses_a_shadow_bets_named_path(tmp_path):
    with pytest.raises(ReplayStoreError):
        AppendOnlyReplayStore(tmp_path / "shadow_bets.jsonl")


def test_store_refuses_a_signal_table_named_path(tmp_path):
    with pytest.raises(ReplayStoreError):
        AppendOnlyReplayStore(tmp_path / "signal_table_dump.jsonl")


def test_store_has_no_update_or_delete_api(tmp_path):
    store = AppendOnlyReplayStore(tmp_path / "replay_results.jsonl")
    public_methods = {name for name in dir(store) if not name.startswith("_")}
    assert public_methods & {"append", "append_many", "read_all", "path"} == public_methods
    assert "update" not in public_methods
    assert "delete" not in public_methods
    assert "overwrite" not in public_methods


def test_replaying_and_storing_does_not_mutate_the_input_historical_row(tmp_path, engine):
    store = AppendOnlyReplayStore(tmp_path / "replay_results.jsonl")
    row = current_model_agrees_with_original_action()
    row_before = copy.deepcopy(row)

    store.append(engine.replay(row, ReplayMode.ORIGINAL_DECISION_REPLAY))

    assert row == row_before


def test_append_requires_provenance_linking_field(tmp_path):
    store = AppendOnlyReplayStore(tmp_path / "replay_results.jsonl")
    with pytest.raises(ReplayStoreError):
        store.append({"no_historical_decision_id": True})
