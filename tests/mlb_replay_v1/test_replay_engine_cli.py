"""CLI smoke tests."""
import json

from fixtures.mlb_replay_v1.validation_set import VALIDATION_SET
from replay_engine.cli import main


def test_cli_run_replays_a_jsonl_batch(tmp_path):
    input_path = tmp_path / "historical_rows.jsonl"
    output_path = tmp_path / "replay_results.jsonl"
    rows = [
        VALIDATION_SET["current model agrees with original action"],
        VALIDATION_SET["current model rejects historical bet"],
    ]
    with open(input_path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    rc = main(
        [
            "run",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--mode",
            "ORIGINAL_DECISION_REPLAY",
            "--replay-policy-version",
            "POLICY_CLI_TEST_V1",
        ]
    )

    assert rc == 0
    with open(output_path, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    assert len(records) == 2
    assert {r["replay_proposed_action"] for r in records} == {"BET", "NO_BET"}


def test_cli_validation_set_subcommand(tmp_path):
    output_path = tmp_path / "replay_results_validation.jsonl"

    rc = main(["validation-set", "--output", str(output_path), "--mode", "POLICY_COUNTERFACTUAL"])

    assert rc == 0
    with open(output_path, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    assert len(records) == len(VALIDATION_SET)
    for record in records:
        assert record["replay_mode"] == "POLICY_COUNTERFACTUAL"


def test_cli_run_with_explicit_policy_config(tmp_path):
    input_path = tmp_path / "historical_rows.jsonl"
    output_path = tmp_path / "replay_results.jsonl"
    policy_config_path = tmp_path / "policy_config.json"
    with open(input_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(VALIDATION_SET["current model agrees with original action"]) + "\n")
    with open(policy_config_path, "w", encoding="utf-8") as f:
        json.dump({"max_units": 0.5}, f)

    rc = main(
        [
            "run",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--mode",
            "ORIGINAL_DECISION_REPLAY",
            "--replay-policy-version",
            "POLICY_CLI_TEST_V1",
            "--policy-config",
            str(policy_config_path),
        ]
    )

    assert rc == 0
    with open(output_path, "r", encoding="utf-8") as f:
        record = json.loads(f.readline())
    assert record["replay_units"] == 0.5
