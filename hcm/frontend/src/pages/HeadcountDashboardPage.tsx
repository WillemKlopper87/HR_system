import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { HeadcountBreakdownRow, HeadcountDashboard } from '../api/types'

function Breakdown({ title, rows }: { title: string; rows: HeadcountBreakdownRow[] }) {
  const maxCount = Math.max(1, ...rows.map((r) => (typeof r.count === 'number' ? r.count : 0)))
  return (
    <div className="breakdown-card">
      <h3>{title}</h3>
      <ul className="breakdown-list">
        {rows.map((row) => (
          <li key={row.key}>
            <span className="breakdown-label">{row.key}</span>
            <span className="breakdown-bar-track">
              <span
                className="breakdown-bar"
                style={{ width: `${typeof row.count === 'number' ? Math.max(4, (row.count / maxCount) * 100) : 6}%` }}
              />
            </span>
            <span className={row.suppressed ? 'breakdown-count suppressed' : 'breakdown-count'}>
              {row.count}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function HeadcountDashboardPage() {
  const [data, setData] = useState<HeadcountDashboard | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .get<HeadcountDashboard>('/dashboards/headcount/')
      .then(setData)
      .catch(() => setError('Failed to load the headcount dashboard.'))
  }, [])

  return (
    <div className="page">
      <div className="page-header">
        <h1>Headcount Dashboard</h1>
      </div>

      {error && <p className="form-error">{error}</p>}

      {data && (
        <>
          <div className="stat-row">
            <div className="stat-tile">
              <span className="stat-value">{data.total_headcount}</span>
              <span className="stat-label">Total headcount</span>
            </div>
            {data.small_cell_suppression_applied && (
              <p className="hint-text suppression-note">
                Demographic breakdowns below suppress any cell under 5 employees (shown as "&lt;5") — your role
                doesn't have organisation-wide sensitive-data access.
              </p>
            )}
          </div>

          <div className="breakdown-grid">
            <Breakdown title="By department" rows={data.by_department} />
            <Breakdown title="By occupational level" rows={data.by_occupational_level} />
            <Breakdown title="By job grade" rows={data.by_job_grade} />
            <Breakdown title="By race" rows={data.by_race} />
            <Breakdown title="By gender" rows={data.by_gender} />
            <Breakdown title="By disability status" rows={data.by_disability_status} />
          </div>
        </>
      )}
    </div>
  )
}
