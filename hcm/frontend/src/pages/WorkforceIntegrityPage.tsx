import { useMemo, useState } from 'react'
import { api, ApiError, type Paginated } from '../api/client'
import { useApiQuery } from '../api/hooks'
import { LIVENESS_OUTCOME_LABELS } from '../api/contract-labels'
import type { LivenessCheck } from '../api/contracts'
import type { AttendanceSummaryRow } from '../api/types'

export function WorkforceIntegrityPage() {
  const [pagePath, setPagePath] = useState<string | null>(null)
  const requestPath = pagePath ?? '/liveness-checks/?review_status=pending'

  const { data: attendance, error: attendanceError } = useApiQuery(
    () => api.get<AttendanceSummaryRow[]>('/dashboards/attendance/'),
    [],
    { errorMessage: 'Failed to load attendance data.' },
  )
  const { data: checkResponse, error: checksError, reload: load } = useApiQuery(
    () =>
      api.get<Paginated<LivenessCheck>>(requestPath).then((page) => ({ requestPath, page })),
    [requestPath],
    { errorMessage: 'Failed to load identity checks.' },
  )
  const checkPage = checkResponse?.requestPath === requestPath ? checkResponse.page : null
  const checks = checkPage?.results ?? null

  const pendingChecks = checks ?? []
  const nonCompliant = useMemo(() => (attendance ?? []).filter((row) => !row.compliant), [attendance])
  const loadError = attendanceError ?? checksError

  return (
    <div className="page">
      <div className="page-header">
        <h1>Workforce Integrity</h1>
      </div>

      <p className="hint-text">
        Office-attendance policy and identity-verification review. No automated result here is a final decision —
        flagged checks always need a human hr_admin review before any action is taken.
      </p>

      {loadError && <p className="form-error">{loadError}</p>}

      <section className="detail-card">
        <h2>Flagged for review ({pendingChecks.length} on this page)</h2>
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
                  return (
                    <ReviewRow
                      key={c.id}
                      check={c}
                      employeeName={c.employee_display}
                      onChanged={load}
                    />
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
        {checkPage && (checkPage.previous || checkPage.next) && (
          <nav className="form-actions" aria-label="Pending identity-check pages">
            <button type="button" className="btn-secondary" disabled={!checkPage.previous} onClick={() => setPagePath(checkPage.previous)}>
              Previous
            </button>
            <button type="button" className="btn-secondary" disabled={!checkPage.next} onClick={() => setPagePath(checkPage.next)}>
              Next
            </button>
          </nav>
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
