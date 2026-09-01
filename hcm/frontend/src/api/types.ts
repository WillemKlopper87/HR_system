import type { ExitInterviewReason } from './contracts'

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
  has_demographic_consent: boolean
  current_department: number | null
  current_occupational_level: number | null
  current_employment_status: string | null
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
  contract_end_date: string | null
  contract_renewal_decision: ContractRenewalDecision | null
}

// ---- Contract end-date tracking & renewal decisions (C1 part 2) ----

export type ContractAction = 'renew' | 'convert_permanent' | 'let_lapse'
export type ContractDecisionStatus = 'recommended' | 'decided'

export interface ContractRenewalDecision {
  id: number
  status: ContractDecisionStatus
  recommended_action: ContractAction | null
  recommended_by: number | null
  recommended_at: string | null
  recommended_comment: string
  recommended_end_date: string | null
  decided_action: ContractAction | null
  decided_by: number | null
  decided_at: string | null
  decided_comment: string
  decided_end_date: string | null
  resulting_employee_version: number | null
}

export const CONTRACT_ACTION_LABELS: Record<ContractAction, string> = {
  renew: 'Renew',
  convert_permanent: 'Convert to permanent',
  let_lapse: 'Let lapse',
}

// ProbationStatus/ProbationRecommendation/ProbationReview/ProbationPeriod and
// their label maps were migrated to the generated-contract facade -- see
// api/contracts.ts and api/contract-labels.ts, and
// docs/frontend/generated-api-contracts.md for the migration pattern.

export interface ProbationCompletionBreakdownRow {
  key: string
  confirmed: number | string
  terminated: number | string
  completion_pct: number | null
  suppressed: boolean
}

export interface ProbationCompletionDashboard {
  small_cell_suppression_applied: boolean
  total_closed: number
  total_confirmed: number
  overall_completion_pct: number | null
  in_progress: number
  by_race: ProbationCompletionBreakdownRow[]
  by_gender: ProbationCompletionBreakdownRow[]
  by_disability_status: ProbationCompletionBreakdownRow[]
}

// ExitInterviewReason/ExitInterview and their label map were migrated to the
// generated-contract facade -- see api/contracts.ts and api/contract-labels.ts.

export interface ExitInterviewGroupBreakdownRow {
  key: string
  total: number | string
  by_reason: Partial<Record<ExitInterviewReason, number | string>>
  suppressed: boolean
}

export interface ExitInterviewDashboard {
  small_cell_suppression_applied: boolean
  total_interviews: number
  by_reason: { key: ExitInterviewReason; count: number }[]
  by_race: ExitInterviewGroupBreakdownRow[]
  by_gender: ExitInterviewGroupBreakdownRow[]
  by_disability_status: ExitInterviewGroupBreakdownRow[]
}

// ---- Employment exit states & access cascade (C1 part 3) ----

export type EmploymentChangeType =
  | 'suspension'
  | 'lift_suspension'
  | 'dismissal_summary'
  | 'dismissal_misconduct'
  | 'dismissal_incapacity'
  | 'operational_requirements'
  | 'resignation'
  | 'retirement'
  | 'contract_end'
  | 'death'

export type EmploymentChangeState = 'proposed' | 'confirmed' | 'executed' | 'cancelled'

export interface EmploymentChange {
  id: number
  employee: number
  change_type: EmploymentChangeType
  state: EmploymentChangeState
  effective_date: string
  reason: string
  proposed_by: number | null
  proposed_at: string | null
  confirmed_by: number | null
  confirmed_at: string | null
  executed_at: string | null
  cancelled_by: number | null
  cancelled_at: string | null
  cancellation_reason: string
  lifts_suspension: number | null
  resulting_event: number | null
}

export const EMPLOYMENT_CHANGE_TYPE_LABELS: Record<EmploymentChangeType, string> = {
  suspension: 'Suspension (pending investigation)',
  lift_suspension: 'Lift suspension',
  dismissal_summary: 'Summary dismissal',
  dismissal_misconduct: 'Dismissal — misconduct',
  dismissal_incapacity: 'Dismissal — incapacity',
  operational_requirements: 'Operational requirements',
  resignation: 'Resignation',
  retirement: 'Retirement',
  contract_end: 'Contract end',
  death: 'Death',
}

/** Types that require a *different* hr_admin to confirm (design spec §4.2 —
 * the ones with CCMA exposure or that are hardest to undo). Mirrored here so
 * the form can warn before submission; the backend is the actual authority
 * and rejects a same-person confirmation regardless of what the UI shows. */
export const TIERED_CHANGE_TYPES: readonly EmploymentChangeType[] = [
  'suspension',
  'lift_suspension',
  'dismissal_summary',
  'dismissal_misconduct',
  'dismissal_incapacity',
  'operational_requirements',
]

/** Change types a user proposes directly. `contract_end` is excluded on
 * purpose: it is produced by the contract renewal workflow's `let_lapse`
 * (which carries its own two-actor review), never captured by hand here. */
export const PROPOSABLE_CHANGE_TYPES: readonly EmploymentChangeType[] = [
  'suspension',
  'lift_suspension',
  'resignation',
  'retirement',
  'dismissal_summary',
  'dismissal_misconduct',
  'dismissal_incapacity',
  'operational_requirements',
  'death',
]

export interface Department {
  id: number
  name: string
  code: string
  parent: number | null
  active: boolean
}

// --- Onboarding / offboarding checklists (C1 part 3 slice 3) -------------

export type ChecklistDirection = 'onboarding' | 'offboarding'
export type ChecklistTemplateStatus = 'draft' | 'published' | 'retired'
export type ChecklistInstanceStatus = 'active' | 'completed' | 'cancelled'
export type ChecklistOwnerRole = 'hr' | 'it' | 'line_manager' | 'employee' | 'other'

export const CHECKLIST_DIRECTION_LABELS: Record<ChecklistDirection, string> = {
  onboarding: 'Onboarding',
  offboarding: 'Offboarding',
}

export const CHECKLIST_OWNER_ROLE_LABELS: Record<ChecklistOwnerRole, string> = {
  hr: 'HR',
  it: 'IT',
  line_manager: 'Line manager',
  employee: 'Employee',
  other: 'Other',
}

export interface ChecklistTemplateItem {
  id: number
  template: number
  label: string
  description: string
  owner_role: ChecklistOwnerRole
  order: number
}

export interface ChecklistTemplate {
  id: number
  name: string
  direction: ChecklistDirection
  version: number
  status: ChecklistTemplateStatus
  created_by: number | null
  published_at: string | null
  created_at: string
  items: ChecklistTemplateItem[]
}

export interface ChecklistInstanceItem {
  id: number
  instance: number
  label: string
  description: string
  owner_role: ChecklistOwnerRole
  order: number
  completed_by: number | null
  completed_at: string | null
  notes: string
  is_complete: boolean
}

export interface ChecklistInstance {
  id: number
  employee: number
  employee_display: string
  template: number
  template_version: number
  direction: ChecklistDirection
  status: ChecklistInstanceStatus
  triggering_change: number | null
  created_by: number | null
  created_at: string
  completed_at: string | null
  items: ChecklistInstanceItem[]
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

// --- Role-adaptive overview dashboard (Wireframe all features spec(4),
// Style A) -----------------------------------------------------------

export type OverviewRowScope = 'employee' | 'line_manager' | 'hr_admin'
export type OverviewTone = 'good' | 'warn' | 'bad' | 'neutral'

export interface OverviewKpi {
  label: string
  value: string
  delta: string
  tone: OverviewTone
}

export interface OverviewQueueItem {
  title: string
  meta: string
  ref: string
  age: string
  primary: string
  secondary: string
  href: string
}

export interface OverviewPolicyRow {
  title: string
  acknowledged_pct: number
}

export interface OverviewTrainingCompliance {
  compliant: number
  due: number
  overdue: number
  total: number
  compliant_pct: number | null
}

export interface OverviewDashboard {
  as_of: string
  row_scope: OverviewRowScope
  scope_note: string
  kpis: OverviewKpi[]
  queue: OverviewQueueItem[]
  queue_count: number
  departments?: BreakdownRow[]
  occupational_levels?: BreakdownRow[]
  small_cell_suppression_applied?: boolean
  recruitment_funnel?: BreakdownRow[]
  training_compliance?: OverviewTrainingCompliance
  policy_acknowledgment?: OverviewPolicyRow[]
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

// ---- Position / establishment control (Position-Establishment plan) ----

export type PositionStatus = 'draft' | 'in_review' | 'approved' | 'rejected'

export interface PositionApprovalStep {
  id: number
  step_index: number
  role: string
  actor: number | null
  decision: 'approved' | 'rejected'
  comment: string
  created_at: string
}

export interface Position {
  id: number
  post_number: string
  title: string
  department: number
  occupational_level: number
  job_grade: number | null
  location: number
  status: PositionStatus
  current_step: number
  proposed_by: number | null
  approval_steps: PositionApprovalStep[]
  is_vacant: boolean
  current_incumbent_number: string | null
  /** The role that must act next (server-computed from the live, deployment-
   * configurable settings.POSITION_APPROVAL_CHAIN) -- null unless status is
   * 'in_review'. Read this instead of re-deriving it from a hardcoded chain
   * on the frontend, since the chain's roles/length can vary by deployment. */
  next_approver_role: string | null
}

export const POSITION_STATUS_LABELS: Record<PositionStatus, string> = {
  draft: 'Draft',
  in_review: 'In review',
  approved: 'Approved',
  rejected: 'Rejected',
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
  positions: number[]
  hiring_manager: number | null
  created_by: number | null
  opened_at: string | null
  target_fill_date: string | null
  closed_at: string | null
  // C6 careers portal — description is generally useful (not portal-only);
  // external_posting is the deliberate opt-in flag (default false).
  description?: string
  external_posting: boolean
}

export type ApplicantStage = 'applied' | 'screened' | 'interview' | 'offer' | 'hired' | 'rejected'
export type ApplicantSource = 'internal' | 'portal'

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
  source: ApplicantSource
  // write-only on the wire (upload only) -- reads never return a storage
  // locator; see has_resume/resume_download_url below (2026-08-28 fix).
  resume?: File
  has_resume: boolean
  resume_download_url: string | null
  resume_content_type?: string
  resume_size_bytes?: number
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
  total_applicants: number | string
  avg_time_to_fill_days: number | null
  small_cell_suppression_applied: boolean
  by_stage: RecruitmentBreakdownRow[]
  by_race: RecruitmentBreakdownRow[]
  by_gender: RecruitmentBreakdownRow[]
  by_disability_status: RecruitmentBreakdownRow[]
}

export interface RecruitmentFunnelStageRow {
  stage: Exclude<ApplicantStage, 'rejected'>
  total: number | string
  breakdown: RecruitmentBreakdownRow[]
}

export interface RecruitmentFunnel {
  small_cell_suppression_applied: boolean
  total_applicants: number | string
  by_race: RecruitmentFunnelStageRow[]
  by_gender: RecruitmentFunnelStageRow[]
  by_disability_status: RecruitmentFunnelStageRow[]
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

// --- C6: interview scheduling, panel scorecards, background checks -------

export type InterviewSessionStatus = 'scheduled' | 'completed' | 'cancelled'

export interface InterviewApplicantSummary {
  id: number
  first_name: string
  last_name: string
  requisition: number
  requisition_title: string
  current_stage: ApplicantStage
}

export interface InterviewSession {
  id: number
  applicant: number
  applicant_summary: InterviewApplicantSummary
  round_number: number
  scheduled_at: string
  duration_minutes: number
  location: string
  status: InterviewSessionStatus
  notes: string
  interviewers: number[]
  created_by: number | null
  created_at: string
}

export const INTERVIEW_SESSION_STATUS_LABELS: Record<InterviewSessionStatus, string> = {
  scheduled: 'Scheduled',
  completed: 'Completed',
  cancelled: 'Cancelled',
}

export type InterviewRecommendation = 'strong_hire' | 'hire' | 'no_hire' | 'strong_no_hire'

export interface InterviewScorecard {
  id: number
  session: number
  interviewer: number
  // Blind-review masked (design spec §2.2): a scorecard whose content isn't
  // yet visible to the viewer omits these five fields entirely rather than
  // sending null — treat their absence as "not visible yet", not "unrated".
  skill_rating?: number
  communication_rating?: number
  culture_fit_rating?: number
  comments?: string
  recommendation?: InterviewRecommendation
  created_at: string
}

export const INTERVIEW_RECOMMENDATION_LABELS: Record<InterviewRecommendation, string> = {
  strong_hire: 'Strong hire',
  hire: 'Hire',
  no_hire: 'No hire',
  strong_no_hire: 'Strong no hire',
}

export type BackgroundCheckType =
  | 'reference'
  | 'criminal_record'
  | 'qualification_verification'
  | 'credit_check'
  | 'other'
export type BackgroundCheckStatus = 'not_started' | 'requested' | 'in_progress' | 'cleared' | 'flagged'

export interface BackgroundCheck {
  id: number
  applicant: number
  check_type: BackgroundCheckType
  status: BackgroundCheckStatus
  requested_by: number | null
  requested_at: string | null
  completed_at: string | null
  notes: string
  created_at: string
}

export const BACKGROUND_CHECK_TYPE_LABELS: Record<BackgroundCheckType, string> = {
  reference: 'Reference check',
  criminal_record: 'Criminal record check',
  qualification_verification: 'Qualification verification',
  credit_check: 'Credit check',
  other: 'Other',
}

export const BACKGROUND_CHECK_STATUS_LABELS: Record<BackgroundCheckStatus, string> = {
  not_started: 'Not started',
  requested: 'Requested',
  in_progress: 'In progress',
  cleared: 'Cleared',
  flagged: 'Flagged',
}

// --- C6: public careers portal (no auth) ----------------------------------

export interface PublicPosting {
  id: number
  title: string
  department: string
  occupational_level: string
  location: string
  description: string
  target_fill_date: string | null
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

export type TrainingStatus = 'requested' | 'planned' | 'in_progress' | 'completed' | 'cancelled'

export interface TrainingRecord {
  id: number
  employee: number
  title?: string
  provider?: string
  course?: number | null
  status?: TrainingStatus
  start_date?: string | null
  completion_date?: string | null
  hours?: string | null
  cost?: string | null
  learning_programme_category?: string
  learner_agreement_signed?: boolean
  has_evidence_file?: boolean
  evidence_download_url?: string | null
  evidence_content_type?: string
  evidence_sha256?: string
}

export const TRAINING_STATUS_LABELS: Record<TrainingStatus, string> = {
  requested: 'Requested',
  planned: 'Planned',
  in_progress: 'In progress',
  completed: 'Completed',
  cancelled: 'Cancelled',
}

// C6: mandatory-training compliance (design spec
// docs/superpowers/specs/2026-08-25-mandatory-training-compliance-design.md)
export interface Course {
  id: number
  name: string
  provider?: string
  description?: string
  hours?: string | null
  mandatory: boolean
  validity_days?: number | null
  active: boolean
}

export interface CourseRequirement {
  id: number
  course: number
  department: number | null
  occupational_level: number | null
  effective_from: string
  due_within_days: number
  active: boolean
}

export type ComplianceStatusLabel = 'compliant' | 'due' | 'overdue'

export interface TrainingComplianceBreakdownRow {
  key: string
  total_subject: number
  compliant: number
  due: number
  overdue: number
}

export interface TrainingComplianceCourseRow {
  course: number
  name: string
  total_subject: number
  compliant: number
  due: number
  overdue: number
  completion_rate_pct: number | null
  by_department: TrainingComplianceBreakdownRow[]
  by_occupational_level: TrainingComplianceBreakdownRow[]
}

export interface OverdueTrainingRow {
  employee: number
  employee_number: string
  name: string
  course: number
  course_name: string
  due_date: string
  days_overdue: number
}

export interface PayBand {
  id: number
  job_grade: number
  min_salary: string
  mid_salary: string
  max_salary: string
  valid_from: string
  valid_to: string | null
  created_by: number | null
}

export type CompCycleStatus = 'draft' | 'open' | 'closed'

export interface PerformanceContext {
  final_score: string
  period_name: string
  hr_attention: boolean
}

export interface CompCycleUtilization {
  committed_total: string
  pending_total: string
  total_used: string
  remaining: string
  over_budget: boolean
}

export interface CompCycle {
  id: number
  name: string
  period_start: string
  period_end: string
  budget_amount: string
  department: number | null
  status: CompCycleStatus
  status_display: string
  created_by: number | null
  closed_by: number | null
  closed_at: string | null
  utilization: CompCycleUtilization
  proposal_count: number
}

export const COMP_CYCLE_STATUS_LABELS: Record<CompCycleStatus, string> = {
  draft: 'Draft',
  open: 'Open',
  closed: 'Closed',
}

export interface TotalRewardsPayBandPosition {
  job_grade: number
  job_grade_code: string
  min_salary: string
  mid_salary: string
  max_salary: string
  valid_from: string
  percentile: number | null
}

export interface TotalRewardsSalary {
  fixed_remuneration: number
  variable_remuneration: number
  total_remuneration: number
  period_start: string
  period_end: string
}

export interface TotalRewardsBenefit {
  benefit_id: number
  benefit_name: string
  category: BenefitCategory
  status: BenefitsElectionStatus
  effective_date: string | null
}

export interface TotalRewardsStatement {
  employee: number
  job_grade: number | null
  job_grade_code: string | null
  salary: TotalRewardsSalary | null
  pay_band_position: TotalRewardsPayBandPosition | null
  benefits: TotalRewardsBenefit[]
  performance_context: PerformanceContext | null
}

export type BenefitCategory = 'medical' | 'retirement' | 'risk_cover' | 'other'

export interface Benefit {
  id: number
  name: string
  category: BenefitCategory
  description: string
  active: boolean
}

export const BENEFIT_CATEGORY_LABELS: Record<BenefitCategory, string> = {
  medical: 'Medical aid',
  retirement: 'Retirement fund',
  risk_cover: 'Risk cover (life/disability)',
  other: 'Other',
}

export type BenefitsElectionStatus = 'enrolled' | 'waived' | 'pending'

export interface BenefitsElection {
  id: number
  employee: number
  benefit: number
  status: BenefitsElectionStatus
  effective_date: string | null
  notes: string
}

export const BENEFITS_ELECTION_STATUS_LABELS: Record<BenefitsElectionStatus, string> = {
  enrolled: 'Enrolled',
  waived: 'Waived',
  pending: 'Pending',
}

export type AssessmentType = 'cognitive' | 'personality' | 'technical' | 'other'
export type AssessmentAssignmentStatus = 'assigned' | 'in_progress' | 'completed' | 'expired' | 'cancelled'

export interface AssessmentResult {
  raw_score: string
  summary: string
  detail: Record<string, unknown>
  received_at: string
}

export interface AssessmentAssignment {
  id: number
  employee: number | null
  applicant_id: number | null
  assessment_type: AssessmentType
  provider_key: string
  provider_reference: string
  access_url: string
  status: AssessmentAssignmentStatus
  assigned_by: number | null
  completed_at: string | null
  result: AssessmentResult | null
  created_at: string
}

export const ASSESSMENT_TYPE_LABELS: Record<AssessmentType, string> = {
  cognitive: 'Cognitive ability',
  personality: 'Personality profile',
  technical: 'Technical / skills test',
  other: 'Other',
}

export const ASSESSMENT_STATUS_LABELS: Record<AssessmentAssignmentStatus, string> = {
  assigned: 'Assigned',
  in_progress: 'In progress',
  completed: 'Completed',
  expired: 'Expired',
  cancelled: 'Cancelled',
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

export interface BiometricEnrollment {
  id: number
  employee: number
  enrolled_by: number | null
  created_at: string
  updated_at: string
}

export type LivenessOutcome = 'match' | 'no_match' | 'no_face_detected'
export type LivenessReviewStatus = 'not_required' | 'pending' | 'confirmed_match' | 'confirmed_mismatch'
export type LivenessTrigger = 'self' | 'hr_requested'

export interface LivenessCheck {
  id: number
  employee: number
  trigger: LivenessTrigger
  requested_by: number | null
  match_distance: number | null
  outcome: LivenessOutcome
  latitude: number | null
  longitude: number | null
  distance_from_office_m: number | null
  at_office: boolean | null
  review_status: LivenessReviewStatus
  reviewed_by: number | null
  reviewed_at: string | null
  review_notes: string
  created_at: string
}

export interface AttendanceSummaryRow {
  employee: number
  employee_number: string
  employee_name: string
  week_start: string
  days_in_office: number
  required_days: number
  compliant: boolean
}

export const LIVENESS_OUTCOME_LABELS: Record<LivenessOutcome, string> = {
  match: 'Matched enrolled identity',
  no_match: 'Did not match',
  no_face_detected: 'No face detected',
}

export const LIVENESS_REVIEW_STATUS_LABELS: Record<LivenessReviewStatus, string> = {
  not_required: 'Not required',
  pending: 'Pending HR review',
  confirmed_match: 'Confirmed match',
  confirmed_mismatch: 'Confirmed mismatch — escalated',
}

// ---- EE Reporting (Sprint 13-14) — EEA2/EEA4 ----

export type DemographicColumn =
  | 'african_male' | 'coloured_male' | 'indian_male' | 'white_male'
  | 'african_female' | 'coloured_female' | 'indian_female' | 'white_female'
  | 'foreign_national_male' | 'foreign_national_female'

export type WorkforceMatrix = Record<string, Partial<Record<DemographicColumn, number | string | null>>>

export interface EESector {
  id: number
  code: string
  name: string
  targets: Record<string, Record<string, number>>
  disability_target_pct: string
}

export interface EmployerConfig {
  id: number
  trade_name: string
  dti_registration_name: string
  dti_registration_number: string
  paye_sars_number: string
  uif_reference_number: string
  ee_reference_number: string
  national_or_provincial_eap: string
  industry_sector: string
  sector: number | null
  sector_detail: EESector | null
  seta_classification: string
  bargaining_council: string
  telephone_number: string
  postal_address: string
  postal_code: string
  postal_city: string
  postal_province: string
  physical_address: string
  physical_code: string
  physical_city: string
  physical_province: string
  ceo_name: string
  ceo_telephone: string
  ceo_email: string
  ee_senior_manager_name: string
  ee_senior_manager_telephone: string
  ee_senior_manager_email: string
  business_type: string
  is_organ_of_state: boolean
  employee_count_band: string
  is_group_or_holding: boolean
  group_name: string
}

export interface EEQuestionnaire {
  id: number
  report_year: number
  achieved_all_targets: boolean | null
  justifiable_reasons: Record<string, string[]>
  consultation: Record<string, boolean>
  barriers: Record<string, { barriers: boolean; aa_measures: boolean; start_date: string | null; end_date: string | null }>
  monitoring_frequency: string
  achieved_annual_objectives: boolean | null
  achieved_annual_objectives_explanation: string
  has_remuneration_policy: boolean | null
  remuneration_gap_aligned_to_policy: boolean | null
  has_measures_in_ee_plan: boolean | null
  differential_reason: string
  differential_reason_other: string
  vertical_gap_multiple: string | null
}

export interface RemunerationRecord {
  id: number
  employee: number
  employee_number: string
  period_start: string
  period_end: string
  fixed_remuneration: number
  variable_remuneration: number
  total_remuneration: number
}

export type EEFormType = 'eea2' | 'eea4'
export type EEReportStatus = 'draft' | 'pending_ee_review' | 'pending_signoff' | 'signed_off' | 'superseded'

export interface EEReport {
  id: number
  form_type: EEFormType
  report_year: number
  version: number
  period_start: string
  period_end: string
  status: EEReportStatus
  data: Record<string, unknown>
  generated_by: number | null
  generated_at: string
  ee_reviewed_by: number | null
  ee_reviewed_at: string | null
  signed_off_by: number | null
  signed_off_at: string | null
  signed_off_place: string
}

export const EE_FORM_TYPE_LABELS: Record<EEFormType, string> = { eea2: 'EEA2', eea4: 'EEA4' }

export const EE_REPORT_STATUS_LABELS: Record<EEReportStatus, string> = {
  draft: 'Draft',
  pending_ee_review: 'Pending EE manager review',
  pending_signoff: 'Pending Accounting Officer sign-off',
  signed_off: 'Signed off',
  superseded: 'Superseded',
}

export interface EquityDashboard {
  as_of: string
  small_cell_suppression_applied: boolean
  workforce_profile: WorkforceMatrix
  disability_workforce: WorkforceMatrix
  ee_plan_id: number | null
  target_vs_actual_gap_pct: WorkforceMatrix
}

export interface ManagementControlLevelRow {
  level: string
  headcount: number | string
  black: number | string
  black_pct: number | null
  eap_black_pct: number | null
  black_female: number | string
  black_female_pct: number | null
  eap_black_female_pct: number | null
  employees_with_disabilities: number | string
  disability_pct: number | null
}

export interface ManagementControlSchedule {
  as_of: string
  small_cell_suppression_applied: boolean
  ee_plan_id: number | null
  disability_target_pct: string | null
  by_level: ManagementControlLevelRow[]
}

// C6: EE plan depth + consultation forum (design spec 2026-08-26)

export interface EEPlan {
  id: number
  plan_period_start: string
  plan_period_end: string
  sector_targets: Record<string, Record<string, number>>
  numerical_goals: Record<string, Record<string, number>>
  disability_5yr_target_pct: string | null
  annual_targets: Record<string, Record<string, number>>
  annual_target_disability_value: number | null
  annual_target_disability_pct: string | null
  eap_profile: Record<string, Record<string, number>>
  created_by: number | null
}

export type EEForumRepresentation = 'union_nominated' | 'employee_nominated' | 'employer'
export type EEForumRole = 'chair' | 'secretary' | 'member'

export const EE_FORUM_REPRESENTATION_LABELS: Record<EEForumRepresentation, string> = {
  union_nominated: 'Nominated by a representative trade union',
  employee_nominated: 'Nominated by employees',
  employer: 'Employer / management representative',
}
export const EE_FORUM_ROLE_LABELS: Record<EEForumRole, string> = {
  chair: 'Chairperson', secretary: 'Secretary', member: 'Member',
}

export interface EEForumMember {
  id: number
  employee: number
  employee_number: string
  employee_name: string
  /** Absent for a reader who only reaches the roster through the member carve-out (POPIA: union affiliation). */
  representation?: EEForumRepresentation
  role: EEForumRole
  term_start: string
  term_end: string | null
  notes?: string
  is_active: boolean
}

export interface EEForumMemberSummary {
  id: number
  employee_name: string
}

export interface EEForumComposition {
  as_of: string
  active_member_count: number
  by_representation: Record<EEForumRepresentation, number>
  levels_in_workforce: string[]
  levels_uncovered: string[]
  designated_groups_represented: boolean
  non_designated_represented: boolean
  union_nominated_present: boolean
  adequate: boolean
}

export interface EEForumMeeting {
  id: number
  meeting_date: string
  title: string
  report_year: number
  agenda: string
  summary: string
  resolutions: string
  attendees: number[]
  attendee_count: number
  has_minutes: boolean
  minutes_content_type: string
  minutes_sha256: string
  minutes_download_url: string | null
  recorded_by: number | null
}

export type EEPlanMeasureStatus = 'planned' | 'in_progress' | 'completed' | 'abandoned'
export const EE_PLAN_MEASURE_STATUS_LABELS: Record<EEPlanMeasureStatus, string> = {
  planned: 'Planned', in_progress: 'In progress', completed: 'Completed', abandoned: 'Abandoned',
}

export interface EEPlanMeasure {
  id: number
  plan: number
  category: string
  category_label: string
  barrier_description: string
  measure_description: string
  owner: number
  owner_number: string
  owner_name: string
  target_start: string
  target_end: string
  status: EEPlanMeasureStatus
  progress_notes: string
  is_overdue: boolean
}

export interface EEPlanSnapshotFlag {
  row: string
  col: string
  basis: 'annual_target_shortfall' | 'over_eap' | 'disability_target_shortfall'
  gap_pct: number
}

export interface EEPlanProgressSnapshot {
  id: number
  plan: number
  as_of: string
  workforce_profile: WorkforceMatrix
  disability_workforce: WorkforceMatrix
  annual_target_gap_pct: WorkforceMatrix
  sector_target_gap_pct: Record<string, Record<string, number>>
  eap_gap_pct: WorkforceMatrix
  designated_group_pct: Record<string, { male: number; female: number; total: number }>
  disability_pct: string | null
  flags: EEPlanSnapshotFlag[]
  note: string
  taken_by: number | null
  created_at: string
  small_cell_suppression_applied: boolean
}

// Policy library (Policy section)

export type PolicyCategory =
  | 'code_of_conduct' | 'leave' | 'it_acceptable_use' | 'anti_harassment'
  | 'health_safety' | 'remote_work' | 'popia_privacy' | 'other'

export const POLICY_CATEGORY_LABELS: Record<PolicyCategory, string> = {
  code_of_conduct: 'Code of Conduct',
  leave: 'Leave Policy',
  it_acceptable_use: 'IT Acceptable Use',
  anti_harassment: 'Anti-Harassment & Anti-Discrimination',
  health_safety: 'Health & Safety',
  remote_work: 'Remote Work',
  popia_privacy: 'POPIA / Data Privacy',
  other: 'Other',
}

export type PolicyStatus = 'draft' | 'published' | 'archived'

export const POLICY_STATUS_LABELS: Record<PolicyStatus, string> = {
  draft: 'Draft',
  published: 'Published',
  archived: 'Archived',
}

export interface Policy {
  id: number
  code: string
  title: string
  category: PolicyCategory
  body: string
  has_source_file: boolean
  download_url: string | null
  chunk_count: number
  version: number
  status: PolicyStatus
  effective_date: string | null
  created_by: number | null
  published_by: number | null
  published_at: string | null
}

export interface PolicyChunk {
  id: number
  sequence: number
  text: string
}

export interface PolicyAcknowledgment {
  id: number
  employee: number
  employee_number: string
  policy: number
  policy_title: string
  policy_version: number
  acknowledged_at: string
}

export interface PolicyAcknowledgmentDashboardRow {
  policy_id: number
  title: string
  category: PolicyCategory
  version: number
  published_at: string | null
  total_employees: number
  acknowledged_count: number
  acknowledged_pct: number
}

export interface PolicyAcknowledgmentDashboard {
  as_of: string
  policies: PolicyAcknowledgmentDashboardRow[]
}

// Step-up MFA (Restricted-tier payroll data access)

export interface TOTPStatus {
  enrolled: boolean
  pending_confirmation: boolean
}

export interface TOTPEnrollResponse {
  secret: string
  provisioning_uri: string
}

export type StepUpReason =
  | 'payroll_processing' | 'employee_query' | 'compliance_reporting' | 'system_troubleshooting' | 'other'

export const STEP_UP_REASON_LABELS: Record<StepUpReason, string> = {
  payroll_processing: 'Payroll processing or audit',
  employee_query: 'Employee query or dispute resolution',
  compliance_reporting: 'Compliance or regulatory reporting',
  system_troubleshooting: 'System troubleshooting',
  other: 'Other (specify)',
}

export interface StepUpStatus {
  active: boolean
}

// --- Performance agreements / KPI contracting (PC-1, ADR-010) ---------------

export type PerformancePeriodStatus =
  | 'draft' | 'contracting' | 'active' | 'midyear' | 'final' | 'closed' | 'archived'

export type PhaseStage = 'contracting' | 'midyear' | 'final'

export const PHASE_STAGE_LABELS: Record<PhaseStage, string> = {
  contracting: 'Contracting',
  midyear: 'Mid-year review (Q2)',
  final: 'Final assessment (Q4)',
}

export interface PeriodPhase {
  id: number
  period: number
  stage: PhaseStage
  stage_display: string
  opens_on: string
  due_on: string
  reminder_offsets_days: number[]
  overdue_every_days: number
}

export interface PerformancePeriod {
  id: number
  name: string
  start_date: string
  end_date: string
  status: PerformancePeriodStatus
  status_display: string
  phases: PeriodPhase[]
  attention_threshold: string
  agreement_count: number
  created_by: number | null
}

export type AgreementStatus =
  | 'draft' | 'submitted' | 'returned' | 'approved' | 'employee_signed' | 'agreed'
  | 'midyear_open' | 'midyear_employee_signed' | 'midyear_signed'
  | 'final_open' | 'final_employee_signed' | 'final_signed' | 'archived'

export type EvidenceKind = 'file' | 'link'

export interface EvidenceItem {
  id: number
  element: number
  stage: PhaseStage
  kind: EvidenceKind
  url: string
  description: string
  uploaded_by: number | null
  uploaded_by_name: string | null
  sha256: string
  added_after_signoff: boolean
  created_at: string
  download_url: string | null
}

export interface AgreementElement {
  id: number
  agreement: number
  section_title: string
  section_order: number
  kpa_description: string
  kpi_title: string
  metric: string
  weight: string
  level_descriptors: Record<string, string>
  order: number
  locked: boolean
  q2_target_note: string
  q2_employee_comment: string
  q2_head_comment: string
  final_rating: number | null
  final_employee_comment: string
  final_head_comment: string
  score: string | null
  evidence_items: EvidenceItem[]
  has_evidence: boolean
}

export interface PDPItem {
  id: number
  agreement: number
  business_process: string
  course_or_training: string
  order: number
  training_record_id: number | null
}

export interface AgreementSignature {
  id: number
  agreement: number
  stage: PhaseStage
  revision: number
  role: 'employee' | 'head'
  role_display: string
  signer: number
  signer_name: string
  acting_for: number | null
  acting_for_name: string | null
  signed_at: string
  method: 'password_reauth' | 'totp_stepup'
  method_display: string
  document: number
  document_sha256: string
}

export interface AgreementDocument {
  id: number
  agreement: number
  stage: PhaseStage
  revision: number
  sha256: string
  generated_at: string
  download_url: string
}

export type ImprovementPlanOutcome = 'open' | 'resolved' | 'escalated' | 'cancelled'

export interface ImprovementPlan {
  id: number
  agreement: number
  owner: number
  owner_name: string
  reasons: string
  actions: string
  review_date: string
  outcome: ImprovementPlanOutcome
  outcome_display: string
  outcome_notes: string
  created_by: number | null
  created_by_name: string | null
  created_at: string
}

export interface PerformanceAgreement {
  id: number
  period: number
  period_name: string
  employee: number
  employee_name: string
  head: number | null
  head_name: string | null
  template: number
  template_version: number
  revision: number
  status: AgreementStatus
  status_display: string
  return_reason: string
  amendment_reason: string
  final_score: string | null
  hr_attention: boolean
  hr_attention_reason: string
  submitted_at: string | null
  agreed_at: string | null
  total_weight: string
  current_stage: PhaseStage
  is_editable: boolean
  elements: AgreementElement[]
  pdp_items: PDPItem[]
  improvement_plans: ImprovementPlan[]
  signatures: AgreementSignature[]
  documents: AgreementDocument[]
  calibration_adjustments: CalibrationAdjustment[]
}

export interface CanSignResponse {
  as_employee: boolean
  as_head: boolean
  employee_signed: boolean
  acting_for_head: boolean
  method: 'password_reauth' | 'totp_stepup'
  blocked_reason: string
}

export interface AgreementTemplateSummary {
  id: number
  name: string
  version: number
  status: 'draft' | 'published' | 'retired'
  status_display: string
  period: number | null
  rating_scale: Record<string, string>
  evidence_required: boolean
  signature_method: 'password_reauth' | 'totp_stepup'
  total_default_weight: string
  published_at: string | null
  sections: {
    id: number
    title: string
    order: number
    locked: boolean
    elements: {
      id: number
      kpa_description: string
      kpi_title: string
      metric: string
      default_weight: string
      level_descriptors: Record<string, string>
      order: number
      locked: boolean
    }[]
  }[]
}

export interface SigningDelegation {
  id: number
  delegator: number
  delegator_name: string
  delegate: number
  delegate_name: string
  start_date: string
  end_date: string
  reason: string
  created_by: number | null
  revoked_at: string | null
  is_active: boolean
}

export interface PeriodCompletion {
  period: string
  status: string
  total: number
  signed: number
  outstanding: number
  completion_pct: number
  by_division: { division: string; total: number; signed: number; completion_pct: number }[]
}

export interface RatingDistribution {
  period: string
  rating_unit: 'kpi_element'
  small_cell_suppression_applied: boolean
  by_division: Record<string, Record<string, number | string>>
  by_race: Record<string, Record<string, number | string>>
  by_gender: Record<string, Record<string, number | string>>
  by_disability_status: Record<string, Record<string, number | string>>
}

export interface ArchiveResult {
  archived: number
  outstanding: number
}

export type NotificationKind =
  | 'pc_reminder' | 'comp_approval' | 'review_launch' | 'policy_publish' | 'liveness_flag' | 'ee_signoff'

export interface Notification {
  id: number
  kind: NotificationKind
  kind_display: string
  title: string
  body: string
  link: string
  read_at: string | null
  created_at: string
}

export type AuditAction =
  | 'read_sensitive' | 'access_denied' | 'create' | 'update' | 'delete' | 'export' | 'login'
  | 'permission_change' | 'step_up_granted'

export type FieldTierCode = 'P' | 'I' | 'S' | 'R'

export interface AuditLogEntry {
  id: number
  timestamp: string
  actor: number | null
  actor_name: string
  actor_employee_number: string | null
  action: AuditAction
  action_display: string
  entity_type: string
  entity_id: string
  field_tier: FieldTierCode
  field_tier_display: string
  fields_touched: string
  request_id: string
  ip_address: string | null
}

// C2 — employee documents & POPIA rights
// (docs/superpowers/specs/2026-08-25-employee-documents-popia-design.md)

export type EmployeeDocumentType =
  | 'id_copy' | 'qualification' | 'employment_contract' | 'disability_verification' | 'other'

export const EMPLOYEE_DOCUMENT_TYPE_LABELS: Record<EmployeeDocumentType, string> = {
  id_copy: 'ID copy',
  qualification: 'Qualification / certificate',
  employment_contract: 'Employment contract',
  disability_verification: 'Disability verification',
  other: 'Other',
}

// documents/models.py::EmployeeDocument.CONSENT_REQUIRED_TYPES — mirrored
// here so the upload form can prompt for consent before submitting rather
// than only finding out from a 400.
export const EMPLOYEE_DOCUMENT_CONSENT_REQUIRED_TYPES: EmployeeDocumentType[] = ['id_copy', 'disability_verification']

export interface EmployeeDocument {
  id: number
  employee: number
  employee_number: string
  document_type: EmployeeDocumentType
  title: string
  description: string
  download_url: string
  content_type: string
  size_bytes: number
  tier: FieldTierCode
  uploaded_by: number | null
  uploaded_by_number: string | null
  created_at: string
}

export type DependantRelationship = 'spouse' | 'child' | 'parent' | 'other'

export const DEPENDANT_RELATIONSHIP_LABELS: Record<DependantRelationship, string> = {
  spouse: 'Spouse', child: 'Child', parent: 'Parent', other: 'Other',
}

export interface Dependant {
  id: number
  employee: number
  first_name: string
  last_name: string
  relationship: DependantRelationship
  date_of_birth: string | null
  id_number: string
  notes: string
}

export interface EmergencyContact {
  id: number
  employee: number
  name: string
  relationship: string
  phone: string
  alternative_phone: string
  email: string
  is_primary: boolean
}

export type DataSubjectRequestType = 'export' | 'erasure'
export type DataSubjectRequestStatus = 'submitted' | 'completed' | 'declined'

export const DATA_SUBJECT_REQUEST_TYPE_LABELS: Record<DataSubjectRequestType, string> = {
  export: 'Export my data', erasure: 'Erasure request',
}

export const DATA_SUBJECT_REQUEST_STATUS_LABELS: Record<DataSubjectRequestStatus, string> = {
  submitted: 'Submitted', completed: 'Completed', declined: 'Declined',
}

export interface DataSubjectRequest {
  id: number
  employee: number
  employee_number: string
  request_type: DataSubjectRequestType
  status: DataSubjectRequestStatus
  requested_by: number | null
  requested_by_number: string | null
  requested_at: string
  request_notes: string
  reviewed_by: number | null
  reviewed_by_number: string | null
  reviewed_at: string | null
  resolution_notes: string
  download_url: string | null
}

// ---- Succession planning / talent pools (C6) ----
// docs/superpowers/specs/2026-08-25-succession-talent-pools-design.md

export interface CriticalPost {
  id: number
  position: number
  reason: string
  active: boolean
  flagged_by: number | null
  created_at: string
  updated_at: string
}

export type SuccessionReadiness = 'ready_now' | 'ready_1_2_years' | 'ready_3_plus_years' | 'development_needed'

export const SUCCESSION_READINESS_LABELS: Record<SuccessionReadiness, string> = {
  ready_now: 'Ready now',
  ready_1_2_years: 'Ready in 1–2 years',
  ready_3_plus_years: 'Ready in 3+ years',
  development_needed: 'Development needed',
}

/** Read-only cross-app context (spec §2.7) — informational only, never an
 * input to `readiness`, which is always the human judgement call HR
 * records directly. */
export interface SuccessionPerformanceContext {
  final_score: string
  period_name: string
  hr_attention: boolean
}

export interface SuccessionCandidate {
  id: number
  critical_post: number
  employee: number
  readiness: SuccessionReadiness
  notes: string
  nominated_by: number | null
  active: boolean
  skill_names: string[]
  latest_performance: SuccessionPerformanceContext | null
  created_at: string
  updated_at: string
}

// ---- Performance calibration/moderation + 360 feedback (C6) ----
// docs/superpowers/specs/2026-08-25-performance-calibration-360-design.md

export type CalibrationSessionStatus = 'open' | 'completed'

export interface CalibrationAdjustment {
  id: number
  session: number
  agreement: number
  agreement_employee_name: string
  previous_score: string | null
  new_score: string | null
  reason: string
  adjusted_by: number | null
  adjusted_by_name: string | null
  created_at: string
}

export interface CalibrationSession {
  id: number
  period: number
  period_name: string
  department: number | null
  department_name: string | null
  status: CalibrationSessionStatus
  status_display: string
  meeting_date: string | null
  participants_note: string
  summary: string
  convened_by: number | null
  convened_by_name: string | null
  completed_at: string | null
  created_at: string
  adjustments: CalibrationAdjustment[]
}

export interface CalibrationCandidate {
  id: number
  employee_name: string
  employee_number: string
  department_name: string | null
  final_score: string
  hr_attention: boolean
}

export type Feedback360RequestStatus = 'open' | 'closed'
export type Feedback360Relationship = 'self' | 'manager' | 'peer' | 'direct_report'
export type Feedback360RaterStatus = 'pending_approval' | 'approved' | 'declined_nomination' | 'withdrawn'

export const FEEDBACK_360_RELATIONSHIP_LABELS: Record<Feedback360Relationship, string> = {
  self: 'Self', manager: 'Manager / Head', peer: 'Peer', direct_report: 'Direct report',
}

export interface Feedback360Response {
  id: number
  rater_slot: number
  collaboration_rating: number
  communication_rating: number
  reliability_rating: number
  strengths: string
  development_areas: string
  submitted_at: string
}

export interface Feedback360Rater {
  id: number
  request: number
  rater: number
  rater_name: string
  relationship: Feedback360Relationship
  relationship_display: string
  status: Feedback360RaterStatus
  status_display: string
  nominated_by: number | null
  approved_by: number | null
  approved_at: string | null
  has_submitted: boolean
  // Masked server-side per the visibility decision (spec §2.10): null both
  // when nothing was submitted yet AND when the viewer isn't allowed to see
  // this particular row's content -- the two cases are indistinguishable on
  // purpose, so the UI must not infer "not submitted" from a null response.
  response: Feedback360Response | null
  subject_name: string
  period_name: string
  created_at: string
}

export interface Feedback360Aggregate {
  response_count: number
  collaboration_rating: number
  communication_rating: number
  reliability_rating: number
}

export interface Feedback360Request {
  id: number
  agreement: number
  status: Feedback360RequestStatus
  status_display: string
  opened_by: number | null
  opened_by_name: string | null
  due_date: string | null
  closed_at: string | null
  created_at: string
  raters: Feedback360Rater[]
  peer_aggregate: Feedback360Aggregate | null
  direct_report_aggregate: Feedback360Aggregate | null
}
