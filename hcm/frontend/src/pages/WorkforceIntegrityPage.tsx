import { useEffect, useMemo, useState } from 'react'
import { api, ApiError, fetchAllPages } from '../api/client'
import {
  LIVENESS_OUTCOME_LABELS,
  type AttendanceSummaryRow,
  type Employee,
  type LivenessCheck,
} from '../api/types'

export function WorkforceIntegrityPage() {
  const [attendance, setAttendance] = useState<AttendanceSummaryRow[] | null>(null)
  const [checks, setChecks] = useState<LivenessCheck[] | null>(null)
  const [employees, setEmployees] = useState<Employee[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  function load() {
    setError(null)
    Promise.all([
      api.get<AttendanceSummaryRow[]>('/dashboards/attendance/'),
      fetchAllPages<LivenessCheck>('/liveness-checks/'),
      fetchAllPages<Employee>('/employees/'),
    ])
      .then(([a, c, e]) => {
        setAttendance(a)
        setChecks(c)
        setEmployees(e)
      })
      .catch(() => setError('Failed to load workforce integrity data.'))
  }

  useEffect(load, [])

  const employeeById = useMemo(() => new Map((employees ?? []).map((e) => [e.id, e])), [employees])
  const pendingChecks = useMemo(() => (checks ?? []).filter((c) => c.review_status === 'pending'), [checks])
  const nonCompliant = useMemo(() => (attendance ?? []).filter((row) => !row.compliant), [attendance])

  return (
    <div className="page">
      <div className="page-header">
        <h1>Workforce Integrity</h1>
      </div>

      <p className="hint-text">
        Office-attendance policy and identity-verification review. No automated result here is a final decision —
        flagged checks always need a human hr_admin review before any action is taken.
      </p>

      {error && <p className="form-error">{error}</p>}

      <section className="detail-card">
        <h2>Flagged for review ({pendingChecks.length})</h2>
        {pendingChecks.length === 0 ? (
          <p className="empty-state">Nothing pending review.</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Employee</th>
                  <th>When</th>
                  <th>Result</th>
                  <th>Distance</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {pendingChecks.map((c) => {
                  const emp = employeeById.get(c.employee)
                  return (
                    <ReviewRow
                      key={c.id}
                      check={c}
                      employeeName={emp ? `${emp.first_name} ${emp.last_name}` : `#${c.employee}`}
                      onChanged={load}
                    />
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="detail-card">
        <h2>
          This week's office-attendance compliance ({nonCompliant.length} of {attendance?.length ?? 0} not yet met)
        </h2>
        {attendance === null ? (
          <p className="empty-state">Loading…</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Employee</th>
                  <th>Days in office</th>
                  <th>Required</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {attendance.map((row) => (
                  <tr key={row.employee}>
                    <td>{row.employee_name}</td>
                    <td>{row.days_in_office}</td>
                    <td>{row.required_days}</td>
                    <td>
                      {row.compliant ? (
                        <span className="status-badge">On track</span>
                      ) : (
                        <span className="restricted-badge">Not yet met</span>
                      )}
                    </td>
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

function ReviewRow({
  check, employeeName, onChanged,
}: { check: LivenessCheck; employeeName: string; onChanged: () => void }) {
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleReview(decision: 'confirmed_match' | 'confirmed_mismatch') {
    setError(null)
    setBusy(true)
    try {
      await api.post(`/liveness-checks/${check.id}/review/`, { decision, notes })
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Review failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <tr>
      <td>{employeeName}</td>
      <td>{new Date(check.created_at).toLocaleString()}</td>
      <td>{LIVENESS_OUTCOME_LABELS[check.outcome]}</td>
      <td>{check.match_distance !== null ? check.match_distance.toFixed(2) : '—'}</td>
      <td>
        {error && <p className="form-error">{error}</p>}
        <div className="inline-form" style={{ marginBottom: 8 }}>
          <label>
            Notes
            <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Investigation notes…" />
          </label>
        </div>
        <div className="form-actions">
          <button type="button" className="btn-primary" disabled={busy} onClick={() => void handleReview('confirmed_match')}>
            Confirm match
          </button>
          <button type="button" className="btn-secondary btn-danger" disabled={busy} onClick={() => void handleReview('confirmed_mismatch')}>
            Confirm mismatch
          </button>
        </div>
      </td>
    </tr>
  )
}
