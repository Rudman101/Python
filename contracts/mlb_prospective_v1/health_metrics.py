"""Prospective evidence-health coverage metrics for MLB decisions.

compute_coverage() is the single place these percentages are computed so
the daily report and any ad hoc dashboard use identical definitions:

- MLB decisions with attributable model version %
- MLB decisions with traceable rationale %
- MLB decisions with valid decision-time price %
- MLB decisions with eventual valid close %
- MLB decisions with settlement %
"""
from typing import Dict, List, Optional

from contracts.mlb_prospective_v1.alerts import ALERT_UNMAPPED_WRITER
from contracts.mlb_prospective_v1.enrichment import SETTLED_RESULTS

EMPTY_COVERAGE = {
    "total_decisions": 0,
    "pct_model_version_attributable": None,
    "pct_rationale_traceable": None,
    "pct_valid_decision_price": None,
    "pct_eventual_valid_close": None,
    "pct_settled": None,
    "unmapped_writer_ids": [],
}


def compute_coverage(decisions: List[Dict], outcomes_by_decision: Dict[str, Dict]) -> Dict:
    total = len(decisions)
    if total == 0:
        return dict(EMPTY_COVERAGE)

    model_attributable = sum(1 for d in decisions if d.get("model_attributable"))
    rationale_traceable = sum(1 for d in decisions if d.get("rationale_traceable"))
    valid_price = sum(1 for d in decisions if d.get("sportsbook_price_valid"))

    settled = 0
    valid_close = 0
    for d in decisions:
        outcome = outcomes_by_decision.get(d["decision_id"])
        if outcome and outcome.get("result") in SETTLED_RESULTS:
            settled += 1
        if outcome and outcome.get("clv_usable"):
            valid_close += 1

    unmapped_writers = sorted(
        {
            d.get("writer_id")
            for d in decisions
            if ALERT_UNMAPPED_WRITER in (d.get("evidence_quality_warnings") or [])
        }
    )

    def pct(n: int) -> float:
        return round(100.0 * n / total, 2)

    return {
        "total_decisions": total,
        "pct_model_version_attributable": pct(model_attributable),
        "pct_rationale_traceable": pct(rationale_traceable),
        "pct_valid_decision_price": pct(valid_price),
        "pct_eventual_valid_close": pct(valid_close),
        "pct_settled": pct(settled),
        "unmapped_writer_ids": unmapped_writers,
    }
