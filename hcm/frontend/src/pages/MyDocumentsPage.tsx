import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import {
  DATA_SUBJECT_REQUEST_STATUS_LABELS,
  DATA_SUBJECT_REQUEST_TYPE_LABELS,
  DEPENDANT_RELATIONSHIP_LABELS,
  EMPLOYEE_DOCUMENT_CONSENT_REQUIRED_TYPES,
  EMPLOYEE_DOCUMENT_TYPE_LABELS,
  type DataSubjectRequest,
  type DataSubjectRequestType,
  type Dependant,
  type DependantRelationship,
  type EmergencyContact,
  type EmployeeDocument,
  type EmployeeDocumentType,
} from '../api/types'

/** Self-service home for C2: my documents, my dependants, my emergency
 * contacts, and the POPIA export/erasure request workflow — one page,
 * matching the shape of MyBenefitsPage/MyPoliciesPage's combined layout
 * rather than four separate nav entries. */
export function MyDocumentsPage() {
  const { user } = useAuth()
  const employeeId = user?.employee_id ?? null

  if (!employeeId) return <p className="empty-state">Loading…</p>

  return (
    <div className="page">
      <div className="page-header">
        <h1>My Documents</h1>
      </div>
      <p className="hint-text">
        Your personal documents, dependants, emergency contacts, and data rights under POPIA.
      </p>
      <DocumentsSection employeeId={employeeId} />
      <DependantsSection employeeId={employeeId} />
      <EmergencyContactsSection employeeId={employeeId} />
      <DataSubjectRequestsSection employeeId={employeeId} />
    </div>
  )
}

function DocumentsSection({ employeeId }: { employeeId: number }) {
  const [documents, setDocuments] = useState<EmployeeDocument[] | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function load() {
    setError(null)
    fetchAllPages<EmployeeDocument>(`/employee-documents/?employee=${employeeId}`)
      .then(setDocuments)
      .catch(() => setError('Failed to load documents.'))
  }

  useEffect(load, [employeeId])

  async function handleDelete(document: EmployeeDocument) {
    if (!window.confirm(`Delete "${document.title}"? This cannot be undone.`)) return
    try {
      await api.delete(`/employee-documents/${document.id}/`)
      load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Delete failed.')
    }
  }

  return (
    <section className="detail-card">
      <div className="page-header">
        <h2>My documents</h2>
        <button type="button" className="btn-secondary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : '+ Upload document'}
        </button>
      </div>
      {error && <p className="form-error">{error}</p>}
      {showForm && (
        <NewDocumentForm
          employeeId={employeeId}
          onCreated={() => {
            setShowForm(false)
            load()
          }}
        />
      )}
      {documents === null ? (
        <p className="empty-state">Loading…</p>
      ) : documents.length === 0 ? (
        <p className="empty-state">No documents on file yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Title</th>
                <th>Uploaded</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((d) => (
                <tr key={d.id}>
                  <td>{EMPLOYEE_DOCUMENT_TYPE_LABELS[d.document_type]}</td>
                  <td>{d.title}</td>
                  <td>{new Date(d.created_at).toLocaleDateString()}</td>
                  <td>
                    <div className="form-actions">
                      <a className="btn-link" href={d.download_url} target="_blank" rel="noreferrer">
                        Download
                      </a>
                      <button type="button" className="btn-link" onClick={() => void handleDelete(d)}>
                        Delete
                      </button>
                    </div>
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

function NewDocumentForm({ employeeId, onCreated }: { employeeId: number; onCreated: () => void }) {
  const [documentType, setDocumentType] = useState<EmployeeDocumentType>('qualification')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [capturingConsent, setCapturingConsent] = useState(false)

  const consentRequired = EMPLOYEE_DOCUMENT_CONSENT_REQUIRED_TYPES.includes(documentType)

  async function handleCaptureConsent() {
    setError(null)
    setCapturingConsent(true)
    try {
      await api.post('/employee-documents/consent/', { employee: employeeId })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not record consent.')
    } finally {
      setCapturingConsent(false)
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!file) return
    setError(null)
    setSubmitting(true)
    try {
      const form = new FormData()
      form.append('employee', String(employeeId))
      form.append('document_type', documentType)
      form.append('title', title)
      form.append('description', description)
      form.append('file', file)
      await api.postForm('/employee-documents/', form)
      onCreated()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Upload failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit} style={{ flexDirection: 'column', alignItems: 'stretch' }}>
      <label>
        Document type
        <select value={documentType} onChange={(e) => setDocumentType(e.target.value as EmployeeDocumentType)}>
          {Object.entries(EMPLOYEE_DOCUMENT_TYPE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
      </label>
      <label>
        Title
        <input value={title} onChange={(e) => setTitle(e.target.value)} required />
      </label>
      <label>
        Description
        <textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
      </label>
      <label>
        File (PDF, JPEG, PNG, or Word)
        <input
          type="file" accept=".pdf,.jpg,.jpeg,.png,.docx"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)} required
        />
      </label>
      {consentRequired && (
        <p className="hint-text">
          This document type requires consent to be captured before it can be uploaded.{' '}
          <button type="button" className="btn-link" disabled={capturingConsent} onClick={() => void handleCaptureConsent()}>
            {capturingConsent ? 'Recording…' : 'Capture consent now'}
          </button>
        </p>
      )}
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting || !file}>
          {submitting ? 'Uploading…' : 'Upload'}
        </button>
      </div>
    </form>
  )
}

function DependantsSection({ employeeId }: { employeeId: number }) {
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
        <h2>My dependants</h2>
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
        <p className="empty-state">No dependants recorded yet.</p>
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

function EmergencyContactsSection({ employeeId }: { employeeId: number }) {
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
        <h2>My emergency contacts</h2>
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
        <p className="empty-state">No emergency contacts recorded yet.</p>
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

function DataSubjectRequestsSection({ employeeId }: { employeeId: number }) {
  const [requests, setRequests] = useState<DataSubjectRequest[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notes, setNotes] = useState('')
  const [busyType, setBusyType] = useState<DataSubjectRequestType | null>(null)

  function load() {
    setError(null)
    fetchAllPages<DataSubjectRequest>('/data-subject-requests/')
      .then(setRequests)
      .catch(() => setError('Failed to load your requests.'))
  }

  useEffect(load, [employeeId])

  const hasOpenRequest = (type: DataSubjectRequestType) =>
    requests?.some((r) => r.request_type === type && r.status === 'submitted') ?? false

  async function submit(type: DataSubjectRequestType) {
    setError(null)
    setBusyType(type)
    try {
      await api.post('/data-subject-requests/', { employee: employeeId, request_type: type, request_notes: notes })
      setNotes('')
      load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not submit your request.')
    } finally {
      setBusyType(null)
    }
  }

  return (
    <section className="detail-card">
      <h2>My data rights (POPIA)</h2>
      <p className="hint-text">
        Request an export of your personal data, or request erasure of your documents, dependants, and emergency
        contacts. Every request is reviewed and actioned by HR — an erasure request never touches your employment
        history or audit records, which must be retained regardless.
      </p>
      {error && <p className="form-error">{error}</p>}
      <label>
        Notes (optional)
        <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      <div className="form-actions">
        <button
          type="button" className="btn-secondary" disabled={busyType !== null || hasOpenRequest('export')}
          onClick={() => void submit('export')}
        >
          {hasOpenRequest('export') ? 'Export request pending' : 'Request data export'}
        </button>
        <button
          type="button" className="btn-secondary" disabled={busyType !== null || hasOpenRequest('erasure')}
          onClick={() => void submit('erasure')}
        >
          {hasOpenRequest('erasure') ? 'Erasure request pending' : 'Request erasure'}
        </button>
      </div>

      {requests === null ? (
        <p className="empty-state">Loading…</p>
      ) : requests.length === 0 ? (
        <p className="empty-state">No requests yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Status</th>
                <th>Requested</th>
                <th>Resolution</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {requests.map((r) => (
                <tr key={r.id}>
                  <td>{DATA_SUBJECT_REQUEST_TYPE_LABELS[r.request_type]}</td>
                  <td><span className="status-badge">{DATA_SUBJECT_REQUEST_STATUS_LABELS[r.status]}</span></td>
                  <td>{new Date(r.requested_at).toLocaleDateString()}</td>
                  <td>{r.resolution_notes || '—'}</td>
                  <td>
                    {r.download_url && (
                      <a className="btn-link" href={r.download_url} target="_blank" rel="noreferrer">Download</a>
                    )}
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
