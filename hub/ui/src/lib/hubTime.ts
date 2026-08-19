/**
 * Parse a timestamp the Hub sent, as the UTC instant it actually is.
 *
 * The Hub's datetime columns are `DateTime(timezone=True)`, but SQLite has no timezone storage, so
 * a value read back from the database comes out of SQLAlchemy naive and Pydantic serialises it
 * with no `Z` and no offset — `"2026-08-19T19:09:01.285899"`. `new Date()` reads a bare date-time
 * string as **local** time, so on any machine that is not on UTC every relative timestamp in the
 * app is wrong by that machine's offset. Measured against the trial Hub on 2026-08-19 (UTC+1): an
 * edit staged seconds earlier rendered as "about 1 hour ago".
 *
 * The values are UTC — only the label is missing — so this supplies the label. A string that
 * already carries `Z` or an explicit offset is left exactly as it is, which is why this is safe to
 * apply to a field whose serialisation varies by route (the same `staged_at` comes back aware from
 * `PATCH /jobs/{job_id}`, because there it is still the in-memory aware object, and naive from
 * `GET /loops/{loop_id}`, because there it has been through SQLite).
 *
 * **Every Hub timestamp the UI parses goes through here.** Two call sites deliberately do not, and
 * both say why at the line: `JobForm`'s stop-at field is wall-clock time the operator typed into a
 * `datetime-local` input, and `LogsView`'s `dataUpdatedAt` is React Query's own epoch milliseconds.
 * Neither is a timestamp the Hub serialised, so neither is this function's business.
 *
 * This is the *consumer-side* fix. Correcting it at the Hub's serialisation boundary instead —
 * so a naive datetime never leaves the API — remains the better fix and is still open. The two
 * compose rather than conflict: this function leaves an already-labelled string untouched, so it
 * keeps working unchanged the day the server starts labelling them.
 */
export function hubDate(value: string): Date {
  return new Date(hasTimezone(value) ? value : `${value}Z`)
}

/** Trailing `Z`, or a `+hh:mm`/`-hh:mm` offset after the time part. A `-` inside the date is not
 *  an offset, so the search deliberately starts after `T`. */
function hasTimezone(value: string): boolean {
  if (value.endsWith('Z')) return true
  const time = value.indexOf('T')
  if (time === -1) return false
  const rest = value.slice(time)
  return rest.includes('+') || rest.lastIndexOf('-') > 0
}
