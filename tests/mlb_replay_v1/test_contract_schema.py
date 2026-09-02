from contracts.mlb_replay_v1.contract import (
    CONTRACT_VERSION,
    EVIDENCE_TIERS,
    KNOWN_HISTORICAL_DEFECTS,
    REASON_CODES,
    SCHEMA_SECTIONS,
    schema_field_names,
)
from contracts.mlb_replay_v1.tiers import (
    _CLAIM_LEVEL_REQUIRED_TRUE,
    _ROW_LEVEL_BOOLEAN_EXCLUSIONS,
    _ROW_LEVEL_REQUIRED_TRUE,
)


def test_contract_version_is_frozen_v1():
    assert CONTRACT_VERSION == "MLB_REPLAY_EVIDENCE_V1"


def test_schema_has_all_five_sections():
    assert set(SCHEMA_SECTIONS.keys()) == {
        "identity",
        "decision_time_evidence",
        "outcome",
        "replay",
        "integrity_eligibility",
    }


def test_schema_field_names_nonempty_for_each_section():
    names = schema_field_names()
    for section, fields in names.items():
        assert fields, f"section {section} has no fields"


def test_all_three_tiers_defined():
    assert set(EVIDENCE_TIERS.keys()) == {
        "TIER_A_FULL_REPLAY",
        "TIER_B_PERFORMANCE_REPLAY",
        "TIER_C_FORENSIC_ONLY",
    }


def test_every_reason_code_used_by_tiers_py_is_registered():
    used_codes = {code for _, code in _ROW_LEVEL_BOOLEAN_EXCLUSIONS}
    used_codes |= {code for _, code in _ROW_LEVEL_REQUIRED_TRUE}
    used_codes |= {code for _, code in _CLAIM_LEVEL_REQUIRED_TRUE}
    used_codes.add("INFO_MISSING_SHADOW_ROW")
    unregistered = used_codes - set(REASON_CODES.keys())
    assert not unregistered, f"reason codes used in code but missing from registry: {unregistered}"


def test_known_historical_defects_registry_covers_all_six_named_defects():
    codes = {d["code"] for d in KNOWN_HISTORICAL_DEFECTS}
    assert codes == {
        "DEFECT_JUL2026_MISSING_FOREIGN_SHADOW",
        "DEFECT_MISSING_MODEL_ATTRIBUTION",
        "DEFECT_UNRECOVERABLE_REPLAY_TIMESTAMP",
        "DEFECT_DFS_PRICE_CONTAMINATION",
        "DEFECT_CLOSE_PROVENANCE_ENTRY_FALLBACK",
        "DEFECT_REASON_NULLING",
    }
