import { NavLink, Outlet } from 'react-router-dom'
import { ReferenceDataProvider } from '../api/ReferenceDataContext'
import { useAuth } from '../auth/AuthContext'

export function AppShell() {
  const { user, logout, hasRole } = useAuth()
  const canRecruit = hasRole('recruiter') || hasRole('hr_admin')
  const canManageComp = hasRole('comp_manager') || hasRole('hr_admin')
  const canManageAssessments = hasRole('ee_manager') || hasRole('hr_admin')
  const canSeeEEReporting =
    hasRole('hr_admin') || hasRole('ee_manager') || hasRole('accounting_officer') || hasRole('auditor')

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
            <NavLink to="/team-development" className={({ isActive }) => (isActive ? 'active' : undefined)}>
              Team Development
            </NavLink>
            {canManageComp && (
              <>
                <NavLink to="/pay-bands" className={({ isActive }) => (isActive ? 'active' : undefined)}>
                  Pay Bands
                </NavLink>
                <NavLink to="/comp-proposals" className={({ isActive }) => (isActive ? 'active' : undefined)}>
                  Comp Proposals
                </NavLink>
                <NavLink to="/benefits" className={({ isActive }) => (isActive ? 'active' : undefined)}>
                  Benefits
                </NavLink>
              </>
            )}
            {hasRole('hr_admin') && (
              <NavLink to="/skills-inventory" className={({ isActive }) => (isActive ? 'active' : undefined)}>
                Skills Inventory
              </NavLink>
            )}
            {canManageAssessments && (
              <NavLink to="/assessments" className={({ isActive }) => (isActive ? 'active' : undefined)}>
                Assessments
              </NavLink>
            )}
            <NavLink to="/my-verification" className={({ isActive }) => (isActive ? 'active' : undefined)}>
              My Verification
            </NavLink>
            <NavLink to="/my-profile" className={({ isActive }) => (isActive ? 'active' : undefined)}>
              My Profile
            </NavLink>
            <NavLink to="/my-benefits" className={({ isActive }) => (isActive ? 'active' : undefined)}>
              My Benefits
            </NavLink>
            <NavLink to="/my-learning" className={({ isActive }) => (isActive ? 'active' : undefined)}>
              My Learning
            </NavLink>
            <NavLink to="/my-policies" className={({ isActive }) => (isActive ? 'active' : undefined)}>
              My Policies
            </NavLink>
            {hasRole('hr_admin') && (
              <>
                <NavLink to="/policies" className={({ isActive }) => (isActive ? 'active' : undefined)}>
                  Policy Library
                </NavLink>
                <NavLink to="/dashboards/policy-acknowledgment" className={({ isActive }) => (isActive ? 'active' : undefined)}>
                  Policy Compliance
                </NavLink>
              </>
            )}
            {hasRole('hr_admin') && (
              <NavLink to="/workforce-integrity" className={({ isActive }) => (isActive ? 'active' : undefined)}>
                Workforce Integrity
              </NavLink>
            )}
            {canSeeEEReporting && (
              <>
                <NavLink to="/dashboards/equity" className={({ isActive }) => (isActive ? 'active' : undefined)}>
                  Equity Dashboard
                </NavLink>
                <NavLink to="/ee-configuration" className={({ isActive }) => (isActive ? 'active' : undefined)}>
                  EE Configuration
                </NavLink>
                <NavLink to="/ee-reports" className={({ isActive }) => (isActive ? 'active' : undefined)}>
                  EE Reports
                </NavLink>
              </>
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
