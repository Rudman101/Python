# MLB Replay V1 — Workstream C: Prospective Clean Evidence Capture

**Contract version:** `MLB_PROSPECTIVE_CAPTURE_V1`
**Based on:** [`MLB_REPLAY_EVIDENCE_V1`](MLB_REPLAY_V1_EVIDENCE_CONTRACT.md) (Phase 0, frozen)
**Status:** ACTIVE — governs every new MLB decision from this point forward
**Code:** [`contracts/mlb_prospective_v1/`](../contracts/mlb_prospective_v1/)
**Tests:** [`tests/mlb_prospective_v1/`](../tests/mlb_prospective_v1/)

## Scope

Phase 0 (`MLB_REPLAY_EVIDENCE_V1`) defines how to *classify* historical MLB
decisions given whatever evidence survived. This workstream is the
complementary, forward-looking half: make sure every *new* MLB decision,
from now on, captures the evidence Phase 0 needs so the rest of the 2026
season produces clean prospective data regardless of historical defects.

It does **not** change betting policy, does **not** automatically increase
financial exposure, and does **not** retrain any model. It is a capture and
alerting layer that sits at decision time, plus a reporting layer that sits
on top of what gets captured.

## Why this reuses Phase 0 directly

`contracts.mlb_prospective_v1.capture.capture_decision()` calls
`contracts.mlb_replay_v1.tiers.classify_tier()` verbatim — it does not
re-derive tier logic. The integrity/eligibility flags Phase 0 operates on
(`decision_time_valid`, `sportsbook_price_valid`, `result_valid`,
`model_attributable`, `rationale_traceable`, `clv_usable`, ...) describe any
MLB decision record, not specifically a replay observation, so the same
deterministic classifier applies unchanged. The reason-code registry
(`EXCL_DFS_PLACEHOLDER_PRICE`, `DOWNGRADE_MISSING_MODEL_ATTRIBUTION`,
`DOWNGRADE_MISSING_RATIONALE`, `DOWNGRADE_UNSUPPORTED_CLOSE_PROVENANCE`,
...) is reused the same way.

One consequence worth calling out: **a decision can never be `TIER_A` at
the moment it is captured.** No closing price exists yet, so `clv_usable`
is correctly `False` until enrichment runs — every freshly captured
decision is capped at `TIER_B` (or `TIER_C` if something else is wrong).
`TIER_A` becomes reachable only through the combined decision+outcome view
(`contracts.mlb_prospective_v1.tier_view.current_eligibility`) once a
genuine closing price arrives — and even then, the *decision record's own*
`eligibility_tier` field, frozen at capture, never changes.

## Capture chokepoint

`capture_decision(payload, *, writer_id)` in
[`contracts/mlb_prospective_v1/capture.py`](../contracts/mlb_prospective_v1/capture.py)
is the single sanctioned entrypoint every MLB scanner/governor/tracking
writer must call. It returns an immutable `ProspectiveMLBDecision`
(frozen dataclass) covering exactly the fields the task specifies:

- **IDENTITY** — `decision_id`, `event_id`, `player_id`/`team_id`,
  `market`, `side`, `line`, `book`.
- **MODEL** — `model_version`, `model_probability`, `fair_odds`,
  `edge_probability`, `ev`, `confidence`, `feature_versions`.
- **MARKET** — `odds_american`, `price_ts_utc`, `price_age_seconds`,
  `sharp_reference`, `market_consensus`, `price_provenance`.
- **DECISION** — `scanner_label`, `scanner_actionability_tier`,
  `resolver_reasons`, `policy_state`, `governor_decision`,
  `final_funded_units`, `tracking_stake` (tracked separately),
  `block_hold_reason`, `decision_ts_utc`, `cohort`.
- **TIMING** — `game_start_ts_utc`, `minutes_to_start` (derived).

Only `decision_id`, `event_id`, `market`, `side`, `book`, and `cohort` are
structurally required — without them a row cannot even be addressed or
stored, so `capture_decision` raises `CaptureValidationError`. Everything
else (model version, rationale, decision timestamp, price) is allowed to be
missing: the decision still captures, the relevant integrity flag comes
back `False`, and an alert fires (see **Alerting** below). Phase 0
Principle 8 — unknown provenance stays unknown rather than reconstructed —
applies here too: capture never fabricates a value to fill a gap.

## Model attribution

Every writer that calls `capture_decision` must supply a `writer_id`.
[`writer_registry.py`](../contracts/mlb_prospective_v1/writer_registry.py)
holds the set of writers confirmed to reliably populate `model_version`. A
writer *not* in that set is unmapped: its decisions are forced
`model_attributable=False` and `model_version=None` regardless of what the
raw payload claims — an unmapped writer never receives a fabricated model
version, it stays visibly unattributable and fires
`ALERT_UNMAPPED_WRITER`. A *registered* writer that simply omits
`model_version` on one decision fires the narrower
`ALERT_MISSING_MODEL_VERSION` instead.

## Rationale coverage

[`rationale_registry.py`](../contracts/mlb_prospective_v1/rationale_registry.py)
is the single shared registry mapping a `(dialect, raw_reason_text)` pair
to a canonical reason code. Different scanner/governor code versions
("dialects") have used different vocabulary for the same underlying
reason (e.g. `governor_v1`'s `"allocated"` and `governor_v2`'s `"funded"`
both normalize to `GOVERNOR_ALLOCATED`) — normalization here is what makes
rationale comparable across versions. The raw text is always kept
alongside the canonical code, untouched.

## Prospective cohorts

[`cohorts.py`](../contracts/mlb_prospective_v1/cohorts.py) defines the four
required cohorts and enforces they can never be conflated:

| Cohort | `final_funded_units` | `tracking_stake` | Notes |
|---|---|---|---|
| `OFFICIAL_GOVERNOR_BET` | `> 0` | must be unset | real governor-funded money |
| `ZERO_UNIT_TRACKING` | `== 0` | — | paper tracking, no stake at all |
| `MANUAL_$1_TRACKING` | `== 0` (never official units) | `== 1` | a $1 manual tracking stake is never an official engine unit |
| `BLOCKED_COUNTERFACTUAL` | `== 0` | — | requires `block_hold_reason`; still receives eventual outcome evidence via enrichment |

`validate_cohort_units()` raises `CohortConflationError` for any violation,
and `capture_decision()` calls it on every decision.

## Closing-price capture

[`enrichment.py`](../contracts/mlb_prospective_v1/enrichment.py) defines
four distinct `closing_price_provenance` states —
`book_snapshot`, `entry_fallback`, `stale_reference`, `missing` — and only
`book_snapshot` makes `clv_usable=True`. `entry_fallback` is never
relabeled or upgraded to `book_snapshot`; an unregistered provenance string
is rejected outright (`ClosePriceProvenanceError`) rather than silently
accepted.

## Immutability

`ProspectiveMLBDecision` is a frozen dataclass: no code path can rebind one
of its fields after capture. `enrich_with_outcome()` never receives or
returns a mutated decision — it returns a brand-new, independently-keyed
`ProspectiveMLBOutcome`, joined only by `decision_id`. As a second layer of
protection, any enrichment payload that tries to carry a decision-time
field name (e.g. `model_version`, `original_rationale_raw`,
`decision_ts_utc`) is rejected with `EnrichmentLeakageError` before it can
even be considered — later settlement cannot overwrite decision-time
evidence, structurally, not just by convention.

`ProspectiveMLBStore` ([`store.py`](../contracts/mlb_prospective_v1/store.py))
mirrors this at the persistence layer: decisions are appended once to an
append-only JSONL file and re-capturing the same `decision_id` raises
`DuplicateDecisionError`; outcome enrichments append new lines (audit
trail preserved) and the *latest* line per `decision_id` is the current
view.

## Alerting

[`alerts.py`](../contracts/mlb_prospective_v1/alerts.py) fires immediately,
inside `capture_decision`, whenever a decision reaches the system without
one of the four required signals:

- `ALERT_MISSING_MODEL_VERSION` / `ALERT_UNMAPPED_WRITER`
- `ALERT_MISSING_DECISION_REASON` / `ALERT_UNTRACEABLE_RATIONALE_DIALECT`
- `ALERT_INVALID_DECISION_TIMESTAMP`
- `ALERT_UNUSABLE_PRICE`

Alerting is purely diagnostic: it never blocks capture and never touches
`final_funded_units`, `tracking_stake`, or any policy/governor field —
consistent with the task's "do not change betting policy or automatically
increase financial exposure" constraint.

## Health metrics

[`health_metrics.py`](../contracts/mlb_prospective_v1/health_metrics.py)
`compute_coverage()` is the single implementation of the five required
percentages:

- MLB decisions with attributable model version %
- MLB decisions with traceable rationale %
- MLB decisions with valid decision-time price %
- MLB decisions with eventual valid close %
- MLB decisions with settlement %

## Daily report

[`daily_report.py`](../contracts/mlb_prospective_v1/daily_report.py)
`build_daily_report(store, report_date)` computes today's and all-time
coverage, cohort mix, and combined-eligibility-tier mix from a
`ProspectiveMLBStore`; `render_markdown(report)` renders it for a daily
post/notification. Intended to run once per day while the season is
active — `report_date` defaults to today.

## Reference persistence

No production MLB writer/scanner/governor code exists in this repository
yet — Phase 0 shipped the evidence contract only. `store.py` ships a
reference append-only JSONL store so this workstream is runnable
end-to-end (`capture_decision` → `store.append_decision` →
`enrich_with_outcome` → `store.append_outcome` → `build_daily_report`)
without inventing a database dependency. A real writer integration should
call `capture_decision`/`enrich_with_outcome` from its own code path and
either keep this store or swap in a database that preserves the same
append-only, non-overwriting contract.

## Ambiguities / open items

1. **Registered-writer list** (`writer_registry.REGISTERED_WRITERS`) is a
   placeholder set (`mlb_scanner_v1`, `mlb_governor_v1`,
   `mlb_manual_tracking_v1`) — the real production writer IDs need to be
   confirmed and registered by whoever owns each writer's code path before
   this goes live, or every real decision will alert as unmapped.
2. **Rationale dialect maps** (`rationale_registry._DIALECT_MAPS`) are
   placeholders illustrating the normalization pattern across
   `scanner_v1`/`governor_v1`/`governor_v2`/`manual_tracking_v1` — the real
   vocabulary used by each live scanner/governor version needs to be
   registered here.
3. **Plausible American-odds bounds** in `price_validation.py` reuse the
   same open question Phase 0 left for ingestion validation (bounds may be
   market-dependent); current bounds (`100`–`100000` magnitude) are a
   conservative placeholder.
4. **Persistence backend**: the JSONL reference store is sufficient for
   correctness and for driving the daily report, but a live system
   generating meaningful decision volume should back this with a real
   database keeping the same append-only guarantees.
