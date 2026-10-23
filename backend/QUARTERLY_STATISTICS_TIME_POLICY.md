# Quarterly statistics time policy

This policy is the basis for future statistics calculations. It does not add
quarterly aggregations or API behavior.

## Instants and storage

- Application instants are created in UTC and exchanged as ISO 8601 timestamps
  with an explicit UTC offset (`Z` on JSON responses where applicable).
- Database `DATETIME` values do not carry a timezone. A row may be interpreted
  as UTC only when its provenance says it was written as UTC. For completion
  rows, `completed_at_is_utc` provides that distinction. Legacy rows with this
  flag false have an unknown timezone and must not be silently assigned to a
  local quarter or week.
- `WorkItemCompletionCoverage.tracking_started_at` is always written from a
  UTC instant by either the creation route or the migration. When MySQL or
  SQLite returns it without timezone metadata, interpret it as UTC based on
  this field's write contract.
- `tracking_state_at` is the explicit state and assignee snapshot boundary for
  replaying subsequent assignment/status events. For pre-existing tasks, the
  cycle start is not inferred; a non-final status at the snapshot can indicate
  an open cycle while `tracking_open_cycle_started_at` remains unknown.
- Legacy assignment-history diagnostics are independent of completion snapshot
  quality. `legacy_assignment_history_partial` covers the interval before the
  tracking snapshot; the assignment sequence flags describe events captured
  since that snapshot. A known unassigned snapshot has a NULL assignee ID and
  `tracking_state_assignee_known = true`.
- For migrated work items, `tracking_state_at` is a new cutover snapshot and
  does not rewrite the earlier completion-history `tracking_started_at` or
  assignment baseline. The interval before the new snapshot remains legacy and
  may be partial.
- The database's current `DATETIME` columns have no explicit fractional-second
  precision. Consumers must not assume that sub-second precision survives a
  round trip.

## Calendar and periods

- The reporting calendar is `Europe/Madrid`.
- Convert a known UTC instant to `Europe/Madrid` before deriving its date,
  natural quarter, or week.
- Quarters use local calendar dates and half-open boundaries: Q1 Jan 1 to Apr 1,
  Q2 Apr 1 to Jul 1, Q3 Jul 1 to Oct 1, and Q4 Oct 1 to Jan 1 of the next year.
- Weeks follow ISO calendar weeks (Monday through Sunday), also after timezone
  conversion. A week crossing a quarter boundary contributes only its dates
  inside the selected quarter.
- Use timezone-aware boundaries from Python's standard-library `zoneinfo`;
  never model a local quarter boundary as a fixed UTC offset. This preserves
  Europe/Madrid daylight-saving transitions.

## Due dates and punctuality

- `due_date` is a local calendar date, not an instant; do not timezone-convert
  it.
- Compare the Europe/Madrid local calendar date of a known completion instant
  with the known `due_date_at_completion` snapshot.
- Include a completion in the punctuality denominator only when its completion
  instant is known to be UTC and its due-date snapshot is known and non-null.
  A known `NULL` due date and an unknown due date are both not comparable, but
  remain distinguishable in storage through `due_date_known`.
- Do not substitute `WorkItem.created_at` or the current `WorkItem.due_date` for
  a missing completion timestamp or historical due-date snapshot.

The future statistics implementation should test quarter/year boundaries,
Europe/Madrid DST changes, local week assignment, and due-date comparisons
before exposing aggregated results.

## Quarterly statistics service semantics

- The service uses only currently accessible, active projects and non-deleted
  `type = 'task'` rows. Organization projects require both project membership
  and current organization membership. A missing per-task coverage row makes
  state and completion reconstruction unavailable for that task.
- A reliable completion count consists only of completion snapshots whose
  `completed_at_is_utc` flag is true and whose unique source history row
  confirms a transition from a non-final state to `resolved`/`closed`, or a
  task initialized directly in a final state. `resolved -> closed` does not
  qualify as another completion.
- The exact total load at a reporting cut is confirmed completions in the
  quarter plus reconstructed cycles still pending at that cut. It is returned
  as unavailable when either dimension is incomplete. A current quarter is
  cut at the current instant and marked `period_complete = false`; it does not
  predict tasks or cycles that may be created later in that quarter.
- For an active cycle at quarter start, its opening date is not required to
  count it as carried-in. Cycles opened during the quarter are counted from
  known creation baselines or unambiguous post-snapshot reopen transitions.
  The split is unavailable if the period start predates a task's known cut or
  if the required cycle history is ambiguous.
- Punctuality numerator is the number of comparable completions whose local
  Europe/Madrid completion date is on or before the snapshotted due date.
  Denominator is the comparable completion count (UTC-confirmed completion
  and known, non-NULL due date). The percentage is `100 * numerator /
  denominator`; it is `null` when the denominator is zero or completion
  coverage is partial.
- The weekly straight-line reference is `period_load * elapsed_local_calendar
  days / quarter_calendar_days`. Separately, the required pace at a weekly cut
  is `pending_at_cut / remaining seven-day equivalents`; it is recalculated at
  each cut and is null if the cut's pending load is unavailable. These are
  derived references, not historical goals stored by the product. Future
  weekly points in an in-progress quarter are marked unavailable rather than
  filled with zero activity.
- A partial coverage indicator means the service can expose confirmed
  observations but cannot claim the metric is complete. Counts whose complete
  population cannot be established are returned as `null`, not as zero.
- If no currently accessible, non-deleted task existed by the exclusive end of
  the selected period, that period has a demonstrably empty task population and
  its counts and coverage are reliable zeros. Tasks created after the period do
  not make that earlier period incomplete. Conversely, an eligible task with
  missing or incomplete history prevents affected counts from being reported as
  exact zeros.
- The carried-in/new-cycle split requires a reconstructible state at the
  quarter start. If a migrated task's tracking snapshot falls inside the
  quarter and its earlier cycle state cannot be reconstructed, both load split
  values remain `null`; a known completion and known closing state may still be
  reported independently.
- Assignment cuts use `WorkItemAssignmentBaseline` only from its recorded
  baseline time forward. If a requested interval crosses the later tracking
  state cut, the replay must meet that snapshot and the migration's ambiguity
  and inconsistency diagnostics; otherwise assignment attribution is partial.
