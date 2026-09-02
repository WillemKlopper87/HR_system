import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../../api/client'
import type { EmergencyContact } from '../../api/types'

export function EmergencyContactsSection({ employeeId }: { employeeId: number }) {
  const [contacts, setContacts] = useState<EmergencyContact[] | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function load() {
    setError(null)
    fetchAllPages<EmergencyContact>(`/emergency-contacts/?employee=${employeeId}`)
      .then(setContacts)
      .catch(() => setError('Failed to load emergency contacts.'))
  }

  useEffect(load, [employeeId])

  async function handleDelete(contact: EmergencyContact) {
    if (!window.confirm(`Remove ${contact.name}?`)) return
    try {
      await api.delete(`/emergency-contacts/${contact.id}/`)
      load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Delete failed.')
    }
  }

  return (
    <section className="detail-card">
      <div className="page-header">
        <h2>Emergency contacts</h2>
        <button type="button" className="btn-secondary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : '+ Add contact'}
        </button>
      </div>
      {error && <p className="form-error">{error}</p>}
      {showForm && (
        <NewEmergencyContactForm
          employeeId={employeeId}
          onCreated={() => {
            setShowForm(false)
            load()
          }}
        />
      )}
      {contacts === null ? (
        <p className="empty-state">Loading…</p>
      ) : contacts.length === 0 ? (
        <p className="empty-state">No emergency contacts recorded.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Relationship</th>
                <th>Phone</th>
                <th>Primary</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {contacts.map((c) => (
                <tr key={c.id}>
                  <td>{c.name}</td>
                  <td>{c.relationship || '—'}</td>
                  <td>{c.phone}</td>
                  <td>{c.is_primary ? 'Yes' : ''}</td>
                  <td>
                    <button type="button" className="btn-link" onClick={() => void handleDelete(c)}>Delete</button>
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

function NewEmergencyContactForm({ employeeId, onCreated }: { employeeId: number; onCreated: () => void }) {
  const [name, setName] = useState('')
  const [relationship, setRelationship] = useState('')
  const [phone, setPhone] = useState('')
  const [isPrimary, setIsPrimary] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await api.post('/emergency-contacts/', {
        employee: employeeId, name, relationship, phone, is_primary: isPrimary,
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
        Relationship
        <input value={relationship} onChange={(e) => setRelationship(e.target.value)} placeholder="e.g. Spouse" />
      </label>
      <label>
        Phone
        <input value={phone} onChange={(e) => setPhone(e.target.value)} required />
      </label>
      <label>
        <input type="checkbox" checked={isPrimary} onChange={(e) => setIsPrimary(e.target.checked)} /> Primary contact
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Adding…' : 'Add contact'}
        </button>
      </div>
    </form>
  )
}
