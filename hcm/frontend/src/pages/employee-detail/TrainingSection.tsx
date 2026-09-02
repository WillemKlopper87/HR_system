import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../../api/client'
import type { TrainingRecord } from '../../api/types'

export function TrainingSection({ employeeId }: { employeeId: number }) {
  const [records, setRecords] = useState<TrainingRecord[] | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function load() {
    setError(null)
    fetchAllPages<TrainingRecord>(`/training-records/?employee=${employeeId}`)
      .then(setRecords)
      .catch(() => setError('Failed to load training records.'))
  }

  useEffect(load, [employeeId])

  return (
    <section className="detail-card">
      <div className="page-header">
        <h2>Training</h2>
        <button type="button" className="btn-secondary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : '+ Add training record'}
        </button>
      </div>

      {error && <p className="form-error">{error}</p>}

      {showForm && (
        <NewTrainingForm
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
        <p className="empty-state">No training records yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Provider</th>
                <th>Status</th>
                <th>Hours</th>
              </tr>
            </thead>
            <tbody>
              {records.map((t) => (
                <tr key={t.id}>
                  <td>{t.title ?? '—'}</td>
                  <td>{t.provider || '—'}</td>
                  <td>
                    <span className="status-badge">{t.status ?? '—'}</span>
                  </td>
                  <td>{t.hours ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function NewTrainingForm({ employeeId, onCreated }: { employeeId: number; onCreated: () => void }) {
  const [title, setTitle] = useState('')
  const [provider, setProvider] = useState('')
  const [status, setStatus] = useState('planned')
  const [hours, setHours] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await api.post('/training-records/', { employee: employeeId, title, provider, status, hours: hours || null })
      onCreated()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Add failed.')
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
        Provider
        <input value={provider} onChange={(e) => setProvider(e.target.value)} />
      </label>
      <label>
        Status
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="planned">Planned</option>
          <option value="in_progress">In progress</option>
          <option value="completed">Completed</option>
          <option value="cancelled">Cancelled</option>
        </select>
      </label>
      <label>
        Hours
        <input type="number" min={0} step="0.5" value={hours} onChange={(e) => setHours(e.target.value)} />
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Adding…' : 'Add record'}
        </button>
      </div>
    </form>
  )
}
