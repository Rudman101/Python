"""Decision-reason dialect normalization for prospective MLB capture.

Different scanner/governor code versions have used different vocabularies
("dialects") for the same underlying decision reason. This module is the
single shared registry that normalizes any registered dialect's raw reason
text into a canonical reason code, so rationale coverage can be measured
and compared across code versions. The original raw text is never rewritten
by this module — callers keep it verbatim alongside the canonical code.
"""
from typing import Dict, Optional, Tuple

CANONICAL_REASON_CODES: Dict[str, str] = {
    "EDGE_THRESHOLD_MET": "Model edge exceeded the scanner's actionability threshold.",
    "SHARP_CONSENSUS_ALIGNED": "Model side agrees with sharp/consensus market reference.",
    "GOVERNOR_ALLOCATED": "Governor allocated funded units to this decision.",
    "GOVERNOR_HELD_EXPOSURE_CAP": "Governor held/blocked the decision due to an exposure cap.",
    "GOVERNOR_HELD_POLICY": "Governor held/blocked the decision due to a policy rule.",
    "MANUAL_TRACKING_ONLY": "Decision recorded as manual $1 tracking, not an official bet.",
    "ZERO_UNIT_PAPER_TRACK": "Decision recorded as zero-unit prospective tracking only.",
    "STALE_PRICE_NO_ACTION": "No action taken because the reference price was stale.",
}

# dialect -> {raw_reason_text (case-insensitive) -> canonical reason code}
# Register a new scanner/governor rationale vocabulary here as it ships;
# never hand-roll a mapping anywhere else.
_DIALECT_MAPS: Dict[str, Dict[str, str]] = {
    "scanner_v1": {
        "edge_above_threshold": "EDGE_THRESHOLD_MET",
        "consensus_aligned": "SHARP_CONSENSUS_ALIGNED",
    },
    "governor_v1": {
        "allocated": "GOVERNOR_ALLOCATED",
        "held_exposure_cap": "GOVERNOR_HELD_EXPOSURE_CAP",
        "held_policy": "GOVERNOR_HELD_POLICY",
    },
    "governor_v2": {
        # governor_v2 renamed a few reasons; still normalizes to the same
        # canonical codes so cross-version rationale stays comparable.
        "funded": "GOVERNOR_ALLOCATED",
        "blocked_exposure_cap": "GOVERNOR_HELD_EXPOSURE_CAP",
        "blocked_policy": "GOVERNOR_HELD_POLICY",
        "stale_price": "STALE_PRICE_NO_ACTION",
    },
    "manual_tracking_v1": {
        "manual_dollar_track": "MANUAL_TRACKING_ONLY",
        "zero_unit_track": "ZERO_UNIT_PAPER_TRACK",
    },
}

REGISTERED_DIALECTS = frozenset(_DIALECT_MAPS.keys())


def normalize_rationale(
    dialect: Optional[str], raw_reason: Optional[str]
) -> Tuple[Optional[str], bool]:
    """Return (canonical_reason_code_or_None, rationale_traceable).

    An unregistered dialect, or a raw reason not present in a registered
    dialect's vocabulary, leaves rationale_traceable False and returns no
    canonical code — the caller still stores the raw text untouched.
    """
    if not raw_reason or not dialect:
        return None, False
    dialect_map = _DIALECT_MAPS.get(dialect)
    if dialect_map is None:
        return None, False
    canonical = dialect_map.get(raw_reason.strip().lower())
    if canonical is None:
        return None, False
    return canonical, True
