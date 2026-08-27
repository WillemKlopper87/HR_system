import { useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../api/client'
import { useApiQuery } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import type {
  Employee, ProbationCompletionDashboard, ProbationPeriod, ProbationRecommendation,
} from '../api/types'
import { PROBATION_RECOMMENDATION_LABELS, PROBATION_STATUS_LABELS } from '../api/types'

export function ProbationPage() {
  const { hasRole } = useAuth()
  const isHrAdmin = hasRole('hr_admin')
  const isLineManager = hasRole('line_manager')
  const periods = useApiQuery(() => fetchAllPages<ProbationPeriod>('/probation-periods/'), [], {
    errorMessage: 'Failed to load probation periods.',
  })
  const employees = useApiQuery(() => fetchAllPages<Employee>('/employees/'), [], {
    errorMessage: 'Failed to load employees.', enabled: isHrAdmin,
  })
  const dashboard = useApiQuery(() => api.get<ProbationCompletionDashboard>('/dashboards/probation/'), [], {
    errorMessage: 'Failed to load the completion dashboard.', enabled: isHrAdmin,
  })

  return (
    <div className="page">
      <div className="page-header">
        <h1>Probation</h1>
      </div>
      <p className="hint-text">
        Documented reviews and outcomes for each probation window — the Code on integrating EE into HR
        practice calls for regular reviews signed by the employee and completion rates tracked by
        designated group.
      </p>

      {isHrAdmin && dashboard.data && (
        <section className="detail-card">
          <h2>Completion rate</h2>
          <div className="stat-row">
            <div className="stat-tile">
              <span className="stat-value">{dashboard.data.overall_completion_pct ?? '—'}%</span>
              <span className="stat-label">Confirmed of closed</span>
            </div>
            <div className="stat-tile">
              <span className="stat-value">{dashboard.data.in_progress}</span>
              <span className="stat-label">Still open</span>
            </div>
          </div>
          {dashboard.data.small_cell_suppression_applied && (
            <p className="hint-text suppression-note">Small cells (n &lt; 5) are suppressed for your role.</p>
          )}
        </section>
      )}

      {isHrAdmin && (
        <section className="detail-card">
          <h2>Open a probation period</h2>
          <OpenPeriodForm employees={employees.data ?? []} onSaved={periods.reload} />
        </section>
      )}

      <section className="detail-card">
        <h2>Probation periods</h2>
        {periods.error && <p className="form-error">{periods.error}</p>}
        {periods.data === null ? (
          !periods.error && <p className="empty-state">Loading…</p>
        ) : periods.data.length === 0 ? (
          <p className="empty-state">No probation periods recorded.</p>
        ) : (
          periods.data.map((period) => (
            <PeriodCard
              key={period.id} period={period} canRecordOutcome={isHrAdmin}
              canReview={isHrAdmin || isLineManager} onChanged={periods.reload}
            />
          ))
        )}
      </section>
    </div>
  )
}

function OpenPeriodForm({ employees, onSaved }: { employees: Employee[]; onSaved: () => void }) {
  const [employeeId, setEmployeeId] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSaving(true)
    try {
      await api.post('/probation-periods/', {
        employee: Number(employeeId), start_date: startDate, end_date: endDate,
      })
      setEmployeeId('')
      setStartDate('')
      setEndDate('')
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Save failed.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit}>
      <label>
        Employee
        <select value={employeeId} onChange={(e) => setEmployeeId(e.target.value)} required>
          <option value="">— Select —</option>
          {employees.map((emp) => (
            <option key={emp.id} value={emp.id}>{emp.employee_number} — {emp.first_name} {emp.last_name}</option>
          ))}
        </select>
      </label>
      <label>
        Start date
        <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} required />
      </label>
      <label>
        End date
        <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} required />
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={saving || !employeeId}>
          {saving ? 'Opening…' : 'Open probation period'}
        </button>
      </div>
    </form>
  )
}

function PeriodCard({
  period, canRecordOutcome, canReview, onChanged,
}: { period: ProbationPeriod; canRecordOutcome: boolean; canReview: boolean; onChanged: () => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const isOpen = period.status === 'in_progress' || period.status === 'extended'

  async function recordOutcome(status: 'confirmed' | 'extended' | 'terminated') {
    setError(null)
    let notes: string | undefined
    let end_date: string | undefined
    if (status === 'extended') {
      end_date = window.prompt('New end date (YYYY-MM-DD):') ?? undefined
      if (!end_date) return
    }
    if (status === 'terminated') {
      notes = window.prompt('Reason for non-confirmation (for the exit-interview record):') ?? ''
    }
    setBusy(true)
    try {
      await api.post(`/probation-periods/${period.id}/record_outcome/`, { status, notes, end_date })
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to record outcome.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="detail-card">
      <h3>
        {period.employee_number} — {period.start_date} to {period.end_date}
        {' '}<span className={`status-badge status-${period.status}`}>{PROBATION_STATUS_LABELS[period.status]}</span>
      </h3>
      {period.outcome_notes && <p className="hint-text">{period.outcome_notes}</p>}

      {period.reviews.length > 0 && (
        <table className="data-table">
          <thead>
            <tr><th>Date</th><th>Recommendation</th><th>Comments</th></tr>
          </thead>
          <tbody>
            {period.reviews.map((r) => (
              <tr key={r.id}>
                <td>{r.review_date}</td>
                <td>{PROBATION_RECOMMENDATION_LABELS[r.recommendation]}</td>
                <td>{r.comments || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {error && <p className="form-error">{error}</p>}

      {isOpen && canReview && <AddReviewForm periodId={period.id} onSaved={onChanged} />}

      {isOpen && canRecordOutcome && (
        <div className="form-actions">
          <button type="button" className="btn-primary" disabled={busy} onClick={() => recordOutcome('confirmed')}>
            Confirm
          </button>
          <button type="button" disabled={busy} onClick={() => recordOutcome('extended')}>Extend</button>
          <button type="button" disabled={busy} onClick={() => recordOutcome('terminated')}>Terminate</button>
        </div>
      )}
    </div>
  )
}

function AddReviewForm({ periodId, onSaved }: { periodId: number; onSaved: () => void }) {
  const [reviewDate, setReviewDate] = useState('')
  const [recommendation, setRecommendation] = useState<ProbationRecommendation>('continue')
  const [comments, setComments] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSaving(true)
    try {
      await api.post('/probation-reviews/', {
        probation_period: periodId, review_date: reviewDate, recommendation, comments,
      })
      setReviewDate('')
      setComments('')
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Save failed.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit} aria-label="Add probation review">
      <label>
        Review date
        <input type="date" value={reviewDate} onChange={(e) => setReviewDate(e.target.value)} required />
      </label>
      <label>
        Recommendation
        <select value={recommendation} onChange={(e) => setRecommendation(e.target.value as ProbationRecommendation)}>
          {(Object.keys(PROBATION_RECOMMENDATION_LABELS) as ProbationRecommendation[]).map((key) => (
            <option key={key} value={key}>{PROBATION_RECOMMENDATION_LABELS[key]}</option>
          ))}
        </select>
      </label>
      <label>
        Comments
        <input value={comments} onChange={(e) => setComments(e.target.value)} />
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={saving || !reviewDate}>
          {saving ? 'Saving…' : 'Add review'}
        </button>
      </div>
    </form>
  )
}
