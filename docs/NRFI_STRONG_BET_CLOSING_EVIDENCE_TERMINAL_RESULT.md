# NRFI STRONG_BET — closing-evidence check: status and source review

**Status:** `SOURCE_REVIEW_ONLY` / `ARCHIVE_CHECK_BLOCKED_NO_RUNTIME_DATA`
**This is not an archive verdict.** `ARCHIVE_EXHAUSTED` is **not** established.
**Revised:** 2026-09-17 (supersedes the 2026-09-16 revision of this file)
**Scope:** read-only source analysis. No policy edits, deployment, wagers,
historical writes, schema changes, capture-writer changes, or unlock.
FAST_STRIKE unchanged.

## 0. Correction notice

The previous revision of this document was labelled "Route 2 — archive
exhausted for the historical cohort." **That label was wrong and is
withdrawn.** It contradicted this document's own central finding, that the
check was never executed. An environment that cannot read the archive cannot
report on its contents.

Four claims in that revision are corrected below and must not be used to
support a deployment decision:

| Prior claim | Corrected status |
|---|---|
| "The historical quotes were deleted" (retention) | **Hypothesis about a different backend.** See §3. |
| "Port the capture code to main" | **Withdrawn.** See §4. |
| "There is no 0.10u path" | **Wrong.** `MIN_BET_UNITS = 0.10`. See §7. |
| "The gate reads no ROI term" | **Inaccurate as phrased.** See §6. |

What survives is source analysis and the arithmetic. Nothing here measures
the cohort.

## 1. What this environment could and could not do

The bounded check was **not executed**, and is not executable here:

| Requirement | State |
|---|---|
| Frozen extract (438 recs, 2026-09-16T23:03:36Z, txn 130682594) | Not in the repository. `main` was last pushed 2026-09-16 17:59:15Z. |
| `data/bets.db`, `data/odds.db` | Absent; `.gitignore` excludes `data/*.db`. |
| PostgreSQL server | Absent. `psql` client only, no listening socket. |

Per the host-side audit, the production runtime is a different environment
from the one inspected here: repository `Rudman101/syndicate_bettor`, running
branch `codex/consolidated-engine-20260721` at commit `38c8e2ca`, PostgreSQL
`syndicate_bettor / public` on port 5432, with **both** bets and odds backends
on PostgreSQL. **Those are the prior audit's findings, restated — not a new
inspection.** A cloud checkout of `main` is not a substitute for that runtime
or its database.

## 2. What does hold: the structural correction and the arithmetic

These are source-level facts, verifiable without the database.

**2.1 Discovery is already event-level, not source-ID-bound.**
`bet_engine/shadow_closing_truth.py:_quote_rows` searches on
`market IN (...) AND sport IN (...) AND line BETWEEN ... AND
changed_at/last_seen_ts BETWEEN ...`, anchored by `canonical_event_id` when
present, falling back to `player_name`. `source_id` is not a predicate. NRFI
resolves via `shadow_clv.MARKET_ALIASES["nrfi / yrfi"] = ["total_1i"]`.

**2.2 Raw closes are retained separately from stored CLV.**
`config/postgres_schema.sql:587` — `shadow_closing_truth` holds
`entry_odds_american` / `entry_ts_utc` alongside `routed_close_*`,
`best_close_*`, and the derived `routed_clv_profit_delta` /
`market_clv_profit_delta`. A→C is recomputable from retained columns. Routed
and market-reference metrics are stored separately, so neither need be
selected over the other.

**2.3 The CLV formula and worked example are exact.**
`_profit_delta = _american_price_profit_per_unit(open) - (close)`, the helper
being `odds/100` positive, `100/|odds|` negative. A=-110, B=-120, C=-130 give
A→C = **+0.13986** and B→C = **+0.06410** — a profit-per-unit price
difference, not ROI and not EV.

**2.4 The fallback exclusion is already implemented.**
`shadow_high_quality_clv_*` (`truth_engine` aggregation, `truth_promotion.py`
lines 301-303) counts only `truth_reason = 'closing truth captured'`,
excluding `'last observed fallback'`. `_closing_quality` classifies
`FALLBACK_ONLY` / `MIXED_FALLBACK`, and `_recommend` refuses to promote from
either. The engine already enforces "missing stays missing, never flat."

## 3. Retention: a hypothesis about the wrong backend

**`db_prune_v2.py` is SQLite-only.** It imports `sqlite3`, calls
`sqlite3.connect(path)`, and defaults to `data/bets.db` / `data/odds.db`
(lines 42, 50-51, 85). There is no `psycopg` path in it.

Its `ODDS_RETENTION = [("odds_history", "scan_cycle_ts", 7)]` and
`PRICES_KEEP_DAYS = 3` therefore **do not establish PostgreSQL production
retention**, do not show that any deletion ran, and say nothing about what
remains in the separately stored closing-truth and snapshot tables. The repo
additionally keeps a `tools/legacy_sqlite_diagnostics/` tree and a
`ODDS_STORE_BACKEND` cutover switch in `config/postgres.env.example`, both
consistent with the SQLite path being legacy relative to the audited runtime.

Even a *verified* PostgreSQL retention rule would not establish that every
opportunity in the cohort lacks a retained close. Retention bounds raw quote
history; it does not govern `shadow_closing_truth` or `shadow_close_snapshots`
rows already materialized. **This remains a question for the host-side query,
not a finding.**

## 4. The port recommendation is withdrawn

The prior revision inferred that because `shadow_close_snapshots` is absent
from `main`, it must be ported. **That inference assumed production runs
`main`, which was never verified and is contradicted by the host-side audit.**
The audited running branch is `codex/consolidated-engine-20260721` at
`38c8e2ca` — the very commit where this review found the capture code. Its
absence from `main` does not establish its absence from production.

The open question is **not** whether `main` contains the capture path. It is
whether the capture path already present in the audited runtime is **active**
and **supports first-inning totals** (`total_1i`, line 0.5, generic side).
`tools/shadow_close_snapshot_capture.py` is market-agnostic with an optional
`--market` restriction, so suitability is plausible but unverified; binding
for a game-level total goes through `subject_team = shadow["player"]`, which
for NRFI is the game name, not a team — that path needs checking against real
rows, not reasoning.

No port to `main` should be approved on the basis of this document.

## 5. P42 corroborates a method; it does not substitute

The completed event-level search
(`codex/syndicate-bettor-v3-p42-closing-observation-query-ambiguity-repair-r1`,
2026-09-10) returned: 270 streams, **270 `NO_POST_DECISION_TICK`**, 0
`ELIGIBLE_UNPUBLISHED_CLOSE_EXISTS`, 0 `AMBIGUOUS`, route
`PRESERVE_MISSING_COMPATIBLE_CLOSE_STATE`.

Its population is `PROPSBOT / AUTHORIZED_ACCOUNT_UI / TEAM_MONEYLINE_BOARD /
MLB / FULL_GAME / MONEYLINE` — six events, twelve outcome identities, one
Chicago board date. **It is not the NRFI first-inning cohort and cannot stand
in for the missing NRFI check.** It shows the method terminates cleanly and
records refusals honestly. That is all it shows here.

## 6. The gate: what is and is not true about ROI

`bet_engine/truth_promotion.py:_recommend`. Correcting the prior phrasing —
`real_roi` **is** read, in three places:

- **Confidence:** `roi_strength = 0.0 if real_roi is None else real_roi`,
  clamped into the confidence score.
- **Veto:** `real_n >= 8 and real_roi <= -0.08` → `TIGHTEN_GATE`.
- **Eligibility:** `OPEN_SMALL_CAP` requires `real_n < 8 or real_roi is None
  or real_roi >= -0.03`; `OPEN_REAL_MONEY` requires `real_n < 10 or real_roi
  >= 0.02`.

The accurate and narrower claim is this: **no amount of positive ROI satisfies
the opening pathway on its own.** Both opening branches additionally require
clean high-quality CLV volume and quality:

| Outcome | Permission | Units | CLV conditions (all mandatory) |
|---|---|---:|---|
| `OPEN_SMALL_CAP` | `ALLOW_PILOT` | 0.25 | `market_dec >= 18`, `market_rate >= 0.58`, `avg_market >= +0.01` |
| `OPEN_REAL_MONEY` | `ALLOW_SMALL_REAL` | 0.50 | `market_dec >= 45`, `market_rate >= 0.66`, `avg_market >= +0.04` |

where `market_dec = shadow_high_quality_clv_decisions`. ROI modulates and can
veto; it cannot substitute for clean CLV.

One further distinction worth preserving: `real_roi` is realized ROI over
*matched placed wagers*, not the reconstructed ROI of a recommendation cohort.
The +10.33% figure is the latter and would not populate `real_roi` at all.

**Gate result for NRFI STRONG_BET: not evaluable here.** `market_dec` for the
exact slice is unknown without the database.

## 7. The 0.10u claim was wrong

`bet_engine/capital_allocation.py:22` — **`MIN_BET_UNITS = 0.10`**. It is the
minimum allocatable size, gating real allocations at lines 405, 427 and 507.
`FALLBACK_UNIT_CAP = 0.25`; `FAMILY_CAPS["nrfi_yrfi"] = 1.00`. A supplied
`TRUTH_CAP` preserves its own `truth_cap["units"]` (lines 420-426), so a
0.10u cap can flow through. `first5_lane_audit.PILOT_UNIT_CAP = 0.10` and
`MODEL_EMAIL_NRFI_LEAN_UNITS` (default 0.10, hi 0.25) show 0.10u used
elsewhere.

So 0.10u is a representable, permitted allocation size. **The categorical
claim that it is impossible was incorrect.**

What *is* accurate, and remains outstanding:

- The NRFI micro lane currently books `recommended_units = 0.0` with
  `micro_pilot_tracking = 1`; `NRFI_MICRO_TRACKING_STAKE_USD = 1.0` is a
  nominal dollar figure, and `MICRO_MAX_UNITS = 0.25` is an alert-recognition
  filter, not a stake control.
- Allocation authority is the portfolio governor, and the two have disagreed
  before: the card showed 5 NRFI rows at 0.80u while `mlb_bankroll_decisions`
  recorded every one `TRACK` at 0.00u.

**Correct status: exact-slice enforcement of a 0.10u cap for this cohort is
unverified** — not impossible.

## 8. Standing blocker, unchanged

`docs/PIKKIT_MATCHER_NRFI_R4A.md` (2026-09-16): no Tier 2 or Tier 3 consumer
distinguishes `AGREE` from `OPPOSE` or `PASS`, and `match_confidence >= 0.90`
does not separate them (all three record 1.0). `truth_promotion.py` is named
in that Tier 3 blocking set and is the source of the `real_n` / `real_roi`
input in §6. Gates: `NRFI_REPORTING_R4A_READY_FOR_REVIEW_NOT_DEPLOYED`,
`PRODUCTION_CANARY_NOT_AUTHORIZED`, `HISTORICAL_PROCESSING_NOT_AUTHORIZED`.
Also recorded there: `availability_before_placement_proven = false`.

## 9. Next step: host-side, not here

The outstanding work is a bounded read-only query on the audited Windows host
against its PostgreSQL instance, using the frozen 438 IDs and original opening
prices/times, primary slice the 118 NRFI STRONG_BET opportunities. It requires
no remote PostgreSQL exposure, no credential sharing, no database upload, and
no port to another branch.

**Offline evaluation only.** Gate eligibility is to be computed from audited
metrics as a *recommendation*. Do not run `sync_truth_promotion_decisions`,
`sync_shadow_closing_truth`, schema initializers, or any other refresh/write
path — `sync_truth_promotion_decisions` calls both sync functions and then
`DELETE`s and rewrites `mlb_truth_promotion_decisions` for the date, so
"evaluating the gate" through it would be a production write. Do not update
policy, allocation, or promotion records. Keep NRFI STRONG_BET separate from
YRFI STRONG_BET and from all BET tiers; do not pool observations to reach a
minimum sample.

**Authentic flat is not missing.** A genuine quote showing no price movement is
a legitimate flat comparison; a missing close replaced by the entry price is
missing evidence and must never be counted as one. The schema already carries
the distinction, and the gate treats the two asymmetrically — worth knowing
before reading any coverage number:

- `shadow_high_quality_clv_decisions` counts only
  `market_clv_status IN ('won_clv','lost_clv')`, so an **authentic flat does
  not advance `market_dec` toward the 18-decision threshold**;
- `shadow_avg_high_quality_clv_delta` averages over
  `('won_clv','lost_clv','flat')`, so an authentic flat **does** enter the
  average delta and dilutes it toward zero.

Both are restricted to `truth_reason = 'closing truth captured'`;
`'last observed fallback'` is excluded from each and is separately counted as
`shadow_fallback_matched`.

It must return exactly one of:

- `HISTORICAL_CLOSES_RECOVERED` — with coverage and applicable gate results;
- `ARCHIVE_EXHAUSTED_FOR_THIS_COHORT` — with queried coverage and refusals; or
- `ACCESS_BLOCKED` — with no archive verdict.

Separately, and not as part of that verdict: whether the capture path already
present in the audited runtime is active and supports `total_1i`.

## 10. Standing separations

The recovered first-inning outcome table remains the current internally
corroborated assessment, with the frozen 438 IDs, tiers, sides, prices, times,
extraction identity and evidence sources preserved. The earlier YRFI BET
verdict from 14 recorded-only outcomes stays superseded. Strikeout tracing was
not reopened.

Internally recovered outcomes are not independently verified game results.
CLV coverage is independent of outcome resolution. And current reads are
current reads — never a reconstruction of an earlier database state.

**NRFI STRONG_BET remains the leading candidate and is not cleared for paid
activation. Nothing in this document changes either half of that.**
