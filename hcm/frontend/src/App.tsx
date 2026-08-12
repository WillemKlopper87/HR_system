import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { LoginPage } from './auth/LoginPage'
import { RequireAuth, RequireRole } from './auth/RequireAuth'
import { AppShell } from './layout/AppShell'
import { ApplicantDetailPage } from './pages/ApplicantDetailPage'
import { ApplicantsPage } from './pages/ApplicantsPage'
import { DataQualityPage } from './pages/DataQualityPage'
import { EmployeeDetailPage } from './pages/EmployeeDetailPage'
import { EmployeeListPage } from './pages/EmployeeListPage'
import { HeadcountDashboardPage } from './pages/HeadcountDashboardPage'
import { OrgStructurePage } from './pages/OrgStructurePage'
import { RecruitmentDashboardPage } from './pages/RecruitmentDashboardPage'
import { RequisitionsPage } from './pages/RequisitionsPage'
import { ReviewCyclesPage } from './pages/ReviewCyclesPage'
import { ReviewDetailPage } from './pages/ReviewDetailPage'
import { ReviewsPage } from './pages/ReviewsPage'

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
            <Route element={<RequireRole roles={['hr_admin']} />}>
              <Route path="/data-quality" element={<DataQualityPage />} />
              <Route path="/review-cycles" element={<ReviewCyclesPage />} />
            </Route>
            <Route path="/dashboards/headcount" element={<HeadcountDashboardPage />} />
            <Route element={<RequireRole roles={['recruiter', 'hr_admin']} />}>
              <Route path="/requisitions" element={<RequisitionsPage />} />
              <Route path="/applicants" element={<ApplicantsPage />} />
              <Route path="/applicants/:id" element={<ApplicantDetailPage />} />
              <Route path="/dashboards/recruitment" element={<RecruitmentDashboardPage />} />
            </Route>
            <Route path="/reviews" element={<ReviewsPage />} />
            <Route path="/reviews/:id" element={<ReviewDetailPage />} />
            <Route path="*" element={<Navigate to="/employees" replace />} />
          </Route>
        </Route>
      </Routes>
    </AuthProvider>
  )
}
