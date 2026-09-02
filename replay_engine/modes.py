"""Replay modes.

Two modes only, per the Workstream B spec. They are never blended: each
maps to a distinct code path in replay_engine.engine.ReplayEngine.run_decision
that builds a different input projection and, for POLICY_COUNTERFACTUAL,
never invokes the scanner port at all (see replay_engine.projection).
"""
from enum import Enum


class ReplayMode(str, Enum):
    #: Re-evaluate at the original historical decision time using today's
    #: full pipeline (scanner independently re-derives belief from raw
    #: decision-time features; historical model belief is not shown to it).
    ORIGINAL_DECISION_REPLAY = "ORIGINAL_DECISION_REPLAY"

    #: Keep the historical model belief fixed (model_probability,
    #: edge_probability, ev, confidence, model_version as originally
    #: recorded) and apply only today's resolver/policy/governor to it.
    #: The scanner port is bypassed entirely in this mode.
    POLICY_COUNTERFACTUAL = "POLICY_COUNTERFACTUAL"
