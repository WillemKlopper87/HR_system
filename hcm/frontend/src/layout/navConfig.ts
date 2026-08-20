/** The main navigation as data (H2), grouped into collapsible sidebar
 * categories (nav redesign, "Option A"). Adding a page = one entry in the
 * relevant category's `items` array below + one <Route> in App.tsx; the
 * role gate is expressed once, next to the label, instead of as an ad-hoc
 * `hasRole(...) &&` block in the JSX. `roles` empty = every authenticated
 * employee. */
export interface NavItem {
  to: string
  label: string
  /** any-of; empty = everyone */
  roles: readonly string[]
}

export interface NavCategory {
  label: string
  items: readonly NavItem[]
}

const HR = ['hr_admin'] as const
const MANAGER = ['line_manager', 'hr_admin'] as const
const RECRUIT = ['recruiter', 'hr_admin'] as const
const ESTABLISHMENT = ['hr_admin', 'comp_manager', 'accounting_officer', 'auditor', 'recruiter'] as const
const COMP = ['comp_manager', 'hr_admin'] as const
const ASSESS = ['ee_manager', 'hr_admin'] as const
const EE = ['hr_admin', 'ee_manager', 'accounting_officer', 'auditor'] as const
const AUDIT_ROLES = ['hr_admin', 'auditor'] as const
const CONTRACTS = ['hr_admin', 'line_manager', 'auditor'] as const

export const NAV_CATEGORIES: readonly NavCategory[] = [
  {
    label: 'Workforce',
    items: [
      { to: '/employees', label: 'Employees', roles: [] },
      { to: '/org-structure', label: 'Org Structure', roles: [] },
      { to: '/data-quality', label: 'Data Quality', roles: HR },
      { to: '/dashboards/headcount', label: 'Headcount', roles: [] },
    ],
  },
  {
    label: 'Recruitment',
    items: [
      { to: '/requisitions', label: 'Requisitions', roles: RECRUIT },
      { to: '/positions', label: 'Positions', roles: ESTABLISHMENT },
      { to: '/applicants', label: 'Applicants', roles: RECRUIT },
      { to: '/dashboards/recruitment', label: 'Recruitment', roles: RECRUIT },
    ],
  },
  {
    label: 'Compensation',
    items: [
      { to: '/pay-bands', label: 'Pay Bands', roles: COMP },
      { to: '/comp-proposals', label: 'Comp Proposals', roles: COMP },
      { to: '/benefits', label: 'Benefits', roles: COMP },
    ],
  },
  {
    label: 'Performance & Growth',
    items: [
      { to: '/team-performance', label: 'Team Performance', roles: MANAGER },
      { to: '/performance-periods', label: 'Performance Periods', roles: HR },
      { to: '/performance-records', label: 'Performance Records', roles: AUDIT_ROLES },
      { to: '/team-development', label: 'Team Development', roles: [] },
      { to: '/skills-inventory', label: 'Skills Inventory', roles: HR },
      { to: '/assessments', label: 'Assessments', roles: ASSESS },
    ],
  },
  {
    label: 'Compliance & Audit',
    items: [
      { to: '/audit-log', label: 'Audit Log', roles: AUDIT_ROLES },
      { to: '/policies', label: 'Policy Library', roles: HR },
      { to: '/dashboards/policy-acknowledgment', label: 'Policy Compliance', roles: HR },
      { to: '/workforce-integrity', label: 'Workforce Integrity', roles: HR },
    ],
  },
  {
    label: 'Equity',
    items: [
      { to: '/dashboards/equity', label: 'Equity Dashboard', roles: EE },
      { to: '/ee-configuration', label: 'EE Configuration', roles: EE },
      { to: '/ee-reports', label: 'EE Reports', roles: EE },
    ],
  },
  {
    label: 'Contract Renewals',
    items: [
      { to: '/contract-renewals', label: 'Contract Renewals', roles: CONTRACTS },
    ],
  },
  {
    label: 'My Space',
    items: [
      { to: '/my-verification', label: 'My Verification', roles: [] },
      { to: '/my-profile', label: 'My Profile', roles: [] },
      { to: '/my-benefits', label: 'My Benefits', roles: [] },
      { to: '/my-learning', label: 'My Learning', roles: [] },
      { to: '/my-policies', label: 'My Policies', roles: [] },
      { to: '/my-performance', label: 'My Performance', roles: [] },
    ],
  },
]

/** Flattened view derived from NAV_CATEGORIES (single source of truth) —
 * kept for any consumer that just wants "all nav items" without caring
 * about category grouping. */
export const NAV_ITEMS: readonly NavItem[] = NAV_CATEGORIES.flatMap((category) => category.items)
