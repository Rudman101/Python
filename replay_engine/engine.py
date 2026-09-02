"""ReplayEngine: orchestrates one deterministic replay decision end-to-end.

run_decision() is the only function that talks to the scanner/resolver/
policy/governor ports. It:
  1. Projects the historical row into an anti-leakage-clean payload
     (replay_engine.projection) -- a strict whitelist, so no outcome or
     original-decision-output field can ever reach step 2, structurally.
  2. Dispatches on ReplayMode: ORIGINAL_DECISION_REPLAY calls the scanner
     port; POLICY_COUNTERFACTUAL never calls it, building a fixed
     ScannerResult from the historical row's OWN recorded belief instead.
     These two code paths never merge (no blending of modes).
  3. Runs resolver -> policy -> governor on whichever ScannerResult step 2
     produced.
  4. Derives the final action/units/reason and compares it with the
     ORIGINAL historical action (using original-decision-output fields for
     post-hoc comparison only -- never as pipeline input).
  5. Computes canonical hashes and seals everything above into a frozen
     SealedDecision -- before any outcome/settlement data is touched.

attach_outcome() is the only function that may add result/profit/closing
odds/CLV, and it requires an already-built SealedDecision object, so
scoring can never happen before sealing: there is no code path around it.
"""
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from contracts.mlb_replay_v1.exact_slice import build_exact_slice_key
from contracts.mlb_replay_v1.tiers import classify_tier
from replay_engine.hashing import sha256_hex
from replay_engine.modes import ReplayMode
from replay_engine.pipeline import DecisionPipeline
from replay_engine.projection import (
    project_policy_counterfactual_payload,
    project_raw_replay_payload,
)
from replay_engine.reference_pipeline import build_fixed_scanner_result_from_historical_belief
from replay_engine.schema import ReplayObservation, SealedDecision

_SETTLED_RESULTS = ("win", "loss", "push", "void")


def _derive_historical_original_action(historical_row: Dict[str, Any]) -> str:
    """Derived only for comparison reporting, never for pipeline input.

    Prefers original_recommended_units (>0 => BET); falls back to
    governor_state text when units are absent. Neither field is available
    to the replay decision itself -- both are forbidden pipeline inputs
    under contracts.mlb_replay_v1.anti_leakage.
    """
    units = historical_row.get("original_recommended_units")
    if units is not None:
        return "BET" if float(units) > 0 else "NO_BET"
    governor_state = historical_row.get("governor_state")
    if governor_state:
        return "BET" if str(governor_state).upper() in ("APPROVED", "BET", "CONFIRMED") else "NO_BET"
    return "NO_BET"


def _derive_final_action(resolver_result, governor_result) -> Tuple[str, Optional[float], str]:
    if governor_result.decision == "APPROVE":
        return "BET", governor_result.units, "approved:" + ",".join(governor_result.reasons)
    if governor_result.decision == "BLOCK":
        return "NO_BET", None, "governor_block:" + ",".join(governor_result.reasons)
    return "NO_BET", None, "resolver_rejected:" + ",".join(resolver_result.reasons)


def _diff_from_original(
    replay_action: str,
    replay_units: Optional[float],
    historical_original_action: str,
    historical_row: Dict[str, Any],
) -> Tuple[Tuple[str, ...], str]:
    diffs = []
    if replay_action != historical_original_action:
        diffs.append(f"action_changed:{historical_original_action}->{replay_action}")
    original_units = historical_row.get("original_recommended_units")
    if (
        original_units is not None
        and replay_units is not None
        and round(float(original_units), 2) != round(float(replay_units), 2)
    ):
        diffs.append(f"units_changed:{original_units}->{replay_units}")
    if not diffs:
        return tuple(), "no_material_difference_from_original_decision"
    return tuple(diffs), "current_pipeline_diverges_from_original:" + ";".join(diffs)


def _score(action: str, units: Optional[float], odds_american: Optional[int], result: str) -> Optional[float]:
    """American-odds profit in units. Never fabricates a price: if a BET
    action lacks units or odds, or the result isn't settled yet, returns
    None rather than guessing."""
    if action != "BET":
        return 0.0
    if units is None or odds_american is None:
        return None
    if result not in _SETTLED_RESULTS:
        return None
    stake = float(units)
    if result in ("push", "void"):
        return 0.0
    odds = int(odds_american)
    if result == "win":
        payout = stake * (100.0 / abs(odds)) if odds < 0 else stake * (odds / 100.0)
        return round(payout, 4)
    return round(-stake, 4)  # loss


def run_decision(
    historical_row: Dict[str, Any],
    mode: ReplayMode,
    pipeline: DecisionPipeline,
    policy_config: Dict[str, Any],
    replay_policy_version: str,
    replay_observation_id: Optional[str] = None,
    replay_ts_utc: Optional[str] = None,
) -> SealedDecision:
    if mode == ReplayMode.ORIGINAL_DECISION_REPLAY:
        payload = project_raw_replay_payload(historical_row)
        scanner_result = pipeline.scanner.scan(payload)
    elif mode == ReplayMode.POLICY_COUNTERFACTUAL:
        payload = project_policy_counterfactual_payload(historical_row)
        scanner_result = build_fixed_scanner_result_from_historical_belief(payload)
    else:
        raise ValueError(f"Unknown replay mode: {mode!r}")

    resolver_result = pipeline.resolver.resolve(payload, scanner_result)
    policy_result = pipeline.policy.apply(payload, scanner_result, resolver_result, policy_config)
    governor_result = pipeline.governor.govern(payload, scanner_result, resolver_result, policy_result, policy_config)

    final_action, final_units, final_reason = _derive_final_action(resolver_result, governor_result)
    historical_original_action = _derive_historical_original_action(historical_row)
    diffs, diff_reason = _diff_from_original(final_action, final_units, historical_original_action, historical_row)

    replay_inputs_available = tuple(sorted(k for k, v in payload.items() if v is not None))
    input_evidence_hash = sha256_hex(payload)
    policy_config_hash = sha256_hex(policy_config)

    # Everything that determinism must reproduce byte-for-byte across runs.
    # Deliberately excludes replay_observation_id (fresh uuid per run) and
    # replay_ts_utc (wall-clock, always later than T) -- neither is part of
    # the decision itself.
    decision_core = {
        "mode": mode.value,
        "scanner_result": asdict(scanner_result),
        "resolver_result": asdict(resolver_result),
        "policy_result": asdict(policy_result),
        "governor_result": asdict(governor_result),
        "final_action": final_action,
        "final_units": final_units,
        "final_reason": final_reason,
        "input_evidence_hash": input_evidence_hash,
        "policy_config_hash": policy_config_hash,
        "replay_code_version": pipeline.code_version,
        "replay_policy_version": replay_policy_version,
    }
    output_hash = sha256_hex(decision_core)

    game_date = historical_row.get("game_date")
    return SealedDecision(
        replay_observation_id=replay_observation_id or str(uuid.uuid4()),
        historical_decision_id=historical_row["historical_decision_id"],
        source_identity=historical_row.get("source_identity"),
        source_table=historical_row["source_table"],
        shadow_bet_id=historical_row.get("shadow_bet_id"),
        event_id=historical_row["event_id"],
        game_date=str(game_date) if game_date is not None else None,
        market=historical_row["market"],
        side=historical_row["side"],
        line=historical_row.get("line"),
        player_id=historical_row.get("player_id"),
        team_id=historical_row.get("team_id"),
        book=historical_row["book"],
        decision_ts_utc=str(historical_row["decision_ts_utc"]),
        game_start_ts_utc=str(historical_row["game_start_ts_utc"]),
        minutes_to_start=historical_row.get("minutes_to_start"),
        odds_american=historical_row.get("odds_american"),
        implied_probability=historical_row.get("implied_probability"),
        ORIGINAL_MODEL_VERSION=historical_row.get("model_version"),
        CURRENT_REPLAY_MODEL_VERSION=pipeline.code_version,
        replay_code_version=pipeline.code_version,
        replay_policy_version=replay_policy_version,
        replay_mode=mode.value,
        replay_ts_utc=replay_ts_utc or datetime.now(timezone.utc).isoformat(),
        replay_inputs_available=replay_inputs_available,
        replay_scanner_result=scanner_result,
        replay_resolver_result=resolver_result,
        replay_policy_result=policy_result,
        replay_governor_result=governor_result,
        replay_proposed_action=final_action,
        replay_units=final_units,
        replay_reason=final_reason,
        historical_original_action=historical_original_action,
        differences_from_original=diffs,
        difference_reason=diff_reason,
        input_evidence_hash=input_evidence_hash,
        policy_config_hash=policy_config_hash,
        output_hash=output_hash,
    )


def attach_outcome(sealed: SealedDecision, historical_row: Dict[str, Any]) -> ReplayObservation:
    """Attach outcome/settlement fields to an ALREADY-SEALED decision.

    Price semantics (V1): both the historical and the simulated-replay
    profit are computed against the exact same historical decision-time
    odds_american snapshot -- the only price this replay is entitled to use
    (contract PRICE SEMANTICS). No later/executable price is fabricated.
    """
    result = historical_row.get("result", "unsettled")

    original_units = historical_row.get("original_recommended_units")
    original_action = "BET" if (original_units or 0) > 0 else "NO_BET"
    historical_profit_at_original_price = _score(
        action=original_action,
        units=original_units,
        odds_american=historical_row.get("odds_american"),
        result=result,
    )
    simulated_replay_profit_at_historical_price = _score(
        action=sealed.replay_proposed_action,
        units=sealed.replay_units,
        odds_american=sealed.odds_american,
        result=result,
    )

    integrity = historical_row.get("integrity_eligibility") or {}
    tier, exclusion_reasons = classify_tier(integrity)

    slice_source = {
        "sport": historical_row.get("sport", "MLB"),
        "market": sealed.market,
        "side": sealed.side,
        "line": sealed.line,
        "odds_american": sealed.odds_american,
        "minutes_to_start": sealed.minutes_to_start,
        "model_version": sealed.ORIGINAL_MODEL_VERSION,
    }
    exact_slice_key = build_exact_slice_key(slice_source)

    return ReplayObservation(
        sealed=sealed,
        result=result,
        profit_units=historical_row.get("profit_units"),
        result_provenance=historical_row.get("result_provenance"),
        closing_odds=historical_row.get("closing_odds"),
        closing_price_provenance=historical_row.get("closing_price_provenance"),
        clv=historical_row.get("clv"),
        settlement_route=historical_row.get("settlement_route"),
        historical_profit_at_original_price=historical_profit_at_original_price,
        simulated_replay_profit_at_historical_price=simulated_replay_profit_at_historical_price,
        replay_eligibility_tier=tier,
        exclusion_reasons=tuple(exclusion_reasons),
        exact_slice_key=exact_slice_key,
    )


class ReplayEngine:
    """Stateful convenience wrapper binding a pipeline/policy_config so
    callers (e.g. the CLI) don't have to thread them through every call.
    run_decision()/attach_outcome() module functions remain the ground
    truth; this class only forwards to them."""

    def __init__(self, pipeline: DecisionPipeline, policy_config: Dict[str, Any], replay_policy_version: str):
        self.pipeline = pipeline
        self.policy_config = dict(policy_config)
        self.replay_policy_version = replay_policy_version

    def run_decision(
        self,
        historical_row: Dict[str, Any],
        mode: ReplayMode,
        replay_observation_id: Optional[str] = None,
        replay_ts_utc: Optional[str] = None,
    ) -> SealedDecision:
        return run_decision(
            historical_row=historical_row,
            mode=mode,
            pipeline=self.pipeline,
            policy_config=self.policy_config,
            replay_policy_version=self.replay_policy_version,
            replay_observation_id=replay_observation_id,
            replay_ts_utc=replay_ts_utc,
        )

    @staticmethod
    def attach_outcome(sealed: SealedDecision, historical_row: Dict[str, Any]) -> ReplayObservation:
        return attach_outcome(sealed, historical_row)

    def replay(
        self,
        historical_row: Dict[str, Any],
        mode: ReplayMode,
        replay_observation_id: Optional[str] = None,
        replay_ts_utc: Optional[str] = None,
    ) -> ReplayObservation:
        """Convenience: seal, then attach outcome. Still two distinct
        internal calls, in that order -- see attach_outcome's docstring."""
        sealed = self.run_decision(historical_row, mode, replay_observation_id, replay_ts_utc)
        return self.attach_outcome(sealed, historical_row)
