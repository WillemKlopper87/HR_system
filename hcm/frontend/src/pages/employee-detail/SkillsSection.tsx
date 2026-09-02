import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../../api/client'
import type { EmployeeSkill, Skill } from '../../api/types'

export function SkillsSection({ employeeId }: { employeeId: number }) {
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
