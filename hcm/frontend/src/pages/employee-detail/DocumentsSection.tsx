import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../../api/client'
import {
  EMPLOYEE_DOCUMENT_CONSENT_REQUIRED_TYPES,
  EMPLOYEE_DOCUMENT_TYPE_LABELS,
  type EmployeeDocument,
  type EmployeeDocumentType,
} from '../../api/types'

// C2 (docs/superpowers/specs/2026-08-25-employee-documents-popia-design.md):
// documents/dependants/emergency-contacts management for whoever this page
// is already open to — hr_admin managing anyone, or an employee viewing
// their own record (self-or-hr_admin is enforced server-side either way;
// a stranger simply gets an empty/403'd section, same as every other
// section on this page relies on row-scope to hide, not client logic).

export function DocumentsSection({ employeeId }: { employeeId: number }) {
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
        <h2>Documents</h2>
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
        <p className="empty-state">No documents on file.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Title</th>
                <th>Tier</th>
                <th>Uploaded</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((d) => (
                <tr key={d.id}>
                  <td>{EMPLOYEE_DOCUMENT_TYPE_LABELS[d.document_type]}</td>
                  <td>{d.title}</td>
                  <td>{d.tier}</td>
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
