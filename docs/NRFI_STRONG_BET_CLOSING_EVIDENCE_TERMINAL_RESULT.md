# NRFI STRONG_BET — bounded closing-evidence check: terminal result

**Status:** TERMINAL — Route 2 (archive exhausted for the historical cohort)
**Date:** 2026-09-16
**Scope:** read-only. No policy edits, no deployment, no wagers, no historical
writes, no capture-writer changes, no automatic unlock. FAST_STRIKE unchanged.

## 0. Executive answer

**Route 2: the historical archive is exhausted for this cohort, and the reason
is data retention, not lookup keying.** The reviewer's structural correction
about source-ID binding is *correct and already implemented*, but it does not
change the outcome, because the rows a broadened search would look for have
been deleted on a 7-day retention schedule.

A separate, harder finding: **the applicable paid-opening gate does not read
ROI at all.** The +10.33% NRFI STRONG_BET figure cannot open this lane under
the existing gate no matter how it is verified. Only clean closing-line value
can, and that is exactly the evidence that is missing.

**The 0.10u cap is not enforceable.** This is now established, not pending.

## 1. What could not be done here, and why

The bounded check was **not executed**. It is not executable from this
environment:

| Requirement | State |
|---|---|
| Frozen extract (438 recs, 2026-09-16 23:03:36 UTC) | **Not in the repository.** `main` was last pushed 2026-09-16 17:59:15 UTC, ~5h before the extract timestamp. |
| `data/bets.db`, `data/odds.db` | **Absent.** `.gitignore` lines 9-13 exclude `data/*.db` and its sidecars. |
| PostgreSQL service | **Absent.** `psql` client present; no server, no listening socket. |

The evidence lives only on the operator's machine. No supplementary read-only
snapshot was taken, and cohort membership was not altered. The counts requested
in the instruction cannot be produced from here by me or by any agent in this
container. Everything below is derived from source, schema, and committed
audit artifacts.

## 2. The reviewer's structural correction is confirmed

All three claims check out against the source.

**2.1 Discovery is already event-level, not source-ID-bound.**
`bet_engine/shadow_closing_truth.py:_quote_rows` searches `odds_history` and
`current_odds` on `market IN (...) AND sport IN (...) AND line BETWEEN ... AND
changed_at/last_seen_ts BETWEEN ...`, anchored by `canonical_event_id` when
available and falling back to `player_name`. `source_id` is not a predicate.
NRFI resolves through `shadow_clv.MARKET_ALIASES["nrfi / yrfi"] = ["total_1i"]`,
so the first-inning lookup path exists.

**2.2 Raw closes are retained separately from stored CLV.**
`config/postgres_schema.sql:587` — `shadow_closing_truth` holds
`entry_odds_american` / `entry_ts_utc` alongside `routed_close_book`,
`routed_close_odds_american`, `routed_close_ts_utc`, `best_close_book`,
`best_close_odds_american`, `best_close_ts_utc`, and the derived
`routed_clv_profit_delta` / `market_clv_profit_delta`. **A→C is recomputable by
arithmetic on retained columns and needs no archive search at all.** Routed and
market-reference metrics are already stored separately, so neither has to be
selected over the other.

**2.3 The CLV formula and the worked example are exact.**
`_profit_delta = _american_price_profit_per_unit(open) - _american_price_profit_per_unit(close)`,
where the helper is `odds/100` for positive and `100/|odds|` for negative.
So for A=-110, B=-120, C=-130: A→C = 100/110 - 100/130 = **+0.13986**;
B→C = 100/120 - 100/130 = **+0.06410**. This is a profit-per-unit price
difference, not ROI and not EV, exactly as stated.

## 3. Why the broadened search still fails: retention

This is the decisive fact and it was not in view when the instruction was written.

`db_prune_v2.py`:

```
ODDS_RETENTION = [ ("odds_history", "scan_cycle_ts", 7) ]   # 7 days
PRICES_KEEP_DAYS = 3                                         # prices
```

- `odds_history` rows are **deleted after 7 days**.
- `prices` rows are deleted after 3 days.
- `current_odds` is overwritten in place as prices move.

The frozen cohort spans a season. For any recommendation older than seven days,
**there are no raw quote rows left to find.** Broadening the key from
`source_id` to event/market/side/line identity searches the same empty table.
Missing here means deleted, and it must stay missing rather than be filled.

## 4. `shadow_close_snapshots` is forward-capture, and is not on main

The structure the reviewer inspected at pinned commit `38c8e2ca` is real, and
its schema matches the description (canonical event ID, sport, book, market,
side, line, subject team, quote timestamp, binding method and binding state).
Two qualifications matter:

1. **It is not on `main`.** `38c8e2ca` is the head of the unmerged branch
   `codex/consolidated-engine-20260721`. No `shadow_close_snapshots` reference
   exists anywhere in the current main-line tree.
2. **It cannot be backfilled.** Its own migration header states the purpose:
   *"current_odds is a snapshot that is overwritten as prices move, and
   odds_history only records CHANGES... This table captures the price BEFORE
   first pitch and never mutates it."* Its inputs are `current_odds` and
   `odds_history` (`tools/shadow_close_snapshot_capture.py:61-82`), so it can
   only record what is still present when it runs. It is a going-forward
   remedy for precisely the loss described in §3.

The same module header carries a measured contamination figure worth quoting
directly: **"70% of all closes since 2026-09-01 (31,120 rows) are that
fallback"** — the entry-price fallback that manufactured `clv_status='flat'`.
That is the fabricated-flat evidence the instruction rules out, quantified.

## 5. The equivalent search has already been run once — counts included

Per the instruction not to re-run completed work: a bounded, event-level,
non-source-ID archive search **has already been executed and published**, on the
branch `codex/syndicate-bettor-v3-p42-closing-observation-query-ambiguity-repair-r1`
(2026-09-10), result at
`v3/docs/architecture/prospective-evidence-exhausted-feature-cohort-closing-observation-salvageability-audit-result-r1.json`.

| Classification | Count |
|---|---:|
| `AMBIGUOUS` | 0 |
| `NO_POST_DECISION_TICK` | **270** |
| `NORMALIZATION_OR_SOURCE_LINEAGE_INCOMPATIBLE` | 0 |
| `ONLY_POST_START` | 0 |
| `QUOTE_TOO_OLD` | 0 |
| `ELIGIBLE_UNPUBLISHED_CLOSE_EXISTS` | **0** |

Streams 270, candidate universe 270, duplicate identities 0, overflow false,
sporting-result fields consulted false. Route
`PRESERVE_MISSING_COMPATIBLE_CLOSE_STATE`; reason
`NO_ELIGIBLE_UNPUBLISHED_CLOSES_PRESERVE_MISSING_STATE`;
`exhausted_historical_salvage_lane_closed: true`; next checkpoint
`P36_EXACT_0020_BOUNDED_FRESH_COHORT_CAPTURE`.

**Read this carefully before transferring it.** That cohort is 270 decision
snapshots over six events, twelve outcome identities and one Chicago board
date, in the source arm `PROPSBOT / AUTHORIZED_ACCOUNT_UI /
TEAM_MONEYLINE_BOARD / MLB / FULL_GAME / MONEYLINE`. **It is not the 438
NRFI/YRFI first-inning cohort**, so it does not by itself settle NRFI. What it
does establish is that the same method, applied with the same distinctions,
found zero recoverable closes and terminated in a prospective-capture
recommendation — and that every one of its 270 failures was
`NO_POST_DECISION_TICK`, i.e. nothing was ever recorded post-decision, rather
than a binding or keying failure.

## 6. The applicable gate — and it is not an ROI gate

`bet_engine/truth_promotion.py:_recommend`.

```
market_dec   = shadow_high_quality_clv_decisions
market_rate  = shadow_high_quality_clv_won / market_dec
avg_market   = shadow_avg_high_quality_clv_delta
```

`shadow_high_quality_clv_*` is defined at lines 301-303 as
`truth_reason = 'closing truth captured'` only — **the `'last observed
fallback'` path is already excluded from the gate**. The gate independently
implements "missing remains missing, never flat."

| Outcome | Permission | Units | Conditions |
|---|---|---:|---|
| `OPEN_SMALL_CAP` | `ALLOW_PILOT` | **0.25** | `market_dec >= 18` **and** `market_rate >= 0.58` **and** `avg_market >= +0.01` **and** (`real_n < 8` or `real_roi >= -0.03`) |
| `OPEN_REAL_MONEY` | `ALLOW_SMALL_REAL` | 0.50 | `market_dec >= 45`, `market_rate >= 0.66`, `avg_market >= +0.04`, (`real_n < 10` or `real_roi >= +0.02`) |

Blocking clauses that fire first: `no_match_rate >= 0.40` with `shadow_n >= 10`
→ `WATCH_PRICE_ONLY`; fallback-only closing truth → `KEEP_SHADOW`
(*"do not promote from stale/last-observed CLV"*); `MIXED_FALLBACK` with
`fallback_rate >= 0.50` and `market_dec < 18` → `KEEP_SHADOW`.

**ROI is not an opening term.** It appears only as a veto
(`real_n >= 8 and real_roi <= -0.08` → `TIGHTEN_GATE`) and as a secondary
tolerance. **A reported +10.33% cannot open this lane.** The only currency this
gate accepts is clean closing-line value, which is the evidence §3 says is gone.
That is a stronger reason not to waive the paid-opening requirements than the
one the instruction anticipated.

**Gate result for NRFI STRONG_BET: not evaluable.** `market_dec` for the exact
slice is unknown without the database, and the gate cannot be evaluated on
anything else.

## 7. The 0.10u cap is not enforceable — established

| Fact | Source |
|---|---|
| The NRFI micro lane books **zero** official units and sets a flag instead: `signal["recommended_units"] = 0.0`, `signal["micro_pilot_tracking"] = 1` | `nrfi_scanner`, pinned by `tests/test_nrfi_micro_pilot_authority.py` |
| Tracking stake is nominal: `NRFI_MICRO_TRACKING_STAKE_USD = 1.0` (dollars, not bankroll units) | `bet_engine/nrfi_scanner.py` |
| `MICRO_MAX_UNITS = 0.25` (`NRFI_ALERT_MICRO_MAX_UNITS`) is an **alert-recognition filter** for legacy unit-bearing rows, not a stake control | `bet_engine/nrfi_alerter.py:116,233` |
| Allocation authority is the portfolio governor, not the lane. These previously disagreed: the card showed 5 NRFI rows at 0.80u while `mlb_bankroll_decisions` recorded every one `TRACK` at 0.00u | `tests/test_nrfi_micro_pilot_authority.py` docstring |
| Alerts are explicitly labelled `MODEL_METADATA_NOT_EXECUTION` | `bet_engine/nrfi_alerter.py:300,339` |
| The gate's own pilot size is **0.25u** | `truth_promotion._recommend` |

There is no code path that sizes an NRFI wager at 0.10u. A 0.10u cap would
require a **new governor-side allocation path that does not exist**, and
building one is a financial-authority change, not a trial parameter.

## 8. Additional blocker, not previously surfaced

`docs/PIKKIT_MATCHER_NRFI_R4A.md` (2026-09-16) records that no Tier 2 or Tier 3
consumer distinguishes `AGREE` from `OPPOSE` or `PASS`, and that the
`match_confidence >= 0.90` gates do not separate them either — all three record
confidence 1.0. **`bet_engine/truth_promotion.py` is named in that Tier 3
blocking set**: it joins `shadow_bets` at `match_confidence >= 0.90` and
aggregates those wagers as a lane's *real* results. That is the `real_n` /
`real_roi` input to the gate in §6. Standing gates on that branch:
`NRFI_REPORTING_R4A_READY_FOR_REVIEW_NOT_DEPLOYED`,
`PRODUCTION_CANARY_NOT_AUTHORIZED`, `HISTORICAL_PROCESSING_NOT_AUTHORIZED`.

The same document states the governing constraint plainly: *"AGREE alone, or
confidence 1.0 alone, is not proof of availability, delivery, or causation,"*
with `availability_before_placement_proven = false`.

## 9. Recommendation — smallest prospective, no-money capture cohort

This matches the system's own already-published next checkpoint (§5), so it
reopens nothing.

**Population.** NRFI/YRFI `STRONG_BET` only, MLB, canonical market `total_1i`,
line 0.5, side NRFI/YRFI. Forward-dated decisions only. No historical rows.

**Money.** None. Units stay 0.0 with `micro_pilot_tracking = 1` — current
behavior, unchanged. No governor change, no permission change, no unlock.

**Mechanism.** `tools/shadow_close_snapshot_capture.py` already accepts
`--market`, is market-agnostic, and enforces exact binding with explicit
unbound states (`UNBOUND_NO_EXACT_TEAM_MATCH`, `UNBOUND_AMBIGUOUS_EQUAL_PRICES`,
`UNBOUND_NO_PRESTART_QUOTE`, `UNBOUND_TEAM_UNPARSEABLE`) and no price on an
unbindable quote. It must run **before first pitch**, inside the 7-day window,
or it captures nothing.

**One enabling step requires explicit authorization.** `shadow_close_snapshots`
and its capture tool live only on unmerged `38c8e2ca`. Porting them to main is
a capture-writer change, which the instruction forbids. **This is the single
decision that gates the whole proposal** and it belongs to the operator, not to
me. Note the alternative is not neutral: leaving it unported means first-inning
closes keep being lost at 7 days, and the measured 70% fallback rate continues.

**Exit criterion.** `market_dec >= 18` clean high-quality CLV decisions
(`truth_reason = 'closing truth captured'`) on the exact NRFI STRONG_BET slice,
then re-evaluate §6 on its own terms. Nothing about reaching it authorizes a
wager; it only makes the gate evaluable.

**Exact missing evidence, per row.** For each of the 118 NRFI STRONG_BET
recommendations: a pre-start closing quote **C** bound to the exact
`(canonical_event_id, total_1i, side, line 0.5, book)` identity, with quote
timestamp strictly before first pitch, recorded under
`truth_reason = 'closing truth captured'`. Not the entry-price fallback, not a
post-start quote, not a pre-entry `last_observed` row, not a substring-bound
opponent price.

## 10. What remains true about the outcome table

The recovered first-inning outcome table stands as the current internally
corroborated assessment, with its frozen 438 IDs, tiers, sides, prices, times,
extraction identity and evidence sources preserved. The earlier YRFI BET verdict
drawn from 14 recorded-only outcomes is superseded. Strikeout tracing was not
reopened.

Two separations hold regardless of anything above: internally recovered
outcomes are **not** independently verified game results, and **CLV coverage is
independent of outcome resolution** — a row can have a resolved outcome and no
usable close, which is precisely this cohort's situation.
