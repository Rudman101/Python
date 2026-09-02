"""MLB Replay V1 — deterministic historical replay engine (Workstream B).

Built strictly on top of the frozen contracts.mlb_replay_v1 evidence contract
(MLB_REPLAY_EVIDENCE_V1). Does not depend on Workstream A's production
scanner/resolver/policy/governor: replay_engine.pipeline defines the ports
those components must satisfy, and replay_engine.reference_pipeline is a
synthetic, clearly-labeled stand-in used for tests and fixtures until the
real pipeline is wired in through the same ports.

This module is simulation only. Nothing here places, creates, or modifies a
real wager, and nothing here writes to the original shadow_bets/signal
tables (see replay_engine.store).
"""
from replay_engine.modes import ReplayMode
from replay_engine.pipeline import (
    DecisionPipeline,
    GovernorResult,
    PolicyResult,
    ResolverResult,
    ScannerResult,
)
from replay_engine.engine import ReplayEngine
from replay_engine.schema import ReplayObservation, SealedDecision
from replay_engine.store import AppendOnlyReplayStore

__all__ = [
    "ReplayMode",
    "DecisionPipeline",
    "ScannerResult",
    "ResolverResult",
    "PolicyResult",
    "GovernorResult",
    "ReplayEngine",
    "SealedDecision",
    "ReplayObservation",
    "AppendOnlyReplayStore",
]
