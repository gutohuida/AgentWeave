/**
 * Parse a timestamp the Hub sent, as the UTC instant it actually is.
 *
 * The Hub's datetime columns are `DateTime(timezone=True)`, but SQLite has no timezone storage, so
 * a value read back from the database used to come out of SQLAlchemy naive, and Pydantic serialised
 * it with no `Z` and no offset — `"2026-08-19T19:09:01.285899"`. `new Date()` reads a bare
 * date-time string as **local** time, so on any machine that is not on UTC every relative
 * timestamp in the app was wrong by that machine's offset. Measured against the trial Hub on
 * 2026-08-19 (UTC+1): an edit staged seconds earlier rendered as "about 1 hour ago".
 *
 * That bug is now fixed at the source: `hub/hub/db/models.py`'s `UTCDateTime` column type relabels
 * a naive result as UTC the moment it comes out of SQLite, so every timestamp this function ever
 * receives already carries `Z` or an explicit offset. This function is kept as a thin pass-through
 * rather than inlined at each call site, so the sweep test below still has one seam to lock — if a
 * future response ever reintroduces a bare timestamp, it surfaces here as a visibly wrong relative
 * time instead of being silently re-guessed and hidden again.
 *
 * **Every Hub timestamp the UI parses goes through here.** Two call sites deliberately do not, and
 * both say why at the line: `JobForm`'s stop-at field is wall-clock time the operator typed into a
 * `datetime-local` input, and `LogsView`'s `dataUpdatedAt` is React Query's own epoch milliseconds.
 * Neither is a timestamp the Hub serialised, so neither is this function's business.
 */
export function hubDate(value: string): Date {
  return new Date(value)
}
