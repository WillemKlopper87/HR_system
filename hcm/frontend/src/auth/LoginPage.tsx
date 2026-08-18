import { useEffect, useState, type FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useAuth } from './AuthContext'

export function LoginPage() {
  const { login, user, sessionExpired } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const returnTo = (location.state as { from?: string } | null)?.from
  // Never bounce back to /login itself; default landing stays /employees.
  const destination = returnTo && !returnTo.startsWith('/login') ? returnTo : '/employees'
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // Redirect-if-already-authenticated belongs in an effect, not the render
  // body — calling navigate() during render is a side effect and caused a
  // real bug here (a stale RequireAuth redirect target could fire the
  // navigation more than once with an outdated destination).
  useEffect(() => {
    if (user) navigate(destination, { replace: true })
  }, [user, navigate, destination])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(username, password)
      navigate(destination, { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Login failed — please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={handleSubmit}>
        <h1>Sentech HCM</h1>
        <p className="login-subtitle">Sign in to continue</p>
        {sessionExpired && (
          <p className="form-notice" role="status">
            Your session expired — please sign in again to continue where you left off.
          </p>
        )}

        <label className="field">
          <span>Username</span>
          {/* eslint-disable-next-line jsx-a11y/no-autofocus */}
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus autoComplete="username" />
        </label>
        <label className="field">
          <span>Password</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </label>

        {error && <p className="form-error">{error}</p>}

        <button type="submit" className="btn-primary" disabled={submitting || !username || !password}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>

        <p className="login-hint">
          Local dev logins (see hcm/backend README): <code>hradmin</code> / <code>manager</code> /{' '}
          <code>employee</code>, password matches username + "123".
        </p>
      </form>
    </div>
  )
}
