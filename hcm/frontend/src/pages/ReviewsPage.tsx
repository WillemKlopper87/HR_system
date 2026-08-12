import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchAllPages } from '../api/client'
import type { Employee, Review, ReviewCycle } from '../api/types'

const STATUS_LABELS: Record<Review['completion_status'], string> = {
  not_started: 'Not started',
  self_submitted: 'Self-review submitted',
  manager_submitted: 'Manager review submitted',
  completed: 'Completed',
}

export function ReviewsPage() {
  const [reviews, setReviews] = useState<Review[] | null>(null)
  const [cycles, setCycles] = useState<ReviewCycle[] | null>(null)
  const [employees, setEmployees] = useState<Employee[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      fetchAllPages<Review>('/reviews/'),
      fetchAllPages<ReviewCycle>('/review-cycles/'),
      fetchAllPages<Employee>('/employees/'),
    ])
      .then(([r, c, e]) => {
        setReviews(r)
        setCycles(c)
        setEmployees(e)
      })
      .catch(() => setError('Failed to load reviews.'))
  }, [])

  const cycleById = useMemo(() => new Map((cycles ?? []).map((c) => [c.id, c])), [cycles])
  const employeeById = useMemo(() => new Map((employees ?? []).map((e) => [e.id, e])), [employees])

  return (
    <div className="page">
      <div className="page-header">
        <h1>Reviews</h1>
      </div>

      {error && <p className="form-error">{error}</p>}

      {reviews === null ? (
        <p className="empty-state">Loading…</p>
      ) : reviews.length === 0 ? (
        <p className="empty-state">No reviews visible to you yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Employee</th>
                <th>Cycle</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {reviews.map((r) => {
                const emp = employeeById.get(r.employee)
                return (
                  <tr key={r.id}>
                    <td>
                      <Link to={`/reviews/${r.id}`}>{emp ? `${emp.first_name} ${emp.last_name}` : `#${r.employee}`}</Link>
                    </td>
                    <td>{cycleById.get(r.review_cycle)?.name ?? '—'}</td>
                    <td>
                      <span className="status-badge">{STATUS_LABELS[r.completion_status]}</span>
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
