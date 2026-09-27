// The browser's locale, so dates read the way the operator is used to.
const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' })
const dateTimeFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

export const formatDate = (iso: string) => dateFormat.format(new Date(iso))

export const formatDateTime = (iso: string) => dateTimeFormat.format(new Date(iso))

const relativeFormat = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
const relativeUnits: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 365 * 86_400],
  ['month', 30 * 86_400],
  ['week', 7 * 86_400],
  ['day', 86_400],
  ['hour', 3_600],
  ['minute', 60],
]

// "3 hours ago", "yesterday": the largest unit `iso` is at least one whole
// step away in, truncated so 23 hours is not rounded up to "24 hours ago".
export function formatTimeAgo(iso: string, now: Date = new Date()): string {
  const seconds = (new Date(iso).getTime() - now.getTime()) / 1000
  for (const [unit, size] of relativeUnits) {
    if (Math.abs(seconds) >= size) return relativeFormat.format(Math.trunc(seconds / size), unit)
  }
  return relativeFormat.format(0, 'second')
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// Whole calendar days from `iso` to today, in the browser's timezone: captured
// yesterday at 23:50 is one day ago this morning, as the briefing counts it.
export function daysSince(iso: string, now: Date = new Date()): number {
  const then = new Date(iso)
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  return Math.max(0, Math.round((startOfDay(now) - startOfDay(then)) / 86_400_000))
}

// A date without a time ("2026-09-26", a birthday or a project's start), in
// the browser's locale. Parsed as local midnight: `new Date("2026-09-26")` is
// UTC midnight, which is the day before anywhere west of Greenwich.
export function formatDay(isoDate: string): string {
  const [y, m, d] = isoDate.slice(0, 10).split('-').map(Number)
  return dateFormat.format(new Date(y, m - 1, d))
}

// Tags as typed in a form: comma-separated, trimmed, blanks dropped.
export const splitTags = (text: string) =>
  text
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean)

// The calendar day a moment falls on here, as YYYY-MM-DD. A task's due date is
// a moment (23:59 local on the day), and its UTC date is the next day anywhere
// west of Greenwich.
export function localDay(iso: string): string {
  const d = new Date(iso)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// The moment a day's deadline falls on: 23:59 local, so a task stays "today"
// until midnight. As the API wants it, an ISO string in UTC.
export function endOfLocalDay(isoDate: string): string {
  const [y, m, d] = isoDate.split('-').map(Number)
  return new Date(y, m - 1, d, 23, 59).toISOString()
}

// A moment as the local "YYYY-MM-DDTHH:mm" a date-time field edits, and back.
export function toLocalDateTime(iso: string): string {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${localDay(iso)}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function fromLocalDateTime(local: string): string {
  const [day, time] = local.split('T')
  const [y, m, d] = day.split('-').map(Number)
  const [h, min] = time.split(':').map(Number)
  return new Date(y, m - 1, d, h, min).toISOString()
}
