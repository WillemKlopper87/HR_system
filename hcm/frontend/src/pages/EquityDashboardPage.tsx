import { api } from '../api/client'
import { useApiQuery } from '../api/hooks'
import type { EquityDashboard } from '../api/types'
import { DEMOGRAPHIC_COLUMNS } from '../ee-reporting/constants'
import { MatrixTable } from '../ee-reporting/MatrixTable'

export function EquityDashboardPage() {
  const { data: dashboard, error } = useApiQuery(() => api.get<EquityDashboard>('/dashboards/equity/'), [], { errorMessage: 'Failed to load the equity dashboard.' })

  if (error) return <p className="form-error">{error}</p>
  if (!dashboard) return <p className="empty-state">Loading…</p>

  const hasTargetGap = Object.keys(dashboard.target_vs_actual_gap_pct).length > 0

  return (
    <div className="page">
      <div className="page-header">
        <h1>Equity Dashboard</h1>
      </div>
      <p className="hint-text">
        Extends the Headcount dashboard with the same level x population-group x gender matrix EEA2 Section B uses —
        live, not a frozen report snapshot. As of {dashboard.as_of}.
        {dashboard.small_cell_suppression_applied && ' Small cells (n < 5) are suppressed for your role.'}
      </p>

      <section className="detail-card">
        <h2>Workforce profile</h2>
        <MatrixTable matrix={dashboard.workforce_profile} columns={DEMOGRAPHIC_COLUMNS} />
      </section>

      <section className="detail-card">
        <h2>Employees with disabilities</h2>
        <MatrixTable matrix={dashboard.disability_workforce} columns={DEMOGRAPHIC_COLUMNS} />
      </section>

      <section className="detail-card">
        <h2>Target vs. actual (percentage-point gap)</h2>
        {hasTargetGap ? (
          <MatrixTable matrix={dashboard.target_vs_actual_gap_pct} columns={DEMOGRAPHIC_COLUMNS} />
        ) : (
          <p className="empty-state">No current EE Plan with annual targets set for this period yet.</p>
        )}
      </section>
    </div>
  )
}
