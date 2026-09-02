"""Prospective evidence-quality alerting for MLB decisions.

capture_decision() calls evaluate_decision_alerts() synchronously on every
decision, so a coverage gap surfaces immediately at capture time rather
than being discovered later in a retrospective audit. Alerting never
blocks capture, never changes betting policy, and never changes funded
units — it only surfaces a warning (task requirement: do not change
betting policy or automatically increase financial exposure).
"""
from dataclasses import dataclass
from typing import List, Optional

ALERT_MISSING_MODEL_VERSION = "ALERT_MISSING_MODEL_VERSION"
ALERT_UNMAPPED_WRITER = "ALERT_UNMAPPED_WRITER"
ALERT_MISSING_DECISION_REASON = "ALERT_MISSING_DECISION_REASON"
ALERT_UNTRACEABLE_RATIONALE_DIALECT = "ALERT_UNTRACEABLE_RATIONALE_DIALECT"
ALERT_INVALID_DECISION_TIMESTAMP = "ALERT_INVALID_DECISION_TIMESTAMP"
ALERT_UNUSABLE_PRICE = "ALERT_UNUSABLE_PRICE"

ALL_ALERT_CODES = frozenset(
    {
        ALERT_MISSING_MODEL_VERSION,
        ALERT_UNMAPPED_WRITER,
        ALERT_MISSING_DECISION_REASON,
        ALERT_UNTRACEABLE_RATIONALE_DIALECT,
        ALERT_INVALID_DECISION_TIMESTAMP,
        ALERT_UNUSABLE_PRICE,
    }
)


@dataclass(frozen=True)
class EvidenceQualityAlert:
    decision_id: str
    code: str
    message: str


# Reference in-process alert sink. A real deployment swaps this for a
# metrics/paging integration; the interface (append-only list) is what
# matters and is exercised by the tests.
ALERT_LOG: List[EvidenceQualityAlert] = []


def evaluate_decision_alerts(
    *,
    decision_id: str,
    writer_registered: bool,
    model_version: Optional[str],
    canonical_reason_code: Optional[str],
    raw_reason: Optional[str],
    decision_time_valid: bool,
    sportsbook_price_valid: bool,
) -> List[EvidenceQualityAlert]:
    fired: List[EvidenceQualityAlert] = []

    if not writer_registered:
        fired.append(
            EvidenceQualityAlert(
                decision_id,
                ALERT_UNMAPPED_WRITER,
                "Writer is not in the registered-writer coverage map; "
                "decision forced unattributable rather than given a fake "
                "model version.",
            )
        )
    elif not model_version:
        fired.append(
            EvidenceQualityAlert(
                decision_id,
                ALERT_MISSING_MODEL_VERSION,
                "Decision reached capture without model_version.",
            )
        )

    if not raw_reason:
        fired.append(
            EvidenceQualityAlert(
                decision_id,
                ALERT_MISSING_DECISION_REASON,
                "Decision reached capture without a decision reason.",
            )
        )
    elif not canonical_reason_code:
        fired.append(
            EvidenceQualityAlert(
                decision_id,
                ALERT_UNTRACEABLE_RATIONALE_DIALECT,
                "Decision reason present but its dialect/text is not "
                "registered for normalization.",
            )
        )

    if not decision_time_valid:
        fired.append(
            EvidenceQualityAlert(
                decision_id,
                ALERT_INVALID_DECISION_TIMESTAMP,
                "Decision reached capture without a valid decision timestamp.",
            )
        )

    if not sportsbook_price_valid:
        fired.append(
            EvidenceQualityAlert(
                decision_id,
                ALERT_UNUSABLE_PRICE,
                "Decision reached capture without a usable sportsbook price.",
            )
        )

    return fired


def emit(alerts: List[EvidenceQualityAlert]) -> None:
    ALERT_LOG.extend(alerts)


def clear_alert_log() -> None:
    """Test/ops helper to reset the reference in-process alert sink."""
    ALERT_LOG.clear()
