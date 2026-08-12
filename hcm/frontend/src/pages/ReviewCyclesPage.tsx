import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../api/client'
import type { ReviewCycle, ReviewCycleCompletion, ReviewCycleType } from '../api/types'

export function ReviewCyclesPage() {
  const [cycles, setCycles] = useState<ReviewCycle[] | null>(null)
  const [completions, setCompletions] = useState<Record<number, ReviewCycleCompletion>>({})
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)

  function load() {
    setError(null)
    fetchAllPages<ReviewCycle>('/review-cycles/')
      .then(async (data) => {
        setCycles(data)
        const entries = await Promise.all(
          data
            .filter((c) => c.status !== 'draft')
            .map(async (c) => [c.id, await api.get<ReviewCycleCompletion>(`/review-cycles/${c.id}/completion/`)] as const),
        )
        setCompletions(Object.fromEntries(entries))
      })
      .catch(() => setError('Failed to load review cycles.'))
  }

  useEffect(load, [])

  async function handleLaunch(cycle: ReviewCycle) {
    setError(null)
    setBusyId(cycle.id)
    try {
      await api.post(`/review-cycles/${cycle.id}/launch/`)
      load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Launch failed.')
    } finally {
      setBusyId(null)
    }
  }

  async function handleClose(cycle: ReviewCycle) {
    setError(null)
    setBusyId(cycle.id)
    try {
      await api.post(`/review-cycles/${cycle.id}/close/`)
      load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Close failed.')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Review Cycles</h1>
        <button type="button" className="btn-primary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : '+ New cycle'}
        </button>
      </div>

      {error && <p className="form-error">{error}</p>}

      {showForm && (
        <NewCycleForm
          onCreated={() => {
            setShowForm(false)
            load()
          }}
        />
      )}

      {cycles === null ? (
        <p className="empty-state">Loading…</p>
      ) : cycles.length === 0 ? (
        <p className="empty-state">No review cycles yet.</p>
      ) : (
        cycles.map((cycle) => {
          const completion = completions[cycle.id]
          return (
            <section key={cycle.id} className="detail-card">
              <div className="page-header">
                <h2>
                  {cycle.name} <span className="status-badge">{cycle.status}</span>
                </h2>
                <div className="row-actions">
                  {cycle.status === 'draft' && (
                    <button
                      type="button"
                      className="btn-primary"
                      disabled={busyId === cycle.id}
                      onClick={() => void handleLaunch(cycle)}
                    >
                      Launch
                    </button>
                  )}
                  {cycle.status === 'launched' && (
                    <button
                      type="button"
                      className="btn-secondary"
                      disabled={busyId === cycle.id}
                      onClick={() => void handleClose(cycle)}
                    >
                      Close
                    </button>
                  )}
                </div>
              </div>
              <p className="hint-text">
                {cycle.cycle_type} · {cycle.start_date} – {cycle.end_date}
              </p>

              {completion && (
                <div className="stat-row" style={{ marginTop: 12 }}>
                  <div className="stat-tile">
                    <span className="stat-value">{completion.total}</span>
                    <span className="stat-label">In cycle</span>
                  </div>
                  <div className="stat-tile">
                    <span className="stat-value">{completion.self_submitted_pct}%</span>
                    <span className="stat-label">Self-reviews submitted</span>
                  </div>
                  <div className="stat-tile">
                    <span className="stat-value">{completion.manager_submitted_pct}%</span>
                    <span className="stat-label">Manager reviews submitted</span>
                  </div>
                  <div className="stat-tile">
                    <span className="stat-value">{completion.completed_pct}%</span>
                    <span className="stat-label">Fully completed</span>
                  </div>
                </div>
              )}
            </section>
          )
        })
      )}
    </div>
  )
}

function NewCycleForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState('')
  const [cycleType, setCycleType] = useState<ReviewCycleType>('annual')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await api.post('/review-cycles/', { name, cycle_type: cycleType, start_date: startDate, end_date: endDate })
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
        Name
        <input value={name} onChange={(e) => setName(e.target.value)} required />
      </label>
      <label>
        Type
        <select value={cycleType} onChange={(e) => setCycleType(e.target.value as ReviewCycleType)}>
          <option value="annual">Annual</option>
          <option value="biannual">Biannual</option>
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
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Creating…' : 'Create cycle'}
        </button>
      </div>
    </form>
  )
}
