from contracts.mlb_replay_v1.exact_slice import (
    SLICE_KEY_FIELDS,
    UNATTRIBUTED_MODEL,
    UNMODELED_FAMILY,
    build_exact_slice_key,
)


def _observation(**overrides):
    base = {
        "sport": "MLB",
        "market": "player_strikeouts",
        "side": "over",
        "line": 6.5,
        "odds_american": -115,
        "minutes_to_start": 180,
        "model_version": "gbm_v3.2",
    }
    base.update(overrides)
    return base


def test_slice_key_length_matches_field_spec():
    key = build_exact_slice_key(_observation())
    assert len(key) == len(SLICE_KEY_FIELDS)


def test_slice_key_is_deterministic_for_identical_inputs():
    obs = _observation()
    assert build_exact_slice_key(obs) == build_exact_slice_key(dict(obs))


def test_slice_key_differs_on_line_bucket_change():
    key_a = build_exact_slice_key(_observation(line=6.5))
    key_b = build_exact_slice_key(_observation(line=7.5))
    assert key_a != key_b


def test_unattributed_model_placeholder_used_when_model_version_missing():
    key = build_exact_slice_key(_observation(model_version=None))
    assert key[-1] == UNATTRIBUTED_MODEL
    assert key[1] == UNMODELED_FAMILY  # model_source_family


def test_model_source_family_derived_from_model_version_prefix():
    key = build_exact_slice_key(_observation(model_version="gbm_v3.2"))
    assert key[1] == "gbm_v3"


def test_missing_line_uses_no_line_bucket():
    key = build_exact_slice_key(_observation(line=None))
    line_bucket_index = SLICE_KEY_FIELDS.index("line_bucket")
    assert key[line_bucket_index] == "NO_LINE"


def test_lead_time_bucket_negative_minutes_is_in_play():
    key = build_exact_slice_key(_observation(minutes_to_start=-5))
    lead_index = SLICE_KEY_FIELDS.index("decision_lead_time_bucket")
    assert key[lead_index] == "IN_PLAY"
