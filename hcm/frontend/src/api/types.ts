export interface MeResponse {
  employee_id: number
  employee_number: string
  first_name: string
  last_name: string
  work_email: string
  roles: string[]
}

export interface Employee {
  id: number
  employee_number: string
  first_name: string
  last_name: string
  preferred_name: string
  // Restricted-tier fields — present only for roles with R-tier read
  // (Data-Dictionary.md); absent (not just empty) for everyone else.
  national_id_number?: string
  passport_number?: string
  date_of_birth: string
  work_email: string
  personal_email?: string
  phone?: string
  hire_date: string
}

export interface EmployeeVersion {
  id: number
  employee: number
  valid_from: string
  valid_to: string | null
  department: number
  job_title: string
  occupational_level: number
  job_grade: number | null
  manager: number | null
  employment_status: string
  // Sensitive-tier fields — stripped entirely for roles without S-tier
  // read (e.g. line_manager sees none of these on a report's record).
  citizenship_status?: string
  location: number
  race?: string
  gender?: string
  disability_status?: string
  disability_detail?: string
  race_source?: string
  disability_source?: string
}

export interface Department {
  id: number
  name: string
  code: string
  parent: number | null
  active: boolean
}

export interface OccupationalLevel {
  id: number
  name: string
  code: string
  order: number
  active: boolean
}

export interface JobGrade {
  id: number
  name: string
  code: string
  occupational_level: number
  active: boolean
}

export interface Location {
  id: number
  name: string
  code: string
  province: string
  active: boolean
}

export interface DataQualityException {
  id: number
  employee: number
  employee_number: string
  employee_name: string
  exception_type: 'missing_grade' | 'missing_demographics' | 'orphan_record'
  detail: string
  detected_at: string
  resolved_at: string | null
}

/** Shared shape for every "count of X by Y" dashboard breakdown — used by
 * the headcount, recruitment, and skills-inventory dashboards alike, all
 * rendered through the one shared <Breakdown> component. */
export interface BreakdownRow {
  key: string
  count: number | string
  suppressed?: boolean
}

export type HeadcountBreakdownRow = BreakdownRow

export interface HeadcountDashboard {
  total_headcount: number
  small_cell_suppression_applied: boolean
  by_department: HeadcountBreakdownRow[]
  by_occupational_level: HeadcountBreakdownRow[]
  by_job_grade: HeadcountBreakdownRow[]
  by_race: HeadcountBreakdownRow[]
  by_gender: HeadcountBreakdownRow[]
  by_disability_status: HeadcountBreakdownRow[]
}

export const EXCEPTION_TYPE_LABELS: Record<DataQualityException['exception_type'], string> = {
  missing_grade: 'Missing job grade',
  missing_demographics: 'Missing demographics',
  orphan_record: 'Orphan record (no version history)',
}

export type RequisitionStatus = 'draft' | 'open' | 'on_hold' | 'closed' | 'filled'

export interface Requisition {
  id: number
  title: string
  department: number
  occupational_level: number
  job_grade: number | null
  location: number
  headcount: number
  status: RequisitionStatus
  hiring_manager: number | null
  created_by: number | null
  opened_at: string | null
  target_fill_date: string | null
  closed_at: string | null
}

export type ApplicantStage = 'applied' | 'screened' | 'interview' | 'offer' | 'hired' | 'rejected'

export interface Applicant {
  id: number
  requisition: number
  first_name: string
  last_name: string
  email: string
  phone?: string
  date_of_birth?: string
  current_stage: ApplicantStage
  rejected_reason?: string
  has_demographic_consent: boolean
  // Sensitive-tier, consent-gated — absent (not empty) until consent
  // exists AND the viewer's role grants Sensitive-tier read.
  race?: string
  gender?: string
  disability_status?: string
  resulting_employee: number | null
}

export interface ApplicantStageEvent {
  id: number
  applicant: number
  from_stage: string
  to_stage: string
  changed_by: number | null
  notes: string
  created_at: string
}

export type OfferStatus = 'proposed' | 'approved' | 'accepted' | 'declined' | 'withdrawn'

export interface Offer {
  id: number
  applicant: number
  proposed_job_grade: number
  proposed_annual_salary: string
  status: OfferStatus
  proposed_by: number | null
  approved_by: number | null
  approved_at: string | null
  start_date: string | null
}

export type RecruitmentBreakdownRow = BreakdownRow

export interface RecruitmentDashboard {
  open_requisitions: number
  total_applicants: number
  avg_time_to_fill_days: number | null
  small_cell_suppression_applied: boolean
  by_stage: RecruitmentBreakdownRow[]
  by_race: RecruitmentBreakdownRow[]
  by_gender: RecruitmentBreakdownRow[]
  by_disability_status: RecruitmentBreakdownRow[]
}

export const STAGE_LABELS: Record<ApplicantStage, string> = {
  applied: 'Applied',
  screened: 'Screened',
  interview: 'Interview',
  offer: 'Offer',
  hired: 'Hired',
  rejected: 'Rejected',
}

export const REQUISITION_STATUS_LABELS: Record<RequisitionStatus, string> = {
  draft: 'Draft',
  open: 'Open',
  on_hold: 'On hold',
  closed: 'Closed',
  filled: 'Filled',
}

export type ReviewCycleType = 'annual' | 'biannual'
export type ReviewCycleStatus = 'draft' | 'launched' | 'closed'

export interface ReviewCycle {
  id: number
  name: string
  cycle_type: ReviewCycleType
  status: ReviewCycleStatus
  start_date: string
  end_date: string
  launched_at: string | null
  closed_at: string | null
  created_by: number | null
}

export interface ReviewCycleCompletion {
  total: number
  self_submitted: number
  self_submitted_pct: number
  manager_submitted: number
  manager_submitted_pct: number
  completed: number
  completed_pct: number
}

export type GoalStatus = 'draft' | 'active' | 'completed' | 'cancelled'

export interface Goal {
  id: number
  employee: number
  manager: number | null
  title: string
  description?: string
  target_date: string | null
  status: GoalStatus
  created_by: number | null
}

export type ReviewCompletionStatus = 'not_started' | 'self_submitted' | 'manager_submitted' | 'completed'

export interface Review {
  id: number
  review_cycle: number
  employee: number
  manager: number | null
  self_rating: number | null
  self_comments: string
  self_submitted_at: string | null
  manager_rating: number | null
  manager_comments: string
  manager_submitted_at: string | null
  completion_status: ReviewCompletionStatus
}

export type FeedbackType = 'manager' | 'peer'

export interface Feedback {
  id: number
  employee: number
  author: number | null
  feedback_type: FeedbackType
  text: string
  created_at: string
}

export type SkillCategory = 'technical' | 'soft' | 'leadership' | 'compliance' | 'other'

export interface Skill {
  id: number
  name: string
  category: SkillCategory
  description?: string
  active: boolean
}

export type ProficiencyLevel = 'beginner' | 'intermediate' | 'advanced' | 'expert'

export interface EmployeeSkill {
  id: number
  employee: number
  skill: number
  proficiency?: ProficiencyLevel
  acquired_date?: string | null
  notes?: string
}

export interface Certification {
  id: number
  employee: number
  name?: string
  issuing_body?: string
  credential_id?: string
  issue_date?: string | null
  expiry_date?: string | null
  is_expired?: boolean
}

export type TrainingStatus = 'planned' | 'in_progress' | 'completed' | 'cancelled'

export interface TrainingRecord {
  id: number
  employee: number
  title?: string
  provider?: string
  status?: TrainingStatus
  start_date?: string | null
  completion_date?: string | null
  hours?: string | null
  cost?: string | null
}

export interface SkillsInventoryRow {
  skill: string
  category: SkillCategory
  total_holders: number
  by_department: { key: string; count: number }[]
  by_occupational_level: { key: string; count: number }[]
}

export interface TeamDevelopmentRow {
  employee: number
  employee_number: string
  name: string
  skill_count: number
  certification_count: number
  active_training_count: number
  completed_training_count: number
}
