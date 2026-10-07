import { formatWeek, type WeekCount, weeklySummary } from '../metrics'

// New deals per week, the last twelve calendar weeks (GET /metrics/dashboard,
// `trends`). One series, so one hue and no legend; the running week is drawn
// lighter because its count is so far, not final. Counts show on hover and
// focus, and a table carries every value for a screen reader.
export function WeeklyDeals({ weeks }: { weeks: WeekCount[] }) {
  const { current, previous, average } = weeklySummary(weeks)
  const most = Math.max(1, ...weeks.map((w) => w.count))

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
          <dt>Average</dt>
          <dd>
            {average ?? '–'} <span className="muted">/ week</span>
          </dd>
        </div>
      </dl>

      <div className="weekly-chart" aria-hidden="true">
        {average != null && average > 0 && (
          <span className="weekly-average" style={{ bottom: `${(average / most) * 100}%` }} />
        )}
        {weeks.map((w) => (
          <span
            key={w.start}
            className="weekly-column"
            data-partial={!w.complete || undefined}
            title={`Week of ${formatWeek(w.start)}: ${w.count} ${w.count === 1 ? 'deal' : 'deals'}${w.complete ? '' : ' so far'}`}
          >
            {w.count > 0 && <span className="weekly-bar" style={{ height: `${(w.count / most) * 100}%` }} />}
          </span>
        ))}
      </div>
      {weeks.length > 0 && (
        <div className="weekly-axis" aria-hidden="true">
          <span>{formatWeek(weeks[0].start)}</span>
          <span>this week</span>
        </div>
      )}

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
