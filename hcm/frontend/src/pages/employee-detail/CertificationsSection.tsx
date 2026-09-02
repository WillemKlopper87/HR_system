import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../../api/client'
import type { Certification } from '../../api/types'

export function CertificationsSection({ employeeId }: { employeeId: number }) {
  const [certs, setCerts] = useState<Certification[] | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function load() {
    setError(null)
    fetchAllPages<Certification>(`/certifications/?employee=${employeeId}`)
      .then(setCerts)
      .catch(() => setError('Failed to load certifications.'))
  }

  useEffect(load, [employeeId])

  return (
    <section className="detail-card">
      <div className="page-header">
        <h2>Certifications</h2>
        <button type="button" className="btn-secondary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : '+ Add certification'}
        </button>
      </div>

      {error && <p className="form-error">{error}</p>}

      {showForm && (
        <NewCertificationForm
          employeeId={employeeId}
          onCreated={() => {
            setShowForm(false)
            load()
          }}
        />
      )}

      {certs === null ? (
        <p className="empty-state">Loading…</p>
      ) : certs.length === 0 ? (
        <p className="empty-state">No certifications recorded yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Issuing body</th>
                <th>Issued</th>
                <th>Expires</th>
              </tr>
            </thead>
            <tbody>
              {certs.map((c) => (
                <tr key={c.id}>
                  <td>{c.name ?? '—'}</td>
                  <td>{c.issuing_body || '—'}</td>
                  <td>{c.issue_date ?? '—'}</td>
                  <td>
                    {c.expiry_date ?? '—'}
                    {c.is_expired && <span className="restricted-badge" style={{ marginLeft: 6 }}>Expired</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function NewCertificationForm({ employeeId, onCreated }: { employeeId: number; onCreated: () => void }) {
  const [name, setName] = useState('')
  const [issuingBody, setIssuingBody] = useState('')
  const [issueDate, setIssueDate] = useState('')
  const [expiryDate, setExpiryDate] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await api.post('/certifications/', {
        employee: employeeId, name, issuing_body: issuingBody,
        issue_date: issueDate || null, expiry_date: expiryDate || null,
      })
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
        Name
        <input value={name} onChange={(e) => setName(e.target.value)} required />
      </label>
      <label>
        Issuing body
        <input value={issuingBody} onChange={(e) => setIssuingBody(e.target.value)} />
      </label>
      <label>
        Issue date
        <input type="date" value={issueDate} onChange={(e) => setIssueDate(e.target.value)} />
      </label>
      <label>
        Expiry date
        <input type="date" value={expiryDate} onChange={(e) => setExpiryDate(e.target.value)} />
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Adding…' : 'Add certification'}
        </button>
      </div>
    </form>
  )
}
