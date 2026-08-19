import { useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import { useAllPages } from '../api/hooks'
import { useReferenceData } from '../api/ReferenceDataContext'
import { POSITION_STATUS_LABELS, type Position } from '../api/types'
import { useAuth } from '../auth/AuthContext'

export function PositionsPage() {
  const { hasRole } = useAuth()
  const { data: positions, error: loadError, reload: load } = useAllPages<Position>('/positions/', [], 'Failed to load positions.')
  const [showForm, setShowForm] = useState(false)

  const canPropose = hasRole('hr_admin')
  const approvedCount = positions?.filter((p) => p.status === 'approved').length ?? 0
  const filledCount = positions?.filter((p) => p.status === 'approved' && !p.is_vacant).length ?? 0
  const vacantCount = approvedCount - filledCount
  const vacancyRate = approvedCount > 0 ? Math.round((vacantCount / approvedCount) * 1000) / 10 : 0

  return (
    <div className="page">
      <div className="page-header">
        <h1>Positions</h1>
        {canPropose && (
          <button type="button" className="btn-primary" onClick={() => setShowForm((v) => !v)}>
            {showForm ? 'Cancel' : '+ Propose position'}
          </button>
        )}
      </div>

      {positions && (
        <p className="hint-text">
          {approvedCount} approved · {filledCount} filled · {vacantCount} vacant · {vacancyRate}% vacancy rate
        </p>
      )}

      {loadError && <p className="form-error">{loadError}</p>}

      {showForm && <ProposePositionForm onCreated={() => { setShowForm(false); load() }} />}

      {positions === null ? (
        <p className="empty-state">Loading…</p>
      ) : positions.length === 0 ? (
        <p className="empty-state">No positions yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Post</th>
                <th>Title</th>
                <th>Status</th>
                <th>Incumbent</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((position) => (
                <PositionRow key={position.id} position={position} onChanged={load} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function PositionRow({ position, onChanged }: { position: Position; onChanged: () => void }) {
  const { hasRole } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function act(action: string, body?: Record<string, unknown>) {
    setError(null)
    setBusy(true)
    try {
      await api.post(`/positions/${position.id}/${action}/`, body)
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Action failed.')
    } finally {
      setBusy(false)
    }
  }

  const requiredRole = position.next_approver_role

  return (
    <tr>
      <td>{position.post_number}</td>
      <td>{position.title}</td>
      <td>
        <span className="status-badge">{POSITION_STATUS_LABELS[position.status]}</span>
      </td>
      <td>{position.current_incumbent_number ?? (position.status === 'approved' ? 'Vacant' : '—')}</td>
      <td>
        {error && <p className="form-error">{error}</p>}
        <div className="form-actions">
          {position.status === 'draft' && hasRole('hr_admin') && (
            <button type="button" className="btn-secondary" disabled={busy} onClick={() => void act('submit')}>
              Submit
            </button>
          )}
          {requiredRole && hasRole(requiredRole) && (
            <>
              <button type="button" className="btn-primary" disabled={busy} onClick={() => void act('decide', { decision: 'approved' })}>
                Approve
              </button>
              <button type="button" className="btn-secondary" disabled={busy} onClick={() => void act('decide', { decision: 'rejected' })}>
                Reject
              </button>
            </>
          )}
          {position.status === 'rejected' && hasRole('hr_admin') && (
            <button type="button" className="btn-link" disabled={busy} onClick={() => void act('revise', {})}>
              Revise &amp; resubmit
            </button>
          )}
        </div>
      </td>
    </tr>
  )
}

function ProposePositionForm({ onCreated }: { onCreated: () => void }) {
  const ref = useReferenceData()
  const [title, setTitle] = useState('')
  const [department, setDepartment] = useState<number | ''>('')
  const [occupationalLevel, setOccupationalLevel] = useState<number | ''>('')
  const [jobGrade, setJobGrade] = useState<number | ''>('')
  const [location, setLocation] = useState<number | ''>('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!department || !occupationalLevel || !location) {
      setError('Department, occupational level, and location are required.')
      return
    }
    setSubmitting(true)
    try {
      await api.post('/positions/', {
        title, department, occupational_level: occupationalLevel, job_grade: jobGrade || null, location,
      })
      onCreated()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Propose failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit}>
      <label>
        Title
        <input value={title} onChange={(e) => setTitle(e.target.value)} required />
      </label>
      <label>
        Department
        <select value={department} onChange={(e) => setDepartment(e.target.value ? Number(e.target.value) : '')} required>
          <option value="">— Select —</option>
          {ref.departmentList.map((d) => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </select>
      </label>
      <label>
        Occupational level
        <select value={occupationalLevel} onChange={(e) => setOccupationalLevel(e.target.value ? Number(e.target.value) : '')} required>
          <option value="">— Select —</option>
          {ref.occupationalLevelList.map((l) => (
            <option key={l.id} value={l.id}>{l.name}</option>
          ))}
        </select>
      </label>
      <label>
        Job grade
        <select value={jobGrade} onChange={(e) => setJobGrade(e.target.value ? Number(e.target.value) : '')}>
          <option value="">— None —</option>
          {ref.jobGradeList.filter((g) => g.occupational_level === occupationalLevel).map((g) => (
            <option key={g.id} value={g.id}>{g.name}</option>
          ))}
        </select>
      </label>
      <label>
        Location
        <select value={location} onChange={(e) => setLocation(e.target.value ? Number(e.target.value) : '')} required>
          <option value="">— Select —</option>
          {ref.locationList.map((l) => (
            <option key={l.id} value={l.id}>{l.name}</option>
          ))}
        </select>
      </label>

      {error && <p className="form-error">{error}</p>}

      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Proposing…' : 'Propose position'}
        </button>
      </div>
    </form>
  )
}
