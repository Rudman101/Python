"""Exact-slice key construction for MLB_REPLAY_EVIDENCE_V1.

The exact-slice key is the evaluation unit (contract Principle 6): exact
market slices, never aggregate lanes. Bucket boundaries here are Phase 0
defaults so downstream workstreams can start in parallel; refining a bucket
function's boundaries in a later phase does not change the contract's field
names or ordering, so existing slice keys stay comparable in shape even if
their bucket labels are re-tuned.
"""
from typing import Any, Dict, Optional, Tuple

SLICE_KEY_FIELDS: Tuple[str, ...] = (
    "sport",
    "model_source_family",
    "market",
    "side",
    "line_bucket",
    "price_bucket",
    "decision_lead_time_bucket",
    "model_version_or_unattributed",
)

UNATTRIBUTED_MODEL = "UNATTRIBUTED"
UNMODELED_FAMILY = "UNMODELED"
NO_LINE_BUCKET = "NO_LINE"
UNKNOWN_LEAD_TIME_BUCKET = "UNKNOWN"


def bucket_model_source_family(model_version: Optional[str]) -> str:
    if not model_version:
        return UNMODELED_FAMILY
    return model_version.split(".")[0]


def bucket_line(line: Optional[float]) -> str:
    if line is None:
        return NO_LINE_BUCKET
    rounded = round(float(line) * 2) / 2.0
    return f"{rounded:g}"


def bucket_price(odds_american: Optional[int]) -> str:
    if odds_american is None:
        return "UNKNOWN"
    odds = int(odds_american)
    if odds <= -200:
        return "HEAVY_FAVORITE"
    if -199 <= odds <= -110:
        return "FAVORITE"
    if -109 <= odds <= 109:
        return "PICKEM"
    if 110 <= odds <= 199:
        return "UNDERDOG"
    return "HEAVY_UNDERDOG"


def bucket_decision_lead_time(minutes_to_start: Optional[float]) -> str:
    if minutes_to_start is None:
        return UNKNOWN_LEAD_TIME_BUCKET
    m = float(minutes_to_start)
    if m < 0:
        return "IN_PLAY"
    if m < 30:
        return "LT_30M"
    if m < 120:
        return "30M_TO_2H"
    if m < 720:
        return "2H_TO_12H"
    if m < 1440:
        return "12H_TO_24H"
    return "GT_24H"


def build_exact_slice_key(observation: Dict[str, Any]) -> Tuple[str, ...]:
    """Build the canonical exact-slice key tuple for one replay observation.

    Field order matches SLICE_KEY_FIELDS / the contract's exact_slice_key.
    Never substitute a lane-level aggregate for this key.
    """
    model_version = observation.get("model_version")
    return (
        observation["sport"],
        bucket_model_source_family(model_version),
        observation["market"],
        observation["side"],
        bucket_line(observation.get("line")),
        bucket_price(observation.get("odds_american")),
        bucket_decision_lead_time(observation.get("minutes_to_start")),
        model_version if model_version else UNATTRIBUTED_MODEL,
    )
