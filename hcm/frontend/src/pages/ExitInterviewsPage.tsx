import { useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../api/client'
import type { ExitInterview, ExitInterviewReason } from '../api/contracts'
import { useApiQuery } from '../api/hooks'
import { EmployeeAsyncSelect } from '../components/EmployeeAsyncSelect'
import type { ExitInterviewDashboard } from '../api/types'
import { EXIT_INTERVIEW_REASON_LABELS } from '../api/contract-labels'

export function ExitInterviewsPage() {
  const interviews = useApiQuery(() => fetchAllPages<ExitInterview>('/exit-interviews/'), [], {
    errorMessage: 'Failed to load exit interviews.',
  })
  const dashboard = useApiQuery(() => api.get<ExitInterviewDashboard>('/dashboards/exit-interviews/'), [], {
    errorMessage: 'Failed to load the exit-interview dashboard.',
  })

  return (
    <div className="page">
      <div className="page-header">
        <h1>Exit Interviews</h1>
      </div>
      <p className="hint-text">
        Departure reasons reviewed by designated group — the Code on integrating EE into HR practice calls for
        exit interviews on both genuine departures and probation non-confirmations, with retention patterns
        reviewed across groups.
      </p>

      {dashboard.data && (
        <section className="detail-card">
          <h2>By reason</h2>
          <ul className="breakdown-list">
            {dashboard.data.by_reason.map((row) => (
              <li key={row.key}>
                <span className="breakdown-label">{EXIT_INTERVIEW_REASON_LABELS[row.key]}</span>
                <span className="breakdown-count">{row.count}</span>
              </li>
            ))}
          </ul>
          {dashboard.data.small_cell_suppression_applied && (
            <p className="hint-text suppression-note">
              Group breakdowns below suppress any cell under 5 interviews — your role does not have
              organisation-wide sensitive-data access.
            </p>
          )}
          <GroupTable title="By race" rows={dashboard.data.by_race} />
          <GroupTable title="By gender" rows={dashboard.data.by_gender} />
          <GroupTable title="By disability status" rows={dashboard.data.by_disability_status} />
        </section>
      )}

      <section className="detail-card">
        <h2>Record an interview</h2>
        <RecordInterviewForm onSaved={() => { interviews.reload(); dashboard.reload() }} />
      </section>

      <section className="detail-card">
        <h2>Interviews</h2>
        {interviews.error && <p className="form-error">{interviews.error}</p>}
        {interviews.data === null ? (
          !interviews.error && <p className="empty-state">Loading…</p>
        ) : interviews.data.length === 0 ? (
          <p className="empty-state">No exit interviews recorded.</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr><th>Date</th><th>Reason</th><th>Would recommend</th><th>Comments</th></tr>
              </thead>
              <tbody>
                {interviews.data.map((i) => (
                  <tr key={i.id}>
                    <td>{i.interview_date}</td>
                    <td>{EXIT_INTERVIEW_REASON_LABELS[i.primary_reason]}</td>
                    <td>{i.would_recommend_employer === null ? '—' : i.would_recommend_employer ? 'Yes' : 'No'}</td>
                    <td>{i.comments || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}

function GroupTable({
  title, rows,
}: { title: string; rows: { key: string; total: number | string; suppressed: boolean }[] }) {
  if (rows.length === 0) return null
  return (
    <div className="table-scroll">
      <h3>{title}</h3>
      <table className="data-table">
        <thead><tr><th>Group</th><th>Total</th></tr></thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <td>{row.key}</td>
              <td className={row.suppressed ? 'suppressed' : undefined}>{row.total}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RecordInterviewForm({ onSaved }: { onSaved: () => void }) {
  const [employeeId, setEmployeeId] = useState<number | null>(null)
  const [interviewDate, setInterviewDate] = useState('')
  const [reason, setReason] = useState<ExitInterviewReason>('other')
  const [wouldRecommend, setWouldRecommend] = useState('')
  const [comments, setComments] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSaving(true)
    try {
      await api.post('/exit-interviews/', {
        employee: employeeId, interview_date: interviewDate, primary_reason: reason,
        would_recommend_employer: wouldRecommend === '' ? null : wouldRecommend === 'true',
        comments,
      })
      setEmployeeId(null)
      setInterviewDate('')
      setComments('')
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Save failed.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit}>
      <EmployeeAsyncSelect value={employeeId} onChange={setEmployeeId} required />
      <label>
        Interview date
        <input type="date" value={interviewDate} onChange={(e) => setInterviewDate(e.target.value)} required />
      </label>
      <label>
        Primary reason
        <select value={reason} onChange={(e) => setReason(e.target.value as ExitInterviewReason)}>
          {(Object.keys(EXIT_INTERVIEW_REASON_LABELS) as ExitInterviewReason[]).map((key) => (
            <option key={key} value={key}>{EXIT_INTERVIEW_REASON_LABELS[key]}</option>
          ))}
        </select>
      </label>
      <label>
        Would recommend employer?
        <select value={wouldRecommend} onChange={(e) => setWouldRecommend(e.target.value)}>
          <option value="">— Not asked —</option>
          <option value="true">Yes</option>
          <option value="false">No</option>
        </select>
      </label>
      <label>
        Comments
        <input value={comments} onChange={(e) => setComments(e.target.value)} />
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={saving || !employeeId || !interviewDate}>
          {saving ? 'Saving…' : 'Record interview'}
        </button>
      </div>
    </form>
  )
}
