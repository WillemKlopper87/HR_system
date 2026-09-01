import { useMemo} from 'react'
import { Link } from 'react-router-dom'
import { fetchAllPages } from '../api/client'
import { useApiQuery } from '../api/hooks'
import type { Review, ReviewCycle } from '../api/types'

const STATUS_LABELS: Record<Review['completion_status'], string> = {
  not_started: 'Not started',
  self_submitted: 'Self-review submitted',
  manager_submitted: 'Manager review submitted',
  completed: 'Completed',
}

export function ReviewsPage() {
  const { data, error } = useApiQuery(
    () =>
      Promise.all([
        fetchAllPages<Review>('/reviews/'),
        fetchAllPages<ReviewCycle>('/review-cycles/'),
      ]).then(([reviews, cycles]) => ({ reviews, cycles })),
    [],
    { errorMessage: 'Failed to load reviews.' },
  )
  const reviews = data?.reviews ?? null
  const cycles = data?.cycles ?? null

  const cycleById = useMemo(() => new Map((cycles ?? []).map((c) => [c.id, c])), [cycles])

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
                return (
                  <tr key={r.id}>
                    <td>
                      <Link to={`/reviews/${r.id}`}>{r.employee_name}</Link>
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
