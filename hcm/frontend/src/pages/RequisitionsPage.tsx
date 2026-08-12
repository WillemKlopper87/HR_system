import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../api/client'
import { useReferenceData } from '../api/ReferenceDataContext'
import { REQUISITION_STATUS_LABELS, type Requisition, type RequisitionStatus } from '../api/types'

const STATUS_OPTIONS = Object.entries(REQUISITION_STATUS_LABELS) as [RequisitionStatus, string][]

export function RequisitionsPage() {
  const [requisitions, setRequisitions] = useState<Requisition[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const ref = useReferenceData()

  function load() {
    setError(null)
    fetchAllPages<Requisition>('/requisitions/')
      .then(setRequisitions)
      .catch(() => setError('Failed to load requisitions.'))
  }

  useEffect(load, [])

  async function handleStatusChange(req: Requisition, status: RequisitionStatus) {
    setError(null)
    try {
      const updated = await api.patch<Requisition>(`/requisitions/${req.id}/`, { status })
      setRequisitions((prev) => prev?.map((r) => (r.id === req.id ? updated : r)) ?? null)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Update failed.')
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Requisitions</h1>
        <button type="button" className="btn-primary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : '+ New requisition'}
        </button>
      </div>

      {error && <p className="form-error">{error}</p>}

      {showForm && (
        <NewRequisitionForm
          onCreated={() => {
            setShowForm(false)
            load()
          }}
        />
      )}

      {requisitions === null ? (
        <p className="empty-state">Loading…</p>
      ) : requisitions.length === 0 ? (
        <p className="empty-state">No requisitions yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Department</th>
                <th>Level</th>
                <th>Location</th>
                <th>Headcount</th>
                <th>Status</th>
                <th>Opened</th>
              </tr>
            </thead>
            <tbody>
              {requisitions.map((req) => (
                <tr key={req.id}>
                  <td>{req.title}</td>
                  <td>{ref.departments.get(req.department)?.name ?? '—'}</td>
                  <td>{ref.occupationalLevels.get(req.occupational_level)?.name ?? '—'}</td>
                  <td>{ref.locations.get(req.location)?.name ?? '—'}</td>
                  <td>{req.headcount}</td>
                  <td>
                    <select
                      value={req.status}
                      onChange={(e) => void handleStatusChange(req, e.target.value as RequisitionStatus)}
                    >
                      {STATUS_OPTIONS.map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>{req.opened_at ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function NewRequisitionForm({ onCreated }: { onCreated: () => void }) {
  const ref = useReferenceData()
  const [title, setTitle] = useState('')
  const [department, setDepartment] = useState<number | ''>('')
  const [occupationalLevel, setOccupationalLevel] = useState<number | ''>('')
  const [jobGrade, setJobGrade] = useState<number | ''>('')
  const [location, setLocation] = useState<number | ''>('')
  const [headcount, setHeadcount] = useState(1)
  const [status, setStatus] = useState<RequisitionStatus>('open')
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
      await api.post('/requisitions/', {
        title,
        department,
        occupational_level: occupationalLevel,
        job_grade: jobGrade || null,
        location,
        headcount,
        status,
      })
      onCreated()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Create failed.')
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
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Occupational level
        <select
          value={occupationalLevel}
          onChange={(e) => setOccupationalLevel(e.target.value ? Number(e.target.value) : '')}
          required
        >
          <option value="">— Select —</option>
          {ref.occupationalLevelList.map((l) => (
            <option key={l.id} value={l.id}>
              {l.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Job grade
        <select value={jobGrade} onChange={(e) => setJobGrade(e.target.value ? Number(e.target.value) : '')}>
          <option value="">— None —</option>
          {ref.jobGradeList
            .filter((g) => g.occupational_level === occupationalLevel)
            .map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
        </select>
      </label>
      <label>
        Location
        <select value={location} onChange={(e) => setLocation(e.target.value ? Number(e.target.value) : '')} required>
          <option value="">— Select —</option>
          {ref.locationList.map((l) => (
            <option key={l.id} value={l.id}>
              {l.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Headcount
        <input type="number" min={1} value={headcount} onChange={(e) => setHeadcount(Number(e.target.value))} />
      </label>
      <label>
        Status
        <select value={status} onChange={(e) => setStatus(e.target.value as RequisitionStatus)}>
          {STATUS_OPTIONS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>

      {error && <p className="form-error">{error}</p>}

      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Creating…' : 'Create requisition'}
        </button>
      </div>
    </form>
  )
}
