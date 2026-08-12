import { useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError, fetchAllPages } from '../api/client'
import { useReferenceData } from '../api/ReferenceDataContext'
import {
  STAGE_LABELS,
  type Applicant,
  type ApplicantStage,
  type ApplicantStageEvent,
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

export function ApplicantDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [applicant, setApplicant] = useState<Applicant | null>(null)
  const [requisition, setRequisition] = useState<Requisition | null>(null)
  const [events, setEvents] = useState<ApplicantStageEvent[] | null>(null)
  const [offer, setOffer] = useState<Offer | null>(null)
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
        const [req, evts, allOffers] = await Promise.all([
          api.get<Requisition>(`/requisitions/${app.requisition}/`),
          api.get<ApplicantStageEvent[]>(`/applicants/${id}/stage_events/`),
          fetchAllPages<Offer>('/offers/'),
        ])
        setRequisition(req)
        setEvents(evts)
        setOffer(allOffers.find((o) => o.applicant === app.id) ?? null)
      })
      .catch(() => setError('Failed to load applicant.'))
  }

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
