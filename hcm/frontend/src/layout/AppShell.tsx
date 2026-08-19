import { NavLink, Outlet } from 'react-router-dom'
import { ReferenceDataProvider } from '../api/ReferenceDataContext'
import { useAuth } from '../auth/AuthContext'
import { NAV_ITEMS } from './navConfig'
import { NotificationBell } from './NotificationBell'

export function AppShell() {
  const { user, logout, hasRole } = useAuth()
  const visible = NAV_ITEMS.filter((item) => item.roles.length === 0 || item.roles.some(hasRole))

  return (
    <ReferenceDataProvider>
      <div className="app-shell">
        <header className="app-header">
          <div className="app-brand">Sentech HCM</div>
          <nav className="app-nav">
            {visible.map((item) => (
              <NavLink key={item.to} to={item.to} className={({ isActive }) => (isActive ? 'active' : undefined)}>
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="app-user">
            <NotificationBell />
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
