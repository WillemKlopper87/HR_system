import { useMemo, useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../api/client'
import { useApiQuery } from '../api/hooks'
import {
  ASSESSMENT_STATUS_LABELS,
  ASSESSMENT_TYPE_LABELS,
  type AssessmentAssignment,
  type AssessmentType,
  type Employee,
} from '../api/types'

export function AssessmentsPage() {
  const [showForm, setShowForm] = useState(false)

  const { data, error: loadError, reload: load } = useApiQuery(
    () =>
      Promise.all([
        fetchAllPages<AssessmentAssignment>('/assessment-assignments/'),
        fetchAllPages<Employee>('/employees/'),
      ]).then(([assignments, employees]) => {
        assignments = assignments.filter((row) => row.employee !== null)
        return { assignments, employees }
      }),
    [],
    { errorMessage: 'Failed to load assessment assignments.' },
  )
  const assignments = data?.assignments ?? null
  const employees = data?.employees ?? null


  const employeeById = useMemo(() => new Map((employees ?? []).map((e) => [e.id, e])), [employees])

  return (
    <div className="page">
      <div className="page-header">
        <h1>Employee Assessments</h1>
        <button type="button" className="btn-primary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : '+ Assign assessment'}
        </button>
      </div>

      <p className="hint-text">
        Psychometric/skills assessments for current employees — candidate assessments live on each applicant's own
        page. No real provider is under contract yet (see Sprint-0-Decision-Log.md); this runs against an in-process
        sandbox adapter that fulfils the same assign/status/result interface a real one would.
      </p>

      {loadError && <p className="form-error">{loadError}</p>}

      {showForm && (
        <NewAssignmentForm
          employees={employees ?? []}
          onCreated={() => {
            setShowForm(false)
            load()
          }}
        />
      )}

      {assignments === null ? (
        <p className="empty-state">Loading…</p>
      ) : assignments.length === 0 ? (
        <p className="empty-state">No assessments assigned yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Employee</th>
                <th>Type</th>
                <th>Status</th>
                <th>Result</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {assignments.map((assignment) => {
                const emp = assignment.employee !== null ? employeeById.get(assignment.employee) : undefined
                return (
                  <AssignmentRow
                    key={assignment.id}
                    assignment={assignment}
                    subjectName={emp ? `${emp.first_name} ${emp.last_name}` : `#${assignment.employee}`}
                    onChanged={load}
                  />
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function AssignmentRow({
  assignment, subjectName, onChanged,
}: { assignment: AssessmentAssignment; subjectName: string; onChanged: () => void }) {
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleSimulate() {
    setError(null)
    setBusy(true)
    try {
      await api.post(`/assessment-assignments/${assignment.id}/simulate_completion/`)
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Action failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <tr>
      <td>{subjectName}</td>
      <td>{ASSESSMENT_TYPE_LABELS[assignment.assessment_type]}</td>
      <td>
        <span className="status-badge">{ASSESSMENT_STATUS_LABELS[assignment.status]}</span>
      </td>
      <td>
        {assignment.result ? (
          <div>
            <div>{assignment.result.summary}</div>
            <div className="hint-text">Score: {assignment.result.raw_score}</div>
          </div>
        ) : (
          '—'
        )}
      </td>
      <td>
        {error && <p className="form-error">{error}</p>}
        {assignment.status !== 'completed' && (
          <button type="button" className="btn-secondary" disabled={busy} onClick={() => void handleSimulate()}>
            Simulate provider completion
          </button>
        )}
      </td>
    </tr>
  )
}

function NewAssignmentForm({ employees, onCreated }: { employees: Employee[]; onCreated: () => void }) {
  const [search, setSearch] = useState('')
  const [employee, setEmployee] = useState<number | ''>('')
  const [assessmentType, setAssessmentType] = useState<AssessmentType>('cognitive')
  const [error, setError] = useState<string | null>(null)
  const [needsConsent, setNeedsConsent] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase()
    if (!term) return employees
    return employees.filter(
      (e) =>
        e.employee_number.toLowerCase().includes(term) ||
        `${e.first_name} ${e.last_name}`.toLowerCase().includes(term),
    )
  }, [employees, search])

  async function attemptAssign() {
    await api.post('/assessment-assignments/', { employee, assessment_type: assessmentType })
    onCreated()
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setNeedsConsent(false)
    if (!employee) {
      setError('Employee is required.')
      return
    }
    setSubmitting(true)
    try {
      await attemptAssign()
    } catch (err) {
      if (err instanceof ApiError && /consent/i.test(err.message)) {
        setNeedsConsent(true)
        setError(err.message)
      } else {
        setError(err instanceof ApiError ? err.message : 'Create failed.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  async function handleCaptureConsentAndRetry() {
    setError(null)
    setSubmitting(true)
    try {
      await api.post('/assessment-assignments/consent/', { employee })
      await attemptAssign()
      setNeedsConsent(false)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Consent capture failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit}>
      <label>
        Search employee
        <input placeholder="Name or employee #…" value={search} onChange={(e) => setSearch(e.target.value)} />
      </label>
      <label>
        Employee
        <select
          value={employee}
          onChange={(e) => {
            setEmployee(e.target.value ? Number(e.target.value) : '')
            setNeedsConsent(false)
          }}
          required
        >
          <option value="">— Select —</option>
          {filtered.map((emp) => (
            <option key={emp.id} value={emp.id}>
              {emp.employee_number} — {emp.first_name} {emp.last_name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Assessment type
        <select value={assessmentType} onChange={(e) => setAssessmentType(e.target.value as AssessmentType)}>
          {Object.entries(ASSESSMENT_TYPE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>

      {error && <p className="form-error">{error}</p>}

      <div className="form-actions">
        {needsConsent ? (
          <button type="button" className="btn-primary" disabled={submitting} onClick={() => void handleCaptureConsentAndRetry()}>
            {submitting ? 'Capturing consent…' : 'Capture consent and assign'}
          </button>
        ) : (
          <button type="submit" className="btn-primary" disabled={submitting}>
            {submitting ? 'Assigning…' : 'Assign assessment'}
          </button>
        )}
      </div>
    </form>
  )
}
