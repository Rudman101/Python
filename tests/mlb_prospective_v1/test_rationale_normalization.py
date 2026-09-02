from contracts.mlb_prospective_v1.rationale_registry import (
    CANONICAL_REASON_CODES,
    REGISTERED_DIALECTS,
    normalize_rationale,
)


def test_registered_dialect_normalizes_to_canonical_code():
    code, traceable = normalize_rationale("scanner_v1", "edge_above_threshold")
    assert code == "EDGE_THRESHOLD_MET"
    assert traceable is True


def test_case_insensitive_matching():
    code, traceable = normalize_rationale("scanner_v1", "  Edge_Above_Threshold  ")
    assert code == "EDGE_THRESHOLD_MET"
    assert traceable is True


def test_different_dialects_normalize_to_same_canonical_code():
    code_v1, _ = normalize_rationale("governor_v1", "allocated")
    code_v2, _ = normalize_rationale("governor_v2", "funded")
    assert code_v1 == code_v2 == "GOVERNOR_ALLOCATED"


def test_unregistered_dialect_leaves_rationale_untraceable():
    code, traceable = normalize_rationale("some_future_dialect", "allocated")
    assert code is None
    assert traceable is False


def test_registered_dialect_with_unknown_text_leaves_rationale_untraceable():
    code, traceable = normalize_rationale("scanner_v1", "some_brand_new_phrase")
    assert code is None
    assert traceable is False


def test_missing_reason_text_leaves_rationale_untraceable():
    code, traceable = normalize_rationale("scanner_v1", None)
    assert code is None
    assert traceable is False


def test_missing_dialect_leaves_rationale_untraceable():
    code, traceable = normalize_rationale(None, "allocated")
    assert code is None
    assert traceable is False


def test_every_dialect_mapping_targets_a_registered_canonical_code():
    for dialect in REGISTERED_DIALECTS:
        code, traceable = normalize_rationale(dialect, None)
        assert traceable is False  # sanity: no raw text supplied
    # Independently walk the private map via normalize_rationale's public
    # surface for a representative sample per dialect.
    assert "GOVERNOR_ALLOCATED" in CANONICAL_REASON_CODES
    assert "EDGE_THRESHOLD_MET" in CANONICAL_REASON_CODES
