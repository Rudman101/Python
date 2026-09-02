"""Loader for the frozen MLB Replay V1 evidence contract.

evidence_contract.json is the single source of truth. This module exposes it
to Python code; do not hand-duplicate field lists, tier rules, or reason
codes elsewhere — import from here instead.
"""
import json
from pathlib import Path
from typing import Any, Dict

_CONTRACT_PATH = Path(__file__).parent / "evidence_contract.json"

with open(_CONTRACT_PATH, "r", encoding="utf-8") as _f:
    CONTRACT: Dict[str, Any] = json.load(_f)

CONTRACT_VERSION: str = CONTRACT["contract_version"]
SCHEMA_SECTIONS: Dict[str, Any] = CONTRACT["schema_sections"]
EVIDENCE_TIERS: Dict[str, Any] = CONTRACT["evidence_tiers"]
HARD_EXCLUSIONS: Dict[str, Any] = CONTRACT["hard_exclusions"]
EXACT_SLICE_KEY: Dict[str, Any] = CONTRACT["exact_slice_key"]
ANTI_LEAKAGE: Dict[str, Any] = CONTRACT["anti_leakage_forbidden_fields"]
KNOWN_HISTORICAL_DEFECTS = CONTRACT["known_historical_defects"]

REASON_CODES: Dict[str, str] = {}
for _entry in HARD_EXCLUSIONS["row_level"]:
    REASON_CODES[_entry["code"]] = _entry["description"]
for _entry in HARD_EXCLUSIONS["claim_level"]:
    REASON_CODES[_entry["code"]] = _entry["description"]
for _entry in HARD_EXCLUSIONS["informational"]:
    REASON_CODES[_entry["code"]] = _entry["description"]


def schema_field_names() -> Dict[str, list]:
    """Return {section_name: [field_name, ...]} for the whole observation schema."""
    return {
        section: [f["field"] for f in fields]
        for section, fields in SCHEMA_SECTIONS.items()
    }
