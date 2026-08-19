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
 * Scoped to `LoopTab` for now. The same fault affects every other surface that calls
 * `formatDistanceToNow` on a Hub timestamp — see the handoff; fixing it at the serialisation
 * boundary instead is the operator's call, and is the better fix.
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
