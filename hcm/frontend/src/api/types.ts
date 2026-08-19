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

export type TrainingStatus = 'requested' | 'planned' | 'in_progress' | 'completed' | 'cancelled'

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

export const TRAINING_STATUS_LABELS: Record<TrainingStatus, string> = {
  requested: 'Requested',
  planned: 'Planned',
  in_progress: 'In progress',
  completed: 'Completed',
  cancelled: 'Cancelled',
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

export type CompProposalStatus = 'proposed' | 'approved' | 'rejected'

export interface CompProposal {
  id: number
  employee: number
  current_job_grade: number
  proposed_annual_salary: string
  justification: string
  status: CompProposalStatus
  requires_override: boolean
  override_reason: string
  effective_date: string | null
  proposed_by: number | null
  approved_by: number | null
  approved_at: string | null
}

export const COMP_PROPOSAL_STATUS_LABELS: Record<CompProposalStatus, string> = {
  proposed: 'Proposed',
  approved: 'Approved',
  rejected: 'Rejected',
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

export type WorkforceMatrix = Record<string, Partial<Record<DemographicColumn, number>>>

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
  small_cell_suppression_applied: boolean
  by_division: Record<string, Record<string, number | string>>
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
