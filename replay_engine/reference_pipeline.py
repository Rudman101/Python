"""Synthetic reference decision pipeline.

NOT Workstream A's real scanner/resolver/policy/governor — that component
does not exist in this repository yet. This is a small, fully deterministic
stand-in implementing the replay_engine.pipeline ports, built only so the
replay engine, its anti-leakage/determinism proofs, and its validation-set
fixtures can be exercised end-to-end today. Swap it out by constructing a
replay_engine.pipeline.DecisionPipeline from the real components once
Workstream A ships; nothing else in replay_engine changes.

Rules implemented here are intentionally simple and documented inline, each
one chosen to make one required validation-set scenario reachable:
  - invalid/DFS price -> resolver rejection (DFS invalid-price exclusion)
  - post-start decision -> resolver rejection (post-start exclusion)
  - opposite side already on the books at decision time -> resolver
    rejection (contradictory side)
  - governor exposure-cap context -> governor block even on a confirmed BET
  - policy consensus requirement -> policy block
"""
from typing import Any, Dict

from replay_engine.pipeline import (
    DecisionPipeline,
    GovernorResult,
    PolicyResult,
    ResolverResult,
    ScannerResult,
)

REFERENCE_PIPELINE_VERSION = "REPLAY_REFERENCE_PIPELINE_V1"
SCANNER_VERSION = "REFERENCE_SCANNER_V1"
RESOLVER_VERSION = "REFERENCE_RESOLVER_V1"
POLICY_VERSION = "REFERENCE_POLICY_V1"
GOVERNOR_VERSION = "REFERENCE_GOVERNOR_V1"

#: Minimum model-derived edge to classify as BET. Shared between the
#: reference scanner (ORIGINAL_DECISION_REPLAY) and the fixed-belief
#: ScannerResult builder used for POLICY_COUNTERFACTUAL, so both modes
#: apply an identical, documented bar.
BET_EDGE_THRESHOLD = 0.03

_DFS_BOOK_MARKERS = ("dfs", "dfs_placeholder", "dfs_fallback")


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _looks_like_invalid_or_dfs_price(payload: Dict[str, Any]) -> bool:
    book = str(payload.get("book") or "").lower()
    if any(marker in book for marker in _DFS_BOOK_MARKERS):
        return True
    odds = payload.get("odds_american")
    if odds is None:
        return True
    try:
        odds = int(odds)
    except (TypeError, ValueError):
        return True
    if odds == 0 or -100 < odds < 100:
        # American odds are never in (-100, 100); 0 is never valid.
        return True
    return False


def _has_contradictory_side(payload: Dict[str, Any]) -> bool:
    concurrent = payload.get("concurrent_decision_context") or []
    market = payload.get("market")
    event_id = payload.get("event_id")
    side = payload.get("side")
    for entry in concurrent:
        if (
            isinstance(entry, dict)
            and entry.get("market") == market
            and entry.get("event_id") == event_id
            and entry.get("side") is not None
            and entry.get("side") != side
        ):
            return True
    return False


class ReferenceScanner:
    version = SCANNER_VERSION

    def scan(self, payload: Dict[str, Any]) -> ScannerResult:
        implied = payload.get("implied_probability")
        features = payload.get("features") or {}
        signal = features.get("current_model_edge_signal")

        if implied is None or signal is None:
            return ScannerResult(
                classification="NO_BET",
                model_probability=None,
                edge_probability=None,
                ev=None,
                confidence=None,
                model_version=self.version,
                reasons=["insufficient_features_for_current_model"],
            )

        model_probability = _clamp01(float(implied) + float(signal))
        edge = model_probability - float(implied)
        ev = edge  # simplified synthetic EV proxy; not a real payout model
        classification = "BET" if edge >= BET_EDGE_THRESHOLD else "NO_BET"
        return ScannerResult(
            classification=classification,
            model_probability=model_probability,
            edge_probability=edge,
            ev=ev,
            confidence=features.get("current_model_confidence"),
            model_version=self.version,
            reasons=[f"edge={edge:.4f}_threshold={BET_EDGE_THRESHOLD}"],
        )


def build_fixed_scanner_result_from_historical_belief(payload: Dict[str, Any]) -> ScannerResult:
    """POLICY_COUNTERFACTUAL: build a ScannerResult from recorded historical
    belief without calling any Scanner port. If the historical belief is
    itself missing, this does not fabricate one — it reports NO_BET with an
    explicit reason, consistent with "missing/unknown provenance must
    remain unknown" (contract Principle 8)."""
    model_probability = payload.get("model_probability")
    edge = payload.get("edge_probability")
    ev = payload.get("ev")
    confidence = payload.get("confidence")
    model_version = payload.get("model_version")

    if model_probability is None or edge is None:
        return ScannerResult(
            classification="NO_BET",
            model_probability=model_probability,
            edge_probability=edge,
            ev=ev,
            confidence=confidence,
            model_version=model_version,
            reasons=["missing_historical_model_belief"],
            historical_belief_fixed=True,
        )

    classification = "BET" if float(edge) >= BET_EDGE_THRESHOLD else "NO_BET"
    return ScannerResult(
        classification=classification,
        model_probability=model_probability,
        edge_probability=edge,
        ev=ev,
        confidence=confidence,
        model_version=model_version,
        reasons=[f"historical_edge={float(edge):.4f}_threshold={BET_EDGE_THRESHOLD}"],
        historical_belief_fixed=True,
    )


class ReferenceResolver:
    version = RESOLVER_VERSION

    def resolve(self, payload: Dict[str, Any], scanner_result: ScannerResult) -> ResolverResult:
        if _looks_like_invalid_or_dfs_price(payload):
            return ResolverResult(decision="REJECTED", reasons=["invalid_price_source"])

        minutes_to_start = payload.get("minutes_to_start")
        if minutes_to_start is not None and float(minutes_to_start) < 0:
            return ResolverResult(decision="REJECTED", reasons=["post_start_exclusion"])

        if _has_contradictory_side(payload):
            return ResolverResult(decision="REJECTED", reasons=["contradictory_side"])

        if scanner_result.classification != "BET":
            return ResolverResult(decision="REJECTED", reasons=["scanner_no_bet"])

        return ResolverResult(decision="CONFIRMED", reasons=["scanner_bet_confirmed"])


class ReferencePolicyLayer:
    version = POLICY_VERSION

    def apply(
        self,
        payload: Dict[str, Any],
        scanner_result: ScannerResult,
        resolver_result: ResolverResult,
        policy_config: Dict[str, Any],
    ) -> PolicyResult:
        policy_version = policy_config.get("policy_version", "POLICY_REFERENCE_V1")
        if policy_config.get("require_consensus") and payload.get("consensus_state") != "consensus":
            return PolicyResult(decision="BLOCK", policy_version=policy_version, reasons=["consensus_required"])
        return PolicyResult(decision="ALLOW", policy_version=policy_version, reasons=["policy_clear"])


class ReferenceGovernor:
    version = GOVERNOR_VERSION

    def govern(
        self,
        payload: Dict[str, Any],
        scanner_result: ScannerResult,
        resolver_result: ResolverResult,
        policy_result: PolicyResult,
        policy_config: Dict[str, Any],
    ) -> GovernorResult:
        if resolver_result.decision != "CONFIRMED":
            return GovernorResult(decision="NO_ACTION", units=None, reasons=["resolver_not_confirmed"])

        if policy_result.decision == "BLOCK":
            return GovernorResult(decision="BLOCK", units=None, reasons=list(policy_result.reasons))

        governor_context = payload.get("governor_context") or {}
        if governor_context.get("exposure_cap_hit"):
            return GovernorResult(decision="BLOCK", units=None, reasons=["exposure_cap_hit"])

        max_units = float(policy_config.get("max_units", 2.0))
        edge = scanner_result.edge_probability or 0.0
        units = round(min(max(float(edge) * 10.0, 0.5), max_units), 2)
        return GovernorResult(decision="APPROVE", units=units, reasons=["approved"])


def build_reference_pipeline() -> DecisionPipeline:
    return DecisionPipeline(
        scanner=ReferenceScanner(),
        resolver=ReferenceResolver(),
        policy=ReferencePolicyLayer(),
        governor=ReferenceGovernor(),
        code_version=REFERENCE_PIPELINE_VERSION,
    )
