# MLB Replay V1 — Workstream A Status: BLOCKED before corpus generation

**Workstream:** A — Historical Corpus + Evidence Eligibility
**Contract used:** `MLB_REPLAY_EVIDENCE_V1` (`docs/MLB_REPLAY_V1_EVIDENCE_CONTRACT.md`,
`contracts/mlb_replay_v1/evidence_contract.json`), unmodified.
**Outcome:** No corpus, eligibility summary, exact-slice table, or exclusion table was
produced. Producing any of those without a real data source would mean fabricating the
numbers, which the contract itself forbids (Principle 8: "Missing/unknown provenance
must remain unknown rather than reconstructed"). This document reports the blocker and
what was verified instead, per the contract's own instruction to "raise" a gap rather
than "fill it unilaterally."

## 1. What was checked

`rudman101/Python` — the repo this workstream develops in — contains only the Phase 0
contract deliverable: `docs/`, `contracts/mlb_replay_v1/`, `tests/mlb_replay_v1/`,
`conftest.py`, `pytest.ini`. No database, no historical rows, no engine code, no DFS
registry, no signal/shadow tables. That is the entire contents of the repo (confirmed
via `git log --all`, `git ls-remote`, full directory listing).

The contract references an "engine" (canonical DFS book registry, signal/shadow
families, pregame decision sources) that does not exist in this repo. That engine lives
in a sibling repo, `rudman101/syndicate_bettor` (added read-only this session to check
before reporting a hard blocker). Key findings there:

- **It is a real, currently-operated betting engine**, run locally by the user
  (`README.md`: PowerShell loop scripts, a local Flask server at `127.0.0.1:5000`,
  Windows Terminal tabs for scrapers/engine/alerts).
- **Its data store is not in git and not reachable from this session.**
  `bet_engine/db/db.py` defaults to `DB_PATH=data/bets.db` (SQLite); `.gitignore`
  explicitly excludes `data/*.db*`. The README states production has cut over to
  Postgres (`BETS_STORE_BACKEND=postgres`, `POSTGRES_DSN`), which is likewise never
  committed and, per the local-loop/localhost-only operational model in the README, is
  not exposed to this sandboxed session. `env | grep -i "database\|postgres"` in this
  session returns nothing. A fresh clone of the repo confirms `data/*.db` is genuinely
  absent (not just gitignored-but-present).
- A handful of **pre-computed audit snapshot files** are committed under
  `data/audit_outputs/` (e.g. `mlb_ev_roi_7d_2026-07-08.txt`, `kbo_shadow_2026-07-08.json`,
  `npb_shadow_2026-07-08.json`, `foreign_confidence_slice_2026-07-08.json`), all dated
  2026-07-08. These are one-off aggregated outputs, not row-level replay-observation
  data, and are a single day's snapshot — not usable as the corpus itself without
  misrepresenting scope. Not used as a substitute for real inventory.

**Conclusion:** there is no historical MLB pregame-decision data reachable from this
session in either repo. Corpus inventory, tier classification counts, exact-slice
performance, and exclusion-reason tables all require row-level access to that data;
none can be produced honestly without it.

## 2. A second, more consequential finding

`rudman101/syndicate_bettor/bet_engine/` already contains an extensive, independently
versioned historical-evidence/replay system that appears to cover much of what this
workstream describes, under different naming:

- `bet_engine/historical_evidence/` — 18,080 lines across `contracts.py`,
  `eligibility.py`, `replay.py`, `backfill.py`, `audit.py`, `performance.py`,
  `model_governance.py`, `storage.py`, `reporting.py`, `snapshots.py`,
  `public_sources.py`, `governance_storage.py`. Its own contract version is
  `"historical_evidence_v1"` (plus `"hef_temporal_asof_v2"` for temporal handling) —
  **not** `MLB_REPLAY_EVIDENCE_V1`, and its vocabulary (`CanonicalOpportunity`,
  `FieldProvenance`, `MissingEvidence`, `QuarantineFinding`) does not use this
  contract's TIER_A/B/C terms at all.
- MLB-specific modules with names that overlap this workstream's stated goals:
  `mlb_slate_replay.py`, `mlb_exact_slice_hardening.py`, `mlb_provenance_contracts.py`
  (contract version `"mlb_signal_provenance_contract_v1"`), `mlb_model_governance.py`,
  `mlb_decision_e2e_audit.py`, `pitcher_ks_execution_replay.py`. These use their own
  tier/action vocabulary (e.g. promotion states `QUARANTINE`/`TRACK_ONLY`/`WATCH`/
  `LAUNCH_LAB`/`CARD_ELIGIBLE`/`BET_CANDIDATE`/`PAID_CARD`; exact-slice actions
  `FREEZE`/`TIGHTEN`/`PILOT_REVIEW`/…), distinct from `TIER_A_FULL_REPLAY` etc.

This means two non-identical "evidence tier" / "replay" specifications currently exist
for the same domain, in two repos, under two owners' worth of naming. I did not
reconcile them — that is a scope/architecture decision, not something to resolve
unilaterally per the contract's own "Ambiguities" section. Flagging it here because it
changes what Workstream A even means: build a fresh corpus under the new
`MLB_REPLAY_EVIDENCE_V1` contract from raw historical rows, or reconcile with the
already-operating `historical_evidence_v1` / `mlb_signal_provenance_contract_v1`
system that has presumably been classifying this same data for a while.

## 3. What could be verified without row-level data (real, grounded, not fabricated)

**Canonical DFS book registry** (per the contract's instruction to use the engine's
registry, not a hand-maintained duplicate): `bet_engine/odds_store.py:253`

```python
DFS_BOOKS = frozenset({"underdog", "prizepicks", "sleeper", "thrivefantasy", "boomfantasy"})
```

**MLB-relevant source/signal families present in the engine** (by code path only —
this is an inventory of *sources*, not of rows, and makes no claim about volume or
tier composition):

| Family | Scanner/grader modules |
|---|---|
| NRFI/YRFI | `nrfi_scanner.py`, `nrfi_grader.py`, `nrfi_edge_finder.py`, `nrfi_alerter.py`, `nrfi_lane_audit.py` |
| Pitcher strikeouts | `mlb_pitcher_ks_scanner.py`, `mlb_pitcher_ks_grader.py`, `pitcher_ks_execution_replay.py`, `pitcher_ks_timing_audit.py` |
| Pitcher outs | `mlb_pitcher_outs_scanner.py`, `mlb_pitcher_outs_grader.py` |
| Pitcher damage | `mlb_pitcher_damage_scanner.py`, `mlb_pitcher_damage_grader.py`, `pitcher_damage_lane_audit.py` |
| Batter hits | `batter_hits_scanner.py`, `batter_hits_grader.py`, `batter_hits_calibrator.py`, `batter_hits_lane_audit.py` |
| Batter total bases | `batter_total_bases_scanner.py`, `batter_total_bases_grader.py`, `batter_total_bases_lane_audit.py` |
| Batter home run/HRR | `mlb_home_run_scanner.py`, `mlb_home_run_grader.py`, `batter_hrr_scanner.py`, `batter_hrr_grader.py` |
| Batter event/discipline | `mlb_batter_event_scanner.py`, `mlb_batter_event_grader.py`, `mlb_batter_discipline_scanner.py`, `mlb_batter_discipline_grader.py`, `batter_discipline_lane_audit.py` |
| Totals | `mlb_totals_scanner.py`, `mlb_totals_grader.py` |
| Foreign baseball (KBO/NPB) shadow | `foreign_baseball_shadow_scanner.py`, `foreign_baseball_shadow_audit.py`, `foreign_baseball_finality.py`, `foreign_baseball_result_fetcher.py`, `foreign_baseball_result_settlement.py`, `foreign_baseball_registry.py` |

`mlb_slate_replay.py` independently defines this same source-family grouping in code
(`SOURCE_FAMILY` dict mapping e.g. `nrfi_signals→nrfi_yrfi`, `pitcher_ks_signals→pitcher_ks`,
`batter_hrr_signals→batter_hrr`), which corroborates the table above from a second,
independent source.

**July 2026 foreign-baseball shadow defect** (`DEFECT_JUL2026_MISSING_FOREIGN_SHADOW`
in the Phase 0 contract, registered there as provisional/unconfirmed): committed
`kbo_shadow_2026-07-08.json` and `npb_shadow_2026-07-08.json` audit outputs, plus the
existence of dedicated `foreign_baseball_shadow_*` modules, corroborate that a real
KBO/NPB shadow-data issue exists in this system. This does **not** confirm the
2026-07-12→07-18 window itself — that still requires row-level query against the
actual data, which is unavailable here. Per contract Principle 10, this is registered
as an open, bounded item and does not block anything else in this report.

**Pregame-required market list, plausible odds bounds** (Ambiguities #2–3 in the
contract): still unresolved — same reason, needs either the market-definition owner or
row-level data to derive sensible bounds empirically.

## 4. Blockers for Workstream B (and for completing Workstream A itself)

1. **No read access to the historical data store.** Need one of: a read-only Postgres
   DSN for the engine's production database reachable from this environment, an
   exported snapshot (CSV/parquet/SQLite dump) of the relevant tables, or this
   workstream run in an environment with that access.
2. **Which contract governs.** Confirm whether `MLB_REPLAY_EVIDENCE_V1` (this repo) is
   meant to (a) be built out fresh against raw historical rows independent of
   `bet_engine/historical_evidence/` and the `mlb_signal_provenance_contract_v1`
   modules, or (b) reconcile with/consume output from that already-running system.
   Building the corpus generator twice, from two contracts, against the same
   underlying data would itself become a provenance problem the contract exists to
   prevent.
3. Once (1) and (2) are resolved, Workstream A can proceed exactly as scoped: query
   the resolved source, classify every row with
   `contracts.mlb_replay_v1.tiers.classify_tier`, build exact-slice keys with
   `contracts.mlb_replay_v1.exact_slice.build_exact_slice_key`, exclude `DFS_BOOKS`
   rows from sportsbook ROI/EV/CLV per the registry above (while still classifying
   them for forensic purposes, per the contract), and produce the eight deliverables
   listed in the workstream brief with real counts and content hashes.

No files were modified outside this repo. `rudman101/syndicate_bettor` was added
read-only for verification only; nothing was written to it, and no historical or
shadow data anywhere was modified.
