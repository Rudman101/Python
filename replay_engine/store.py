"""Append-only replay result store.

Replay results are never written back into original shadow_bets or signal
tables (contract Principle 9 / Workstream B OUTPUT STORAGE requirement).
AppendOnlyReplayStore writes to its own JSONL artifact file, keyed for
provenance by historical_decision_id, and exposes no update/delete: the
only mutating method is append().
"""
import json
from pathlib import Path
from typing import Any, Dict, Iterator, Union

from replay_engine.hashing import canonical_json
from replay_engine.schema import ReplayObservation

FORBIDDEN_TARGET_NAME_MARKERS = ("shadow_bets", "signal")


class ReplayStoreError(ValueError):
    pass


class AppendOnlyReplayStore:
    """One replay-result artifact file, append-only, one JSON object per line.

    Refuses to target a path whose name suggests it is (or aliases) an
    original shadow_bets/signal table -- a cheap guard against accidental
    reuse of a production artifact path, on top of this store's own,
    separate on-disk location.
    """

    def __init__(self, path: Union[str, Path]):
        path = Path(path)
        lowered = path.name.lower()
        if any(marker in lowered for marker in FORBIDDEN_TARGET_NAME_MARKERS):
            raise ReplayStoreError(
                f"Refusing to use {path} as a replay result store: name suggests an "
                "original shadow_bets/signal table, which replay results must never "
                "be written back into."
            )
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, observation: Union[ReplayObservation, Dict[str, Any]]) -> Dict[str, Any]:
        record = observation.to_dict() if isinstance(observation, ReplayObservation) else observation
        if "historical_decision_id" not in record:
            raise ReplayStoreError("replay result missing provenance-linking historical_decision_id")
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(canonical_json(record) + "\n")
        return record

    def append_many(self, observations) -> int:
        count = 0
        for obs in observations:
            self.append(obs)
            count += 1
        return count

    def read_all(self) -> Iterator[Dict[str, Any]]:
        if not self.path.exists():
            return
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)
