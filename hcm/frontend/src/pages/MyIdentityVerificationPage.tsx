import { useEffect, useState } from 'react'
import { api, ApiError, type Paginated } from '../api/client'
import {
  LIVENESS_OUTCOME_LABELS,
  LIVENESS_REVIEW_STATUS_LABELS,
  type AttendanceSummaryRow,
  type BiometricEnrollment,
  type LivenessCheck,
} from '../api/types'
import { useAuth } from '../auth/useAuth'
import { CameraCapture, type CaptureResult } from '../liveness/CameraCapture'

export function MyIdentityVerificationPage() {
  const { user } = useAuth()
  const employeeId = user?.employee_id ?? null

  const [enrollment, setEnrollment] = useState<BiometricEnrollment | null>(null)
  const [checkPage, setCheckPage] = useState<Paginated<LivenessCheck> | null>(null)
  const [checkPagePath, setCheckPagePath] = useState<string | null>(null)
  const [attendance, setAttendance] = useState<AttendanceSummaryRow | null>(null)
  const [hasConsent, setHasConsent] = useState<boolean | null>(null)
  const [consentConfirmed, setConsentConfirmed] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [lastResult, setLastResult] = useState<LivenessCheck | null>(null)

  function load() {
    if (!employeeId) return
    setError(null)
    Promise.all([
      api.get<Paginated<BiometricEnrollment>>(`/biometric-enrollments/?employee=${employeeId}`),
      api.get<Paginated<LivenessCheck>>(
        checkPagePath ?? `/liveness-checks/?employee=${employeeId}`,
      ),
      api.get<AttendanceSummaryRow[]>('/dashboards/attendance/'),
      api.get<{ active: boolean }>(`/liveness-checks/consent/?employee=${employeeId}`),
    ])
      .then(([enrollments, checkRows, attendanceRows, consentStatus]) => {
        setEnrollment(enrollments.results[0] ?? null)
        setCheckPage(checkRows)
        setAttendance(attendanceRows[0] ?? null)
        setHasConsent(consentStatus.active)
      })
      .catch(() => setError('Failed to load your verification status.'))
  }

  useEffect(load, [employeeId, checkPagePath])

  async function handleCaptureConsent() {
    if (!employeeId) return
    setError(null)
    setBusy(true)
    try {
      await api.post('/liveness-checks/consent/', {
        employee: employeeId, lawful_basis: 'consent', text_version: 'biometric-v1',
      })
      setHasConsent(true)
      setConsentConfirmed(false)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Consent could not be recorded.')
    } finally {
      setBusy(false)
    }
  }

  async function handleEnroll(result: CaptureResult) {
    if (!employeeId) return
    setError(null)
    setBusy(true)
    try {
      if (!result.descriptor) {
        setError('No face was detected — make sure your face is clearly visible and try again.')
        return
      }
      await api.post('/biometric-enrollments/', { employee: employeeId, descriptor: result.descriptor })
      load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Enrollment failed.')
    } finally {
      setBusy(false)
    }
  }

  async function handleVerify(result: CaptureResult) {
    if (!employeeId) return
    setError(null)
    setBusy(true)
    setLastResult(null)
    try {
      const check = await api.post<LivenessCheck>('/liveness-checks/', {
        employee: employeeId, descriptor: result.descriptor, latitude: result.latitude, longitude: result.longitude,
      })
      setLastResult(check)
      load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Verification failed.')
    } finally {
      setBusy(false)
    }
  }

  if (!employeeId) return <p className="empty-state">Loading…</p>

  return (
    <div className="page">
      <div className="page-header">
        <h1>My Identity Verification</h1>
      </div>

      <p className="hint-text">
        A workplace-integrity check ("ghost employee" mitigation) and office-attendance record. Face detection and
        matching run entirely in your browser — only the derived numeric descriptor is sent to the server, never your
        photo or video. A mismatch is never auto-flagged as fraud; it's queued for HR to review.
      </p>

      {error && <p className="form-error">{error}</p>}

      {attendance && (
        <section className="detail-card">
          <h2>This week's office attendance</h2>
          <p>
            {attendance.days_in_office} of {attendance.required_days} required day(s) —{' '}
            <span className="status-badge">{attendance.compliant ? 'On track' : 'Not yet met'}</span>
          </p>
        </section>
      )}

      <section className="detail-card">
        <h2>{enrollment ? 'Verify my identity' : 'Enroll my face'}</h2>
        {!enrollment && (
          <p className="hint-text">
            You haven't enrolled yet. Capturing your face now creates your reference identity — every future check-in
            is compared against it.
          </p>
        )}
        {lastResult && (
          <p className={lastResult.outcome === 'match' ? 'status-badge' : 'restricted-badge'} style={{ display: 'inline-block', marginBottom: 12 }}>
            {LIVENESS_OUTCOME_LABELS[lastResult.outcome]}
            {lastResult.review_status === 'pending' && ' — flagged for HR review'}
          </p>
        )}
        {hasConsent === false ? (
          <div className="notice-card">
            <p>
              Biometric verification is optional. If you consent, your camera runs locally and only a derived numeric
              face template is stored. You may use the non-biometric HR-assisted check-in process instead, without
              penalty, and may ask HR to withdraw consent or appeal a result.
            </p>
            <label>
              <input
                type="checkbox"
                checked={consentConfirmed}
                onChange={(event) => setConsentConfirmed(event.target.checked)}
              />{' '}
              I have read this notice and consent to biometric identity and attendance verification.
            </label>
            <div className="form-actions">
              <button type="button" className="btn-primary" disabled={busy || !consentConfirmed} onClick={() => void handleCaptureConsent()}>
                Record consent
              </button>
            </div>
          </div>
        ) : hasConsent === true ? (
          <CameraCapture
            buttonLabel={enrollment ? 'Verify now' : 'Enroll now'}
            busy={busy}
            onCapture={(result) => void (enrollment ? handleVerify(result) : handleEnroll(result))}
          />
        ) : (
          <p className="empty-state">Loading consent status...</p>
        )}
      </section>

      {checkPage && checkPage.results.length > 0 && (
        <section className="detail-card">
          <h2>My recent checks</h2>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Result</th>
                  <th>At office</th>
                  <th>Review</th>
                </tr>
              </thead>
              <tbody>
                {checkPage.results.map((c) => (
                  <tr key={c.id}>
                    <td>{new Date(c.created_at).toLocaleString()}</td>
                    <td>{LIVENESS_OUTCOME_LABELS[c.outcome]}</td>
                    <td>{c.at_office === null ? '—' : c.at_office ? 'Yes' : 'No'}</td>
                    <td>{LIVENESS_REVIEW_STATUS_LABELS[c.review_status]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {(checkPage.previous || checkPage.next) && (
            <nav className="form-actions" aria-label="My identity-check pages">
              <button type="button" className="btn-secondary" disabled={!checkPage.previous} onClick={() => setCheckPagePath(checkPage.previous)}>
                Previous
              </button>
              <button type="button" className="btn-secondary" disabled={!checkPage.next} onClick={() => setCheckPagePath(checkPage.next)}>
                Next
              </button>
            </nav>
          )}
        </section>
      )}
    </div>
  )
}
