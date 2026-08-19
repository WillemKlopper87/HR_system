import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { LoginPage } from './auth/LoginPage'
import { RequireAuth, RequireRole } from './auth/RequireAuth'
import { RequirePayrollStepUp } from './auth/RequirePayrollStepUp'
import { AppShell } from './layout/AppShell'
import { ApplicantDetailPage } from './pages/ApplicantDetailPage'
import { ApplicantsPage } from './pages/ApplicantsPage'
import { AssessmentsPage } from './pages/AssessmentsPage'
import { BenefitsPage } from './pages/BenefitsPage'
import { CompProposalsPage } from './pages/CompProposalsPage'
import { DataQualityPage } from './pages/DataQualityPage'
import { EEConfigurationPage } from './pages/EEConfigurationPage'
import { EEReportsPage } from './pages/EEReportsPage'
import { EmployeeDetailPage } from './pages/EmployeeDetailPage'
import { EmployeeListPage } from './pages/EmployeeListPage'
import { EquityDashboardPage } from './pages/EquityDashboardPage'
import { HeadcountDashboardPage } from './pages/HeadcountDashboardPage'
import { MyBenefitsPage } from './pages/MyBenefitsPage'
import { MyLearningPage } from './pages/MyLearningPage'
import { MyProfilePage } from './pages/MyProfilePage'
import { MyPerformancePage } from './pages/MyPerformancePage'
import { PerformancePeriodsPage } from './pages/PerformancePeriodsPage'
import { AuditLogPage } from './pages/AuditLogPage'
import { PerformanceRecordsPage } from './pages/PerformanceRecordsPage'
import { TeamPerformancePage } from './pages/TeamPerformancePage'
import { MyPoliciesPage } from './pages/MyPoliciesPage'
import { OrgStructurePage } from './pages/OrgStructurePage'
import { PayBandsPage } from './pages/PayBandsPage'
import { PolicyComplianceDashboardPage } from './pages/PolicyComplianceDashboardPage'
import { PolicyLibraryPage } from './pages/PolicyLibraryPage'
import { RecruitmentDashboardPage } from './pages/RecruitmentDashboardPage'
import { RequisitionsPage } from './pages/RequisitionsPage'
import { ReviewCyclesPage } from './pages/ReviewCyclesPage'
import { ReviewDetailPage } from './pages/ReviewDetailPage'
import { ReviewsPage } from './pages/ReviewsPage'
import { SkillsInventoryPage } from './pages/SkillsInventoryPage'
import { TeamDevelopmentPage } from './pages/TeamDevelopmentPage'
import { WorkforceIntegrityPage } from './pages/WorkforceIntegrityPage'

// Code-split: face-api.js pulls in TensorFlow.js (~1MB) for client-side
// face descriptor extraction. Only this page needs it, so it shouldn't
// bloat the bundle every other page pays for on load.
const MyIdentityVerificationPage = lazy(() =>
  import('./pages/MyIdentityVerificationPage').then((m) => ({ default: m.MyIdentityVerificationPage })),
)

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
              <Route path="/skills-inventory" element={<SkillsInventoryPage />} />
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
            <Route path="/team-development" element={<TeamDevelopmentPage />} />
            <Route element={<RequireRole roles={['comp_manager', 'hr_admin']} />}>
              <Route
                path="/pay-bands"
                element={<RequirePayrollStepUp><PayBandsPage /></RequirePayrollStepUp>}
              />
              <Route
                path="/comp-proposals"
                element={<RequirePayrollStepUp><CompProposalsPage /></RequirePayrollStepUp>}
              />
              <Route path="/benefits" element={<BenefitsPage />} />
            </Route>
            <Route element={<RequireRole roles={['ee_manager', 'hr_admin']} />}>
              <Route path="/assessments" element={<AssessmentsPage />} />
            </Route>
            <Route
              path="/my-verification"
              element={
                <Suspense fallback={<p className="empty-state">Loading…</p>}>
                  <MyIdentityVerificationPage />
                </Suspense>
              }
            />
            <Route path="/my-profile" element={<MyProfilePage />} />
            <Route path="/my-benefits" element={<MyBenefitsPage />} />
            <Route path="/my-learning" element={<MyLearningPage />} />
            <Route element={<RequireRole roles={['hr_admin']} />}>
              <Route path="/workforce-integrity" element={<WorkforceIntegrityPage />} />
            </Route>
            <Route element={<RequireRole roles={['hr_admin', 'ee_manager', 'accounting_officer', 'auditor']} />}>
              <Route path="/ee-configuration" element={<EEConfigurationPage />} />
              <Route path="/ee-reports" element={<EEReportsPage />} />
              <Route path="/dashboards/equity" element={<EquityDashboardPage />} />
            </Route>
            <Route path="/my-policies" element={<MyPoliciesPage />} />
            <Route path="/my-performance" element={<MyPerformancePage />} />
            <Route path="/team-performance" element={<TeamPerformancePage />} />
            <Route element={<RequireRole roles={['hr_admin']} />}>
              <Route path="/policies" element={<PolicyLibraryPage />} />
              <Route path="/dashboards/policy-acknowledgment" element={<PolicyComplianceDashboardPage />} />
              <Route path="/performance-periods" element={<PerformancePeriodsPage />} />
            </Route>
            <Route element={<RequireRole roles={['hr_admin', 'auditor']} />}>
              <Route path="/performance-records" element={<PerformanceRecordsPage />} />
              <Route path="/audit-log" element={<AuditLogPage />} />
            </Route>
            <Route path="*" element={<Navigate to="/employees" replace />} />
          </Route>
        </Route>
      </Routes>
    </AuthProvider>
  )
}
