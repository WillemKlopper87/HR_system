import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../api/client'
import { useReferenceData } from '../api/ReferenceDataContext'
import type { PayBand } from '../api/types'

function formatZAR(value: string): string {
  return `R ${Number(value).toLocaleString()}`
}

function isCurrent(band: PayBand): boolean {
  const today = new Date().toISOString().slice(0, 10)
  return band.valid_from <= today && (band.valid_to === null || band.valid_to > today)
}

export function PayBandsPage() {
  const [bands, setBands] = useState<PayBand[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const ref = useReferenceData()

  function load() {
    setError(null)
    fetchAllPages<PayBand>('/pay-bands/')
      .then(setBands)
      .catch(() => setError('Failed to load pay bands.'))
  }

  useEffect(load, [])

  return (
    <div className="page">
      <div className="page-header">
        <h1>Pay Bands</h1>
        <button type="button" className="btn-primary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : '+ New pay band'}
        </button>
      </div>

      {error && <p className="form-error">{error}</p>}

      {showForm && (
        <NewPayBandForm
          onCreated={() => {
            setShowForm(false)
            load()
          }}
        />
      )}

      {bands === null ? (
        <p className="empty-state">Loading…</p>
      ) : bands.length === 0 ? (
        <p className="empty-state">No pay bands yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Job grade</th>
                <th>Min</th>
                <th>Mid</th>
                <th>Max</th>
                <th>Valid from</th>
                <th>Valid to</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {bands.map((band) => (
                <tr key={band.id}>
                  <td>{ref.jobGrades.get(band.job_grade)?.name ?? `#${band.job_grade}`}</td>
                  <td>{formatZAR(band.min_salary)}</td>
                  <td>{formatZAR(band.mid_salary)}</td>
                  <td>{formatZAR(band.max_salary)}</td>
                  <td>{band.valid_from}</td>
                  <td>{band.valid_to ?? '—'}</td>
                  <td>
                    {isCurrent(band) ? (
                      <span className="status-badge">Current</span>
                    ) : (
                      <span className="restricted-badge">Expired</span>
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

function NewPayBandForm({ onCreated }: { onCreated: () => void }) {
  const ref = useReferenceData()
  const [jobGrade, setJobGrade] = useState<number | ''>('')
  const [minSalary, setMinSalary] = useState('')
  const [midSalary, setMidSalary] = useState('')
  const [maxSalary, setMaxSalary] = useState('')
  const [validFrom, setValidFrom] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!jobGrade || !validFrom) {
      setError('Job grade and valid-from date are required.')
      return
    }
    setSubmitting(true)
    try {
      await api.post('/pay-bands/', {
        job_grade: jobGrade,
        min_salary: minSalary,
        mid_salary: midSalary,
        max_salary: maxSalary,
        valid_from: validFrom,
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
        Job grade
        <select value={jobGrade} onChange={(e) => setJobGrade(e.target.value ? Number(e.target.value) : '')} required>
          <option value="">— Select —</option>
          {ref.jobGradeList.map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Min salary (ZAR)
        <input type="number" min={0} step="0.01" value={minSalary} onChange={(e) => setMinSalary(e.target.value)} required />
      </label>
      <label>
        Mid salary (ZAR)
        <input type="number" min={0} step="0.01" value={midSalary} onChange={(e) => setMidSalary(e.target.value)} required />
      </label>
      <label>
        Max salary (ZAR)
        <input type="number" min={0} step="0.01" value={maxSalary} onChange={(e) => setMaxSalary(e.target.value)} required />
      </label>
      <label>
        Valid from
        <input type="date" value={validFrom} onChange={(e) => setValidFrom(e.target.value)} required />
      </label>

      {error && <p className="form-error">{error}</p>}

      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Creating…' : 'Create pay band'}
        </button>
      </div>
    </form>
  )
}
