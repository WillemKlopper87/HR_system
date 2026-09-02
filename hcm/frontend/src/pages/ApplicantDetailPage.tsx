import { useEffect, useState } from 'react'
import { Field } from '../components/Field'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError, fetchAllPages } from '../api/client'
import { useReferenceData } from '../api/useReferenceData'
import { ApplicantAssessmentsSection } from './applicant-detail/AssessmentsSection'
import { BackgroundChecksSection } from './applicant-detail/BackgroundChecksSection'
import { DemographicsForm } from './applicant-detail/DemographicsSection'
import { InterviewsSection } from './applicant-detail/InterviewsSection'
import { NewOfferForm, OfferPanel } from './applicant-detail/OfferSection'
import {
  STAGE_LABELS,
  type Applicant,
  type ApplicantStage,
  type ApplicantStageEvent,
  type AssessmentAssignment,
  type BackgroundCheck,
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

/** Page shell + the applicant's own record/stage transitions; every
 * recruitment subdomain below (demographics, offer, assessments,
 * interviews, background checks) is a self-contained section component
 * under ./applicant-detail/, matching EmployeeDetailPage's own split. */
export function ApplicantDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [applicant, setApplicant] = useState<Applicant | null>(null)
  const [requisition, setRequisition] = useState<Requisition | null>(null)
  const [events, setEvents] = useState<ApplicantStageEvent[] | null>(null)
  const [offer, setOffer] = useState<Offer | null>(null)
  const [assessments, setAssessments] = useState<AssessmentAssignment[] | null>(null)
  const [interviewSessions, setInterviewSessions] = useState<InterviewSession[] | null>(null)
  const [backgroundChecks, setBackgroundChecks] = useState<BackgroundCheck[] | null>(null)
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
          <div className="detail-field">
            <dt>Résumé</dt>
            <dd>
              {applicant.has_resume && applicant.resume_download_url ? (
                <a href={applicant.resume_download_url} target="_blank" rel="noreferrer">
                  Download résumé
                </a>
              ) : (
                'Not uploaded'
              )}
            </dd>
          </div>
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
