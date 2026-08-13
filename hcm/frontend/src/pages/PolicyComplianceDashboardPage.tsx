import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { POLICY_CATEGORY_LABELS, type PolicyAcknowledgmentDashboard } from '../api/types'

export function PolicyComplianceDashboardPage() {
  const [dashboard, setDashboard] = useState<PolicyAcknowledgmentDashboard | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .get<PolicyAcknowledgmentDashboard>('/dashboards/policy-acknowledgment/')
      .then(setDashboard)
      .catch(() => setError('Failed to load the policy acknowledgment dashboard.'))
  }, [])

  if (error) return <p className="form-error">{error}</p>
  if (!dashboard) return <p className="empty-state">Loading…</p>

  return (
    <div className="page">
      <div className="page-header">
        <h1>Policy Acknowledgment Compliance</h1>
      </div>
      <p className="hint-text">
        Acknowledgment completion for each currently published policy, as of {dashboard.as_of}. Percentages are
        against every employee with a current employment version (active workforce).
      </p>

      {dashboard.policies.length === 0 ? (
        <p className="empty-state">No published policies yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Policy</th>
                <th>Category</th>
                <th>Version</th>
                <th>Acknowledged</th>
                <th>Completion</th>
              </tr>
            </thead>
            <tbody>
              {dashboard.policies.map((row) => (
                <tr key={row.policy_id}>
                  <td>{row.title}</td>
                  <td>{POLICY_CATEGORY_LABELS[row.category]}</td>
                  <td>v{row.version}</td>
                  <td>{row.acknowledged_count} / {row.total_employees}</td>
                  <td>
                    <span className="status-badge">{row.acknowledged_pct}%</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
