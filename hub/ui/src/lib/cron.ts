/**
 * Cron expressions, said in English — and the times they will actually fire.
 *
 * The operator writes `0 9 * * 1-5` into a text field and commits it with nothing between the
 * typing and the schedule: no translation, no preview. Every cron UI worth copying puts both under
 * the field, because a schedule is the one setting whose mistake is invisible until it fires at the
 * wrong hour a week later.
 *
 * **`describeCron` returns `null` rather than a plausible sentence.** A confident wrong translation
 * of a schedule is worse than no translation at all: the operator reads it, believes it, and stops
 * checking. So every shape this module cannot state exactly — an unenumerable set of fire times, a
 * day expression whose meaning depends on which cron implementation reads it, a non-standard
 * extension (`L`, `W`, `#`, `?`) — is declined, and the caller renders nothing.
 *
 * No dependency: the expression grammar the Hub accepts is five standard fields
 * (`hub/scheduler.py` rejects anything that is not exactly five), which is a small enough target
 * that a parser is cheaper than a package.
 */

/** Full month names, indexed by `month - 1`. */
const MONTH_LABELS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
] as const

/** Full weekday names, indexed by `Date#getUTCDay()`. */
const DAY_LABELS = [
  'Sunday',
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
] as const

/** The three-letter aliases crontab accepts in the month field. */
const MONTH_ALIASES: Record<string, number> = {
  jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6,
  jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12,
}

/** The three-letter aliases crontab accepts in the day-of-week field. */
const DAY_ALIASES: Record<string, number> = {
  sun: 0, mon: 1, tue: 2, wed: 3, thu: 4, fri: 5, sat: 6,
}

/**
 * How many items a list may carry before the sentence stops being readable and the module declines.
 * Months and days-of-month draw from ranges wide enough (12 and 31) that a long list is both
 * unreadable and a sign the expression means something a list is the wrong shape for.
 */
const MAX_LIST = 4

/** The same ceiling for clock times: past four, "at …" is a paragraph, not a translation. */
const MAX_TIMES = 4

/**
 * Weekday names are short enough to list further than `MAX_LIST` before the sentence suffers, and
 * all seven is `*` by definition, so only six can ever need listing.
 */
const MAX_WEEKDAYS = 6

/**
 * How far `nextRuns` will look. An annual schedule (`0 0 1 1 *`) needs a year of lookahead from the
 * worst-case start; past that the expression is either unsatisfiable or so rare that returning
 * fewer entries is the better answer.
 */
const MAX_DAYS_SCANNED = 400

const MS_PER_DAY = 86_400_000

/** One parsed cron field: every value it matches, and whether that is its whole range. */
interface Field {
  /** True when the field matches its entire range — `*`, or a list/range that happens to cover it. */
  all: boolean
  /** Every matching value, ascending and deduplicated. Populated even when `all`. */
  values: number[]
}

interface ParsedCron {
  minute: Field
  hour: Field
  dayOfMonth: Field
  month: Field
  dayOfWeek: Field
}

function parseValue(
  raw: string,
  min: number,
  max: number,
  aliases?: Record<string, number>,
): number | null {
  const alias = aliases?.[raw.toLowerCase()]
  const value = alias !== undefined ? alias : /^\d+$/.test(raw) ? Number(raw) : null
  if (value === null || value < min || value > max) return null
  return value
}

function parseField(
  raw: string,
  min: number,
  max: number,
  aliases?: Record<string, number>,
): Field | null {
  // Anything outside this character class is a non-standard extension — `L`, `W`, `#`, `?`, `~` all
  // survive the class, so they are caught below by failing to parse as a value instead.
  if (!raw || !/^[0-9A-Za-z*/,-]+$/.test(raw)) return null

  const values = new Set<number>()
  for (const part of raw.split(',')) {
    const segments = part.split('/')
    if (segments.length > 2) return null
    const [spec, stepRaw] = segments

    let step = 1
    if (stepRaw !== undefined) {
      if (!/^\d+$/.test(stepRaw)) return null
      step = Number(stepRaw)
      if (step < 1) return null
    }

    let from: number
    let to: number
    if (spec === '*') {
      from = min
      to = max
    } else {
      const bounds = spec.split('-')
      if (bounds.length > 2) return null
      const lo = parseValue(bounds[0], min, max, aliases)
      if (lo === null) return null
      if (bounds.length === 1) {
        from = lo
        // `5/15` means "from 5 to the end of the range, every 15" — the reading both crontab and
        // APScheduler give it. A bare `5` with no step is just the one value.
        to = stepRaw === undefined ? lo : max
      } else {
        const hi = parseValue(bounds[1], min, max, aliases)
        // A wrapping range (`22-2`) is read differently by different implementations, so it is
        // declined here rather than guessed at.
        if (hi === null || hi < lo) return null
        from = lo
        to = hi
      }
    }

    for (let v = from; v <= to; v += step) values.add(v)
  }

  if (values.size === 0) return null
  const sorted = Array.from(values).sort((a, b) => a - b)
  return { all: sorted.length === max - min + 1, values: sorted }
}

/**
 * Day-of-week accepts both 0 and 7 for Sunday, so it cannot use `parseField`'s range-width test for
 * `all` — eight accepted values collapse to seven distinct days.
 */
function parseDayOfWeek(raw: string): Field | null {
  const field = parseField(raw, 0, 7, DAY_ALIASES)
  if (!field) return null
  const values = Array.from(new Set(field.values.map((v) => (v === 7 ? 0 : v)))).sort((a, b) => a - b)
  return { all: values.length === 7, values }
}

/** Split and parse a five-field expression. Anything else — macros, six fields — is not our grammar. */
function parseCron(expr: string): ParsedCron | null {
  const fields = expr.trim().split(/\s+/)
  if (fields.length !== 5) return null

  const minute = parseField(fields[0], 0, 59)
  const hour = parseField(fields[1], 0, 23)
  const dayOfMonth = parseField(fields[2], 1, 31)
  const month = parseField(fields[3], 1, 12, MONTH_ALIASES)
  const dayOfWeek = parseDayOfWeek(fields[4])
  if (!minute || !hour || !dayOfMonth || !month || !dayOfWeek) return null

  return { minute, hour, dayOfMonth, month, dayOfWeek }
}

/**
 * A restricted day-of-month *and* a restricted day-of-week is the one expression this product
 * genuinely cannot translate: Vixie cron ORs the two, APScheduler ANDs them — and both readings are
 * live in this repository at once. `hub/scheduler.py` builds an APScheduler `CronTrigger` (AND) to
 * fire the job, then computes `next_run` a few lines later with `croniter` (OR). Until those agree,
 * neither sentence nor preview can be honest, so both decline.
 */
function isAmbiguousDayPair(parsed: ParsedCron): boolean {
  return !parsed.dayOfMonth.all && !parsed.dayOfWeek.all
}

function pad(n: number): string {
  return n < 10 ? `0${n}` : String(n)
}

function clock(hour: number, minute: number): string {
  const meridiem = hour < 12 ? 'AM' : 'PM'
  const twelve = hour % 12 === 0 ? 12 : hour % 12
  return `${twelve}:${pad(minute)} ${meridiem}`
}

function ordinal(n: number): string {
  const suffix =
    n % 100 >= 11 && n % 100 <= 13
      ? 'th'
      : n % 10 === 1
      ? 'st'
      : n % 10 === 2
      ? 'nd'
      : n % 10 === 3
      ? 'rd'
      : 'th'
  return `${n}${suffix}`
}

function joinList(items: string[]): string {
  if (items.length <= 1) return items[0] ?? ''
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** The constant gap between consecutive values, or null when they are not evenly spaced. */
function commonStride(values: number[]): number | null {
  if (values.length < 2) return null
  const stride = values[1] - values[0]
  for (let i = 2; i < values.length; i++) {
    if (values[i] - values[i - 1] !== stride) return null
  }
  return stride
}

/**
 * The stride of a field that steps across its *whole* range starting at zero — a bare `*` carrying
 * a step of 6 in the hour field, or 15 in the minute field. Distinguished from any other evenly
 * spaced set because only this one can be said as a bare frequency ("Every 6 hours") without also
 * naming the window it runs inside.
 */
function fullRangeStride(field: Field, size: number): number | null {
  const stride = commonStride(field.values)
  if (stride === null || stride < 2) return null
  if (field.values[0] !== 0) return null
  if (field.values.length !== Math.ceil(size / stride)) return null
  return stride
}

/**
 * A time-of-day phrase, in one of two shapes the composer treats differently: `clock` names
 * instants and reads as "<days> at <times>", `freq` names a rate and reads as "<rate> <days>".
 */
type TimePhrase = { kind: 'clock'; text: string } | { kind: 'freq'; text: string }

function describeTime(minute: Field, hour: Field): TimePhrase | null {
  if (minute.all) {
    if (hour.all) return { kind: 'freq', text: 'Every minute' }
    // Every minute of a *scattered* set of hours has no short honest phrasing; a single hour or a
    // contiguous block does, because it is a window rather than a list of instants.
    if (hour.values.length > 1 && commonStride(hour.values) !== 1) return null
    const first = hour.values[0]
    const last = hour.values[hour.values.length - 1]
    return { kind: 'freq', text: `Every minute from ${clock(first, 0)} to ${clock(last, 59)}` }
  }

  if (minute.values.length === 1) {
    const m = minute.values[0]
    // Only a non-zero minute needs saying; ":00" is what a bare hour already implies.
    const at = m === 0 ? '' : ` at :${pad(m)}`

    if (hour.all) return { kind: 'freq', text: `Every hour${at}` }

    const dayStride = fullRangeStride(hour, 24)
    if (dayStride !== null) return { kind: 'freq', text: `Every ${dayStride} hours${at}` }

    if (hour.values.length <= MAX_TIMES) {
      return { kind: 'clock', text: joinList(hour.values.map((h) => clock(h, m))) }
    }

    const stride = commonStride(hour.values)
    if (stride === null) return null
    const rate = stride === 1 ? 'Hourly' : `Every ${stride} hours`
    const first = hour.values[0]
    const last = hour.values[hour.values.length - 1]
    // No `at` suffix here: the window's own endpoints already carry the minute.
    return { kind: 'freq', text: `${rate} from ${clock(first, m)} to ${clock(last, m)}` }
  }

  if (hour.all) {
    const stride = fullRangeStride(minute, 60)
    if (stride !== null) return { kind: 'freq', text: `Every ${stride} minutes` }
    if (minute.values.length <= MAX_TIMES) {
      return {
        kind: 'freq',
        text: `Every hour at ${joinList(minute.values.map((m) => `:${pad(m)}`))}`,
      }
    }
    return null
  }

  // Few enough instants to name them, which is always clearer than a rate — tried before the
  // window phrasing below, so `0,30 9 * * *` reads as two times rather than a half-hourly window
  // that happens to be one hour wide.
  const times: string[] = []
  for (const h of hour.values) {
    for (const m of minute.values) times.push(clock(h, m))
  }
  if (times.length <= MAX_TIMES) return { kind: 'clock', text: joinList(times) }

  // Otherwise: minutes stepping through every hour of a contiguous window — the common "every 5
  // minutes during business hours" shape, whose cross product is dozens of instants.
  const minuteStride = fullRangeStride(minute, 60)
  if (minuteStride !== null && (hour.values.length === 1 || commonStride(hour.values) === 1)) {
    const first = hour.values[0]
    const last = hour.values[hour.values.length - 1]
    return {
      kind: 'freq',
      text: `Every ${minuteStride} minutes from ${clock(first, 0)} to ${clock(last, 59)}`,
    }
  }

  return null
}

/**
 * The day part, in both grammatical positions it has to occupy: `subject` leads a clock sentence
 * ("Weekdays at 9:00 AM") and `qualifier` trails a frequency one ("Every 5 minutes on weekdays").
 * An empty `qualifier` means "no restriction worth saying".
 */
interface DayPhrase {
  subject: string
  qualifier: string
}

function weekdayPhrase(dayOfWeek: Field): string | null {
  const values = dayOfWeek.values
  const same = (other: number[]) =>
    values.length === other.length && values.every((v, i) => v === other[i])

  if (same([1, 2, 3, 4, 5])) return 'weekdays'
  if (same([0, 6])) return 'weekends'
  if (values.length > MAX_WEEKDAYS) return null
  return joinList(values.map((v) => `${DAY_LABELS[v]}s`))
}

function describeDays(dayOfMonth: Field, month: Field, dayOfWeek: Field): DayPhrase | null {
  let monthText: string | null = null
  if (!month.all) {
    if (month.values.length > MAX_LIST) return null
    monthText = joinList(month.values.map((m) => MONTH_LABELS[m - 1]))
  }
  const inMonths = monthText ? ` in ${monthText}` : ''

  // Day-of-month is guaranteed unrestricted here whenever day-of-week is not — the ambiguous pair
  // is refused before this runs.
  if (!dayOfWeek.all) {
    const days = weekdayPhrase(dayOfWeek)
    if (!days) return null
    return { subject: capitalize(days) + inMonths, qualifier: `on ${days}${inMonths}` }
  }

  if (!dayOfMonth.all) {
    if (dayOfMonth.values.length > MAX_LIST) return null
    const days = joinList(dayOfMonth.values.map(ordinal))
    const scope = monthText ?? 'every month'
    return { subject: `The ${days} of ${scope}`, qualifier: `on the ${days} of ${scope}` }
  }

  if (monthText) return { subject: `Every day in ${monthText}`, qualifier: `in ${monthText}` }

  return { subject: 'Daily', qualifier: '' }
}

/**
 * A standard five-field cron expression as a sentence, or `null` when it cannot be said exactly.
 *
 * `null` is a real answer, not a failure to try — see the module comment. Callers render nothing
 * rather than falling back to the raw string a second time.
 */
export function describeCron(expr: string): string | null {
  const parsed = parseCron(expr)
  if (!parsed || isAmbiguousDayPair(parsed)) return null

  const time = describeTime(parsed.minute, parsed.hour)
  if (!time) return null
  const days = describeDays(parsed.dayOfMonth, parsed.month, parsed.dayOfWeek)
  if (!days) return null

  if (time.kind === 'clock') return `${days.subject} at ${time.text}`
  return days.qualifier ? `${time.text} ${days.qualifier}` : time.text
}

function matchesDay(date: Date, parsed: ParsedCron): boolean {
  if (!parsed.month.all && !parsed.month.values.includes(date.getUTCMonth() + 1)) return false
  if (!parsed.dayOfMonth.all && !parsed.dayOfMonth.values.includes(date.getUTCDate())) return false
  if (!parsed.dayOfWeek.all && !parsed.dayOfWeek.values.includes(date.getUTCDay())) return false
  return true
}

/**
 * The next `count` instants an expression fires, strictly after `from`.
 *
 * Computed in **UTC**, because that is the frame the schedule is actually read in: `hub/scheduler.py`
 * pins its `CronTrigger` to `timezone="UTC"`, so `0 9 * * 1-5` means 09:00 UTC regardless of where
 * the Hub or the browser sits. Format the results with `formatNextRun`, which stays in the same
 * frame — reading these back with local getters would restate the hour the operator just typed as
 * some other hour.
 *
 * Days are walked rather than minutes: the hour and minute sets are already enumerated, so a day
 * that matches yields its fire times directly instead of being probed 1,440 times. The scan stops
 * at `MAX_DAYS_SCANNED` and returns what it has — this runs on every keystroke in the cron field.
 */
export function nextRuns(expr: string, from: Date, count: number): Date[] {
  const parsed = parseCron(expr)
  if (!parsed || isAmbiguousDayPair(parsed) || count <= 0) return []

  const runs: Date[] = []
  const startOfDay = Date.UTC(from.getUTCFullYear(), from.getUTCMonth(), from.getUTCDate())
  const after = from.getTime()

  for (let day = 0; day < MAX_DAYS_SCANNED && runs.length < count; day++) {
    // Adding whole days in UTC milliseconds is exact — UTC has no offset transitions to fall into.
    const date = new Date(startOfDay + day * MS_PER_DAY)
    if (!matchesDay(date, parsed)) continue

    for (const hour of parsed.hour.values) {
      for (const minute of parsed.minute.values) {
        const at = Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate(), hour, minute)
        if (at <= after) continue
        runs.push(new Date(at))
        if (runs.length >= count) return runs
      }
    }
  }

  return runs
}

/**
 * One entry of the next-run preview, relative to the same `from` the runs were computed against.
 *
 * Lives beside `nextRuns` rather than in the form because it has to read the same UTC frame — see
 * that function's note. "today"/"tomorrow" are therefore UTC days, which is the day boundary the
 * schedule itself turns on.
 */
export function formatNextRun(date: Date, from: Date): string {
  const days = Math.round(
    (Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()) -
      Date.UTC(from.getUTCFullYear(), from.getUTCMonth(), from.getUTCDate())) /
      MS_PER_DAY,
  )
  const time = clock(date.getUTCHours(), date.getUTCMinutes())

  if (days === 0) return `today ${time}`
  if (days === 1) return `tomorrow ${time}`
  // Inside a week a weekday name locates it; past that it stops being unambiguous and needs a date.
  if (days < 7) return `${DAY_LABELS[date.getUTCDay()].slice(0, 3)} ${time}`
  return `${MONTH_LABELS[date.getUTCMonth()].slice(0, 3)} ${date.getUTCDate()} ${time}`
}
