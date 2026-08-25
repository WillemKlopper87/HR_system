import { useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { PublicPosting } from '../api/types'

const RACE_OPTIONS: [string, string][] = [
  ['not_disclosed', 'Prefer not to say'],
  ['african', 'African'],
  ['coloured', 'Coloured'],
  ['indian', 'Indian'],
  ['white', 'White'],
]
const GENDER_OPTIONS: [string, string][] = [
  ['not_disclosed', 'Prefer not to say'],
  ['male', 'Male'],
  ['female', 'Female'],
]
const DISABILITY_OPTIONS: [string, string][] = [
  ['not_disclosed', 'Prefer not to say'],
  ['no', 'No disability'],
  ['yes', 'Disability'],
]

/** Genuinely public -- no login (design spec §5.2). The application form
 * collects the same Sensitive-tier demographic fields the internal
 * Applicant record carries, under the same consent posture as the rest of
 * the system (§3.4.5): they stay optional, default to "prefer not to say",
 * and are only STORED if demographic_consent is explicitly ticked -- not
 * submitting them, or submitting the form without ticking consent, never
 * blocks the application itself. */
export function CareersPostingPage() {
  const { id } = useParams<{ id: string }>()
  const [posting, setPosting] = useState<PublicPosting | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [submitted, setSubmitted] = useState(false)

  useEffect(() => {
    if (!id) return
    api
      .get<PublicPosting>(`/careers/postings/${id}/`)
      .then(setPosting)
      .catch(() => setNotFound(true))
  }, [id])

  if (notFound) {
    return (
      <div className="page" style={{ maxWidth: 800, margin: '0 auto' }}>
        <p className="form-error">This position could not be found — it may have closed.</p>
        <Link to="/careers">← Back to all openings</Link>
      </div>
    )
  }

  if (!posting) return <p className="empty-state">Loading…</p>

  return (
    <div className="page" style={{ maxWidth: 800, margin: '0 auto' }}>
      <div className="page-header">
        <h1>{posting.title}</h1>
        <Link to="/careers" className="btn-link">
          ← All openings
        </Link>
      </div>
      <p className="hint-text">
        {posting.department} · {posting.location}
        {posting.occupational_level ? ` · ${posting.occupational_level}` : ''}
      </p>
      {posting.description && <p style={{ whiteSpace: 'pre-wrap' }}>{posting.description}</p>}

      <section className="detail-card">
        <h2>Apply</h2>
        {submitted ? (
          <p>
            Thank you — your application has been received. We'll be in touch if you're shortlisted for the next
            step.
          </p>
        ) : (
          <ApplicationForm postingId={posting.id} onSubmitted={() => setSubmitted(true)} />
        )}
      </section>
    </div>
  )
}

function ApplicationForm({ postingId, onSubmitted }: { postingId: number; onSubmitted: () => void }) {
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [dateOfBirth, setDateOfBirth] = useState('')
  const [resume, setResume] = useState<File | null>(null)
  const [race, setRace] = useState('not_disclosed')
  const [gender, setGender] = useState('not_disclosed')
  const [disabilityStatus, setDisabilityStatus] = useState('not_disclosed')
  const [demographicConsent, setDemographicConsent] = useState(false)
  // Honeypot: never rendered visibly, aria-hidden so a screen-reader user
  // never encounters it either -- a scripted bot filling every field
  // blindly is the only thing that ever populates this (design spec §3.4.3).
  const [website, setWebsite] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!resume) {
      setError('Please attach your CV / résumé.')
      return
    }
    setSubmitting(true)
    try {
      const form = new FormData()
      form.append('requisition', String(postingId))
      form.append('first_name', firstName)
      form.append('last_name', lastName)
      form.append('email', email)
      form.append('phone', phone)
      form.append('date_of_birth', dateOfBirth)
      form.append('resume', resume)
      form.append('race', race)
      form.append('gender', gender)
      form.append('disability_status', disabilityStatus)
      form.append('demographic_consent', String(demographicConsent))
      form.append('website', website)
      await api.postForm('/careers/apply/', form)
      onSubmitted()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong submitting your application — please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit}>
      <label>
        First name
        <input value={firstName} onChange={(e) => setFirstName(e.target.value)} required />
      </label>
      <label>
        Last name
        <input value={lastName} onChange={(e) => setLastName(e.target.value)} required />
      </label>
      <label>
        Email
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
      </label>
      <label>
        Phone
        <input value={phone} onChange={(e) => setPhone(e.target.value)} />
      </label>
      <label>
        Date of birth
        <input type="date" value={dateOfBirth} onChange={(e) => setDateOfBirth(e.target.value)} required />
      </label>
      <label>
        CV / résumé (PDF, Word, or image, up to 5MB)
        <input
          type="file"
          accept=".pdf,.doc,.docx,.jpg,.jpeg,.png"
          onChange={(e) => setResume(e.target.files?.[0] ?? null)}
          required
        />
      </label>

      <fieldset>
        <legend>Equity information (optional)</legend>
        <p className="hint-text" style={{ marginTop: 0 }}>
          South African employers report on workforce demographics under the Employment Equity Act. Sharing this
          information is entirely optional — it will only be recorded if you tick the consent box below, and it has
          no bearing on the outcome of your application.
        </p>
        <label>
          Race
          <select value={race} onChange={(e) => setRace(e.target.value)}>
            {RACE_OPTIONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Gender
          <select value={gender} onChange={(e) => setGender(e.target.value)}>
            {GENDER_OPTIONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Disability status
          <select value={disabilityStatus} onChange={(e) => setDisabilityStatus(e.target.value)}>
            {DISABILITY_OPTIONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <input
            type="checkbox"
            checked={demographicConsent}
            onChange={(e) => setDemographicConsent(e.target.checked)}
          />
          I consent to this information being recorded for employment equity purposes.
        </label>
      </fieldset>

      {/* Honeypot -- invisible to a sighted human and skipped by screen
          readers; a bot filling every input blindly populates it. */}
      <div style={{ position: 'absolute', left: '-9999px', top: 'auto' }} aria-hidden="true">
        <label>
          Leave this field blank
          <input type="text" tabIndex={-1} autoComplete="off" value={website} onChange={(e) => setWebsite(e.target.value)} />
        </label>
      </div>

      {error && <p className="form-error">{error}</p>}

      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Submitting…' : 'Submit application'}
        </button>
      </div>
    </form>
  )
}
