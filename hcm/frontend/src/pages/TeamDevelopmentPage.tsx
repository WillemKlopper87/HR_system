import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useApiQuery } from '../api/hooks'
import type { OverdueTrainingRow, TeamDevelopmentRow } from '../api/types'

export function TeamDevelopmentPage() {
  const { data: rows, error } = useApiQuery(
    () => api.get<{ employees: TeamDevelopmentRow[] }>('/dashboards/learning/team-development/').then((res) => res.employees),
    [],
    { errorMessage: 'Failed to load team development data.' },
  )
  // C6: row-scoped exactly like the rollup above (own reporting chain, or
  // everyone for hr_admin) -- a manager's view of their team's mandatory-
  // training compliance, per the design spec's row-scoping decision.
  const { data: overdue, error: overdueError } = useApiQuery(
    () => api.get<{ overdue: OverdueTrainingRow[] }>('/dashboards/learning/training-compliance/overdue/').then((res) => res.overdue),
    [],
    { errorMessage: 'Failed to load overdue mandatory training.' },
  )

  return (
    <div className="page">
      <div className="page-header">
        <h1>Team Development</h1>
      </div>

      <p className="hint-text">Skills, certifications, and training in progress across your team.</p>

      {error && <p className="form-error">{error}</p>}

      {rows === null ? (
        <p className="empty-state">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="empty-state">No employees in scope.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Employee</th>
                <th>Skills</th>
                <th>Certifications</th>
                <th>Training in progress</th>
                <th>Training completed</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.employee}>
                  <td>
                    <Link to={`/employees/${r.employee}`}>{r.name}</Link>
                  </td>
                  <td>{r.skill_count}</td>
                  <td>{r.certification_count}</td>
                  <td>{r.active_training_count}</td>
                  <td>{r.completed_training_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2 style={{ marginTop: '2rem' }}>Overdue mandatory training</h2>
      <p className="hint-text">Scoped to your own reporting chain (org-wide for hr_admin).</p>

      {overdueError && <p className="form-error">{overdueError}</p>}

      {overdue === null ? (
        <p className="empty-state">Loading…</p>
      ) : overdue.length === 0 ? (
        <p className="empty-state">Nobody in scope is overdue on a mandatory course.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Employee</th>
                <th>Course</th>
                <th>Due date</th>
                <th>Days overdue</th>
              </tr>
            </thead>
            <tbody>
              {overdue.map((r) => (
                <tr key={`${r.employee}-${r.course}`}>
                  <td>
                    <Link to={`/employees/${r.employee}`}>{r.name}</Link>
                  </td>
                  <td>{r.course_name}</td>
                  <td>{r.due_date}</td>
                  <td>
                    <span className="restricted-badge">{r.days_overdue}</span>
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
