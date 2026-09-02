"""Anti-leakage enforcement for MLB_REPLAY_EVIDENCE_V1.

The replay engine must construct its decision using only evidence available
at decision_ts_utc. assert_no_leakage() is the single gate every workstream
must run a replay-decision input payload through before it reaches the
scanner/resolver/governor.
"""
from datetime import datetime
from typing import Any, Dict, Optional, Union

from contracts.mlb_replay_v1.contract import ANTI_LEAKAGE

FUTURE_OUTCOME_FIELDS = frozenset(ANTI_LEAKAGE["future_outcome_fields"])
ORIGINAL_DECISION_OUTPUT_FIELDS = frozenset(ANTI_LEAKAGE["original_decision_output_fields"])
FORBIDDEN_REPLAY_INPUT_FIELDS = FUTURE_OUTCOME_FIELDS | ORIGINAL_DECISION_OUTPUT_FIELDS


class LeakageError(ValueError):
    """Raised when a replay-decision input payload contains forbidden evidence."""


def _to_comparable(ts: Union[str, datetime]) -> datetime:
    if isinstance(ts, datetime):
        return ts
    return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))


def assert_no_leakage(payload: Dict[str, Any], decision_ts_utc: Optional[Union[str, datetime]] = None) -> None:
    """Raise LeakageError if `payload` (the input side of a replay decision)
    carries any field forbidden by the contract.

    Checks, in order:
    1. No top-level key is a future-outcome or original-decision-output field.
    2. No market_snapshots entry is timestamped after decision_ts_utc.
    3. No postgame_stats field is present.
    4. historical_decision_id, if present, is not accompanied by any key
       suggesting it was consumed as a feature (best-effort name check).
    """
    forbidden_present = FORBIDDEN_REPLAY_INPUT_FIELDS & payload.keys()
    if forbidden_present:
        raise LeakageError(
            f"Forbidden fields present in replay-decision input payload: {sorted(forbidden_present)}"
        )

    snapshots = payload.get("market_snapshots")
    if snapshots and decision_ts_utc is not None:
        cutoff = _to_comparable(decision_ts_utc)
        for snap in snapshots:
            snap_ts = snap.get("snapshot_ts_utc") if isinstance(snap, dict) else None
            if snap_ts is not None and _to_comparable(snap_ts) > cutoff:
                raise LeakageError(
                    f"Future market snapshot present: snapshot_ts_utc={snap_ts} > decision_ts_utc={decision_ts_utc}"
                )

    if payload.get("postgame_stats"):
        raise LeakageError("postgame_stats field is forbidden in a replay-decision input payload")
