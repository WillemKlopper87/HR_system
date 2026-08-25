import { api } from '../api/client'
import { useApiQuery } from '../api/hooks'
import type { TrainingComplianceCourseRow } from '../api/types'

export function TrainingCompliancePage() {
  const { data: response, error } = useApiQuery(
    () => api.get<{ as_of: string; courses: TrainingComplianceCourseRow[] }>(
      '/dashboards/learning/training-compliance/',
    ),
    [],
    { errorMessage: 'Failed to load training compliance data.' },
  )
  const courses = response?.courses ?? null

  return (
    <div className="page">
      <div className="page-header">
        <h1>Training Compliance</h1>
      </div>
      <p className="hint-text">
        Completion rate by mandatory course, org-wide and by department/occupational level, as of{' '}
        {response?.as_of ?? '…'}. Individual overdue lists are scoped to your own reporting chain — see Team
        Development.
      </p>

      {error && <p className="form-error">{error}</p>}

      {courses === null ? (
        <p className="empty-state">Loading…</p>
      ) : courses.length === 0 ? (
        <p className="empty-state">No mandatory-course requirements are in effect yet.</p>
      ) : (
        courses.map((row) => (
          <section key={row.course} className="detail-card">
            <h2>{row.name}</h2>
            <p className="hint-text">
              {row.total_subject} employee(s) subject to this requirement —{' '}
              {row.completion_rate_pct !== null ? `${row.completion_rate_pct}% compliant` : 'no one subject yet'}
              {' '}({row.compliant} compliant, {row.due} due, {row.overdue} overdue)
            </p>
            {row.total_subject > 0 && (
              <div className="breakdown-grid">
                <BreakdownTable title="By department" rows={row.by_department} />
                <BreakdownTable title="By occupational level" rows={row.by_occupational_level} />
              </div>
            )}
          </section>
        ))
      )}
    </div>
  )
}

function BreakdownTable({
  title, rows,
}: { title: string; rows: TrainingComplianceCourseRow['by_department'] }) {
  return (
    <div className="table-scroll">
      <h3>{title}</h3>
      <table className="data-table">
        <thead>
          <tr>
            <th>{title.replace('By ', '')}</th>
            <th>Subject</th>
            <th>Compliant</th>
            <th>Due</th>
            <th>Overdue</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key}>
              <td>{r.key}</td>
              <td>{r.total_subject}</td>
              <td>{r.compliant}</td>
              <td>{r.due}</td>
              <td>{r.overdue}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
