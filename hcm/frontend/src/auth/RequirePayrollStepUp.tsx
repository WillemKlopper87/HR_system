import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { api, ApiError } from '../api/client'
import { STEP_UP_REASON_LABELS, type StepUpReason, type StepUpStatus, type TOTPStatus } from '../api/types'

const SCOPE = 'payroll_data'

/** Wraps payroll-data content (PayBands, CompProposals, the remuneration
 * import section) — Data-Dictionary.md tiers these Restricted, so holding
 * the comp_manager/hr_admin role (already checked server-side and, for
 * whole pages, via RequireRole) is necessary but not sufficient here. This
 * component itself enforces nothing — the real gate is the
 * RequiresPayrollStepUp permission class on every request; this is only
 * the UI for obtaining a grant, matching what a bypassed/direct API call
 * would hit anyway. */
export function RequirePayrollStepUp({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<StepUpStatus | null>(null)
  const [error, setError] = useState<string | null>(null)

  function load() {
    setError(null)
    api
      .get<StepUpStatus>(`/auth/step-up/status/?scope=${SCOPE}`)
      .then(setStatus)
      .catch(() => setError('Failed to check step-up authentication status.'))
  }

  useEffect(load, [])

  if (error) return <p className="form-error">{error}</p>
  if (status === null) return <p className="empty-state">Checking access…</p>
  if (status.active) return <>{children}</>
  return <StepUpChallenge onGranted={load} />
}

function StepUpChallenge({ onGranted }: { onGranted: () => void }) {
  const [totpStatus, setTotpStatus] = useState<TOTPStatus | null>(null)
  const [error, setError] = useState<string | null>(null)

  function load() {
    setError(null)
    api
      .get<TOTPStatus>('/auth/totp/status/')
      .then(setTotpStatus)
      .catch(() => setError('Failed to check authenticator status.'))
  }

  useEffect(load, [])

  return (
    <div className="page">
      <div className="detail-card">
        <h2>Step-up authentication required</h2>
        <p className="hint-text">
          This is Restricted-tier payroll data. Verify your identity with your authenticator app and state why you
          need access — both are logged against your account.
        </p>
        {error && <p className="form-error">{error}</p>}
        {totpStatus === null ? (
          <p className="empty-state">Loading…</p>
        ) : totpStatus.enrolled ? (
          <StepUpForm onGranted={onGranted} />
        ) : (
          <EnrollForm onEnrolled={load} />
        )}
      </div>
    </div>
  )
}

function EnrollForm({ onEnrolled }: { onEnrolled: () => void }) {
  const [secret, setSecret] = useState<string | null>(null)
  const [uri, setUri] = useState<string | null>(null)
  const [code, setCode] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleStartEnroll() {
    setError(null)
    setBusy(true)
    try {
      const response = await api.post<{ secret: string; provisioning_uri: string }>('/auth/totp/enroll/', {
        current_password: currentPassword,
      })
      setSecret(response.secret)
      setUri(response.provisioning_uri)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Enrollment failed.')
    } finally {
      setBusy(false)
    }
  }

  async function handleConfirm(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await api.post('/auth/totp/confirm/', { code })
      onEnrolled()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Confirmation failed.')
    } finally {
      setBusy(false)
    }
  }

  if (secret === null) {
    return (
      <form
        className="inline-form"
        onSubmit={(event) => { event.preventDefault(); void handleStartEnroll() }}
        style={{ flexDirection: 'column', alignItems: 'stretch' }}
      >
        <p className="hint-text">No authenticator device on file yet. You'll need one before you can access payroll data.</p>
        <label>
          Current password
          <input
            type="password"
            autoComplete="current-password"
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
            required
          />
        </label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button type="submit" className="btn-primary" disabled={busy || !currentPassword}>
          {busy ? 'Starting…' : 'Set up authenticator'}
        </button>
      </form>
    )
  }

  return (
    <form className="inline-form" onSubmit={handleConfirm} style={{ flexDirection: 'column', alignItems: 'stretch' }}>
      <p className="hint-text">
        Add this account to an authenticator app (e.g. Google Authenticator, Microsoft Authenticator) by entering the
        key below manually, then enter the 6-digit code it shows.
      </p>
      <label>
        Manual entry key
        <input value={secret} readOnly onFocus={(e) => e.target.select()} />
      </label>
      {uri && <p className="hint-text" style={{ wordBreak: 'break-all' }}>{uri}</p>}
      <label>
        6-digit code
        <input value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" maxLength={6} required />
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={busy}>
          {busy ? 'Confirming…' : 'Confirm and activate'}
        </button>
      </div>
    </form>
  )
}

function StepUpForm({ onGranted }: { onGranted: () => void }) {
  const [code, setCode] = useState('')
  const [reason, setReason] = useState<StepUpReason>('payroll_processing')
  const [reasonDetail, setReasonDetail] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await api.post('/auth/step-up/', { code, scope: SCOPE, reason, reason_detail: reasonDetail })
      onGranted()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Step-up authentication failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit} style={{ flexDirection: 'column', alignItems: 'stretch' }}>
      <label>
        6-digit authenticator code
        <input value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" maxLength={6} required />
      </label>
      <label>
        Reason for access
        <select value={reason} onChange={(e) => setReason(e.target.value as StepUpReason)}>
          {Object.entries(STEP_UP_REASON_LABELS).map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
      </label>
      {reason === 'other' && (
        <label>
          Detail (required)
          <input value={reasonDetail} onChange={(e) => setReasonDetail(e.target.value)} required />
        </label>
      )}
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={busy}>
          {busy ? 'Verifying…' : 'Verify and continue'}
        </button>
      </div>
    </form>
  )
}
