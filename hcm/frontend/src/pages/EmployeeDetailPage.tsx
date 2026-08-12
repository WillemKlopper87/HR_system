import { useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError, fetchAllPages } from '../api/client'
import { useReferenceData } from '../api/ReferenceDataContext'
import { useAuth } from '../auth/AuthContext'
import type { Employee, EmployeeVersion, Feedback, Goal } from '../api/types'

/** Renders "Restricted" when the key is absent from the API response (the
 * tiered serializer stripped it — the viewer's role lacks read access to
 * that field), vs the actual value — including a deliberately blank one —
 * when the key is present. This is what "RBAC-aware field visibility"
 * means in practice: the UI reflects exactly what the server decided to
 * send, it doesn't re-implement the access decision. */
function Field({ label, obj, field }: { label: string; obj: object; field: string }) {
  const present = field in obj
  const value = (obj as Record<string, unknown>)[field]
  return (
    <div className="detail-field">
      <dt>{label}</dt>
      <dd>
        {!present ? (
          <span className="restricted-badge" title="Not visible to your role">
            Restricted
          </span>
        ) : value === '' || value === null || value === undefined ? (
          '—'
        ) : (
          String(value)
        )}
      </dd>
    </div>
  )
}

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

      {employee && <GoalsSection employeeId={employee.id} />}
      {employee && <FeedbackSection employeeId={employee.id} />}
    </div>
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
