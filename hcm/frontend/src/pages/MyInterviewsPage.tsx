import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../api/client'
import { useAuth } from '../auth/useAuth'
import {
  INTERVIEW_RECOMMENDATION_LABELS,
  INTERVIEW_SESSION_STATUS_LABELS,
  type InterviewRecommendation,
  type InterviewScorecard,
  type InterviewSession,
} from '../api/types'

/** Every authenticated employee can land here (roles: [] in navConfig.ts) --
 * being tapped as an interview panelist is an ad-hoc, row-level assignment,
 * not tied to any RBAC-Roles.md role. Uses ?mine=true so even a recruiter/
 * hr_admin who is ALSO occasionally a panelist sees only their own
 * assignments here, not the whole company's interview schedule (design
 * spec §3.1). */
export function MyInterviewsPage() {
  const { user } = useAuth()
  const [sessions, setSessions] = useState<InterviewSession[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  function load() {
    setError(null)
    fetchAllPages<InterviewSession>('/interview-sessions/?mine=true')
      .then(setSessions)
      .catch(() => setError('Failed to load your interview assignments.'))
  }

  useEffect(load, [])

  return (
    <div className="page">
      <div className="page-header">
        <h1>My Interviews</h1>
      </div>
      <p className="hint-text">
        Sessions you've been asked to interview for. You can only see your own scorecard for a session until you've
        submitted it — after that, your fellow panelists' scores become visible too.
      </p>
      {error && <p className="form-error">{error}</p>}
      {sessions === null ? (
        <p className="empty-state">Loading…</p>
      ) : sessions.length === 0 ? (
        <p className="empty-state">No interviews assigned to you right now.</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {sessions.map((session) => (
            <MyInterviewSessionCard key={session.id} session={session} myEmployeeId={user?.employee_id ?? null} />
          ))}
        </div>
      )}
    </div>
  )
}

function MyInterviewSessionCard({
  session, myEmployeeId,
}: { session: InterviewSession; myEmployeeId: number | null }) {
  const [scorecards, setScorecards] = useState<InterviewScorecard[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  function load() {
    fetchAllPages<InterviewScorecard>(`/interview-scorecards/?session=${session.id}`)
      .then(setScorecards)
      .catch(() => setError('Failed to load scorecards.'))
  }

  useEffect(load, [session.id])

  const mine = scorecards?.find((s) => s.interviewer === myEmployeeId) ?? null
  const peers = scorecards?.filter((s) => s.interviewer !== myEmployeeId) ?? []

  return (
    <div className="detail-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: 8 }}>
        <strong>
          {session.applicant_summary.first_name} {session.applicant_summary.last_name} — round {session.round_number}
        </strong>
        <span className="status-badge">{INTERVIEW_SESSION_STATUS_LABELS[session.status]}</span>
      </div>
      <p className="hint-text" style={{ margin: '4px 0' }}>
        {session.applicant_summary.requisition_title} · {new Date(session.scheduled_at).toLocaleString()} ·{' '}
        {session.location || 'No location set'}
      </p>
      {session.applicant_summary.resume && (
        <p style={{ margin: '4px 0' }}>
          <a href={session.applicant_summary.resume} target="_blank" rel="noreferrer">
            View CV / résumé
          </a>
        </p>
      )}

      {error && <p className="form-error">{error}</p>}

      {/* key forces a remount when `existing` first arrives (or changes
          identity) -- useState's initial value only runs on mount, so
          without this the form would keep showing its default 1-3-3-3
          "new scorecard" state even after the async fetch above resolves
          with the interviewer's real, already-submitted values. */}
      <ScorecardForm key={mine?.id ?? 'new'} session={session} existing={mine} onSaved={load} />

      {peers.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <h3 style={{ fontSize: '0.95em', margin: '0 0 4px' }}>Fellow panelists</h3>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {peers.map((p) => (
              <li key={p.id}>
                {p.recommendation ? (
                  <>
                    {INTERVIEW_RECOMMENDATION_LABELS[p.recommendation as InterviewRecommendation]} — skill{' '}
                    {p.skill_rating}, communication {p.communication_rating}, culture fit {p.culture_fit_rating}
                  </>
                ) : (
                  <span className="hint-text">Has submitted a scorecard — not visible until you submit yours.</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function ScorecardForm({
  session, existing, onSaved,
}: { session: InterviewSession; existing: InterviewScorecard | null; onSaved: () => void }) {
  const [skillRating, setSkillRating] = useState(existing?.skill_rating ?? 3)
  const [communicationRating, setCommunicationRating] = useState(existing?.communication_rating ?? 3)
  const [cultureFitRating, setCultureFitRating] = useState(existing?.culture_fit_rating ?? 3)
  const [comments, setComments] = useState(existing?.comments ?? '')
  const [recommendation, setRecommendation] = useState<InterviewRecommendation>(existing?.recommendation ?? 'hire')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const payload = {
        session: session.id, skill_rating: skillRating, communication_rating: communicationRating,
        culture_fit_rating: cultureFitRating, comments, recommendation,
      }
      if (existing) {
        await api.patch(`/interview-scorecards/${existing.id}/`, payload)
      } else {
        await api.post('/interview-scorecards/', payload)
      }
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
        Skill (1-5)
        <input type="number" min={1} max={5} value={skillRating} onChange={(e) => setSkillRating(Number(e.target.value))} />
      </label>
      <label>
        Communication (1-5)
        <input
          type="number" min={1} max={5} value={communicationRating}
          onChange={(e) => setCommunicationRating(Number(e.target.value))}
        />
      </label>
      <label>
        Culture fit (1-5)
        <input
          type="number" min={1} max={5} value={cultureFitRating}
          onChange={(e) => setCultureFitRating(Number(e.target.value))}
        />
      </label>
      <label>
        Recommendation
        <select value={recommendation} onChange={(e) => setRecommendation(e.target.value as InterviewRecommendation)}>
          {Object.entries(INTERVIEW_RECOMMENDATION_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Comments
        <textarea value={comments} onChange={(e) => setComments(e.target.value)} rows={2} />
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Saving…' : existing ? 'Update scorecard' : 'Submit scorecard'}
        </button>
      </div>
    </form>
  )
}
