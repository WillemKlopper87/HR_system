import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError, fetchAllPages } from '../api/client'
import {
  DATA_SUBJECT_REQUEST_STATUS_LABELS,
  DATA_SUBJECT_REQUEST_TYPE_LABELS,
  type DataSubjectRequest,
} from '../api/types'
import { useAuth } from '../auth/AuthContext'

/** hr_admin's review queue for the C2 POPIA workflow (design spec §5.3,
 * §6.2): both export and erasure requests land here and are reviewed and
 * actioned by hr_admin — never auto-executed, precisely because an
 * erasure request has to respect the exit-cascade's non-destructive
 * philosophy (documents/services.py::complete_erasure_request's
 * allow-list). */
export function DataSubjectRequestsPage() {
  const { hasRole } = useAuth()
  const canAction = hasRole('hr_admin')
  const [requests, setRequests] = useState<DataSubjectRequest[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [showActioned, setShowActioned] = useState(false)

  function load() {
    setError(null)
    fetchAllPages<DataSubjectRequest>('/data-subject-requests/')
      .then(setRequests)
      .catch(() => setError('Failed to load data-subject requests.'))
  }

  useEffect(load, [])

  async function handleComplete(request: DataSubjectRequest) {
    setBusyId(request.id)
    setError(null)
    try {
      await api.post(`/data-subject-requests/${request.id}/complete/`)
      load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not complete this request.')
    } finally {
      setBusyId(null)
    }
  }

  async function handleDecline(request: DataSubjectRequest) {
    const notes = window.prompt('Reason for declining (shown to the requester):') ?? ''
    setBusyId(request.id)
    setError(null)
    try {
      await api.post(`/data-subject-requests/${request.id}/decline/`, { resolution_notes: notes })
      load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not decline this request.')
    } finally {
      setBusyId(null)
    }
  }

  const visible = requests?.filter((r) => showActioned || r.status === 'submitted') ?? null

  return (
    <div className="page">
      <div className="page-header">
        <h1>Data-Subject Requests</h1>
        <label>
          <input type="checkbox" checked={showActioned} onChange={(e) => setShowActioned(e.target.checked)} /> Show actioned
        </label>
      </div>
      <p className="hint-text">
        POPIA export and erasure requests. Completing an erasure request deletes the employee's documents,
        dependants, and emergency contacts, and clears their preferred name / personal email / phone — it never
        touches employment history, audit records, or anything under a retention rule.
      </p>

      {error && <p className="form-error">{error}</p>}

      {visible === null ? (
        <p className="empty-state">Loading…</p>
      ) : visible.length === 0 ? (
        <p className="empty-state">No {showActioned ? '' : 'open '}requests.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Employee</th>
                <th>Type</th>
                <th>Status</th>
                <th>Requested</th>
                <th>Requested by</th>
                <th>Notes</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link to={`/employees/${r.employee}`}>{r.employee_number}</Link>
                  </td>
                  <td>{DATA_SUBJECT_REQUEST_TYPE_LABELS[r.request_type]}</td>
                  <td><span className="status-badge">{DATA_SUBJECT_REQUEST_STATUS_LABELS[r.status]}</span></td>
                  <td>{new Date(r.requested_at).toLocaleDateString()}</td>
                  <td>{r.requested_by_number ?? '—'}</td>
                  <td>{r.request_notes || r.resolution_notes || '—'}</td>
                  <td>
                    {canAction && r.status === 'submitted' && (
                      <div className="form-actions">
                        <button
                          type="button" className="btn-primary" disabled={busyId === r.id}
                          onClick={() => void handleComplete(r)}
                        >
                          {busyId === r.id ? 'Working…' : r.request_type === 'export' ? 'Generate export' : 'Erase'}
                        </button>
                        <button
                          type="button" className="btn-secondary" disabled={busyId === r.id}
                          onClick={() => void handleDecline(r)}
                        >
                          Decline
                        </button>
                      </div>
                    )}
                    {r.download_url && (
                      <a className="btn-link" href={r.download_url} target="_blank" rel="noreferrer">Download</a>
                    )}
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
