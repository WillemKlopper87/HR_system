import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { ReferenceDataProvider } from '../api/ReferenceDataContext'
import { useAuth } from '../auth/useAuth'
import { NAV_CATEGORIES } from './navConfig'
import { NotificationBell } from './NotificationBell'

export function AppShell() {
  const { user, logout, hasRole } = useAuth()
  // Role-gate per category, then drop categories left with nothing visible
  // (same filter NAV_ITEMS used, just applied per-category now).
  const categories = NAV_CATEGORIES.map((category) => ({
    label: category.label,
    items: category.items.filter((item) => item.roles.length === 0 || item.roles.some(hasRole)),
  })).filter((category) => category.items.length > 0)

  // All categories start expanded. At 7 categories / 30 items total that
  // reads cleanly without also having to track "which category contains
  // the active route" — and it means a direct deep link (bookmark,
  // notification link, browser back/forward) always lands with its own
  // nav item visible instead of tucked behind a collapsed header.
  const [collapsedCategories, setCollapsedCategories] = useState<ReadonlySet<string>>(() => new Set())

  function toggleCategory(label: string) {
    setCollapsedCategories((prev) => {
      const next = new Set(prev)
      if (next.has(label)) next.delete(label)
      else next.add(label)
      return next
    })
  }

  return (
    <ReferenceDataProvider>
      <div className="app-shell">
        <aside className="app-sidebar">
          <div className="app-brand">Sentech HCM</div>
          <nav className="app-nav">
            {categories.map((category) => {
              const isCollapsed = collapsedCategories.has(category.label)
              return (
                <div className="nav-category" key={category.label}>
                  <button
                    type="button"
                    className="nav-category-header"
                    aria-expanded={!isCollapsed}
                    onClick={() => toggleCategory(category.label)}
                  >
                    <span className="nav-category-chevron" aria-hidden="true">
                      {isCollapsed ? '▸' : '▾'}
                    </span>
                    {category.label}
                  </button>
                  {!isCollapsed && (
                    <div className="nav-category-items">
                      {category.items.map((item) => (
                        <NavLink key={item.to} to={item.to} className={({ isActive }) => (isActive ? 'active' : undefined)}>
                          {item.label}
                        </NavLink>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
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
        </aside>
        <main className="app-main">
          <Outlet />
        </main>
      </div>
    </ReferenceDataProvider>
  )
}
