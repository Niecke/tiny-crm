// The browser's locale, so dates read the way the operator is used to.
const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' })
const dateTimeFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

export const formatDate = (iso: string) => dateFormat.format(new Date(iso))

export const formatDateTime = (iso: string) => dateTimeFormat.format(new Date(iso))

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
