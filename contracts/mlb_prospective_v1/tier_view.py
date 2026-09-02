"""Combined (decision + latest outcome) eligibility-tier view.

The eligibility_tier stored on a captured ProspectiveMLBDecision reflects
what was knowable at decision time -- clv_usable is always False then,
since no closing price exists yet, which caps every freshly-captured
decision at TIER_B. Once a close does arrive, current_eligibility()
recomputes the tier by combining the decision's own flags with the latest
outcome's clv_usable, purely as a read-only view for reporting/claims.

It never writes back onto the decision record -- the decision stays frozen
and its stored eligibility_tier is untouched (Phase 0 evidence contract:
later enrichment must not overwrite decision-time evidence). This is the
one place that combined tier is computed so reports and any future
consumer agree on the same answer.
"""
from typing import Dict, List, Optional, Tuple

from contracts.mlb_replay_v1.tiers import classify_tier


def current_eligibility(decision: Dict, outcome: Optional[Dict]) -> Tuple[str, List[str]]:
    flags = {
        "decision_time_valid": decision.get("decision_time_valid", False),
        "sportsbook_price_valid": decision.get("sportsbook_price_valid", False),
        "result_valid": decision.get("result_valid", False),
        "model_attributable": decision.get("model_attributable", False),
        "rationale_traceable": decision.get("rationale_traceable", False),
        "clv_usable": bool(outcome and outcome.get("clv_usable")),
        "known_provenance_damage": decision.get("known_provenance_damage", False),
        "reconstructed_evidence": decision.get("reconstructed_evidence", False),
        "historical_missing_shadow": decision.get("historical_missing_shadow", False),
        "ambiguous_identity": decision.get("ambiguous_identity", False),
        "conflicting_results": decision.get("conflicting_results", False),
    }
    tier, reasons = classify_tier(flags)
    dfs_related = "EXCL_DFS_PLACEHOLDER_PRICE" in (decision.get("exclusion_reasons") or ())
    if dfs_related and "EXCL_INVALID_OR_PLACEHOLDER_PRICE" in reasons:
        reasons = [
            "EXCL_DFS_PLACEHOLDER_PRICE" if c == "EXCL_INVALID_OR_PLACEHOLDER_PRICE" else c
            for c in reasons
        ]
    return tier, reasons
