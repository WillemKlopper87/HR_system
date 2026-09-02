import { useState, type FormEvent } from 'react'
import { api, ApiError } from '../../api/client'
import { useReferenceData } from '../../api/useReferenceData'
import type { Offer } from '../../api/types'

export function NewOfferForm({ applicantId, onCreated }: { applicantId: number; onCreated: () => void }) {
  const ref = useReferenceData()
  const [jobGrade, setJobGrade] = useState<number | ''>('')
  const [salary, setSalary] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!jobGrade) {
      setError('Job grade is required.')
      return
    }
    setSubmitting(true)
    try {
      await api.post('/offers/', {
        applicant: applicantId, proposed_job_grade: jobGrade, proposed_annual_salary: salary,
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
        Proposed annual salary (ZAR)
        <input type="number" min={0} step="0.01" value={salary} onChange={(e) => setSalary(e.target.value)} required />
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Creating…' : 'Propose offer'}
        </button>
      </div>
    </form>
  )
}

export function OfferPanel({
  offer, jobGradeName, onChanged,
}: { offer: Offer; jobGradeName: string | undefined; onChanged: () => void }) {
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function act(action: 'approve' | 'accept' | 'decline') {
    setError(null)
    setBusy(true)
    try {
      await api.post(`/offers/${offer.id}/${action}/`)
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Action failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <dl className="detail-grid">
        <div className="detail-field">
          <dt>Job grade</dt>
          <dd>{jobGradeName ?? '—'}</dd>
        </div>
        <div className="detail-field">
          <dt>Proposed annual salary</dt>
          <dd>R {Number(offer.proposed_annual_salary).toLocaleString()}</dd>
        </div>
        <div className="detail-field">
          <dt>Status</dt>
          <dd>
            <span className="status-badge">{offer.status}</span>
          </dd>
        </div>
      </dl>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions" style={{ marginTop: 12 }}>
        {offer.status === 'proposed' && (
          <button type="button" className="btn-primary" disabled={busy} onClick={() => void act('approve')}>
            Approve
          </button>
        )}
        {offer.status === 'approved' && (
          <>
            <button type="button" className="btn-primary" disabled={busy} onClick={() => void act('accept')}>
              Accept
            </button>
            <button type="button" className="btn-secondary" disabled={busy} onClick={() => void act('decline')}>
              Decline
            </button>
          </>
        )}
      </div>
    </div>
  )
}
