import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchAllPages } from '../api/client'
import { useApiQuery } from '../api/hooks'
import { useReferenceData } from '../api/ReferenceDataContext'
import type { Employee, EmployeeVersion } from '../api/types'

export function EmployeeListPage() {
  const [search, setSearch] = useState('')
  const { departments, occupationalLevels } = useReferenceData()
  // useApiQuery's stale-response guard replaces the hand-rolled `cancelled` flag this page used to carry.
  const { data, error } = useApiQuery(
    () => {
      const query = search ? `?search=${encodeURIComponent(search)}` : ''
      return Promise.all([
        fetchAllPages<Employee>(`/employees/${query}`),
        fetchAllPages<EmployeeVersion>('/employee-versions/?current=true'),
      ]).then(([employees, versions]) => ({ employees, versions }))
    },
    [search],
    { errorMessage: 'Failed to load employees.' },
  )
  const employees = data?.employees ?? null
  const versions = data?.versions ?? null

  const versionByEmployee = useMemo(() => {
    const map = new Map<number, EmployeeVersion>()
    versions?.forEach((v) => map.set(v.employee, v))
    return map
  }, [versions])

  return (
    <div className="page">
      <div className="page-header">
        <h1>Employees</h1>
        <input
          className="search-input"
          placeholder="Search by name, number, or email…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
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
                const version = versionByEmployee.get(emp.id)
                return (
                  <tr key={emp.id}>
                    <td>
                      <Link to={`/employees/${emp.id}`}>{emp.employee_number}</Link>
                    </td>
                    <td>
                      {emp.first_name} {emp.last_name}
                    </td>
                    <td>{emp.work_email}</td>
                    <td>{version ? (departments.get(version.department)?.name ?? '—') : '—'}</td>
                    <td>{version ? (occupationalLevels.get(version.occupational_level)?.name ?? '—') : '—'}</td>
                    <td>
                      {version ? <span className="status-badge">{version.employment_status}</span> : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
