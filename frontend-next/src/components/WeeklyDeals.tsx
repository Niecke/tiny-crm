import { formatWeek, type WeekCount, weeklySummary } from '../metrics'

// New deals per week, the last ten calendar weeks (GET /metrics/dashboard,
// `trends`). One series, so one hue and no legend. Every column carries its
// count and its week, so nothing needs a hover to be read; the running week
// is drawn lighter because its count is so far, not final. A table carries
// the same values for a screen reader.
export function WeeklyDeals({ weeks }: { weeks: WeekCount[] }) {
  const { current, previous, average } = weeklySummary(weeks)
  const most = Math.max(1, ...weeks.map((w) => w.count))
  const height = (count: number) => `${(count / most) * 100}%`

  return (
    <div className="weekly">
      <dl className="weekly-figures">
        <div>
          <dt>This week</dt>
          <dd>
            {current?.count ?? 0} <span className="muted">so far</span>
          </dd>
        </div>
        <div>
          <dt>Last week</dt>
          <dd>{previous?.count ?? 0}</dd>
        </div>
        <div>
          <dt title="Over the complete weeks; the running one is left out">Weekly average</dt>
          <dd>
            {average ?? '–'} <span className="muted">/ week</span>
          </dd>
        </div>
      </dl>

      <div className="weekly-plot" aria-hidden="true">
        <div className="weekly-chart">
          {average != null && average > 0 && <span className="weekly-average" style={{ bottom: height(average) }} />}
          {weeks.map((w) => (
            <span key={w.start} className="weekly-column" data-partial={!w.complete || undefined}>
              {w.count > 0 && <span className="weekly-bar" style={{ height: height(w.count) }} />}
              <span className="weekly-count" style={{ bottom: height(w.count) }}>
                {w.count}
              </span>
            </span>
          ))}
        </div>
        <div className="weekly-dates">
          {weeks.map((w) => (
            <span key={w.start}>{w.complete ? formatWeek(w.start) : 'This week'}</span>
          ))}
        </div>
      </div>

      <table className="sr-only">
        <caption>New deals per week</caption>
        <thead>
          <tr>
            <th scope="col">Week of</th>
            <th scope="col">Deals</th>
          </tr>
        </thead>
        <tbody>
          {weeks.map((w) => (
            <tr key={w.start}>
              <td>{formatWeek(w.start)}</td>
              <td>
                {w.count}
                {!w.complete && ' so far'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
