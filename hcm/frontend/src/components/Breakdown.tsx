import type { BreakdownRow } from '../api/types'

/** Renders one "count of X by Y" card — used across the headcount,
 * recruitment, and skills-inventory dashboards. `labels` optionally maps
 * raw keys (e.g. a stage or status code) to a display label. */
export function Breakdown({
  title, rows, labels,
}: { title: string; rows: BreakdownRow[]; labels?: Record<string, string> }) {
  const maxCount = Math.max(1, ...rows.map((r) => (typeof r.count === 'number' ? r.count : 0)))
  return (
    <div className="breakdown-card">
      <h3>{title}</h3>
      <ul className="breakdown-list">
        {rows.map((row) => (
          <li key={row.key}>
            <span className="breakdown-label">{labels?.[row.key] ?? row.key}</span>
            <span className="breakdown-bar-track">
              <span
                className="breakdown-bar"
                style={{ width: `${typeof row.count === 'number' ? Math.max(4, (row.count / maxCount) * 100) : 6}%` }}
              />
            </span>
            <span className={row.suppressed ? 'breakdown-count suppressed' : 'breakdown-count'}>{row.count}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
