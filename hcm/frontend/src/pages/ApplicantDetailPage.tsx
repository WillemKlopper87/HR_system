import { useEffect, useState, type FormEvent } from 'react'
import { Field } from '../components/Field'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError, fetchAllPages } from '../api/client'
import { useReferenceData } from '../api/ReferenceDataContext'
import {
  ASSESSMENT_STATUS_LABELS,
  ASSESSMENT_TYPE_LABELS,
  BACKGROUND_CHECK_STATUS_LABELS,
  BACKGROUND_CHECK_TYPE_LABELS,
  INTERVIEW_RECOMMENDATION_LABELS,
  INTERVIEW_SESSION_STATUS_LABELS,
  STAGE_LABELS,
  type Applicant,
  type ApplicantStage,
  type ApplicantStageEvent,
  type AssessmentAssignment,
  type AssessmentType,
  type BackgroundCheck,
  type BackgroundCheckStatus,
  type BackgroundCheckType,
  type Employee,
  type InterviewRecommendation,
  type InterviewScorecard,
  type InterviewSession,
  type Offer,
  type Requisition,
} from '../api/types'

const NEXT_STAGES: Record<ApplicantStage, ApplicantStage[]> = {
  applied: ['screened', 'rejected'],
  screened: ['interview', 'rejected'],
  interview: ['offer', 'rejected'],
  offer: ['hired', 'rejected'],
  hired: [],
  rejected: [],
}

export function ApplicantDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [applicant, setApplicant] = useState<Applicant | null>(null)
  const [requisition, setRequisition] = useState<Requisition | null>(null)
  const [events, setEvents] = useState<ApplicantStageEvent[] | null>(null)
  const [offer, setOffer] = useState<Offer | null>(null)
  const [assessments, setAssessments] = useState<AssessmentAssignment[] | null>(null)
  const [interviewSessions, setInterviewSessions] = useState<InterviewSession[] | null>(null)
  const [backgroundChecks, setBackgroundChecks] = useState<BackgroundCheck[] | null>(null)
  const [employees, setEmployees] = useState<Employee[]>([])
  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const ref = useReferenceData()

  function load() {
    if (!id) return
    setError(null)
    api
      .get<Applicant>(`/applicants/${id}/`)
      .then(async (app) => {
        setApplicant(app)
        const [req, evts, allOffers, assessmentRows, sessions, checks] = await Promise.all([
          api.get<Requisition>(`/requisitions/${app.requisition}/`),
          api.get<ApplicantStageEvent[]>(`/applicants/${id}/stage_events/`),
          fetchAllPages<Offer>('/offers/'),
          fetchAllPages<AssessmentAssignment>(`/assessment-assignments/?applicant_id=${id}`),
          fetchAllPages<InterviewSession>(`/interview-sessions/?applicant=${id}`),
          fetchAllPages<BackgroundCheck>(`/background-checks/?applicant=${id}`),
        ])
        setRequisition(req)
        setEvents(evts)
        setOffer(allOffers.find((o) => o.applicant === app.id) ?? null)
        setAssessments(assessmentRows)
        setInterviewSessions(sessions)
        setBackgroundChecks(checks)
      })
      .catch(() => setError('Failed to load applicant.'))
  }

  // Interviewer picker + name resolution for the sections below — same
  // established (pre-C7-server-side-pagination) pattern every other
  // employee-picker page in this codebase already uses.
  useEffect(() => {
    fetchAllPages<Employee>('/employees/').then(setEmployees).catch(() => setEmployees([]))
  }, [])

  useEffect(load, [id])

  async function handleTransition(toStage: ApplicantStage) {
    if (!id) return
    setActionError(null)
    setBusy(true)
    try {
      await api.post(`/applicants/${id}/transition/`, { to_stage: toStage })
      load()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Transition failed.')
    } finally {
      setBusy(false)
    }
  }

  async function handleConsent() {
    if (!id) return
    setActionError(null)
    setBusy(true)
    try {
      await api.post(`/applicants/${id}/consent/`, { lawful_basis: 'consent', text_version: 'v1' })
      load()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Consent capture failed.')
    } finally {
      setBusy(false)
    }
  }

  if (error) return <p className="form-error">{error}</p>
  if (!applicant) return <p className="empty-state">Loading…</p>

  const nextStages = NEXT_STAGES[applicant.current_stage]

  return (
    <div className="page">
      <div className="page-header">
        <h1>
          {applicant.first_name} {applicant.last_name}
        </h1>
        <Link to="/applicants" className="btn-link">
          ← Back to list
        </Link>
      </div>

      {actionError && <p className="form-error">{actionError}</p>}

      <section className="detail-card">
        <h2>Application</h2>
        <dl className="detail-grid">
          <Field label="Email" obj={applicant} field="email" />
          <Field label="Phone" obj={applicant} field="phone" />
          <Field label="Date of birth" obj={applicant} field="date_of_birth" />
          <div className="detail-field">
            <dt>Requisition</dt>
            <dd>{requisition?.title ?? '—'}</dd>
          </div>
          <div className="detail-field">
            <dt>Stage</dt>
            <dd>
              <span className="status-badge">{STAGE_LABELS[applicant.current_stage]}</span>
            </dd>
          </div>
          {applicant.rejected_reason !== undefined && applicant.rejected_reason !== '' && (
            <Field label="Rejected reason" obj={applicant} field="rejected_reason" />
          )}
        </dl>

        {nextStages.length > 0 && (
          <div className="form-actions" style={{ marginTop: 16 }}>
            {nextStages.map((stage) => (
              <button
                key={stage}
                type="button"
                className={stage === 'rejected' ? 'btn-secondary btn-danger' : 'btn-primary'}
                disabled={busy}
                onClick={() => void handleTransition(stage)}
              >
                Move to {STAGE_LABELS[stage]}
              </button>
            ))}
          </div>
        )}

        {applicant.resulting_employee !== null && (
          <p className="hint-text" style={{ marginTop: 12 }}>
            Hired — see{' '}
            <Link to={`/employees/${applicant.resulting_employee}`}>the employee record</Link>.
          </p>
        )}
      </section>

      <section className="detail-card">
        <h2>Demographics</h2>
        {!applicant.has_demographic_consent ? (
          <>
            <p className="hint-text">
              No consent on file yet — demographic self-ID can't be recorded until the applicant consents.
            </p>
            <button type="button" className="btn-secondary" disabled={busy} onClick={() => void handleConsent()}>
              Capture consent
            </button>
          </>
        ) : (
          <DemographicsForm applicant={applicant} onSaved={load} />
        )}
      </section>

      {(applicant.current_stage === 'offer' || applicant.current_stage === 'hired' || offer) && (
        <section className="detail-card">
          <h2>Offer</h2>
          {offer ? (
            <OfferPanel offer={offer} jobGradeName={ref.jobGrades.get(offer.proposed_job_grade)?.name} onChanged={load} />
          ) : (
            <NewOfferForm applicantId={applicant.id} onCreated={load} />
          )}
        </section>
      )}

      <section className="detail-card">
        <h2>Assessments</h2>
        <ApplicantAssessmentsSection applicantId={applicant.id} assessments={assessments} onChanged={load} />
      </section>

      <section className="detail-card">
        <h2>Interviews</h2>
        <InterviewsSection
          applicant={applicant}
          sessions={interviewSessions}
          employees={employees}
          onChanged={load}
        />
      </section>

      <section className="detail-card">
        <h2>Background checks</h2>
        <BackgroundChecksSection applicantId={applicant.id} checks={backgroundChecks} onChanged={load} />
      </section>

      {events && events.length > 0 && (
        <section className="detail-card">
          <h2>Pipeline history</h2>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>From</th>
                  <th>To</th>
                  <th>When</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {events.map((e) => (
                  <tr key={e.id}>
                    <td>{e.from_stage ? STAGE_LABELS[e.from_stage as ApplicantStage] : '(new)'}</td>
                    <td>{STAGE_LABELS[e.to_stage as ApplicantStage]}</td>
                    <td>{new Date(e.created_at).toLocaleString()}</td>
                    <td>{e.notes || '—'}</td>
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

function DemographicsForm({ applicant, onSaved }: { applicant: Applicant; onSaved: () => void }) {
  const [race, setRace] = useState(applicant.race ?? 'not_disclosed')
  const [gender, setGender] = useState(applicant.gender ?? 'not_disclosed')
  const [disabilityStatus, setDisabilityStatus] = useState(applicant.disability_status ?? 'not_disclosed')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSaving(true)
    try {
      await api.patch(`/applicants/${applicant.id}/`, {
        race, gender, disability_status: disabilityStatus,
      })
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Save failed.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit}>
      <label>
        Race
        <select value={race} onChange={(e) => setRace(e.target.value)}>
          <option value="african">African</option>
          <option value="coloured">Coloured</option>
          <option value="indian">Indian</option>
          <option value="white">White</option>
          <option value="not_disclosed">Not disclosed</option>
        </select>
      </label>
      <label>
        Gender
        <select value={gender} onChange={(e) => setGender(e.target.value)}>
          <option value="male">Male</option>
          <option value="female">Female</option>
          <option value="not_disclosed">Not disclosed</option>
        </select>
      </label>
      <label>
        Disability status
        <select value={disabilityStatus} onChange={(e) => setDisabilityStatus(e.target.value)}>
          <option value="no">No disability</option>
          <option value="yes">Disability</option>
          <option value="not_disclosed">Not disclosed</option>
        </select>
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </form>
  )
}

function NewOfferForm({ applicantId, onCreated }: { applicantId: number; onCreated: () => void }) {
  const ref = useReferenceData()
  const [jobGrade, setJobGrade] = useState<number | ''>('')
  const [salary, setSalary] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!jobGrade) {
      setError('Job grade is required.')
      return
    }
    setSubmitting(true)
    try {
      await api.post('/offers/', {
        applicant: applicantId, proposed_job_grade: jobGrade, proposed_annual_salary: salary,
      })
      onCreated()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Create failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit}>
      <label>
        Job grade
        <select value={jobGrade} onChange={(e) => setJobGrade(e.target.value ? Number(e.target.value) : '')} required>
          <option value="">— Select —</option>
          {ref.jobGradeList.map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Proposed annual salary (ZAR)
        <input type="number" min={0} step="0.01" value={salary} onChange={(e) => setSalary(e.target.value)} required />
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Creating…' : 'Propose offer'}
        </button>
      </div>
    </form>
  )
}

function OfferPanel({
  offer, jobGradeName, onChanged,
}: { offer: Offer; jobGradeName: string | undefined; onChanged: () => void }) {
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function act(action: 'approve' | 'accept' | 'decline') {
    setError(null)
    setBusy(true)
    try {
      await api.post(`/offers/${offer.id}/${action}/`)
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Action failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <dl className="detail-grid">
        <div className="detail-field">
          <dt>Job grade</dt>
          <dd>{jobGradeName ?? '—'}</dd>
        </div>
        <div className="detail-field">
          <dt>Proposed annual salary</dt>
          <dd>R {Number(offer.proposed_annual_salary).toLocaleString()}</dd>
        </div>
        <div className="detail-field">
          <dt>Status</dt>
          <dd>
            <span className="status-badge">{offer.status}</span>
          </dd>
        </div>
      </dl>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions" style={{ marginTop: 12 }}>
        {offer.status === 'proposed' && (
          <button type="button" className="btn-primary" disabled={busy} onClick={() => void act('approve')}>
            Approve
          </button>
        )}
        {offer.status === 'approved' && (
          <>
            <button type="button" className="btn-primary" disabled={busy} onClick={() => void act('accept')}>
              Accept
            </button>
            <button type="button" className="btn-secondary" disabled={busy} onClick={() => void act('decline')}>
              Decline
            </button>
          </>
        )}
      </div>
    </div>
  )
}

function ApplicantAssessmentsSection({
  applicantId, assessments, onChanged,
}: { applicantId: number; assessments: AssessmentAssignment[] | null; onChanged: () => void }) {
  const [showForm, setShowForm] = useState(false)

  return (
    <div>
      {assessments && assessments.length > 0 && (
        <div className="table-scroll" style={{ marginBottom: 12 }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Status</th>
                <th>Result</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {assessments.map((a) => (
                <AssessmentAssignmentRow key={a.id} assignment={a} onChanged={onChanged} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!showForm ? (
        <button type="button" className="btn-secondary" onClick={() => setShowForm(true)}>
          + Assign assessment
        </button>
      ) : (
        <NewApplicantAssessmentForm
          applicantId={applicantId}
          onCreated={() => {
            setShowForm(false)
            onChanged()
          }}
          onCancel={() => setShowForm(false)}
        />
      )}
    </div>
  )
}

function AssessmentAssignmentRow({ assignment, onChanged }: { assignment: AssessmentAssignment; onChanged: () => void }) {
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleSimulate() {
    setError(null)
    setBusy(true)
    try {
      await api.post(`/assessment-assignments/${assignment.id}/simulate_completion/`)
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Action failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <tr>
      <td>{ASSESSMENT_TYPE_LABELS[assignment.assessment_type]}</td>
      <td>
        <span className="status-badge">{ASSESSMENT_STATUS_LABELS[assignment.status]}</span>
      </td>
      <td>
        {assignment.result ? (
          <div>
            <div>{assignment.result.summary}</div>
            <div className="hint-text">Score: {assignment.result.raw_score}</div>
          </div>
        ) : (
          '—'
        )}
      </td>
      <td>
        {error && <p className="form-error">{error}</p>}
        {assignment.status !== 'completed' && (
          <button type="button" className="btn-secondary" disabled={busy} onClick={() => void handleSimulate()}>
            Simulate provider completion
          </button>
        )}
      </td>
    </tr>
  )
}

function NewApplicantAssessmentForm({
  applicantId, onCreated, onCancel,
}: { applicantId: number; onCreated: () => void; onCancel: () => void }) {
  const [assessmentType, setAssessmentType] = useState<AssessmentType>('technical')
  const [error, setError] = useState<string | null>(null)
  const [needsConsent, setNeedsConsent] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  async function attemptAssign() {
    await api.post('/assessment-assignments/', { applicant_id: applicantId, assessment_type: assessmentType })
    onCreated()
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setNeedsConsent(false)
    setSubmitting(true)
    try {
      await attemptAssign()
    } catch (err) {
      if (err instanceof ApiError && /consent/i.test(err.message)) {
        setNeedsConsent(true)
        setError(err.message)
      } else {
        setError(err instanceof ApiError ? err.message : 'Create failed.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  async function handleCaptureConsentAndRetry() {
    setError(null)
    setSubmitting(true)
    try {
      await api.post(`/applicants/${applicantId}/consent/`, { purpose: 'assessment', lawful_basis: 'consent', text_version: 'v1' })
      await attemptAssign()
      setNeedsConsent(false)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Consent capture failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit}>
      <label>
        Assessment type
        <select value={assessmentType} onChange={(e) => setAssessmentType(e.target.value as AssessmentType)}>
          {Object.entries(ASSESSMENT_TYPE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>

      {error && <p className="form-error">{error}</p>}

      <div className="form-actions">
        {needsConsent ? (
          <button type="button" className="btn-primary" disabled={submitting} onClick={() => void handleCaptureConsentAndRetry()}>
            {submitting ? 'Capturing consent…' : 'Capture consent and assign'}
          </button>
        ) : (
          <button type="submit" className="btn-primary" disabled={submitting}>
            {submitting ? 'Assigning…' : 'Assign assessment'}
          </button>
        )}
        <button type="button" className="btn-secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}

// --- C6: interviews (scheduling + panel scorecards) -----------------------

function employeeName(employees: Employee[], id: number | null): string {
  if (id === null) return '—'
  const found = employees.find((e) => e.id === id)
  return found ? `${found.first_name} ${found.last_name}` : `#${id}`
}

function InterviewsSection({
  applicant, sessions, employees, onChanged,
}: { applicant: Applicant; sessions: InterviewSession[] | null; employees: Employee[]; onChanged: () => void }) {
  const [showForm, setShowForm] = useState(false)

  if (applicant.current_stage !== 'interview' && (!sessions || sessions.length === 0)) {
    return <p className="hint-text">No interviews to schedule until this applicant reaches the Interview stage.</p>
  }

  return (
    <div>
      {sessions && sessions.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginBottom: 12 }}>
          {sessions.map((session) => (
            <InterviewSessionCard key={session.id} session={session} employees={employees} />
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
            employees={employees}
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
  applicantId, employees, nextRound, onCreated, onCancel,
}: {
  applicantId: number
  employees: Employee[]
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
      <label>
        Interviewers (panel)
        <select
          multiple
          value={interviewerIds.map(String)}
          onChange={(e) =>
            setInterviewerIds(Array.from(e.target.selectedOptions, (o) => Number(o.value)))
          }
          size={Math.min(6, Math.max(3, employees.length))}
        >
          {employees.map((emp) => (
            <option key={emp.id} value={emp.id}>
              {emp.first_name} {emp.last_name} ({emp.employee_number})
            </option>
          ))}
        </select>
      </label>
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
  session, employees,
}: { session: InterviewSession; employees: Employee[] }) {
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
        {session.interviewers.map((id) => employeeName(employees, id)).join(', ') || '—'}
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
                        <td>{employeeName(employees, sc.interviewer)}</td>
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

// --- C6: background / reference checks -------------------------------------

function BackgroundChecksSection({
  applicantId, checks, onChanged,
}: { applicantId: number; checks: BackgroundCheck[] | null; onChanged: () => void }) {
  const [showForm, setShowForm] = useState(false)

  return (
    <div>
      {checks && checks.length > 0 && (
        <div className="table-scroll" style={{ marginBottom: 12 }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Status</th>
                <th>Notes</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {checks.map((check) => (
                <BackgroundCheckRow key={check.id} check={check} onChanged={onChanged} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!showForm ? (
        <button type="button" className="btn-secondary" onClick={() => setShowForm(true)}>
          + Log a check
        </button>
      ) : (
        <NewBackgroundCheckForm
          applicantId={applicantId}
          onCreated={() => {
            setShowForm(false)
            onChanged()
          }}
          onCancel={() => setShowForm(false)}
        />
      )}
    </div>
  )
}

function NewBackgroundCheckForm({
  applicantId, onCreated, onCancel,
}: { applicantId: number; onCreated: () => void; onCancel: () => void }) {
  const [checkType, setCheckType] = useState<BackgroundCheckType>('reference')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await api.post('/background-checks/', {
        applicant: applicantId, check_type: checkType, status: 'requested',
        requested_at: new Date().toISOString(),
      })
      onCreated()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to log check.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit}>
      <label>
        Check type
        <select value={checkType} onChange={(e) => setCheckType(e.target.value as BackgroundCheckType)}>
          {Object.entries(BACKGROUND_CHECK_TYPE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Logging…' : 'Log check'}
        </button>
        <button type="button" className="btn-secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}

function BackgroundCheckRow({ check, onChanged }: { check: BackgroundCheck; onChanged: () => void }) {
  const [status, setStatus] = useState<BackgroundCheckStatus>(check.status)
  const [notes, setNotes] = useState(check.notes)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function handleSave() {
    setError(null)
    setSaving(true)
    try {
      const completedAt = status === 'cleared' || status === 'flagged' ? new Date().toISOString() : check.completed_at
      await api.patch(`/background-checks/${check.id}/`, { status, notes, completed_at: completedAt })
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Save failed.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <tr>
      <td>{BACKGROUND_CHECK_TYPE_LABELS[check.check_type]}</td>
      <td>
        <select value={status} onChange={(e) => setStatus(e.target.value as BackgroundCheckStatus)}>
          {Object.entries(BACKGROUND_CHECK_STATUS_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </td>
      <td>
        <input type="text" value={notes} onChange={(e) => setNotes(e.target.value)} style={{ width: '100%' }} />
      </td>
      <td>
        {error && <p className="form-error">{error}</p>}
        <button type="button" className="btn-secondary" disabled={saving} onClick={() => void handleSave()}>
          {saving ? 'Saving…' : 'Save'}
        </button>
      </td>
    </tr>
  )
}
