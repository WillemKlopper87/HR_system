import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError, fetchAllPages } from '../api/client'
import { useReferenceData } from '../api/ReferenceDataContext'
import type { Employee, EmployeeVersion } from '../api/types'

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
    </div>
  )
}
