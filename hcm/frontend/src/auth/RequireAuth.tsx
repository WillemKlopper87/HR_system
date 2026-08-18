import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from './AuthContext'

export function RequireAuth() {
  const { user, loading, explicitLogout } = useAuth()
  const location = useLocation()

  if (loading) return <div className="page-loading">Loading…</div>
  // Remember where the user was so login can return them there — matters
  // most after a session expiry mid-task (see AuthContext.sessionExpired) —
  // but not after an explicit Sign out: then the next login starts at home.
  if (!user) {
    return (
      <Navigate to="/login" replace state={explicitLogout ? undefined : { from: location.pathname + location.search }} />
    )
  }
  return <Outlet />
}

export function RequireRole({ roles }: { roles: string[] }) {
  const { hasRole } = useAuth()
  if (!roles.some(hasRole)) return <Navigate to="/employees" replace />
  return <Outlet />
}
