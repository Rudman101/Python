"""Reference append-only store for prospective MLB decisions and outcomes.

This is the reference implementation of the shadow-writer chokepoint's
persistence: one JSONL file for decisions (append-only, one line per
decision, recapture of the same decision_id is rejected outright) and one
JSONL file for outcome enrichments (append-only; the *latest* line per
decision_id is the current outcome view, earlier lines are kept for audit
and never deleted or edited in place). A production writer can swap this
for a database while keeping the same append-only contract: decision-time
evidence is written once and never rewritten.
"""
import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Iterator

from contracts.mlb_prospective_v1.capture import ProspectiveMLBDecision
from contracts.mlb_prospective_v1.enrichment import ProspectiveMLBOutcome


class DuplicateDecisionError(ValueError):
    """Raised when a decision_id is captured more than once.

    Decision-time evidence is captured once; re-capturing under the same id
    would be indistinguishable from overwriting it, which the contract
    forbids. A genuinely revised decision needs a new decision_id.
    """


class ProspectiveMLBStore:
    DECISIONS_FILENAME = "mlb_prospective_decisions.jsonl"
    OUTCOMES_FILENAME = "mlb_prospective_outcomes.jsonl"

    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.decisions_path = self.base_dir / self.DECISIONS_FILENAME
        self.outcomes_path = self.base_dir / self.OUTCOMES_FILENAME

    def append_decision(self, decision: ProspectiveMLBDecision) -> None:
        if self._decision_id_exists(decision.decision_id):
            raise DuplicateDecisionError(
                f"decision_id {decision.decision_id!r} already captured; "
                "decision-time evidence cannot be recaptured or overwritten"
            )
        with self.decisions_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(decision), sort_keys=True) + "\n")

    def append_outcome(self, outcome: ProspectiveMLBOutcome) -> None:
        with self.outcomes_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(outcome), sort_keys=True) + "\n")

    def _decision_id_exists(self, decision_id: str) -> bool:
        return any(d["decision_id"] == decision_id for d in self.iter_decisions())

    def iter_decisions(self) -> Iterator[Dict]:
        if not self.decisions_path.exists():
            return
        with self.decisions_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def iter_outcomes(self) -> Iterator[Dict]:
        if not self.outcomes_path.exists():
            return
        with self.outcomes_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def latest_outcomes_by_decision(self) -> Dict[str, Dict]:
        latest: Dict[str, Dict] = {}
        for outcome in self.iter_outcomes():
            latest[outcome["decision_id"]] = outcome  # last line wins; earlier lines stay on disk
        return latest
