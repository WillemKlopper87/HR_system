import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { TeamDevelopmentRow } from '../api/types'

export function TeamDevelopmentPage() {
  const [rows, setRows] = useState<TeamDevelopmentRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .get<{ employees: TeamDevelopmentRow[] }>('/dashboards/learning/team-development/')
      .then((res) => setRows(res.employees))
      .catch(() => setError('Failed to load team development data.'))
  }, [])

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
    </div>
  )
}
