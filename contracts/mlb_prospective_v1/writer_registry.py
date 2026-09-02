"""Registry of MLB decision writers known to reliably supply model_version.

capture_decision() is the shadow-writer chokepoint every MLB scanner/
governor/tracking code path must call. A writer_id absent from this
registry is unmapped: capture must not fabricate a model_version for it —
the decision stays visibly unattributable and a coverage alert fires
(see contracts.mlb_prospective_v1.alerts.ALERT_UNMAPPED_WRITER).

Add a writer here only once its code path is confirmed to populate
model_version on every decision it produces.
"""
from typing import FrozenSet

REGISTERED_WRITERS: FrozenSet[str] = frozenset(
    {
        "mlb_scanner_v1",
        "mlb_governor_v1",
        "mlb_manual_tracking_v1",
    }
)


def is_registered_writer(writer_id: str) -> bool:
    return bool(writer_id) and writer_id in REGISTERED_WRITERS
