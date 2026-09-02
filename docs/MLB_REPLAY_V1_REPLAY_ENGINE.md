# MLB Replay V1 — Deterministic Historical Replay Engine (Workstream B)

**Status:** Phase 0 evidence contract (`MLB_REPLAY_EVIDENCE_V1`) is FROZEN and
unchanged by this workstream. This document covers the replay engine built
on top of it: `replay_engine/`, `fixtures/mlb_replay_v1/`, and the new tests
under `tests/mlb_replay_v1/`.

**Simulation only.** Nothing in `replay_engine/` places, creates, or
modifies a real wager. There is no code path from this engine to any live
order/bet system.

**Workstream A is not implemented in this repository.** Rather than block
on it, this workstream defines a port/interface (`replay_engine/pipeline.py`)
that any scanner/resolver/policy/governor must satisfy, and ships a small,
clearly-labeled synthetic reference implementation
(`replay_engine/reference_pipeline.py`, version `REPLAY_REFERENCE_PIPELINE_V1`)
used to build and prove the engine today. Wiring in Workstream A's real
pipeline later means constructing a `DecisionPipeline` from the real
components — no change to `replay_engine/engine.py`, `projection.py`,
`hashing.py`, `schema.py`, or `store.py`.

## 1. API / CLI

### Python API

```python
from replay_engine.modes import ReplayMode
from replay_engine.reference_pipeline import build_reference_pipeline
from replay_engine.engine import ReplayEngine

pipeline = build_reference_pipeline()          # swap for Workstream A's real pipeline later
engine = ReplayEngine(pipeline, policy_config={"max_units": 2.0}, replay_policy_version="POLICY_V1")

sealed = engine.run_decision(historical_row, ReplayMode.ORIGINAL_DECISION_REPLAY)   # decision only, pre-outcome
observation = engine.attach_outcome(sealed, historical_row)                          # scored, post-seal
# or, in one call:
observation = engine.replay(historical_row, ReplayMode.ORIGINAL_DECISION_REPLAY)

from replay_engine.store import AppendOnlyReplayStore
store = AppendOnlyReplayStore("replay_results.jsonl")   # never shadow_bets/signal tables
store.append(observation)
```

`run_decision()` / `attach_outcome()` are also available as plain module
functions in `replay_engine.engine` for callers that don't want the
stateful `ReplayEngine` wrapper.

### CLI

```
python -m replay_engine.cli run \
    --input historical_rows.jsonl \
    --output replay_results.jsonl \
    --mode ORIGINAL_DECISION_REPLAY \
    --replay-policy-version POLICY_V1 \
    [--policy-config policy_config.json] \
    [--pipeline-factory module:callable]   # defaults to the reference pipeline

python -m replay_engine.cli validation-set \
    --output replay_results_validation.jsonl \
    --mode POLICY_COUNTERFACTUAL
```

`--pipeline-factory` is a `module:callable` string returning a
`DecisionPipeline` — the seam Workstream A's real pipeline plugs into.

## 2. Replay modes

Two modes, never blended (`replay_engine/modes.py`, `ReplayMode`):

| Mode | What it does | Scanner port called? |
|---|---|---|
| `ORIGINAL_DECISION_REPLAY` | Re-derives belief from raw decision-time features only (`replay_engine.projection.project_raw_replay_payload`, which excludes `model_probability`/`edge_probability`/`ev`/`confidence`/`model_version`) | Yes |
| `POLICY_COUNTERFACTUAL` | Keeps the historical model's own recorded belief fixed, applies current resolver/policy/governor to it | **No** — `replay_engine.reference_pipeline.build_fixed_scanner_result_from_historical_belief` builds the `ScannerResult` directly from the historical row; the scanner port is never invoked |

Non-blending is structural, not conventional: `run_decision()`'s two
branches use different whitelist projections and, for
`POLICY_COUNTERFACTUAL`, skip the scanner call entirely.
`test_replay_engine_modes.py` proves this with a spy scanner (call count 0
under `POLICY_COUNTERFACTUAL`, 1 under `ORIGINAL_DECISION_REPLAY`) and
proves the raw-replay payload never contains a historical-belief field.

If the historical belief is itself missing under `POLICY_COUNTERFACTUAL`,
the engine reports `NO_BET` with reason `missing_historical_model_belief`
rather than fabricating one (contract Principle 8).

## 3. Anti-leakage proof

Enforcement is structural, per two independent layers:

1. **Whitelist projection** (`replay_engine/projection.py`): the
   payload handed to the pipeline is built by copying *only* named fields
   out of the historical row. A forbidden field cannot reach the pipeline
   through these functions regardless of what else the row contains,
   because nothing is copied unless explicitly named. `market_snapshots`
   entries timestamped after `decision_ts_utc` are filtered out before the
   payload is even assembled.
2. **Contract gate** (`contracts.mlb_replay_v1.anti_leakage.assert_no_leakage`):
   run a second time on every projected payload, independent of the
   whitelist, as belt-and-suspenders.

`test_replay_engine_anti_leakage.py::test_raw_projection_whitelist_shares_no_fields_with_forbidden_sets`
and its `policy_counterfactual` counterpart pin that the whitelists and the
contract's forbidden-field sets can never silently drift apart.

**The core proof** —
`test_replay_decision_is_byte_identical_whether_or_not_future_fields_are_present`
and its `policy_counterfactual` counterpart — deliberately poisons every
`FUTURE_OUTCOME_FIELDS` and `ORIGINAL_DECISION_OUTPUT_FIELDS` entry on a
historical row (`result`, `profit_units`, `closing_odds`, `clv`,
`original_recommended_units`, `original_rationale`, `governor_state`, …)
and asserts the replayed decision's `output_hash`, action, and units are
byte-for-byte identical to the unpoisoned row. The decision cannot see or
depend on inserted future information because the values never reach the
scanner/resolver/policy/governor call, structurally, not by review
discipline.

`original_recommended_units`/`original_rationale`/etc. are still used —
*after* the pipeline decision has run — to compute
`differences_from_original`/`difference_reason` for reporting. That
post-hoc comparison is explicitly excluded from `output_hash`, so it can
never be mistaken for the decision itself.

## 4. Determinism proof

`replay_engine/hashing.py::canonical_json` serializes with sorted keys and
fixed separators before hashing (SHA-256), so two runs over logically
identical input always produce identical hashes regardless of dict
insertion order.

Captured per `SealedDecision`:

| Field | What it hashes |
|---|---|
| `replay_code_version` | The wired-in pipeline's version (`DecisionPipeline.code_version`) |
| `replay_policy_version` | Caller-supplied policy/config identity string |
| `input_evidence_hash` | The exact whitelisted payload handed to the pipeline |
| `policy_config_hash` | The `policy_config` dict |
| `output_hash` | `{mode, scanner/resolver/policy/governor results, final action/units/reason, input_evidence_hash, policy_config_hash, replay_code_version, replay_policy_version}` — deliberately excludes `replay_observation_id` (fresh UUID per run) and `replay_ts_utc` (wall clock), neither of which is part of the decision |

`test_replay_engine_determinism.py` proves:
- identical `(input, code version, policy version, configuration)` →
  identical `output_hash`/`input_evidence_hash` across repeated runs;
- `output_hash` is unaffected by `replay_observation_id`/`replay_ts_utc`
  varying (as they always do between real runs);
- `output_hash` **changes** when `policy_config` changes (sensitivity
  check — a hash that never changes proves nothing);
- `output_hash` **differs** between `ORIGINAL_DECISION_REPLAY` and
  `POLICY_COUNTERFACTUAL` on a row where historical belief and current
  features disagree — proof the two modes are not blended into one hash
  space.

## 5. Replay result schema

`replay_engine/schema.py`:

- **`SealedDecision`** (frozen) — identity, decision-time evidence
  actually used, `ORIGINAL_MODEL_VERSION`/`CURRENT_REPLAY_MODEL_VERSION`
  (never overwrite each other — see below), replay provenance
  (`replay_code_version`, `replay_policy_version`, `replay_mode`,
  `replay_ts_utc`, `replay_inputs_available`), the four port results
  (`replay_scanner_result`, `replay_resolver_result`,
  `replay_policy_result`, `replay_governor_result`),
  `replay_proposed_action`/`replay_units`/`replay_reason`,
  `historical_original_action`/`differences_from_original`/`difference_reason`,
  and the three provenance hashes. **No outcome/settlement field exists on
  this dataclass at all** — `test_sealed_decision_has_no_outcome_field`
  pins that its field names share nothing with
  `FUTURE_OUTCOME_FIELDS`.
- **`ReplayObservation`** — produced only by `attach_outcome(sealed, historical_row)`,
  which requires an already-constructed `SealedDecision`. Adds `result`,
  `profit_units`, `result_provenance`, `closing_odds`,
  `closing_price_provenance`, `clv`, `settlement_route`,
  `historical_profit_at_original_price`,
  `simulated_replay_profit_at_historical_price`, `replay_eligibility_tier`
  and `exclusion_reasons` (delegated to
  `contracts.mlb_replay_v1.tiers.classify_tier` — Workstream B does not
  re-derive tier logic), and `exact_slice_key` (delegated to
  `contracts.mlb_replay_v1.exact_slice.build_exact_slice_key`).

Because `SealedDecision` is frozen and `attach_outcome` is the only
function that adds outcome fields, **there is no code path that can settle
or score a decision before it has been sealed** — `SealedDecision` isn't a
convention, it's a distinct, required, prior object
(`test_attach_outcome_requires_an_already_sealed_decision` proves passing
a plain dict fails).

Field names mirror `evidence_contract.json`'s schema sections wherever a
counterpart exists. Additive extensions beyond Phase 0's minimum schema
(the JSON contract does not forbid extra fields, and the Workstream B task
spec separately requires several of these): `replay_policy_result` (the
task spec lists "replay policy decision" as its own output field, distinct
from resolver/governor), the three provenance hashes,
`ORIGINAL_MODEL_VERSION`/`CURRENT_REPLAY_MODEL_VERSION` as named siblings
of `model_version`, `differences_from_original`/`difference_reason`, and
`historical_profit_at_original_price`/`simulated_replay_profit_at_historical_price`.

**Model version distinction:** `ORIGINAL_MODEL_VERSION` is read once from
the historical row's `model_version` and never touched again;
`CURRENT_REPLAY_MODEL_VERSION` is the wired-in pipeline's own
`code_version`. Neither assignment can overwrite the other — they are
separate dataclass fields set once, at construction, from two different
sources. A historical row missing `model_version` still replays
(`test_missing_original_model_version_does_not_block_replay`); its
`ORIGINAL_MODEL_VERSION` stays `None` and `model_attributable=False`
downgrades it to Tier B via the existing (frozen) tier rules, so
model-attribution claims correctly remain unavailable without blocking the
row.

**Price semantics:** `historical_profit_at_original_price` and
`simulated_replay_profit_at_historical_price` are both scored off the
single historical `odds_american` snapshot recorded at `decision_ts_utc` —
never a later or reconstructed price. `_score()` returns `None` (not a
guess) whenever a `BET` action lacks units/odds or the result isn't
settled yet.

## 6. Tests / results

135 tests pass (49 from the frozen Phase 0 contract, unchanged; 86 new for
Workstream B):

```
tests/mlb_replay_v1/test_replay_engine_anti_leakage.py     — 36 tests
tests/mlb_replay_v1/test_replay_engine_determinism.py      — 5 tests
tests/mlb_replay_v1/test_replay_engine_modes.py            — 7 tests
tests/mlb_replay_v1/test_replay_engine_output_schema.py    — 7 tests
tests/mlb_replay_v1/test_replay_engine_validation_set.py   — 22 tests
tests/mlb_replay_v1/test_replay_engine_store.py            — 6 tests
tests/mlb_replay_v1/test_replay_engine_cli.py               — 3 tests
```

```
$ python3 -m pytest -q
........................................................................ [ 53%]
...............................................................          [100%]
135 passed
```

### Validation set coverage

`fixtures/mlb_replay_v1/validation_set.py` implements all eleven required
scenarios, each exercised through the full engine
(`test_replay_engine_validation_set.py`):

| Scenario | Tier | Replay action | Mechanism exercised |
|---|---|---|---|
| current model agrees with original action | A | BET | scanner/resolver/governor all confirm, matching original |
| current model rejects historical bet | A | NO_BET | flat current-model signal below `BET_EDGE_THRESHOLD` |
| current governor blocks scanner BET | A | NO_BET | governor `exposure_cap_hit` context blocks a confirmed BET |
| historical block current system would accept | A | BET | original blocked (0 units), current pipeline approves |
| missing model version | B | BET | `model_attributable=False` downgrades tier, decision still runs |
| missing rationale | B | BET | `rationale_traceable=False` downgrades tier, decision unaffected |
| Tier B row | B | BET | unsupported close provenance (`clv_usable=False`) |
| Tier C rejection | C | BET | `known_provenance_damage=True`; still replayed for forensic value |
| contradictory side | A | NO_BET | resolver rejects on opposite-side concurrent context |
| post-start exclusion | C | NO_BET | `decision_ts_utc ≥ game_start_ts_utc`; resolver + tier both reject |
| DFS invalid-price exclusion | C | NO_BET | DFS placeholder book; resolver + tier both reject |

## 7. Benchmark on the small historical sample

Reference pipeline, both modes, 200 iterations × 11 validation-set rows
(2,200 replays each), on this session's container:

```
ORIGINAL_DECISION_REPLAY: 2200 replays in 0.4337s -> 5073 replays/sec, 0.197 ms/replay
POLICY_COUNTERFACTUAL:    2200 replays in 0.3005s -> 7321 replays/sec, 0.137 ms/replay
```

This measures engine/reference-pipeline overhead only (projection, port
calls, hashing, sealing) — not I/O, not a real model's inference cost, and
not Workstream A's eventual real scanner. It establishes that the engine
itself is not the bottleneck for a full-corpus run; the real model/service
calls Workstream A eventually wires in will dominate wall-clock time.

## 8. Requirements for a full-corpus run

Before running replay over the entire historical MLB corpus:

1. **Workstream A's real pipeline** must exist and be wired in as a
   `DecisionPipeline` (via `--pipeline-factory` or direct construction).
   The reference pipeline in this delivery is a synthetic stand-in only —
   its scanner formula, resolver thresholds, and governor sizing are not
   validated trading logic.
2. **Ingestion must populate `integrity_eligibility`** (the eleven booleans
   `classify_tier` consumes) for every historical row from real source
   data — this workstream's fixtures set them by hand per scenario;
   production ingestion needs its own validation pass against
   `contracts/mlb_replay_v1/evidence_contract.json`'s hard-exclusion rules.
3. **Known historical defect windows** (`DEFECT_JUL2026_MISSING_FOREIGN_SHADOW`
   and friends, `evidence_contract.json:known_historical_defects`) must be
   confirmed against real source data — Phase 0 explicitly left the
   `2026-07-12`–`2026-07-18` window as an initial registration pending
   confirmation.
4. **Market/price rules pinned down**: the **pregame-required market list**
   for `EXCL_POST_START_DECISION` (contract Ambiguity #3) and **plausible
   American-odds bounds** (contract Ambiguity #2) are still open per Phase
   0 and should be pinned by whoever owns market definitions before a full
   run, since the reference resolver's post-start/price-validity rules are
   placeholders for those decisions.
5. **Storage sizing and location** for the append-only JSONL store (or a
   swapped-in backend) at full-corpus row counts — this delivery only
   proves the store's shape (append-only, provenance-linked, never
   `shadow_bets`/`signal`-named), not its scale.
6. **Runtime budget**: multiply the per-replay-mode benchmark above by the
   real pipeline's own per-decision cost (likely dominated by whatever
   Workstream A's scanner model inference costs, not by this engine) and
   by two (both replay modes, per the spec's requirement to keep them
   separate) to estimate full-corpus wall-clock time.
7. **Explicit authorization** to run replay over the entire corpus — per
   the Workstream B task spec, this delivery stops here and does not run
   the full MLB corpus.

**STOP: this delivery does not run replay over the entire MLB historical
corpus.** It validates the engine against the eleven-scenario validation
set and synthetic fixtures only, per instruction.

## 9. Training

Out of scope, and untouched: nothing in `replay_engine/` fits, tunes,
optimizes, or retrains any model. The reference pipeline's scanner formula
is a fixed, hand-written, deterministic function — not a trained model.
