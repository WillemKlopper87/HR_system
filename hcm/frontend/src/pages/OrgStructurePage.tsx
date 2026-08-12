import { useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import { useReferenceData } from '../api/ReferenceDataContext'
import { useAuth } from '../auth/AuthContext'
import type { Department, JobGrade, Location } from '../api/types'

const PROVINCES = [
  ['EC', 'Eastern Cape'], ['FS', 'Free State'], ['GP', 'Gauteng'], ['KZN', 'KwaZulu-Natal'],
  ['LP', 'Limpopo'], ['MP', 'Mpumalanga'], ['NC', 'Northern Cape'], ['NW', 'North West'],
  ['WC', 'Western Cape'], ['OUT', 'Outside South Africa'],
] as const

export function OrgStructurePage() {
  const { hasRole } = useAuth()
  const canManage = hasRole('hr_admin')
  const ref = useReferenceData()

  if (ref.loading) return <p className="empty-state">Loading…</p>

  return (
    <div className="page">
      <div className="page-header">
        <h1>Org Structure</h1>
      </div>

      <section className="detail-card">
        <h2>Departments</h2>
        <DepartmentSection departments={ref.departmentList} canManage={canManage} onChange={ref.refresh} />
      </section>

      <section className="detail-card">
        <h2>Job Grades</h2>
        <JobGradeSection
          jobGrades={ref.jobGradeList}
          occupationalLevels={ref.occupationalLevelList}
          canManage={canManage}
          onChange={ref.refresh}
        />
      </section>

      <section className="detail-card">
        <h2>Locations</h2>
        <LocationSection locations={ref.locationList} canManage={canManage} onChange={ref.refresh} />
      </section>

      <section className="detail-card">
        <h2>Occupational Levels</h2>
        <p className="hint-text">The six statutory EEA occupational levels — fixed by law, not editable here.</p>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Order</th>
                <th>Code</th>
                <th>Name</th>
              </tr>
            </thead>
            <tbody>
              {ref.occupationalLevelList.map((lvl) => (
                <tr key={lvl.id}>
                  <td>{lvl.order}</td>
                  <td>{lvl.code}</td>
                  <td>{lvl.name}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

function DepartmentSection({
  departments, canManage, onChange,
}: { departments: Department[]; canManage: boolean; onChange: () => void }) {
  const [editingId, setEditingId] = useState<number | 'new' | null>(null)
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const [parent, setParent] = useState<number | ''>('')
  const [error, setError] = useState<string | null>(null)

  function startNew() {
    setEditingId('new')
    setName('')
    setCode('')
    setParent('')
    setError(null)
  }

  function startEdit(dept: Department) {
    setEditingId(dept.id)
    setName(dept.name)
    setCode(dept.code)
    setParent(dept.parent ?? '')
    setError(null)
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    const payload = { name, code, parent: parent === '' ? null : parent }
    try {
      if (editingId === 'new') {
        await api.post('/departments/', payload)
      } else {
        await api.patch(`/departments/${editingId}/`, payload)
      }
      setEditingId(null)
      onChange()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Save failed.')
    }
  }

  async function handleDelete(id: number) {
    setError(null)
    try {
      await api.delete(`/departments/${id}/`)
      onChange()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Delete failed.')
    }
  }

  return (
    <>
      {error && <p className="form-error">{error}</p>}
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Code</th>
              <th>Name</th>
              <th>Parent</th>
              <th>Active</th>
              {canManage && <th></th>}
            </tr>
          </thead>
          <tbody>
            {departments.map((dept) => (
              <tr key={dept.id}>
                <td>{dept.code}</td>
                <td>{dept.name}</td>
                <td>{departments.find((d) => d.id === dept.parent)?.name ?? '—'}</td>
                <td>{dept.active ? 'Yes' : 'No'}</td>
                {canManage && (
                  <td className="row-actions">
                    <button type="button" className="btn-link" onClick={() => startEdit(dept)}>
                      Edit
                    </button>
                    <button type="button" className="btn-link btn-danger" onClick={() => void handleDelete(dept.id)}>
                      Delete
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {canManage && editingId === null && (
        <button type="button" className="btn-secondary" onClick={startNew}>
          + Add department
        </button>
      )}

      {canManage && editingId !== null && (
        <form className="inline-form" onSubmit={handleSubmit}>
          <label>
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label>
            Code
            <input value={code} onChange={(e) => setCode(e.target.value)} required />
          </label>
          <label>
            Parent department
            <select value={parent} onChange={(e) => setParent(e.target.value ? Number(e.target.value) : '')}>
              <option value="">— None —</option>
              {departments
                .filter((d) => d.id !== editingId)
                .map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
            </select>
          </label>
          <div className="form-actions">
            <button type="submit" className="btn-primary">
              Save
            </button>
            <button type="button" className="btn-link" onClick={() => setEditingId(null)}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </>
  )
}

function JobGradeSection({
  jobGrades, occupationalLevels, canManage, onChange,
}: { jobGrades: JobGrade[]; occupationalLevels: { id: number; name: string }[]; canManage: boolean; onChange: () => void }) {
  const [editingId, setEditingId] = useState<number | 'new' | null>(null)
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const [occupationalLevel, setOccupationalLevel] = useState<number | ''>('')
  const [error, setError] = useState<string | null>(null)

  function startNew() {
    setEditingId('new')
    setName('')
    setCode('')
    setOccupationalLevel(occupationalLevels[0]?.id ?? '')
    setError(null)
  }

  function startEdit(grade: JobGrade) {
    setEditingId(grade.id)
    setName(grade.name)
    setCode(grade.code)
    setOccupationalLevel(grade.occupational_level)
    setError(null)
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (occupationalLevel === '') {
      setError('Occupational level is required.')
      return
    }
    const payload = { name, code, occupational_level: occupationalLevel }
    try {
      if (editingId === 'new') {
        await api.post('/job-grades/', payload)
      } else {
        await api.patch(`/job-grades/${editingId}/`, payload)
      }
      setEditingId(null)
      onChange()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Save failed.')
    }
  }

  async function handleDelete(id: number) {
    setError(null)
    try {
      await api.delete(`/job-grades/${id}/`)
      onChange()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Delete failed.')
    }
  }

  return (
    <>
      {error && <p className="form-error">{error}</p>}
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Code</th>
              <th>Name</th>
              <th>Occupational level</th>
              {canManage && <th></th>}
            </tr>
          </thead>
          <tbody>
            {jobGrades.map((grade) => (
              <tr key={grade.id}>
                <td>{grade.code}</td>
                <td>{grade.name}</td>
                <td>{occupationalLevels.find((l) => l.id === grade.occupational_level)?.name ?? '—'}</td>
                {canManage && (
                  <td className="row-actions">
                    <button type="button" className="btn-link" onClick={() => startEdit(grade)}>
                      Edit
                    </button>
                    <button type="button" className="btn-link btn-danger" onClick={() => void handleDelete(grade.id)}>
                      Delete
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {canManage && editingId === null && (
        <button type="button" className="btn-secondary" onClick={startNew}>
          + Add job grade
        </button>
      )}

      {canManage && editingId !== null && (
        <form className="inline-form" onSubmit={handleSubmit}>
          <label>
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label>
            Code
            <input value={code} onChange={(e) => setCode(e.target.value)} required />
          </label>
          <label>
            Occupational level
            <select
              value={occupationalLevel}
              onChange={(e) => setOccupationalLevel(e.target.value ? Number(e.target.value) : '')}
              required
            >
              {occupationalLevels.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </select>
          </label>
          <div className="form-actions">
            <button type="submit" className="btn-primary">
              Save
            </button>
            <button type="button" className="btn-link" onClick={() => setEditingId(null)}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </>
  )
}

function LocationSection({
  locations, canManage, onChange,
}: { locations: Location[]; canManage: boolean; onChange: () => void }) {
  const [editingId, setEditingId] = useState<number | 'new' | null>(null)
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const [province, setProvince] = useState('')
  const [error, setError] = useState<string | null>(null)

  function startNew() {
    setEditingId('new')
    setName('')
    setCode('')
    setProvince('')
    setError(null)
  }

  function startEdit(loc: Location) {
    setEditingId(loc.id)
    setName(loc.name)
    setCode(loc.code)
    setProvince(loc.province)
    setError(null)
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    const payload = { name, code, province }
    try {
      if (editingId === 'new') {
        await api.post('/locations/', payload)
      } else {
        await api.patch(`/locations/${editingId}/`, payload)
      }
      setEditingId(null)
      onChange()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Save failed.')
    }
  }

  async function handleDelete(id: number) {
    setError(null)
    try {
      await api.delete(`/locations/${id}/`)
      onChange()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Delete failed.')
    }
  }

  return (
    <>
      {error && <p className="form-error">{error}</p>}
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Code</th>
              <th>Name</th>
              <th>Province</th>
              {canManage && <th></th>}
            </tr>
          </thead>
          <tbody>
            {locations.map((loc) => (
              <tr key={loc.id}>
                <td>{loc.code}</td>
                <td>{loc.name}</td>
                <td>{PROVINCES.find(([code]) => code === loc.province)?.[1] ?? loc.province}</td>
                {canManage && (
                  <td className="row-actions">
                    <button type="button" className="btn-link" onClick={() => startEdit(loc)}>
                      Edit
                    </button>
                    <button type="button" className="btn-link btn-danger" onClick={() => void handleDelete(loc.id)}>
                      Delete
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {canManage && editingId === null && (
        <button type="button" className="btn-secondary" onClick={startNew}>
          + Add location
        </button>
      )}

      {canManage && editingId !== null && (
        <form className="inline-form" onSubmit={handleSubmit}>
          <label>
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label>
            Code
            <input value={code} onChange={(e) => setCode(e.target.value)} required />
          </label>
          <label>
            Province
            <select value={province} onChange={(e) => setProvince(e.target.value)}>
              <option value="">— None —</option>
              {PROVINCES.map(([code, name]) => (
                <option key={code} value={code}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <div className="form-actions">
            <button type="submit" className="btn-primary">
              Save
            </button>
            <button type="button" className="btn-link" onClick={() => setEditingId(null)}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </>
  )
}
