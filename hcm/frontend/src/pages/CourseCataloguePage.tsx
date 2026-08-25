import { useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import { useAllPages } from '../api/hooks'
import { useReferenceData } from '../api/ReferenceDataContext'
import type { Course, CourseRequirement } from '../api/types'

export function CourseCataloguePage() {
  const { data: courses, error: coursesError, reload: reloadCourses } = useAllPages<Course>(
    '/courses/', [], 'Failed to load the course catalogue.',
  )
  const { data: requirements, error: requirementsError, reload: reloadRequirements } = useAllPages<CourseRequirement>(
    '/course-requirements/', [], 'Failed to load requirement rules.',
  )
  const ref = useReferenceData()
  const [showCourseForm, setShowCourseForm] = useState(false)
  const [showRequirementForm, setShowRequirementForm] = useState(false)

  const coursesById = new Map((courses ?? []).map((c) => [c.id, c]))
  const mandatoryCourses = (courses ?? []).filter((c) => c.mandatory)

  return (
    <div className="page">
      <div className="page-header">
        <h1>Course Catalogue</h1>
        <button type="button" className="btn-primary" onClick={() => setShowCourseForm((v) => !v)}>
          {showCourseForm ? 'Cancel' : '+ New course'}
        </button>
      </div>
      <p className="hint-text">
        Mark a course "mandatory" here before it can be targeted by a requirement rule below — see the
        Requirements section.
      </p>

      {coursesError && <p className="form-error">{coursesError}</p>}

      {showCourseForm && (
        <NewCourseForm onCreated={() => { setShowCourseForm(false); reloadCourses() }} />
      )}

      {courses === null ? (
        <p className="empty-state">Loading…</p>
      ) : courses.length === 0 ? (
        <p className="empty-state">No courses in the catalogue yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Provider</th>
                <th>Hours</th>
                <th>Mandatory</th>
                <th>Renews every</th>
                <th>Active</th>
              </tr>
            </thead>
            <tbody>
              {courses.map((c) => (
                <tr key={c.id}>
                  <td>{c.name}</td>
                  <td>{c.provider || '—'}</td>
                  <td>{c.hours ?? '—'}</td>
                  <td>
                    {c.mandatory ? <span className="status-badge">Mandatory</span> : <span>Elective</span>}
                  </td>
                  <td>{c.validity_days ? `${c.validity_days} days` : 'Never expires'}</td>
                  <td>{c.active ? 'Active' : <span className="restricted-badge">Inactive</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="page-header" style={{ marginTop: '2rem' }}>
        <h2>Requirements (who must complete a mandatory course, and by when)</h2>
        <button type="button" className="btn-primary" onClick={() => setShowRequirementForm((v) => !v)}>
          {showRequirementForm ? 'Cancel' : '+ New requirement'}
        </button>
      </div>
      <p className="hint-text">
        Leave department and/or occupational level unset for an organisation-wide mandate. The due date for
        anyone newly in scope is whichever is later: this rule's effective-from date, or the date they entered
        that department/level.
      </p>

      {requirementsError && <p className="form-error">{requirementsError}</p>}

      {showRequirementForm && (
        <NewRequirementForm
          mandatoryCourses={mandatoryCourses}
          onCreated={() => { setShowRequirementForm(false); reloadRequirements() }}
        />
      )}

      {requirements === null ? (
        <p className="empty-state">Loading…</p>
      ) : requirements.length === 0 ? (
        <p className="empty-state">No requirement rules yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Course</th>
                <th>Department</th>
                <th>Occupational level</th>
                <th>Effective from</th>
                <th>Due within</th>
                <th>Active</th>
              </tr>
            </thead>
            <tbody>
              {requirements.map((r) => (
                <tr key={r.id}>
                  <td>{coursesById.get(r.course)?.name ?? `#${r.course}`}</td>
                  <td>{r.department ? ref.departments.get(r.department)?.name ?? `#${r.department}` : 'Org-wide'}</td>
                  <td>
                    {r.occupational_level
                      ? ref.occupationalLevels.get(r.occupational_level)?.name ?? `#${r.occupational_level}`
                      : 'All levels'}
                  </td>
                  <td>{r.effective_from}</td>
                  <td>{r.due_within_days} days</td>
                  <td>{r.active ? 'Active' : <span className="restricted-badge">Retired</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function NewCourseForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState('')
  const [provider, setProvider] = useState('')
  const [hours, setHours] = useState('')
  const [mandatory, setMandatory] = useState(false)
  const [validityDays, setValidityDays] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await api.post('/courses/', {
        name,
        provider,
        hours: hours || null,
        mandatory,
        validity_days: validityDays ? Number(validityDays) : null,
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
        Course name
        <input value={name} onChange={(e) => setName(e.target.value)} required />
      </label>
      <label>
        Provider
        <input value={provider} onChange={(e) => setProvider(e.target.value)} />
      </label>
      <label>
        Hours
        <input type="number" min={0} step="0.5" value={hours} onChange={(e) => setHours(e.target.value)} />
      </label>
      <label>
        <input type="checkbox" checked={mandatory} onChange={(e) => setMandatory(e.target.checked)} />
        {' '}Mandatory / compliance course
      </label>
      <label>
        Renews every (days, blank = never expires)
        <input
          type="number" min={1} value={validityDays} onChange={(e) => setValidityDays(e.target.value)}
        />
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Creating…' : 'Create course'}
        </button>
      </div>
    </form>
  )
}

function NewRequirementForm({
  mandatoryCourses, onCreated,
}: { mandatoryCourses: Course[]; onCreated: () => void }) {
  const ref = useReferenceData()
  const [course, setCourse] = useState<number | ''>('')
  const [department, setDepartment] = useState<number | ''>('')
  const [occupationalLevel, setOccupationalLevel] = useState<number | ''>('')
  const [effectiveFrom, setEffectiveFrom] = useState('')
  const [dueWithinDays, setDueWithinDays] = useState('90')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!course || !effectiveFrom || !dueWithinDays) {
      setError('Course, effective-from date, and due-within days are required.')
      return
    }
    setSubmitting(true)
    try {
      await api.post('/course-requirements/', {
        course,
        department: department || null,
        occupational_level: occupationalLevel || null,
        effective_from: effectiveFrom,
        due_within_days: Number(dueWithinDays),
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
        Course (mandatory only)
        <select value={course} onChange={(e) => setCourse(e.target.value ? Number(e.target.value) : '')} required>
          <option value="">— Select —</option>
          {mandatoryCourses.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
        {mandatoryCourses.length === 0 && (
          <span className="hint-text">No mandatory courses yet — mark one mandatory above first.</span>
        )}
      </label>
      <label>
        Department (blank = org-wide)
        <select value={department} onChange={(e) => setDepartment(e.target.value ? Number(e.target.value) : '')}>
          <option value="">— All departments —</option>
          {ref.departmentList.map((d) => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </select>
      </label>
      <label>
        Occupational level (blank = all levels)
        <select
          value={occupationalLevel}
          onChange={(e) => setOccupationalLevel(e.target.value ? Number(e.target.value) : '')}
        >
          <option value="">— All levels —</option>
          {ref.occupationalLevelList.map((l) => (
            <option key={l.id} value={l.id}>{l.name}</option>
          ))}
        </select>
      </label>
      <label>
        Effective from
        <input type="date" value={effectiveFrom} onChange={(e) => setEffectiveFrom(e.target.value)} required />
      </label>
      <label>
        Due within (days)
        <input
          type="number" min={1} value={dueWithinDays} onChange={(e) => setDueWithinDays(e.target.value)} required
        />
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Creating…' : 'Create requirement'}
        </button>
      </div>
    </form>
  )
}
