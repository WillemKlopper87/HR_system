import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Paginated } from '../api/client'
import { useApiQuery } from '../api/hooks'
import { useReferenceData } from '../api/ReferenceDataContext'
import type { Employee } from '../api/types'

export function EmployeeListPage() {
  const [search, setSearch] = useState('')
  const [pagePath, setPagePath] = useState<string | null>(null)
  const { departments, occupationalLevels } = useReferenceData()
  // useApiQuery's stale-response guard replaces the hand-rolled `cancelled` flag this page used to carry.
  const initialPath = `/employees/${search ? `?search=${encodeURIComponent(search)}` : ''}`
  const requestPath = pagePath ?? initialPath
  const { data, error } = useApiQuery(
    () => api.get<Paginated<Employee>>(requestPath),
    [requestPath],
    { errorMessage: 'Failed to load employees.' },
  )
  const employees = data?.results ?? null

  return (
    <div className="page">
      <div className="page-header">
        <h1>Employees</h1>
        <input
          className="search-input"
          placeholder="Search by name, number, or email…"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setPagePath(null)
          }}
        />
      </div>

      {error && <p className="form-error">{error}</p>}

      {employees === null ? (
        <p className="empty-state">Loading…</p>
      ) : employees.length === 0 ? (
        <p className="empty-state">No employees found.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Employee #</th>
                <th>Name</th>
                <th>Work email</th>
                <th>Department</th>
                <th>Level</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {employees.map((emp) => {
                return (
                  <tr key={emp.id}>
                    <td>
                      <Link to={`/employees/${emp.id}`}>{emp.employee_number}</Link>
                    </td>
                    <td>
                      {emp.first_name} {emp.last_name}
                    </td>
                    <td>{emp.work_email}</td>
                    <td>{emp.current_department ? (departments.get(emp.current_department)?.name ?? '—') : '—'}</td>
                    <td>{emp.current_occupational_level ? (occupationalLevels.get(emp.current_occupational_level)?.name ?? '—') : '—'}</td>
                    <td>
                      {emp.current_employment_status ? <span className="status-badge">{emp.current_employment_status}</span> : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      {data && (data.previous || data.next) && (
        <div className="form-actions">
          <button type="button" className="btn-secondary" disabled={!data.previous} onClick={() => setPagePath(data.previous)}>
            Previous
          </button>
          <button type="button" className="btn-secondary" disabled={!data.next} onClick={() => setPagePath(data.next)}>
            Next
          </button>
        </div>
      )}
    </div>
  )
}
