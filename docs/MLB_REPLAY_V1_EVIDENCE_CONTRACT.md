# MLB Replay V1 — Evidence Contract

**Version:** `MLB_REPLAY_EVIDENCE_V1` (immutable — a breaking change to this
document requires a new version identifier, e.g. `MLB_REPLAY_EVIDENCE_V2`,
not an in-place edit)
**Status:** FROZEN — Phase 0 deliverable
**Machine-readable source of truth:** [`contracts/mlb_replay_v1/evidence_contract.json`](../contracts/mlb_replay_v1/evidence_contract.json)
**Enforcement code:** [`contracts/mlb_replay_v1/`](../contracts/mlb_replay_v1/)
**Tests:** [`tests/mlb_replay_v1/`](../tests/mlb_replay_v1/)

## Scope of this document

This is the smallest authoritative contract required for parallel MLB
Replay V1 development. It defines:

- the canonical replay observation schema,
- the three evidence tiers and their deterministic eligibility rules,
- hard exclusions from performance claims (row-level and claim-level),
- the exact-slice evaluation key,
- replay semantics and the anti-leakage rules that enforce them,
- a registry of known historical defects to exclude/qualify, not solve.

It does **not** build the replay engine, run historical replay, train a
model, repair history, or change production behavior. Any workstream that
needs a decision this document doesn't make should treat that as a gap to
raise, not a gap to fill unilaterally — see **Ambiguities** at the end.

## Standing principles (unchanged)

1. Scanner discovers.
2. Prospective tracking validates.
3. Governor allocates.
4. Settlement is evidence maintenance, not financial authority.
5. Historical rows are claim-limited by the evidence actually captured.
6. Exact market slices, not aggregate lanes, are the evaluation unit.
7. DFS placeholder prices are not sportsbook prices.
8. Missing/unknown provenance must remain unknown rather than reconstructed
   from current code.
9. A replayed decision must never be presented as the original historical
   decision.
10. Known historical holes may be excluded explicitly rather than blocking
    the entire replay program.

## Canonical replay observation schema

One `replay_observation` row = one historical decision replayed once under
one `(replay_code_version, replay_policy_version)` pair. The full field list
with types is in `evidence_contract.json:schema_sections`; summary below.

### IDENTITY
`replay_observation_id`, `historical_decision_id`, `source_identity`,
`source_table`, `shadow_bet_id` (nullable), `event_id`, `game_date`,
`market`, `side`, `line` (nullable), `player_id`/`team_id`, `book`.

### DECISION-TIME EVIDENCE
`decision_ts_utc`, `game_start_ts_utc`, `minutes_to_start`, `odds_american`,
`implied_probability`, `model_probability`, `edge_probability`, `ev`,
`confidence`, `consensus_state`, `original_rationale`,
`original_reason_dialect`, `policy_state`, `governor_state`,
`original_recommended_units`, `original_shadow_units`, `model_version`.

### OUTCOME
`result`, `profit_units`, `result_provenance`, `closing_odds`,
`closing_price_provenance`, `clv`, `settlement_route`.

### REPLAY
`replay_code_version`, `replay_policy_version`, `replay_ts_utc`,
`replay_inputs_available` (explicit list — operationalizes Principle 5),
`replay_scanner_result`, `replay_resolver_result`, `replay_governor_result`,
`replay_proposed_action`, `replay_units` (nullable), `replay_reason`.

`replay_reason` is never merged with `original_rationale` (Principle 9): a
replay observation carries both, distinct, side by side.

### INTEGRITY / ELIGIBILITY
`replay_eligibility_tier`, `exclusion_reasons`, `decision_time_valid`,
`sportsbook_price_valid`, `result_valid`, `model_attributable`,
`rationale_traceable`, `clv_usable`, `known_provenance_damage`,
`reconstructed_evidence`, `historical_missing_shadow`, `ambiguous_identity`,
`conflicting_results`.

The last two (`ambiguous_identity`, `conflicting_results`) are additions
beyond the task's minimum list, required to make the hard-exclusion rules
below deterministic and testable rather than descriptive-only.

Every boolean in this section defaults to failing (`False`) when absent from
an observation — an unset flag is never treated as "clean" (Principle 8).
`tests/mlb_replay_v1/test_tier_classification.py::test_missing_flags_default_to_failing_not_clean`
pins this.

## Evidence tiers

Implemented once, deterministically, in
[`contracts/mlb_replay_v1/tiers.py`](../contracts/mlb_replay_v1/tiers.py) —
`classify_tier(observation) -> (tier, reason_codes)`. No workstream should
re-derive this logic.

### TIER_A_FULL_REPLAY
Suitable for: model-version comparison, calibration, ROI, CLV,
resolver/governor evaluation, eventual training.

**Rule:** none of the row-level hard exclusions apply, **and**
`decision_time_valid ∧ sportsbook_price_valid ∧ result_valid ∧
model_attributable ∧ rationale_traceable ∧ clv_usable` are all `True`.

### TIER_B_PERFORMANCE_REPLAY
Suitable for: ROI, hit rate, market/side/price/timing slice performance.
**Not** suitable for claims requiring missing model/rationale/close
evidence.

**Rule:** none of the row-level hard exclusions apply, **and**
`decision_time_valid ∧ sportsbook_price_valid ∧ result_valid` are all
`True`, but at least one of `model_attributable`, `rationale_traceable`,
`clv_usable` is `False`.

A row is **never** dropped to Tier C for missing model attribution alone,
missing rationale alone, or unsupported close provenance alone — each of
those is a claim-level downgrade, not a row-level exclusion. This is a
direct, tested requirement (`test_missing_model_attribution_alone_downgrades_to_tier_b_not_excluded`,
and the `rationale`/`clv` equivalents).

### TIER_C_FORENSIC_ONLY
Retained for defect analysis. Excluded from performance claims, promotion
decisions, and training.

**Rule:** any row-level hard exclusion applies, **or** any of
`decision_time_valid`, `sportsbook_price_valid`, `result_valid` is `False`.

Row-level exclusions always win over claim-level downgrades: a row with
`known_provenance_damage = True` lands in Tier C even if its model/rationale/
close-provenance flags are otherwise fine
(`test_row_level_exclusion_overrides_claim_level_downgrade`).

## Hard exclusions from performance claims

Two distinct severities — conflating them was the main way this contract
could turn into an over-broad forensic exercise, so they're kept explicit.

### Row-level (the entire row is excluded from any performance claim; forced into Tier C)

| Reason code | Condition |
|---|---|
| `EXCL_DFS_PLACEHOLDER_PRICE` | DFS placeholder/fallback odds used as if a sportsbook price (Principle 7) |
| `EXCL_POST_START_DECISION` | `decision_ts_utc ≥ game_start_ts_utc` for a market requiring a pregame decision |
| `EXCL_REPLAY_RECONSTRUCTED_TIMESTAMP` | A decision-time field was back-filled from current code; original decision time unrecoverable (Principle 8) |
| `EXCL_AMBIGUOUS_IDENTITY` | `source_identity` resolves to >1 `historical_decision_id`, or to none |
| `EXCL_CONFLICTING_RESULTS` | `result` disagrees across `source_table`/`settlement_route` |
| `EXCL_KNOWN_PROVENANCE_CORRUPTION` | Row matches a registered entry in Known Historical Defects below |
| `EXCL_INVALID_OR_PLACEHOLDER_PRICE` | `odds_american` missing, zero, or outside plausible American-odds bounds |
| `EXCL_RESULT_INVALID` | `result` missing or not a valid settled/pending state |

### Claim-level (the row stays eligible for Tier B claims that don't need the missing evidence)

| Reason code | Condition | Blocks |
|---|---|---|
| `DOWNGRADE_MISSING_MODEL_ATTRIBUTION` | `model_version`/`model_probability` absent | model-version comparison, calibration, training |
| `DOWNGRADE_MISSING_RATIONALE` | `original_rationale` null/nulled | rationale-traceability claims |
| `DOWNGRADE_UNSUPPORTED_CLOSE_PROVENANCE` | `closing_price_provenance` unsupported/fake (e.g. `entry_fallback`) | CLV claims only |

### Informational (never blocks a tier by itself)

| Reason code | Condition |
|---|---|
| `INFO_MISSING_SHADOW_ROW` | `shadow_bet_id` absent (e.g. the July 2026 incident below) |

## Exact-slice contract

The evaluation unit is the **exact slice**, never an aggregate lane
(Principle 6). Canonical key, in order:

```
sport
+ model_source_family
+ market
+ side
+ line_bucket
+ price_bucket
+ decision_lead_time_bucket
+ model_version_or_unattributed
```

Built by [`contracts/mlb_replay_v1/exact_slice.py:build_exact_slice_key`](../contracts/mlb_replay_v1/exact_slice.py).
`model_source_family`, `line_bucket`, `price_bucket`, and
`decision_lead_time_bucket` are derived at analysis time; Phase 0 ships
default bucket boundaries (favorite/underdog price bands, 30m/2h/12h/24h
lead-time bands, 0.5-increment line rounding) so parallel workstreams have
something to build against immediately. Refining a bucket function's
boundaries in a later phase changes bucket *labels*, not the key's field
names or order, so existing slices stay comparable in shape.

Additional dimensions may be appended later. Lane-level aggregate
statistics must never substitute for this exact-slice key in a promotion or
performance claim.

## Replay semantics

```
historical evidence available at T
  → current replay scanner
  → current replay resolver
  → current replay governor
  → simulated action
  → compare with historical result / closing market
```

The replay engine constructs its decision using only evidence available at
`decision_ts_utc` (= T). Outcome and closing-market data become visible to
the replay process only **after** the replay decision (`replay_proposed_action`,
`replay_reason`, `replay_units`) has been generated. `replay_ts_utc` (when
the replay code actually ran) is always later than T and is never used to
backdate `decision_ts_utc`.

## Anti-leakage requirement

Fields forbidden from the input side of a replay-decision payload — the
data handed to the replay scanner/resolver/governor when constructing a
decision at T:

**Future-outcome fields** (chronologically after T):
`result`, `profit_units`, `result_provenance`, `closing_odds`,
`closing_price_provenance`, `clv`, `settlement_route`, `settlement_ts_utc`.

**Original-decision-output fields** (would leak the answer the replay is
supposed to independently derive, and would make the replay not actually
independent of the original decision):
`original_recommended_units`, `original_shadow_units`, `original_rationale`,
`original_reason_dialect`, `policy_state`, `governor_state`.

**Structural rules:**
- No `market_snapshots` entry timestamped after `decision_ts_utc` may appear.
- No `postgame_stats` field (any statistic only knowable after
  `game_start_ts_utc`) may appear.
- `historical_decision_id` may be used only as a join/reporting key *after*
  the replay decision is produced — never as a feature into scanner/
  resolver/governor.

Enforced by [`contracts/mlb_replay_v1/anti_leakage.py:assert_no_leakage`](../contracts/mlb_replay_v1/anti_leakage.py),
which every replay-decision code path must call on its input payload before
handing it to the scanner. Tests in
[`tests/mlb_replay_v1/test_anti_leakage.py`](../tests/mlb_replay_v1/test_anti_leakage.py)
prove each forbidden field is rejected individually, that a future market
snapshot is rejected while a past one passes, and that a clean payload
passes untouched.

## Known historical defects

Registered here for exclusion/qualification, **not solved** in Phase 0
(full detail and matching criteria in `evidence_contract.json:known_historical_defects`):

1. **`DEFECT_JUL2026_MISSING_FOREIGN_SHADOW`** — bounded missing
   foreign-baseball shadow-row incident (2026-07-12 to 2026-07-18, dates as
   initially registered — see Ambiguities). Matching rows get
   `historical_missing_shadow=True`; only get `known_provenance_damage=True`
   if decision-time evidence is *also* unrecoverable. Must be excluded from
   any window-completeness claim; must not block unaffected MLB rows
   outside the window/market (Principle 10).
2. **`DEFECT_MISSING_MODEL_ATTRIBUTION`** — historical rows lacking model
   attribution. Downgrades to Tier B, never auto-excludes.
3. **`DEFECT_UNRECOVERABLE_REPLAY_TIMESTAMP`** — historical replay
   timestamps whose original runtime cannot be recovered. Forces Tier C via
   `reconstructed_evidence`/`decision_time_valid`.
4. **`DEFECT_DFS_PRICE_CONTAMINATION`** — DFS price contamination. Forces
   Tier C via `sportsbook_price_valid`.
5. **`DEFECT_CLOSE_PROVENANCE_ENTRY_FALLBACK`** — close provenance problems
   such as `entry_fallback`. Downgrades to Tier B via `clv_usable`, not
   automatically Tier C.
6. **`DEFECT_REASON_NULLING`** — known reason-nulling history. Downgrades to
   Tier B via `rationale_traceable`, not automatically Tier C.

## Artifacts in this Phase 0 delivery

- `docs/MLB_REPLAY_V1_EVIDENCE_CONTRACT.md` — this document.
- `contracts/mlb_replay_v1/evidence_contract.json` — machine-readable
  source of truth (schema, tiers, exclusions, slice key, anti-leakage
  fields, defect registry, reason codes).
- `contracts/mlb_replay_v1/contract.py` — loader exposing the JSON to
  Python.
- `contracts/mlb_replay_v1/tiers.py` — deterministic tier classification.
- `contracts/mlb_replay_v1/anti_leakage.py` — forbidden-field enforcement.
- `contracts/mlb_replay_v1/exact_slice.py` — exact-slice key construction.
- `contracts/mlb_replay_v1/reason_codes.py` — eligibility reason-code
  registry.
- `tests/mlb_replay_v1/` — unit tests for tier classification,
  anti-leakage, exact-slice construction, and schema/registry consistency.

## Ambiguities / open items for parallel workstreams

These do not block starting parallel work, but should be confirmed rather
than assumed:

1. **`DEFECT_JUL2026_MISSING_FOREIGN_SHADOW` dates** are registered as
   2026-07-12 to 2026-07-18 based on the task description and the current
   session date; the exact calendar window (and year) should be confirmed
   against source data by whichever workstream first touches that data —
   this contract deliberately does not perform that forensic confirmation.
2. **Plausible American-odds bounds** for `EXCL_INVALID_OR_PLACEHOLDER_PRICE`
   are referenced but not numerically pinned in Phase 0 — left for the
   workstream that builds ingestion validation, since the right bounds may
   be market-dependent (e.g. moneyline vs. prop pricing).
3. **Pregame-required market list** for `EXCL_POST_START_DECISION` is
   referenced generically ("a market whose evidence contract requires a
   pregame decision") but the concrete list of which MLB markets require
   pregame-only decisions is not enumerated here — needs a decision from
   whoever owns market definitions.
4. **Bucket boundaries** in `exact_slice.py` (price bands, lead-time bands,
   line rounding) are Phase 0 defaults, explicitly called out as
   refinable without changing the contract's field names/order — but if a
   workstream needs different boundaries before Phase 0 defaults are
   revisited, that's a coordination point, not something to silently
   fork.
