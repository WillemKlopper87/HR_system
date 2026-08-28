import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useAuth } from '../auth/useAuth'
import type { Review } from '../api/types'

function ReviewSection({
  title, editable, rating, comments, submittedAt, onSave, onSubmit, busy,
}: {
  title: string
  editable: boolean
  rating: number | null
  comments: string
  submittedAt: string | null
  onSave: (rating: number, comments: string) => void
  onSubmit: (rating: number, comments: string) => void
  busy: boolean
}) {
  const [localRating, setLocalRating] = useState(rating ?? 3)
  const [localComments, setLocalComments] = useState(comments)

  useEffect(() => {
    setLocalRating(rating ?? 3)
    setLocalComments(comments)
  }, [rating, comments])

  const isSubmitted = submittedAt !== null

  return (
    <section className="detail-card">
      <h2>{title}</h2>
      {isSubmitted ? (
        <dl className="detail-grid">
          <div className="detail-field">
            <dt>Rating</dt>
            <dd>{rating}/5</dd>
          </div>
          <div className="detail-field">
            <dt>Comments</dt>
            <dd>{comments || '—'}</dd>
          </div>
          <div className="detail-field">
            <dt>Submitted</dt>
            <dd>{new Date(submittedAt as string).toLocaleString()}</dd>
          </div>
        </dl>
      ) : editable ? (
        <div>
          <label className="field">
            <span>Rating (1–5)</span>
            <select value={localRating} onChange={(e) => setLocalRating(Number(e.target.value))}>
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <label className="field" style={{ marginTop: 8 }}>
            <span>Comments</span>
            <textarea value={localComments} onChange={(e) => setLocalComments(e.target.value)} rows={4} />
          </label>
          <div className="form-actions" style={{ marginTop: 12 }}>
            <button
              type="button"
              className="btn-secondary"
              disabled={busy}
              onClick={() => onSave(localRating, localComments)}
            >
              Save draft
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={busy}
              onClick={() => onSubmit(localRating, localComments)}
            >
              Submit
            </button>
          </div>
        </div>
      ) : (
        <p className="empty-state">{rating !== null ? `Draft rating: ${rating}/5 (not yet submitted)` : 'Not started yet.'}</p>
      )}
    </section>
  )
}

export function ReviewDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { user } = useAuth()
  const [review, setReview] = useState<Review | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  function load() {
    if (!id) return
    setError(null)
    api
      .get<Review>(`/reviews/${id}/`)
      .then(setReview)
      .catch(() => setError("Failed to load review — you may not have access to it."))
  }

  useEffect(load, [id])

  async function saveSelf(rating: number, comments: string) {
    if (!id) return
    setActionError(null)
    setBusy(true)
    try {
      await api.patch(`/reviews/${id}/`, { self_rating: rating, self_comments: comments })
      load()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Save failed.')
    } finally {
      setBusy(false)
    }
  }

  async function submitSelf(rating: number, comments: string) {
    if (!id) return
    setActionError(null)
    setBusy(true)
    try {
      // Save-then-submit in one action — a rating chosen and "Submit"
      // clicked in the same motion shouldn't need a separate "Save draft"
      // click first just to make the rating exist server-side.
      await api.patch(`/reviews/${id}/`, { self_rating: rating, self_comments: comments })
      await api.post(`/reviews/${id}/submit_self/`)
      load()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Submit failed.')
    } finally {
      setBusy(false)
    }
  }

  async function saveManager(rating: number, comments: string) {
    if (!id) return
    setActionError(null)
    setBusy(true)
    try {
      await api.patch(`/reviews/${id}/`, { manager_rating: rating, manager_comments: comments })
      load()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Save failed.')
    } finally {
      setBusy(false)
    }
  }

  async function submitManager(rating: number, comments: string) {
    if (!id) return
    setActionError(null)
    setBusy(true)
    try {
      await api.patch(`/reviews/${id}/`, { manager_rating: rating, manager_comments: comments })
      await api.post(`/reviews/${id}/submit_manager/`)
      load()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Submit failed.')
    } finally {
      setBusy(false)
    }
  }

  if (error) return <p className="form-error">{error}</p>
  if (!review) return <p className="empty-state">Loading…</p>

  const isReviewee = user?.employee_id === review.employee
  const isManager = user?.employee_id === review.manager

  return (
    <div className="page">
      <div className="page-header">
        <h1>Review</h1>
        <Link to="/reviews" className="btn-link">
          ← Back to list
        </Link>
      </div>

      {actionError && <p className="form-error">{actionError}</p>}

      <ReviewSection
        title="Self-review"
        editable={isReviewee}
        rating={review.self_rating}
        comments={review.self_comments}
        submittedAt={review.self_submitted_at}
        onSave={saveSelf}
        onSubmit={submitSelf}
        busy={busy}
      />

      <ReviewSection
        title="Manager review"
        editable={isManager}
        rating={review.manager_rating}
        comments={review.manager_comments}
        submittedAt={review.manager_submitted_at}
        onSave={saveManager}
        onSubmit={submitManager}
        busy={busy}
      />
    </div>
  )
}
