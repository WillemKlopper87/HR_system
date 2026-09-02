import { useState, type FormEvent } from 'react'
import { EmployeeAsyncSelect } from '../../components/EmployeeAsyncSelect'
import { api, ApiError, fetchAllPages } from '../../api/client'
import {
  INTERVIEW_RECOMMENDATION_LABELS,
  INTERVIEW_SESSION_STATUS_LABELS,
  type Applicant,
  type InterviewRecommendation,
  type InterviewScorecard,
  type InterviewSession,
} from '../../api/types'
import type { EmployeeSearchSummary } from '../../api/contracts'

// C6: interviews (scheduling + panel scorecards)

export function InterviewsSection({
  applicant, sessions, onChanged,
}: { applicant: Applicant; sessions: InterviewSession[] | null; onChanged: () => void }) {
  const [showForm, setShowForm] = useState(false)

  if (applicant.current_stage !== 'interview' && (!sessions || sessions.length === 0)) {
    return <p className="hint-text">No interviews to schedule until this applicant reaches the Interview stage.</p>
  }

  return (
    <div>
      {sessions && sessions.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginBottom: 12 }}>
          {sessions.map((session) => (
            <InterviewSessionCard key={session.id} session={session} />
          ))}
        </div>
      )}
      {applicant.current_stage === 'interview' &&
        (!showForm ? (
          <button type="button" className="btn-secondary" onClick={() => setShowForm(true)}>
            + Schedule interview
          </button>
        ) : (
          <NewInterviewSessionForm
            applicantId={applicant.id}
            nextRound={(sessions?.length ?? 0) + 1}
            onCreated={() => {
              setShowForm(false)
              onChanged()
            }}
            onCancel={() => setShowForm(false)}
          />
        ))}
    </div>
  )
}

function NewInterviewSessionForm({
  applicantId, nextRound, onCreated, onCancel,
}: {
  applicantId: number
  nextRound: number
  onCreated: () => void
  onCancel: () => void
}) {
  const [roundNumber, setRoundNumber] = useState(nextRound)
  const [scheduledAt, setScheduledAt] = useState('')
  const [durationMinutes, setDurationMinutes] = useState(60)
  const [location, setLocation] = useState('')
  const [notes, setNotes] = useState('')
  const [interviewerIds, setInterviewerIds] = useState<number[]>([])
  const [interviewers, setInterviewers] = useState<EmployeeSearchSummary[]>([])
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (interviewerIds.length === 0) {
      setError('At least one interviewer is required.')
      return
    }
    setSubmitting(true)
    try {
      await api.post('/interview-sessions/', {
        applicant: applicantId, round_number: roundNumber, scheduled_at: new Date(scheduledAt).toISOString(),
        duration_minutes: durationMinutes, location, notes, interviewers: interviewerIds,
      })
      onCreated()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Scheduling failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit}>
      <label>
        Round
        <input type="number" min={1} value={roundNumber} onChange={(e) => setRoundNumber(Number(e.target.value))} required />
      </label>
      <label>
        Date &amp; time
        <input type="datetime-local" value={scheduledAt} onChange={(e) => setScheduledAt(e.target.value)} required />
      </label>
      <label>
        Duration (minutes)
        <input
          type="number"
          min={15}
          value={durationMinutes}
          onChange={(e) => setDurationMinutes(Number(e.target.value))}
        />
      </label>
      <label>
        Location / video link
        <input type="text" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Boardroom 2, or a video-call URL" />
      </label>
      <EmployeeAsyncSelect
        key={interviewers.length}
        value={null}
        onChange={() => undefined}
        onSelect={(employee) => {
          setInterviewers((current) => [...current, employee])
          setInterviewerIds((current) => [...current, employee.id])
        }}
        label="Add interviewer"
        excludeIds={interviewerIds}
      />
      {interviewers.length > 0 && (
        <ul className="selected-employees" aria-label="Interview panel">
          {interviewers.map((employee) => (
            <li key={employee.id}>
              {employee.employee_number} — {employee.display_name}{' '}
              <button
                type="button"
                className="btn-link"
                aria-label={`Remove ${employee.display_name}`}
                onClick={() => {
                  setInterviewers((current) => current.filter((item) => item.id !== employee.id))
                  setInterviewerIds((current) => current.filter((id) => id !== employee.id))
                }}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      <label>
        Notes
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Scheduling…' : 'Schedule interview'}
        </button>
        <button type="button" className="btn-secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}

function InterviewSessionCard({
  session,
}: { session: InterviewSession }) {
  const [showScorecards, setShowScorecards] = useState(false)
  const [scorecards, setScorecards] = useState<InterviewScorecard[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  function loadScorecards() {
    fetchAllPages<InterviewScorecard>(`/interview-scorecards/?session=${session.id}`)
      .then(setScorecards)
      .catch(() => setError('Failed to load scorecards.'))
  }

  function toggleScorecards() {
    if (!showScorecards) loadScorecards()
    setShowScorecards((s) => !s)
  }

  const submittedCount = scorecards?.length
  const visibleSkillRatings = (scorecards ?? []).map((s) => s.skill_rating).filter((r): r is number => r !== undefined)
  const avgSkill = visibleSkillRatings.length > 0
    ? visibleSkillRatings.reduce((sum, r) => sum + r, 0) / visibleSkillRatings.length
    : undefined

  return (
    <div className="detail-card" style={{ background: 'var(--surface-2, #f8f8f8)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: 8 }}>
        <strong>
          Round {session.round_number} — {new Date(session.scheduled_at).toLocaleString()}
        </strong>
        <span className="status-badge">{INTERVIEW_SESSION_STATUS_LABELS[session.status]}</span>
      </div>
      <p className="hint-text" style={{ margin: '4px 0' }}>
        {session.location || 'No location set'} · Panel:{' '}
        {session.interviewer_summaries.map((employee) => employee.display_name).join(', ') || '—'}
      </p>
      {session.notes && <p style={{ margin: '4px 0' }}>{session.notes}</p>}

      <button type="button" className="btn-link" onClick={toggleScorecards}>
        {showScorecards ? 'Hide scorecards' : `Show scorecards (${session.interviewers.length} interviewer(s))`}
      </button>

      {showScorecards && (
        <div style={{ marginTop: 8 }}>
          {error && <p className="form-error">{error}</p>}
          {scorecards === null ? (
            <p className="empty-state">Loading…</p>
          ) : scorecards.length === 0 ? (
            <p className="hint-text">No scorecards submitted yet.</p>
          ) : (
            <>
              {avgSkill !== undefined && (
                <p className="hint-text">
                  {submittedCount} of {session.interviewers.length} submitted · avg skill rating: {avgSkill.toFixed(1)}
                </p>
              )}
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Interviewer</th>
                      <th>Skill</th>
                      <th>Comm.</th>
                      <th>Culture fit</th>
                      <th>Recommendation</th>
                      <th>Comments</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scorecards.map((sc) => (
                      <tr key={sc.id}>
                        <td>{sc.interviewer_name}</td>
                        <td>{sc.skill_rating ?? '—'}</td>
                        <td>{sc.communication_rating ?? '—'}</td>
                        <td>{sc.culture_fit_rating ?? '—'}</td>
                        <td>
                          {sc.recommendation ? (
                            INTERVIEW_RECOMMENDATION_LABELS[sc.recommendation as InterviewRecommendation]
                          ) : (
                            <span className="hint-text">Not yet visible</span>
                          )}
                        </td>
                        <td>{sc.comments ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
