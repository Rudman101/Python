"""Eligibility reason-code registry for MLB_REPLAY_EVIDENCE_V1.

This is the canonical, addressable registry of every reason code that can
appear in an observation's exclusion_reasons list. It re-exports the
registry loaded from evidence_contract.json (the source of truth) split by
category, so callers can validate a code without re-parsing JSON.
"""
from typing import Dict

from contracts.mlb_replay_v1.contract import HARD_EXCLUSIONS, REASON_CODES

ROW_LEVEL_EXCLUSION_CODES: Dict[str, str] = {
    e["code"]: e["description"] for e in HARD_EXCLUSIONS["row_level"]
}
CLAIM_LEVEL_DOWNGRADE_CODES: Dict[str, str] = {
    e["code"]: e["description"] for e in HARD_EXCLUSIONS["claim_level"]
}
INFORMATIONAL_CODES: Dict[str, str] = {
    e["code"]: e["description"] for e in HARD_EXCLUSIONS["informational"]
}

ALL_REASON_CODES: Dict[str, str] = REASON_CODES


def is_registered(code: str) -> bool:
    return code in ALL_REASON_CODES


def is_row_level_exclusion(code: str) -> bool:
    return code in ROW_LEVEL_EXCLUSION_CODES


def is_claim_level_downgrade(code: str) -> bool:
    return code in CLAIM_LEVEL_DOWNGRADE_CODES
