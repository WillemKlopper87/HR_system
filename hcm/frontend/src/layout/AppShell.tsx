import { NavLink, Outlet } from 'react-router-dom'
import { ReferenceDataProvider } from '../api/ReferenceDataContext'
import { useAuth } from '../auth/AuthContext'

export function AppShell() {
  const { user, logout, hasRole } = useAuth()
  const canRecruit = hasRole('recruiter') || hasRole('hr_admin')

  return (
    <ReferenceDataProvider>
      <div className="app-shell">
        <header className="app-header">
          <div className="app-brand">Sentech HCM</div>
          <nav className="app-nav">
            <NavLink to="/employees" className={({ isActive }) => (isActive ? 'active' : undefined)}>
              Employees
            </NavLink>
            <NavLink to="/org-structure" className={({ isActive }) => (isActive ? 'active' : undefined)}>
              Org Structure
            </NavLink>
            {hasRole('hr_admin') && (
              <NavLink to="/data-quality" className={({ isActive }) => (isActive ? 'active' : undefined)}>
                Data Quality
              </NavLink>
            )}
            <NavLink to="/dashboards/headcount" className={({ isActive }) => (isActive ? 'active' : undefined)}>
              Headcount
            </NavLink>
            {canRecruit && (
              <>
                <NavLink to="/requisitions" className={({ isActive }) => (isActive ? 'active' : undefined)}>
                  Requisitions
                </NavLink>
                <NavLink to="/applicants" className={({ isActive }) => (isActive ? 'active' : undefined)}>
                  Applicants
                </NavLink>
                <NavLink to="/dashboards/recruitment" className={({ isActive }) => (isActive ? 'active' : undefined)}>
                  Recruitment
                </NavLink>
              </>
            )}
            <NavLink to="/reviews" className={({ isActive }) => (isActive ? 'active' : undefined)}>
              Reviews
            </NavLink>
            {hasRole('hr_admin') && (
              <NavLink to="/review-cycles" className={({ isActive }) => (isActive ? 'active' : undefined)}>
                Review Cycles
              </NavLink>
            )}
          </nav>
          <div className="app-user">
            <span>
              {user?.first_name} {user?.last_name}
            </span>
            <button type="button" className="btn-link" onClick={() => void logout()}>
              Sign out
            </button>
          </div>
        </header>
        <main className="app-main">
          <Outlet />
        </main>
      </div>
    </ReferenceDataProvider>
  )
}
