"""Replay output schema.

SealedDecision is the frozen, pre-outcome decision payload produced by
ReplayEngine.run_decision(). It carries the replayed decision itself plus a
comparison against the *original* historical action (original-decision
fields are legitimate to use for post-hoc comparison — they were simply
forbidden as *pipeline input*, per the contract's anti-leakage rules) — but
never the outcome/settlement fields.

ReplayObservation is produced only by attach_outcome(sealed, ...), which
requires an already-constructed SealedDecision. Because SealedDecision is
frozen (immutable) and attach_outcome is the only function that adds
outcome/settlement fields, there is no code path that can settle or score a
decision before it has been sealed: "sealing" is not a convention here, it
is a distinct, required, prior object.

Field names mirror contracts/mlb_replay_v1/evidence_contract.json's
`replay` / `identity` / `decision_time_evidence` / `outcome` /
`integrity_eligibility` schema sections wherever a corresponding field
exists there. Fields with no counterpart in the frozen Phase 0 schema
(replay_policy_result; the provenance hash block; ORIGINAL_MODEL_VERSION /
CURRENT_REPLAY_MODEL_VERSION as named siblings of model_version;
differences_from_original / difference_reason) are additive extensions —
the JSON contract does not forbid additional fields, and several of these
are explicitly required by the Workstream B task spec even though Phase 0's
minimum schema does not name them individually.
"""
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Tuple

from replay_engine.hashing import sha256_hex
from replay_engine.pipeline import GovernorResult, PolicyResult, ResolverResult, ScannerResult


@dataclass(frozen=True)
class SealedDecision:
    # --- identity ---
    replay_observation_id: str
    historical_decision_id: str
    source_identity: Optional[str]
    source_table: str
    shadow_bet_id: Optional[str]
    event_id: str
    game_date: Optional[str]
    market: str
    side: str
    line: Optional[float]
    player_id: Optional[str]
    team_id: Optional[str]
    book: str

    # --- decision-time evidence actually used (post-projection, reporting only) ---
    decision_ts_utc: str
    game_start_ts_utc: str
    minutes_to_start: Optional[float]
    odds_american: Optional[int]
    implied_probability: Optional[float]

    # --- model version distinction (never overwritten one by the other) ---
    ORIGINAL_MODEL_VERSION: Optional[str]
    CURRENT_REPLAY_MODEL_VERSION: str

    # --- replay identity/provenance ---
    replay_code_version: str
    replay_policy_version: str
    replay_mode: str
    replay_ts_utc: str
    replay_inputs_available: Tuple[str, ...]

    # --- replayed decision ---
    replay_scanner_result: ScannerResult
    replay_resolver_result: ResolverResult
    replay_policy_result: PolicyResult
    replay_governor_result: GovernorResult
    replay_proposed_action: str
    replay_units: Optional[float]
    replay_reason: str

    # --- comparison against the ORIGINAL historical decision (not fed to the pipeline) ---
    historical_original_action: str
    differences_from_original: Tuple[str, ...]
    difference_reason: str

    # --- determinism provenance ---
    input_evidence_hash: str
    policy_config_hash: str
    output_hash: str

    def to_dict(self) -> Dict[str, Any]:
        d = {
            k: v
            for k, v in vars(self).items()
            if k
            not in (
                "replay_scanner_result",
                "replay_resolver_result",
                "replay_policy_result",
                "replay_governor_result",
            )
        }
        d["replay_scanner_result"] = asdict(self.replay_scanner_result)
        d["replay_resolver_result"] = asdict(self.replay_resolver_result)
        d["replay_policy_result"] = asdict(self.replay_policy_result)
        d["replay_governor_result"] = asdict(self.replay_governor_result)
        d["replay_inputs_available"] = list(self.replay_inputs_available)
        d["differences_from_original"] = list(self.differences_from_original)
        return d


@dataclass(frozen=True)
class ReplayObservation:
    """Final, append-only observation: SealedDecision + outcome, scored only
    after sealing, plus the derived evidence tier for the row."""

    sealed: SealedDecision

    # --- outcome (attached only after sealing) ---
    result: str
    profit_units: Optional[float]
    result_provenance: Optional[str]
    closing_odds: Optional[int]
    closing_price_provenance: Optional[str]
    clv: Optional[float]
    settlement_route: Optional[str]

    # --- price-semantics-constrained scoring: historical decision snapshot only ---
    historical_profit_at_original_price: Optional[float]
    simulated_replay_profit_at_historical_price: Optional[float]

    # --- integrity / eligibility (delegated to contracts.mlb_replay_v1.tiers) ---
    replay_eligibility_tier: str
    exclusion_reasons: Tuple[str, ...]
    exact_slice_key: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        d = self.sealed.to_dict()
        d["result"] = self.result
        d["profit_units"] = self.profit_units
        d["result_provenance"] = self.result_provenance
        d["closing_odds"] = self.closing_odds
        d["closing_price_provenance"] = self.closing_price_provenance
        d["clv"] = self.clv
        d["settlement_route"] = self.settlement_route
        d["historical_profit_at_original_price"] = self.historical_profit_at_original_price
        d["simulated_replay_profit_at_historical_price"] = self.simulated_replay_profit_at_historical_price
        d["replay_eligibility_tier"] = self.replay_eligibility_tier
        d["exclusion_reasons"] = list(self.exclusion_reasons)
        d["exact_slice_key"] = list(self.exact_slice_key)
        d["observation_hash"] = sha256_hex(d)
        return d
