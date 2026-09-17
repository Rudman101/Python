# Cross-thread handoff: R02 grader release vs NRFI evidence review

**Status:** record only. No R02 implementation change, no NRFI change, no
historical repair, no deployment, no betting unlock.
**Date:** 2026-09-17
**Companion:** `docs/NRFI_STRONG_BET_CLOSING_EVIDENCE_TERMINAL_RESULT.md`
(closed at `SOURCE_REVIEW_ONLY` / `ARCHIVE_CHECK_BLOCKED_NO_RUNTIME_DATA`).

Two threads touched the same repository, `Rudman101/syndicate_bettor`, and
partially crossed. This records what each established, and corrects three
overstatements made from this session.

## 1. R02 and NRFI are separate decisions

`bet_engine/nrfi_grader.py` is **identical** at `38c8e2ca` (the audited live
checkpoint) and `f42ef4b4` (the reviewed R02F development checkpoint) —
confirmed by equal Git blob SHA. R02 repairs five other graders:

| File | `38c8e2ca` vs `f42ef4b4` |
|---|---|
| `batter_total_bases_grader.py` | different |
| `mlb_pitcher_damage_grader.py` | different |
| `mlb_batter_discipline_grader.py` | different |
| `mlb_batter_event_grader.py` | different |
| `mlb_home_run_grader.py` | different |
| **`nrfi_grader.py`** | **identical** |

**Correction to the earlier framing from this session.** Saying R02's absence
was "not a reason to doubt" the recovered outcomes was too strong. The correct
statement is narrower:

> The R02 defects do not automatically invalidate the NRFI cohort. The NRFI
> cohort still requires its own evidence qualification.

The recovery derived results from same-event first-inning runs rather than
copying another recommendation's win/loss label. That makes the 423 recovered
outcomes **internally corroborated — not independently verified**, and R02
leaving `nrfi_grader.py` untouched does nothing to upgrade that label.

**Second correction.** "The repair is absent from `38c8e2ca`" is a fact about
file contents at a commit. It is **not** an observation of what is running
now. The audit established production was at that commit during its
September 14-16 window. Any current deployment claim needs a fresh host check.

## 2. Branch integration is already resolved — do not restart it

The earlier note from this session ended at "the branches diverge, a merge
check is needed." **That is outdated.** Per the release packets supplied in the
deployment thread:

| Checkpoint | Purpose | Reported status |
|---|---|---|
| `f42ef4b4` | Reviewed R02F development checkpoint | Published |
| `127a2401` | Seven R02 commits applied onto live base `38c8e2ca` | Zero conflicts; focused SQLite and disposable PostgreSQL validation completed |
| `b869dc5e` | R02 release plus default-off legacy-cleanup gate | Latest candidate; eight commits, 14 files; installation and rollback preflight completed |

**Deployment target:** `b869dc5ee95e9f9c616f0a32429be75629e5cc01`, branch
`release/r02-cleanup-hold-20260916`.

Do **not** merge the original divergent branch, rebuild the seven-commit
release, or deploy the older ungated candidate.

Two provenance notes, so this table is not mistaken for verification:

- These are the reported packet contents. Neither the reviewer nor this
  session independently retrieved those commits.
- **They are local-only.** `release/r02-cleanup-hold-20260916` is absent from
  `origin`, and neither `127a2401` nor `b869dc5e` is reachable from a clone.
  The candidate exists on the host alone.

No deployment-completion report exists in either thread. The release is
**prepared, not installed.**

The `DEPLOYMENT_NOT_AUTHORIZED` gate in `docs/R02_GRADER_EVIDENCE.md` scopes
that development checkpoint. It is neither a permanent prohibition nor blanket
permission; the host follows the latest explicit authorization and its
conditions. Note also that R02 does not reset old `no_action` rows — repairing
existing mis-settled rows remains a separate, unauthorized decision.

## 3. NRFI `no_action`: status-gated, but not thereby correct

**Third correction.** This session called the NRFI `no_action` write gated on
an "affirmative not-played status." The predicate is real, but that phrasing
is stronger than the code supports.

`_is_not_played_status()` matches `postponed`, `cancelled`, `canceled`, and
**`suspended`** — a suspended game is not the same disposition as a
postponement.

`_lookup_not_played()` checks the exact `event_id` first, but **when that
event's status does not qualify it does not stop.** It falls through to a scan
over all statuses, returning the **first** pair where both team names match and
the status qualifies — no uniqueness check, no requirement that the qualifying
game be the bet's game.

The narrow distinction still holds — a failed result lookup alone does not
become `no_action`, and with no match and no qualifying status the grader
records `no_match` and leaves `result` NULL. But a status predicate does not
establish that every resulting void carries the correct event identity or
settlement disposition.

## 4. NRFI-specific evidence limitations, recorded not measured

Both are source-level facts. **Neither is a claim of cohort impact**; that
needs row-level evidence.

**4.1 Fuzzy event fallback.** When `event_id` misses, `run_nrfi_grader` scans
completed games and matches on both away and home team names, taking the first
hit with no uniqueness check. Tighter than a single-name slate scan, but the
same family as the unresolved-event fallback R02 §2 deliberately left in place
and labelled "a compatibility fallback, not proof of event identity." It
applies to ordinary outcome matching **and** to the `no_action` path in §3.
Doubleheaders are the obvious stress case: one team pair, two `gamePk`s.

**4.2 Missing runs parse as zero.** In `_get_first_inning_runs`:

```python
away_r = first.get("away", {}).get("runs", 0) or 0
home_r = first.get("home", {}).get("runs", 0) or 0
total  = away_r + home_r
outcome = "NRFI" if total == 0 else "YRFI"
```

A missing or null `runs` field becomes `0`. An accepted response whose first
inning lacks run measurements therefore yields a **positive NRFI finding with
no zero-run evidence**. `NRFI` is the default outcome of absent data, which is
the direction that matters for a cohort of NRFI recommendations.

**4.3 One further item, found here and not previously recorded.** The same
function's completion filter is:

```python
completed_states = ("final", "completed", "game over", "delayed: ppd")
```

`"delayed: ppd"` is a postponement, not a completion. `if not innings:
continue` screens most such games, but a postponed game carrying a linescore
stub would pass the completion filter, and combined with 4.2 would produce
`total = 0` → `NRFI`. Ordering compounds it: `first_inn` is consulted **before**
`_lookup_not_played`, so a postponed game reaching this path is graded rather
than voided. Recorded as a source-level observation only.

## 5. Constraints carried forward

- Do not reopen the R02 grader implementation.
- Do not modify `nrfi_grader.py`, repair historical rows, or unlock any
  betting lane in order to record this handoff.
- Do not restart branch integration or substitute the older ungated candidate.
- NRFI STRONG_BET remains the leading reopening candidate on internally
  corroborated historical results; paid activation remains unapproved.
- Deployment correctness and a slice's betting evidence remain separate
  decisions, and neither confers the other.
