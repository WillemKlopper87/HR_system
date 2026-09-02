import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../../api/client'
import { useAuth } from '../../auth/useAuth'
import type { Feedback } from '../../api/types'

export function FeedbackSection({ employeeId }: { employeeId: number }) {
  const { user } = useAuth()
  const [feedback, setFeedback] = useState<Feedback[] | null>(null)
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  function load() {
    setError(null)
    fetchAllPages<Feedback>(`/feedback/?employee=${employeeId}`)
      .then(setFeedback)
      .catch(() => setError('Failed to load feedback.'))
  }

  useEffect(load, [employeeId])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await api.post('/feedback/', { employee: employeeId, text })
      setText('')
      load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Submit failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="detail-card">
      <h2>Feedback</h2>

      {error && <p className="form-error">{error}</p>}

      {feedback === null ? (
        <p className="empty-state">Loading…</p>
      ) : feedback.length === 0 ? (
        <p className="empty-state">No feedback yet.</p>
      ) : (
        <ul className="breakdown-list" style={{ marginBottom: 16 }}>
          {feedback.map((f) => (
            <li key={f.id} style={{ display: 'block' }}>
              <span className="status-badge">{f.feedback_type}</span>{' '}
              <span>{f.text}</span>{' '}
              <span className="hint-text">— {new Date(f.created_at).toLocaleDateString()}</span>
            </li>
          ))}
        </ul>
      )}

      {employeeId !== user?.employee_id && (
        <form className="inline-form" onSubmit={handleSubmit}>
          <label style={{ minWidth: 320 }}>
            Give feedback
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} required />
          </label>
          <div className="form-actions">
            <button type="submit" className="btn-primary" disabled={submitting || !text}>
              {submitting ? 'Sending…' : 'Send feedback'}
            </button>
          </div>
        </form>
      )}
    </section>
  )
}
