import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { LoginPage } from './auth/LoginPage'
import { RequireAuth, RequireRole } from './auth/RequireAuth'
import { AppShell } from './layout/AppShell'
import { DataQualityPage } from './pages/DataQualityPage'
import { EmployeeDetailPage } from './pages/EmployeeDetailPage'
import { EmployeeListPage } from './pages/EmployeeListPage'
import { HeadcountDashboardPage } from './pages/HeadcountDashboardPage'
import { OrgStructurePage } from './pages/OrgStructurePage'

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAuth />}>
          <Route element={<AppShell />}>
            <Route index element={<Navigate to="/employees" replace />} />
            <Route path="/employees" element={<EmployeeListPage />} />
            <Route path="/employees/:id" element={<EmployeeDetailPage />} />
            <Route path="/org-structure" element={<OrgStructurePage />} />
            <Route element={<RequireRole role="hr_admin" />}>
              <Route path="/data-quality" element={<DataQualityPage />} />
            </Route>
            <Route path="/dashboards/headcount" element={<HeadcountDashboardPage />} />
            <Route path="*" element={<Navigate to="/employees" replace />} />
          </Route>
        </Route>
      </Routes>
    </AuthProvider>
  )
}
