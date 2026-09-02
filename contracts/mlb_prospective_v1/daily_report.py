"""Daily prospective MLB evidence-health report.

Intended to run once per day (or on demand) while the 2026 MLB season is
still active, so coverage gaps are visible immediately rather than
discovered later in a retrospective audit.
"""
from datetime import date as date_cls
from typing import Dict, Optional

from contracts.mlb_prospective_v1.health_metrics import compute_coverage
from contracts.mlb_prospective_v1.store import ProspectiveMLBStore
from contracts.mlb_prospective_v1.tier_view import current_eligibility


def build_daily_report(store: ProspectiveMLBStore, report_date: Optional[str] = None) -> Dict:
    report_date = report_date or date_cls.today().isoformat()

    decisions = list(store.iter_decisions())
    outcomes_by_decision = store.latest_outcomes_by_decision()

    day_decisions = [
        d for d in decisions if (d.get("decision_ts_utc") or "").startswith(report_date)
    ]

    coverage_all_time = compute_coverage(decisions, outcomes_by_decision)
    coverage_today = compute_coverage(day_decisions, outcomes_by_decision)

    cohort_counts: Dict[str, int] = {}
    tier_counts: Dict[str, int] = {}
    for d in day_decisions:
        cohort = d.get("cohort", "UNKNOWN")
        cohort_counts[cohort] = cohort_counts.get(cohort, 0) + 1
        # Combined current view (decision + latest outcome, if any), not
        # the frozen at-capture tier -- so a decision that has since
        # received a genuine close is reflected as TIER_A once eligible.
        tier, _ = current_eligibility(d, outcomes_by_decision.get(d["decision_id"]))
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    return {
        "report_date": report_date,
        "today": coverage_today,
        "all_time": coverage_all_time,
        "cohort_counts_today": cohort_counts,
        "eligibility_tier_counts_today": tier_counts,
    }


def _coverage_lines(coverage: Dict) -> list:
    lines = [f"- Decisions captured: {coverage['total_decisions']}"]
    if coverage["total_decisions"] == 0:
        lines.append("- No decisions in this window.")
        return lines
    lines += [
        f"- Model-version attributable: {coverage['pct_model_version_attributable']}%",
        f"- Rationale traceable: {coverage['pct_rationale_traceable']}%",
        f"- Valid decision-time price: {coverage['pct_valid_decision_price']}%",
        f"- Eventual valid close: {coverage['pct_eventual_valid_close']}%",
        f"- Settled: {coverage['pct_settled']}%",
    ]
    if coverage["unmapped_writer_ids"]:
        lines.append(f"- Unmapped writers seen: {', '.join(coverage['unmapped_writer_ids'])}")
    return lines


def render_markdown(report: Dict) -> str:
    lines = [f"# MLB Prospective Evidence-Health Report — {report['report_date']}", ""]
    lines.append("## Today")
    lines += _coverage_lines(report["today"])
    lines += ["", "## Cohort mix (today)"]
    for cohort, count in sorted(report["cohort_counts_today"].items()):
        lines.append(f"- {cohort}: {count}")
    lines += ["", "## Eligibility tier mix (today)"]
    for tier, count in sorted(report["eligibility_tier_counts_today"].items()):
        lines.append(f"- {tier}: {count}")
    lines += ["", "## All-time"]
    lines += _coverage_lines(report["all_time"])
    return "\n".join(lines) + "\n"
