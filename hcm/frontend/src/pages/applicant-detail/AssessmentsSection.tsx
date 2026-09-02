import { useState, type FormEvent } from 'react'
import { api, ApiError } from '../../api/client'
import { ASSESSMENT_STATUS_LABELS, ASSESSMENT_TYPE_LABELS, type AssessmentAssignment, type AssessmentType } from '../../api/types'

export function ApplicantAssessmentsSection({
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
