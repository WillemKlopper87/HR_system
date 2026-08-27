import { api } from '../api/client'
import { useApiQuery } from '../api/hooks'
import type { EquityDashboard, ManagementControlSchedule } from '../api/types'
import { DEMOGRAPHIC_COLUMNS, OCCUPATIONAL_LEVEL_LABELS } from '../ee-reporting/constants'
import { MatrixTable } from '../ee-reporting/MatrixTable'

export function EquityDashboardPage() {
  const { data: dashboard, error } = useApiQuery(() => api.get<EquityDashboard>('/dashboards/equity/'), [], { errorMessage: 'Failed to load the equity dashboard.' })
  const { data: managementControl } = useApiQuery(
    () => api.get<ManagementControlSchedule>('/dashboards/management-control/'), [],
    { errorMessage: 'Failed to load the management-control schedule.' },
  )

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

      {managementControl && (
        <section className="detail-card">
          <h2>B-BBEE management control</h2>
          <p className="hint-text">
            Black and black-female representation per level, benchmarked to the EAP the current EE plan was set
            against — the evidence schedule a verification agency scores against for the ICT Sector Code's
            Management Control element, not the score itself.
            {managementControl.small_cell_suppression_applied && ' Small cells (n < 5) are suppressed for your role.'}
          </p>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Level</th>
                  <th>Headcount</th>
                  <th>Black</th>
                  <th>Black %</th>
                  <th>EAP black %</th>
                  <th>Black female</th>
                  <th>Black female %</th>
                  <th>EAP black female %</th>
                  <th>With disabilities</th>
                  <th>Disability %</th>
                </tr>
              </thead>
              <tbody>
                {managementControl.by_level.map((row) => (
                  <tr key={row.level}>
                    <td>{OCCUPATIONAL_LEVEL_LABELS[row.level] ?? row.level}</td>
                    <td>{row.headcount}</td>
                    <td>{row.black}</td>
                    <td>{row.black_pct ?? '—'}</td>
                    <td>{row.eap_black_pct ?? '—'}</td>
                    <td>{row.black_female}</td>
                    <td>{row.black_female_pct ?? '—'}</td>
                    <td>{row.eap_black_female_pct ?? '—'}</td>
                    <td>{row.employees_with_disabilities}</td>
                    <td>{row.disability_pct ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {managementControl.disability_target_pct && (
            <p className="hint-text">Disability target: {managementControl.disability_target_pct}%.</p>
          )}
        </section>
      )}
    </div>
  )
}
