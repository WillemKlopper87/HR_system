/** The main navigation as data (H2). Adding a page = one entry here + one
 * <Route> in App.tsx; the role gate is expressed once, next to the label,
 * instead of as an ad-hoc `hasRole(...) &&` block in the JSX. `roles`
 * empty = every authenticated employee. */
export interface NavItem {
  to: string
  label: string
  /** any-of; empty = everyone */
  roles: readonly string[]
}

const HR = ['hr_admin'] as const
const MANAGER = ['line_manager', 'hr_admin'] as const
const RECRUIT = ['recruiter', 'hr_admin'] as const
const ESTABLISHMENT = ['hr_admin', 'comp_manager', 'accounting_officer', 'auditor', 'recruiter'] as const
const COMP = ['comp_manager', 'hr_admin'] as const
const ASSESS = ['ee_manager', 'hr_admin'] as const
const EE = ['hr_admin', 'ee_manager', 'accounting_officer', 'auditor'] as const
const AUDIT_ROLES = ['hr_admin', 'auditor'] as const

export const NAV_ITEMS: readonly NavItem[] = [
  { to: '/employees', label: 'Employees', roles: [] },
  { to: '/org-structure', label: 'Org Structure', roles: [] },
  { to: '/data-quality', label: 'Data Quality', roles: HR },
  { to: '/dashboards/headcount', label: 'Headcount', roles: [] },
  { to: '/requisitions', label: 'Requisitions', roles: RECRUIT },
  { to: '/positions', label: 'Positions', roles: ESTABLISHMENT },
  { to: '/applicants', label: 'Applicants', roles: RECRUIT },
  { to: '/dashboards/recruitment', label: 'Recruitment', roles: RECRUIT },
  { to: '/team-development', label: 'Team Development', roles: [] },
  { to: '/pay-bands', label: 'Pay Bands', roles: COMP },
  { to: '/comp-proposals', label: 'Comp Proposals', roles: COMP },
  { to: '/benefits', label: 'Benefits', roles: COMP },
  { to: '/skills-inventory', label: 'Skills Inventory', roles: HR },
  { to: '/assessments', label: 'Assessments', roles: ASSESS },
  { to: '/my-verification', label: 'My Verification', roles: [] },
  { to: '/my-profile', label: 'My Profile', roles: [] },
  { to: '/my-benefits', label: 'My Benefits', roles: [] },
  { to: '/my-learning', label: 'My Learning', roles: [] },
  { to: '/my-policies', label: 'My Policies', roles: [] },
  { to: '/my-performance', label: 'My Performance', roles: [] },
  { to: '/team-performance', label: 'Team Performance', roles: MANAGER },
  { to: '/performance-periods', label: 'Performance Periods', roles: HR },
  { to: '/performance-records', label: 'Performance Records', roles: AUDIT_ROLES },
  { to: '/audit-log', label: 'Audit Log', roles: AUDIT_ROLES },
  { to: '/policies', label: 'Policy Library', roles: HR },
  { to: '/dashboards/policy-acknowledgment', label: 'Policy Compliance', roles: HR },
  { to: '/workforce-integrity', label: 'Workforce Integrity', roles: HR },
  { to: '/dashboards/equity', label: 'Equity Dashboard', roles: EE },
  { to: '/ee-configuration', label: 'EE Configuration', roles: EE },
  { to: '/ee-reports', label: 'EE Reports', roles: EE },
]
