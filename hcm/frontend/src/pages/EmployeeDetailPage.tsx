import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Field } from '../components/Field'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError, fetchAllPages } from '../api/client'
import { useReferenceData } from '../api/useReferenceData'
import { useAuth } from '../auth/useAuth'
import {
  DEPENDANT_RELATIONSHIP_LABELS,
  EMPLOYEE_DOCUMENT_CONSENT_REQUIRED_TYPES,
  EMPLOYEE_DOCUMENT_TYPE_LABELS,
  SUCCESSION_READINESS_LABELS,
  type Certification,
  type CriticalPost,
  type Dependant,
  type DependantRelationship,
  type EmergencyContact,
  type Employee,
  type EmployeeDocument,
  type EmployeeDocumentType,
  type EmployeeSkill,
  type EmployeeVersion,
  type Feedback,
  type Goal,
  type Position,
  type Skill,
  type SuccessionCandidate,
  type TrainingRecord,
} from '../api/types'

/** Renders "Restricted" when the key is absent from the API response (the
 * tiered serializer stripped it — the viewer's role lacks read access to
 * that field), vs the actual value — including a deliberately blank one —
 * when the key is present. This is what "RBAC-aware field visibility"
 * means in practice: the UI reflects exactly what the server decided to
 * send, it doesn't re-implement the access decision. */
export function EmployeeDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [employee, setEmployee] = useState<Employee | null>(null)
  const [history, setHistory] = useState<EmployeeVersion[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { departments, occupationalLevels, jobGrades, locations } = useReferenceData()

  useEffect(() => {
    if (!id) return
    let cancelled = false
    setEmployee(null)
    setHistory(null)
    setError(null)

    api
      .get<Employee>(`/employees/${id}/`)
      .then((emp) => !cancelled && setEmployee(emp))
      .catch((err) => {
        if (cancelled) return
        setError(err instanceof ApiError && err.status === 403 ? "You don't have access to this record." : 'Failed to load employee.')
      })

    fetchAllPages<EmployeeVersion>(`/employee-versions/?employee=${id}`)
      .then((rows) => !cancelled && setHistory(rows))
      .catch(() => undefined)

    return () => {
      cancelled = true
    }
  }, [id])

  const current = history?.find((v) => v.valid_to === null) ?? null

  return (
    <div className="page">
      <div className="page-header">
        <h1>{employee ? `${employee.first_name} ${employee.last_name}` : 'Employee'}</h1>
        <Link to="/employees" className="btn-link">
          ← Back to list
        </Link>
      </div>

      {error && <p className="form-error">{error}</p>}

      {employee && (
        <section className="detail-card">
          <h2>Identity</h2>
          <dl className="detail-grid">
            <Field label="Employee number" obj={employee} field="employee_number" />
            <Field label="Preferred name" obj={employee} field="preferred_name" />
            <Field label="Date of birth" obj={employee} field="date_of_birth" />
            <Field label="Work email" obj={employee} field="work_email" />
            <Field label="Personal email" obj={employee} field="personal_email" />
            <Field label="Phone" obj={employee} field="phone" />
            <Field label="Hire date" obj={employee} field="hire_date" />
            <Field label="National ID" obj={employee} field="national_id_number" />
            <Field label="Passport number" obj={employee} field="passport_number" />
          </dl>
        </section>
      )}

      {current && (
        <section className="detail-card">
          <h2>Current assignment (as at today)</h2>
          <dl className="detail-grid">
            <div className="detail-field">
              <dt>Department</dt>
              <dd>{departments.get(current.department)?.name ?? '—'}</dd>
            </div>
            <Field label="Job title" obj={current} field="job_title" />
            <div className="detail-field">
              <dt>Occupational level</dt>
              <dd>{occupationalLevels.get(current.occupational_level)?.name ?? '—'}</dd>
            </div>
            <div className="detail-field">
              <dt>Job grade</dt>
              <dd>{current.job_grade ? (jobGrades.get(current.job_grade)?.name ?? '—') : '—'}</dd>
            </div>
            <div className="detail-field">
              <dt>Location</dt>
              <dd>{locations.get(current.location)?.name ?? '—'}</dd>
            </div>
            <Field label="Employment status" obj={current} field="employment_status" />
            <Field label="Citizenship status" obj={current} field="citizenship_status" />
            <Field label="Race" obj={current} field="race" />
            <Field label="Gender" obj={current} field="gender" />
            <Field label="Disability status" obj={current} field="disability_status" />
          </dl>
        </section>
      )}

      {history && history.length > 1 && (
        <section className="detail-card">
          <h2>History</h2>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Valid from</th>
                  <th>Valid to</th>
                  <th>Department</th>
                  <th>Employment status</th>
                </tr>
              </thead>
              <tbody>
                {history.map((v) => (
                  <tr key={v.id}>
                    <td>{v.valid_from}</td>
                    <td>{v.valid_to ?? 'current'}</td>
                    <td>{departments.get(v.department)?.name ?? '—'}</td>
                    <td>{v.employment_status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {employee && <SkillsSection employeeId={employee.id} />}
      {employee && <CertificationsSection employeeId={employee.id} />}
      {employee && <TrainingSection employeeId={employee.id} />}
      {employee && <GoalsSection employeeId={employee.id} />}
      {employee && <FeedbackSection employeeId={employee.id} />}
      {employee && <DocumentsSection employeeId={employee.id} />}
      {employee && <DependantsSection employeeId={employee.id} />}
      {employee && <EmergencyContactsSection employeeId={employee.id} />}
      {employee && <SuccessionSection employeeId={employee.id} />}
    </div>
  )
}

// C6 (docs/superpowers/specs/2026-08-25-succession-talent-pools-design.md
// §2.5/§2.6): read-only "career path" view for hr_admin/auditor only, and
// never for the employee viewing their own record — even for an hr_admin
// looking at their own row. This client-side gate is belt-and-braces; the
// real guarantee is the backend's own get_queryset self-exclusion (spec
// §5.2), which holds even if this check were bypassed entirely.

function SuccessionSection({ employeeId }: { employeeId: number }) {
  const { hasRole, user } = useAuth()
  const [candidates, setCandidates] = useState<SuccessionCandidate[] | null>(null)
  const [criticalPosts, setCriticalPosts] = useState<CriticalPost[]>([])
  const [positions, setPositions] = useState<Position[]>([])
  const [error, setError] = useState<string | null>(null)

  const canView = (hasRole('hr_admin') || hasRole('auditor')) && employeeId !== user?.employee_id

  useEffect(() => {
    if (!canView) return
    let cancelled = false
    Promise.all([
      fetchAllPages<SuccessionCandidate>(`/succession-candidates/?employee=${employeeId}&active=true`),
      fetchAllPages<CriticalPost>('/critical-posts/'),
      fetchAllPages<Position>('/positions/'),
    ])
      .then(([c, cp, p]) => {
        if (cancelled) return
        setCandidates(c)
        setCriticalPosts(cp)
        setPositions(p)
      })
      .catch(() => !cancelled && setError('Failed to load succession data.'))
    return () => {
      cancelled = true
    }
  }, [employeeId, canView])

  if (!canView) return null

  const criticalPostById = new Map(criticalPosts.map((c) => [c.id, c]))
  const positionById = new Map(positions.map((p) => [p.id, p]))

  return (
    <section className="detail-card">
      <h2>Succession</h2>
      <p className="hint-text">
        Critical posts this employee is currently an active successor candidate for. Visible to hr_admin/auditor
        only — not to this employee, and not on their own record even for you.
      </p>
      {error && <p className="form-error">{error}</p>}
      {candidates === null ? (
        <p className="empty-state">Loading…</p>
      ) : candidates.length === 0 ? (
        <p className="empty-state">Not currently nominated as a successor for any critical post.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Post</th>
                <th>Readiness</th>
                <th>Notes</th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((c) => {
                const criticalPost = criticalPostById.get(c.critical_post)
                const position = criticalPost ? positionById.get(criticalPost.position) : undefined
                return (
                  <tr key={c.id}>
                    <td>{position ? `${position.post_number} — ${position.title}` : `#${c.critical_post}`}</td>
                    <td>
                      <span className="status-badge">{SUCCESSION_READINESS_LABELS[c.readiness]}</span>
                    </td>
                    <td>{c.notes || '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

// C2 (docs/superpowers/specs/2026-08-25-employee-documents-popia-design.md):
// documents/dependants/emergency-contacts management for whoever this page
// is already open to — hr_admin managing anyone, or an employee viewing
// their own record (self-or-hr_admin is enforced server-side either way;
// a stranger simply gets an empty/403'd section, same as every other
// section on this page relies on row-scope to hide, not client logic).

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

function SkillsSection({ employeeId }: { employeeId: number }) {
  const [skills, setSkills] = useState<EmployeeSkill[] | null>(null)
  const [catalog, setCatalog] = useState<Skill[]>([])
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function load() {
    setError(null)
    Promise.all([fetchAllPages<EmployeeSkill>(`/employee-skills/?employee=${employeeId}`), fetchAllPages<Skill>('/skills/')])
      .then(([es, cat]) => {
        setSkills(es)
        setCatalog(cat)
      })
      .catch(() => setError('Failed to load skills.'))
  }

  useEffect(load, [employeeId])

  const skillById = useMemo(() => new Map(catalog.map((s) => [s.id, s])), [catalog])

  return (
    <section className="detail-card">
      <div className="page-header">
        <h2>Skills</h2>
        <button type="button" className="btn-secondary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : '+ Add skill'}
        </button>
      </div>

      {error && <p className="form-error">{error}</p>}

      {showForm && (
        <NewSkillForm
          employeeId={employeeId}
          catalog={catalog}
          onCreated={() => {
            setShowForm(false)
            load()
          }}
        />
      )}

      {skills === null ? (
        <p className="empty-state">Loading…</p>
      ) : skills.length === 0 ? (
        <p className="empty-state">No skills recorded yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Skill</th>
                <th>Proficiency</th>
                <th>Acquired</th>
              </tr>
            </thead>
            <tbody>
              {skills.map((es) => (
                <tr key={es.id}>
                  <td>{skillById.get(es.skill)?.name ?? `#${es.skill}`}</td>
                  <td>
                    <span className="status-badge">{es.proficiency ?? '—'}</span>
                  </td>
                  <td>{es.acquired_date ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function NewSkillForm({
  employeeId, catalog, onCreated,
}: { employeeId: number; catalog: Skill[]; onCreated: () => void }) {
  const [skillId, setSkillId] = useState<number | ''>('')
  const [proficiency, setProficiency] = useState('intermediate')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!skillId) {
      setError('Select a skill.')
      return
    }
    setSubmitting(true)
    try {
      await api.post('/employee-skills/', { employee: employeeId, skill: skillId, proficiency })
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
        Skill
        <select value={skillId} onChange={(e) => setSkillId(e.target.value ? Number(e.target.value) : '')} required>
          <option value="">— Select —</option>
          {catalog.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Proficiency
        <select value={proficiency} onChange={(e) => setProficiency(e.target.value)}>
          <option value="beginner">Beginner</option>
          <option value="intermediate">Intermediate</option>
          <option value="advanced">Advanced</option>
          <option value="expert">Expert</option>
        </select>
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Adding…' : 'Add skill'}
        </button>
      </div>
    </form>
  )
}

function CertificationsSection({ employeeId }: { employeeId: number }) {
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

function TrainingSection({ employeeId }: { employeeId: number }) {
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

function GoalsSection({ employeeId }: { employeeId: number }) {
  const [goals, setGoals] = useState<Goal[] | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function load() {
    setError(null)
    fetchAllPages<Goal>(`/goals/?employee=${employeeId}`)
      .then(setGoals)
      .catch(() => setError('Failed to load goals.'))
  }

  useEffect(load, [employeeId])

  return (
    <section className="detail-card">
      <div className="page-header">
        <h2>Goals</h2>
        <button type="button" className="btn-secondary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : '+ Add goal'}
        </button>
      </div>

      {error && <p className="form-error">{error}</p>}

      {showForm && (
        <NewGoalForm
          employeeId={employeeId}
          onCreated={() => {
            setShowForm(false)
            load()
          }}
        />
      )}

      {goals === null ? (
        <p className="empty-state">Loading…</p>
      ) : goals.length === 0 ? (
        <p className="empty-state">No goals yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Target date</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {goals.map((g) => (
                <tr key={g.id}>
                  <td>{g.title}</td>
                  <td>{g.target_date ?? '—'}</td>
                  <td>
                    <span className="status-badge">{g.status}</span>
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

function NewGoalForm({ employeeId, onCreated }: { employeeId: number; onCreated: () => void }) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [targetDate, setTargetDate] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await api.post('/goals/', { employee: employeeId, title, description, target_date: targetDate || null })
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
        Title
        <input value={title} onChange={(e) => setTitle(e.target.value)} required />
      </label>
      <label>
        Target date
        <input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
      </label>
      <label style={{ minWidth: 260 }}>
        Description
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Adding…' : 'Add goal'}
        </button>
      </div>
    </form>
  )
}

function FeedbackSection({ employeeId }: { employeeId: number }) {
  const { user } = useAuth()
  const [feedback, setFeedback] = useState<Feedback[] | null>(null)
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  function load() {
    setError(null)
    fetchAllPages<Feedback>(`/feedback/?employee=${employeeId}`)
      .then(setFeedback)
      .catch(() => setError('Failed to load feedback.'))
  }

  useEffect(load, [employeeId])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await api.post('/feedback/', { employee: employeeId, text })
      setText('')
      load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Submit failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="detail-card">
      <h2>Feedback</h2>

      {error && <p className="form-error">{error}</p>}

      {feedback === null ? (
        <p className="empty-state">Loading…</p>
      ) : feedback.length === 0 ? (
        <p className="empty-state">No feedback yet.</p>
      ) : (
        <ul className="breakdown-list" style={{ marginBottom: 16 }}>
          {feedback.map((f) => (
            <li key={f.id} style={{ display: 'block' }}>
              <span className="status-badge">{f.feedback_type}</span>{' '}
              <span>{f.text}</span>{' '}
              <span className="hint-text">— {new Date(f.created_at).toLocaleDateString()}</span>
            </li>
          ))}
        </ul>
      )}

      {employeeId !== user?.employee_id && (
        <form className="inline-form" onSubmit={handleSubmit}>
          <label style={{ minWidth: 320 }}>
            Give feedback
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} required />
          </label>
          <div className="form-actions">
            <button type="submit" className="btn-primary" disabled={submitting || !text}>
              {submitting ? 'Sending…' : 'Send feedback'}
            </button>
          </div>
        </form>
      )}
    </section>
  )
}
