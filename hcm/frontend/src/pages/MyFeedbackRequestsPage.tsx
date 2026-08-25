import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../api/client'
import { FEEDBACK_360_RELATIONSHIP_LABELS, type Feedback360Rater } from '../api/types'

/** Every authenticated employee can land here (roles: [] in navConfig.ts) --
 * being asked for 360 feedback is a row-level assignment, not tied to any
 * RBAC-Roles.md role, exactly like /my-interviews. Uses ?mine=true so even
 * hr_admin/auditor sees only their own rater slots here, not everyone's
 * (design spec §7). This is also the ONE place a self or manager rater
 * responds -- those slots are automatic, but the person behind them still
 * answers here like any other rater. */
export function MyFeedbackRequestsPage() {
  const [raters, setRaters] = useState<Feedback360Rater[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  function load() {
    setError(null)
    fetchAllPages<Feedback360Rater>('/feedback-360-raters/?mine=true')
      .then(setRaters)
      .catch(() => setError('Failed to load your feedback requests.'))
  }

  useEffect(load, [])

  const actionable = (raters ?? []).filter((r) => r.status === 'approved')
  const other = (raters ?? []).filter((r) => r.status !== 'approved')

  return (
    <div className="page">
      <div className="page-header">
        <h1>My 360° Feedback Requests</h1>
      </div>
      <p className="hint-text">
        People who've asked for your input on how they work, including your own self-assessment and any manager
        response you owe your reports. Peer and direct-report responses are shown to the person's Head/HR in full,
        but never individually attributed back to the person being rated — only a pooled average, once enough
        responses exist.
      </p>
      {error && <p className="form-error">{error}</p>}
      {raters === null ? (
        <p className="empty-state">Loading…</p>
      ) : actionable.length === 0 && other.length === 0 ? (
        <p className="empty-state">No 360 feedback requests right now.</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {actionable.map((rater) => (
            <RaterCard key={rater.id} rater={rater} onSaved={load} />
          ))}
          {other.length > 0 && (
            <div className="detail-card">
              <h3 style={{ fontSize: '0.95em', margin: '0 0 4px' }}>Not yet actionable</h3>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {other.map((r) => (
                  <li key={r.id}>
                    {r.subject_name} ({r.period_name}) — {r.status_display}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function RaterCard({ rater, onSaved }: { rater: Feedback360Rater; onSaved: () => void }) {
  return (
    <div className="detail-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: 8 }}>
        <strong>
          {rater.subject_name} — {rater.period_name}
        </strong>
        <span className="status-badge">{FEEDBACK_360_RELATIONSHIP_LABELS[rater.relationship]}</span>
      </div>
      {rater.has_submitted && <p className="hint-text" style={{ margin: '4px 0' }}>You've already responded — you can update it below.</p>}
      {/* key forces a remount when the response first arrives, same fix as
          MyInterviewsPage's ScorecardForm -- useState's initial value only
          runs on mount, and `rater.response` arrives asynchronously. */}
      <ResponseForm key={rater.response?.id ?? 'new'} rater={rater} onSaved={onSaved} />
    </div>
  )
}

function ResponseForm({ rater, onSaved }: { rater: Feedback360Rater; onSaved: () => void }) {
  const [collaborationRating, setCollaborationRating] = useState(rater.response?.collaboration_rating ?? 3)
  const [communicationRating, setCommunicationRating] = useState(rater.response?.communication_rating ?? 3)
  const [reliabilityRating, setReliabilityRating] = useState(rater.response?.reliability_rating ?? 3)
  const [strengths, setStrengths] = useState(rater.response?.strengths ?? '')
  const [developmentAreas, setDevelopmentAreas] = useState(rater.response?.development_areas ?? '')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await api.post(`/feedback-360-raters/${rater.id}/respond/`, {
        collaboration_rating: collaborationRating, communication_rating: communicationRating,
        reliability_rating: reliabilityRating, strengths, development_areas: developmentAreas,
      })
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Save failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit} style={{ marginTop: 8 }}>
      <label>
        Collaboration (1-5)
        <input
          type="number" min={1} max={5} value={collaborationRating}
          onChange={(e) => setCollaborationRating(Number(e.target.value))}
        />
      </label>
      <label>
        Communication (1-5)
        <input
          type="number" min={1} max={5} value={communicationRating}
          onChange={(e) => setCommunicationRating(Number(e.target.value))}
        />
      </label>
      <label>
        Reliability (1-5)
        <input
          type="number" min={1} max={5} value={reliabilityRating}
          onChange={(e) => setReliabilityRating(Number(e.target.value))}
        />
      </label>
      <label>
        Strengths
        <textarea value={strengths} onChange={(e) => setStrengths(e.target.value)} rows={2} />
      </label>
      <label>
        Development areas
        <textarea value={developmentAreas} onChange={(e) => setDevelopmentAreas(e.target.value)} rows={2} />
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Saving…' : rater.has_submitted ? 'Update response' : 'Submit response'}
        </button>
      </div>
    </form>
  )
}
