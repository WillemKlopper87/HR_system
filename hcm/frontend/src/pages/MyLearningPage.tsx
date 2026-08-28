import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../api/client'
import { useAllPages } from '../api/hooks'
import { TRAINING_STATUS_LABELS, type Course, type TrainingRecord } from '../api/types'
import { useAuth } from '../auth/useAuth'

export function MyLearningPage() {
  const { user } = useAuth()
  const employeeId = user?.employee_id ?? null

  const [records, setRecords] = useState<TrainingRecord[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)

  function load() {
    if (!employeeId) return
    setError(null)
    fetchAllPages<TrainingRecord>(`/training-records/?employee=${employeeId}`)
      .then(setRecords)
      .catch(() => setError('Failed to load your learning requests.'))
  }

  useEffect(load, [employeeId])

  if (!employeeId) return <p className="empty-state">Loading…</p>

  return (
    <div className="page">
      <div className="page-header">
        <h1>My Learning</h1>
        <button type="button" className="btn-primary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : '+ Request enrollment'}
        </button>
      </div>
      <p className="hint-text">
        Requesting a course sends it to your manager or HR to plan and approve — status, hours, and cost are set once
        it's reviewed, not by you.
      </p>

      {error && <p className="form-error">{error}</p>}

      {showForm && (
        <RequestEnrollmentForm
          employeeId={employeeId}
          onCreated={() => {
            setShowForm(false)
            load()
          }}
        />
      )}

      {records === null ? (
        <p className="empty-state">Loading…</p>
      ) : records.length === 0 ? (
        <p className="empty-state">No learning requests yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Provider</th>
                <th>Status</th>
                <th>Start date</th>
                <th>Hours</th>
                <th>Cost</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.id}>
                  <td>{r.title}</td>
                  <td>{r.provider || '—'}</td>
                  <td>
                    <span className="status-badge">{r.status ? TRAINING_STATUS_LABELS[r.status] : '—'}</span>
                  </td>
                  <td>{r.start_date ?? '—'}</td>
                  <td>{r.hours ?? '—'}</td>
                  <td>{r.cost ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function RequestEnrollmentForm({ employeeId, onCreated }: { employeeId: number; onCreated: () => void }) {
  const { data: courses } = useAllPages<Course>('/courses/', [], 'Failed to load the course catalogue.')
  const [courseId, setCourseId] = useState<number | ''>('')
  const [title, setTitle] = useState('')
  const [provider, setProvider] = useState('')
  const [startDate, setStartDate] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  function handleCourseChange(value: string) {
    const id = value ? Number(value) : ''
    setCourseId(id)
    // Pre-fill title/provider from the catalogue entry as a convenience —
    // still editable, since `title` is what's actually stored and shown.
    const chosen = courses?.find((c) => c.id === id)
    if (chosen) {
      setTitle(chosen.name)
      setProvider(chosen.provider ?? '')
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await api.post('/training-records/', {
        employee: employeeId, title, provider, course: courseId || null, start_date: startDate || null,
      })
      onCreated()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Request failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit}>
      <label>
        From the catalogue (optional)
        <select value={courseId} onChange={(e) => handleCourseChange(e.target.value)}>
          <option value="">— Not in the catalogue —</option>
          {(courses ?? []).filter((c) => c.active).map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}{c.mandatory ? ' (mandatory)' : ''}
            </option>
          ))}
        </select>
      </label>
      <label>
        Course/training title
        <input value={title} onChange={(e) => setTitle(e.target.value)} required />
      </label>
      <label>
        Provider
        <input value={provider} onChange={(e) => setProvider(e.target.value)} />
      </label>
      <label>
        Desired start date
        <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Requesting…' : 'Request enrollment'}
        </button>
      </div>
    </form>
  )
}
