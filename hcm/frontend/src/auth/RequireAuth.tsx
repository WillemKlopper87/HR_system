import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from './AuthContext'

export function RequireAuth() {
  const { user, loading } = useAuth()

  if (loading) return <div className="page-loading">Loading…</div>
  if (!user) return <Navigate to="/login" replace />
  return <Outlet />
}

export function RequireRole({ roles }: { roles: string[] }) {
  const { hasRole } = useAuth()
  if (!roles.some(hasRole)) return <Navigate to="/employees" replace />
  return <Outlet />
}
