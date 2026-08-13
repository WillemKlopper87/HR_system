import { useEffect, useState } from 'react'
import { api, ApiError, fetchAllPages } from '../api/client'
import {
  LIVENESS_OUTCOME_LABELS,
  LIVENESS_REVIEW_STATUS_LABELS,
  type AttendanceSummaryRow,
  type BiometricEnrollment,
  type LivenessCheck,
} from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { CameraCapture, type CaptureResult } from '../liveness/CameraCapture'

export function MyIdentityVerificationPage() {
  const { user } = useAuth()
  const employeeId = user?.employee_id ?? null

  const [enrollment, setEnrollment] = useState<BiometricEnrollment | null>(null)
  const [checks, setChecks] = useState<LivenessCheck[] | null>(null)
  const [attendance, setAttendance] = useState<AttendanceSummaryRow | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [needsConsent, setNeedsConsent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [lastResult, setLastResult] = useState<LivenessCheck | null>(null)

  function load() {
    if (!employeeId) return
    setError(null)
    Promise.all([
      fetchAllPages<BiometricEnrollment>(`/biometric-enrollments/?employee=${employeeId}`),
      fetchAllPages<LivenessCheck>(`/liveness-checks/?employee=${employeeId}`),
      api.get<AttendanceSummaryRow[]>('/dashboards/attendance/'),
    ])
      .then(([enrollments, checkRows, attendanceRows]) => {
        setEnrollment(enrollments[0] ?? null)
        setChecks(checkRows)
        setAttendance(attendanceRows[0] ?? null)
      })
      .catch(() => setError('Failed to load your verification status.'))
  }

  useEffect(load, [employeeId])

  async function handleCaptureConsent() {
    if (!employeeId) return
    await api.post('/liveness-checks/consent/', { employee: employeeId, lawful_basis: 'consent', text_version: 'v1' })
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
      setNeedsConsent(false)
      load()
    } catch (err) {
      if (err instanceof ApiError && /consent/i.test(err.message)) {
        setNeedsConsent(true)
        try {
          await handleCaptureConsent()
          await api.post('/biometric-enrollments/', { employee: employeeId, descriptor: result.descriptor })
          setNeedsConsent(false)
          load()
        } catch (retryErr) {
          setError(retryErr instanceof ApiError ? retryErr.message : 'Enrollment failed.')
        }
      } else {
        setError(err instanceof ApiError ? err.message : 'Enrollment failed.')
      }
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
        <CameraCapture
          buttonLabel={enrollment ? 'Verify now' : 'Enroll now'}
          busy={busy}
          onCapture={(result) => void (enrollment ? handleVerify(result) : handleEnroll(result))}
        />
        {needsConsent && <p className="hint-text">Capturing consent and retrying automatically…</p>}
      </section>

      {checks && checks.length > 0 && (
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
                {checks.map((c) => (
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
        </section>
      )}
    </div>
  )
}
