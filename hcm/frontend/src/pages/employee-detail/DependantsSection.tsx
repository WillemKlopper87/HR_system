import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../../api/client'
import { DEPENDANT_RELATIONSHIP_LABELS, type Dependant, type DependantRelationship } from '../../api/types'

export function DependantsSection({ employeeId }: { employeeId: number }) {
  const [dependants, setDependants] = useState<Dependant[] | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function load() {
    setError(null)
    fetchAllPages<Dependant>(`/dependants/?employee=${employeeId}`)
      .then(setDependants)
      .catch(() => setError('Failed to load dependants.'))
  }

  useEffect(load, [employeeId])

  async function handleDelete(dependant: Dependant) {
    if (!window.confirm(`Remove ${dependant.first_name} ${dependant.last_name}?`)) return
    try {
      await api.delete(`/dependants/${dependant.id}/`)
      load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Delete failed.')
    }
  }

  return (
    <section className="detail-card">
      <div className="page-header">
        <h2>Dependants</h2>
        <button type="button" className="btn-secondary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : '+ Add dependant'}
        </button>
      </div>
      {error && <p className="form-error">{error}</p>}
      {showForm && (
        <NewDependantForm
          employeeId={employeeId}
          onCreated={() => {
            setShowForm(false)
            load()
          }}
        />
      )}
      {dependants === null ? (
        <p className="empty-state">Loading…</p>
      ) : dependants.length === 0 ? (
        <p className="empty-state">No dependants recorded.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Relationship</th>
                <th>Date of birth</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {dependants.map((d) => (
                <tr key={d.id}>
                  <td>{d.first_name} {d.last_name}</td>
                  <td>{DEPENDANT_RELATIONSHIP_LABELS[d.relationship]}</td>
                  <td>{d.date_of_birth ?? '—'}</td>
                  <td>
                    <button type="button" className="btn-link" onClick={() => void handleDelete(d)}>Delete</button>
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

function NewDependantForm({ employeeId, onCreated }: { employeeId: number; onCreated: () => void }) {
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [relationship, setRelationship] = useState<DependantRelationship>('child')
  const [dateOfBirth, setDateOfBirth] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await api.post('/dependants/', {
        employee: employeeId, first_name: firstName, last_name: lastName,
        relationship, date_of_birth: dateOfBirth || null,
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
        First name
        <input value={firstName} onChange={(e) => setFirstName(e.target.value)} required />
      </label>
      <label>
        Last name
        <input value={lastName} onChange={(e) => setLastName(e.target.value)} required />
      </label>
      <label>
        Relationship
        <select value={relationship} onChange={(e) => setRelationship(e.target.value as DependantRelationship)}>
          {Object.entries(DEPENDANT_RELATIONSHIP_LABELS).map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
      </label>
      <label>
        Date of birth
        <input type="date" value={dateOfBirth} onChange={(e) => setDateOfBirth(e.target.value)} />
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Adding…' : 'Add dependant'}
        </button>
      </div>
    </form>
  )
}
