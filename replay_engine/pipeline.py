"""Decision-pipeline ports (Protocols) that Workstream B replays against.

Workstream A (the real scanner/resolver/policy/governor) does not exist yet
in this repository. Rather than block on it, this module defines the seam
those components must satisfy. replay_engine.reference_pipeline provides a
synthetic, clearly-labeled implementation of these same ports so the replay
engine, its tests, and its fixtures can be built and proven correct today.
When Workstream A lands, its scanner/resolver/policy/governor can be wired
into replay_engine.engine.ReplayEngine by constructing a DecisionPipeline
from the real components instead of the reference ones — no change to the
engine, projection, hashing, schema, or store code is required.

All four ports receive only the anti-leakage-clean payload produced by
replay_engine.projection (or, for the scanner in POLICY_COUNTERFACTUAL mode,
are not called at all — see replay_engine.modes). None of them may be handed
outcome/settlement data or the original decision's own recommendation.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class ScannerResult:
    """Output of the scanner: does the market look worth acting on."""

    classification: str  # e.g. "BET" | "NO_BET"
    model_probability: Optional[float]
    edge_probability: Optional[float]
    ev: Optional[float]
    confidence: Optional[Any]
    model_version: Optional[str]
    reasons: List[str] = field(default_factory=list)
    #: True only under POLICY_COUNTERFACTUAL, where this result was built
    #: directly from the historical row's recorded belief instead of being
    #: produced by a scanner port call.
    historical_belief_fixed: bool = False


@dataclass(frozen=True)
class ResolverResult:
    """Output of the resolver: is this scanner classification actionable."""

    decision: str  # e.g. "CONFIRMED" | "REJECTED"
    reasons: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class PolicyResult:
    """Output of the policy layer: does configured policy allow this."""

    decision: str  # e.g. "ALLOW" | "BLOCK"
    policy_version: str
    reasons: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class GovernorResult:
    """Output of the governor: final allocation decision and sizing."""

    decision: str  # e.g. "APPROVE" | "BLOCK" | "NO_ACTION"
    units: Optional[float]
    reasons: List[str] = field(default_factory=list)


@runtime_checkable
class Scanner(Protocol):
    version: str

    def scan(self, payload: Dict[str, Any]) -> ScannerResult: ...


@runtime_checkable
class Resolver(Protocol):
    version: str

    def resolve(self, payload: Dict[str, Any], scanner_result: ScannerResult) -> ResolverResult: ...


@runtime_checkable
class PolicyLayer(Protocol):
    version: str

    def apply(
        self,
        payload: Dict[str, Any],
        scanner_result: ScannerResult,
        resolver_result: ResolverResult,
        policy_config: Dict[str, Any],
    ) -> PolicyResult: ...


@runtime_checkable
class Governor(Protocol):
    version: str

    def govern(
        self,
        payload: Dict[str, Any],
        scanner_result: ScannerResult,
        resolver_result: ResolverResult,
        policy_result: PolicyResult,
        policy_config: Dict[str, Any],
    ) -> GovernorResult: ...


@dataclass(frozen=True)
class DecisionPipeline:
    """The four wired-together ports plus an identity for CURRENT_REPLAY_MODEL_VERSION.

    code_version identifies this exact pipeline's code (today: the reference
    pipeline's version string; later: Workstream A's real pipeline version).
    It is recorded as replay_code_version / CURRENT_REPLAY_MODEL_VERSION and
    is never overwritten by, or overwrites, a historical row's own
    model_version (ORIGINAL_MODEL_VERSION).
    """

    scanner: Scanner
    resolver: Resolver
    policy: PolicyLayer
    governor: Governor
    code_version: str
