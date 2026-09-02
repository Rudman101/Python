"""CLI for the MLB Replay V1 deterministic replay engine (Workstream B).

Simulation only: nothing this CLI runs places, creates, or modifies a real
wager. It reads historical decision rows, replays each one through a
decision pipeline under one mode, and appends the resulting, fully-scored
observations to an append-only JSONL store.

Usage
-----
    python -m replay_engine.cli run \\
        --input historical_rows.jsonl \\
        --mode ORIGINAL_DECISION_REPLAY \\
        --output replay_results.jsonl \\
        --replay-policy-version POLICY_V1 \\
        [--policy-config policy_config.json] \\
        [--pipeline-factory some.module:build_pipeline]

    python -m replay_engine.cli validation-set \\
        --mode POLICY_COUNTERFACTUAL \\
        --output replay_results_validation.jsonl

--pipeline-factory defaults to the synthetic reference pipeline
(replay_engine.reference_pipeline:build_reference_pipeline). Point it at
Workstream A's real pipeline factory once it exists -- same dotted
"module:callable" convention, zero changes needed elsewhere in this CLI or
in replay_engine.engine.
"""
import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator

from replay_engine.engine import ReplayEngine
from replay_engine.modes import ReplayMode
from replay_engine.pipeline import DecisionPipeline
from replay_engine.reference_pipeline import build_reference_pipeline
from replay_engine.store import AppendOnlyReplayStore

DEFAULT_PIPELINE_FACTORY = "replay_engine.reference_pipeline:build_reference_pipeline"


def _load_pipeline_factory(dotted: str) -> Callable[[], DecisionPipeline]:
    module_name, _, func_name = dotted.partition(":")
    if not func_name:
        raise ValueError(f"--pipeline-factory must be 'module:callable', got {dotted!r}")
    module = importlib.import_module(module_name)
    return getattr(module, func_name)


def _read_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _run_batch(
    historical_rows: Iterable[Dict[str, Any]],
    mode: ReplayMode,
    engine: ReplayEngine,
    store: AppendOnlyReplayStore,
) -> int:
    count = 0
    for row in historical_rows:
        observation = engine.replay(row, mode)
        store.append(observation)
        count += 1
    return count


def _cmd_run(args: argparse.Namespace) -> int:
    policy_config: Dict[str, Any] = {}
    if args.policy_config:
        with open(args.policy_config, "r", encoding="utf-8") as f:
            policy_config = json.load(f)

    pipeline_factory = _load_pipeline_factory(args.pipeline_factory)
    pipeline = pipeline_factory()
    mode = ReplayMode(args.mode)
    engine = ReplayEngine(pipeline, policy_config, args.replay_policy_version)
    store = AppendOnlyReplayStore(args.output)

    rows = _read_jsonl(Path(args.input))
    count = _run_batch(rows, mode, engine, store)
    print(f"replayed {count} historical row(s) in mode {mode.value} -> {args.output}", file=sys.stderr)
    return 0


def _cmd_validation_set(args: argparse.Namespace) -> int:
    from fixtures.mlb_replay_v1.validation_set import VALIDATION_SET

    policy_config: Dict[str, Any] = {}
    if args.policy_config:
        with open(args.policy_config, "r", encoding="utf-8") as f:
            policy_config = json.load(f)

    pipeline = build_reference_pipeline()
    mode = ReplayMode(args.mode)
    engine = ReplayEngine(pipeline, policy_config, args.replay_policy_version)
    store = AppendOnlyReplayStore(args.output)

    for scenario_name, row in VALIDATION_SET.items():
        observation = engine.replay(row, mode)
        record = store.append(observation)
        print(
            f"{scenario_name!r}: tier={record['replay_eligibility_tier']} "
            f"action={record['replay_proposed_action']} diffs={record['differences_from_original']}",
            file=sys.stderr,
        )
    print(f"replayed {len(VALIDATION_SET)} validation-set row(s) in mode {mode.value} -> {args.output}", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="replay_engine", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Replay a JSONL file of historical rows.")
    run_p.add_argument("--input", required=True, help="JSONL file of historical decision rows.")
    run_p.add_argument("--output", required=True, help="Append-only JSONL replay result store path.")
    run_p.add_argument("--mode", required=True, choices=[m.value for m in ReplayMode])
    run_p.add_argument("--replay-policy-version", required=True)
    run_p.add_argument("--policy-config", help="JSON file of policy/governor config.")
    run_p.add_argument("--pipeline-factory", default=DEFAULT_PIPELINE_FACTORY, help="module:callable -> DecisionPipeline")
    run_p.set_defaults(func=_cmd_run)

    vs_p = sub.add_parser("validation-set", help="Replay the built-in Workstream B validation-set fixtures.")
    vs_p.add_argument("--output", required=True, help="Append-only JSONL replay result store path.")
    vs_p.add_argument("--mode", required=True, choices=[m.value for m in ReplayMode])
    vs_p.add_argument("--replay-policy-version", default="POLICY_VALIDATION_SET_V1")
    vs_p.add_argument("--policy-config", help="JSON file of policy/governor config.")
    vs_p.set_defaults(func=_cmd_validation_set)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
