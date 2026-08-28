import { useState, type FormEvent } from 'react'
import { formatZAR } from '../lib/format'
import { api, ApiError } from '../api/client'
import { useAllPages } from '../api/hooks'
import { useReferenceData } from '../api/useReferenceData'
import type { PayBand } from '../api/types'

function isCurrent(band: PayBand): boolean {
  const today = new Date().toISOString().slice(0, 10)
  return band.valid_from <= today && (band.valid_to === null || band.valid_to > today)
}

export function PayBandsPage() {
  const { data: bands, error: loadError, reload: load } = useAllPages<PayBand>('/pay-bands/', [], 'Failed to load pay bands.')
  const [showForm, setShowForm] = useState(false)
  const ref = useReferenceData()

  return (
    <div className="page">
      <div className="page-header">
        <h1>Pay Bands</h1>
        <button type="button" className="btn-primary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : '+ New pay band'}
        </button>
      </div>

      {loadError && <p className="form-error">{loadError}</p>}

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
