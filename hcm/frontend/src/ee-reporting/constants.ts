import type { DemographicColumn } from '../api/types'

// Mirrors hcm/backend/ee_reporting/constants.py — kept as a small,
// deliberately duplicated source of truth on this side (not fetched from
// the API) since these are static form categories, not data. If the
// backend list ever changes, this file needs a matching edit — same
// "form layouts are versioned configuration" principle, just manual
// rather than auto-synced given the frontend has no code-gen step here.

export const OCCUPATIONAL_LEVEL_CODES = ['TOP', 'SENIOR', 'PQ', 'SKILLED', 'SEMI', 'UNSKILLED'] as const

export const OCCUPATIONAL_LEVEL_LABELS: Record<string, string> = {
  TOP: 'Top management',
  SENIOR: 'Senior management',
  PQ: 'Professionally qualified and experienced specialists and mid-management',
  SKILLED: 'Skilled technical, academically qualified and junior management',
  SEMI: 'Semi-skilled and discretionary decision making',
  UNSKILLED: 'Unskilled and defined decision making',
  total_permanent: 'Total permanent',
  temporary_employees: 'Temporary employees',
  grand_total: 'Grand total',
}

export const AGGREGATE_ROW_KEYS = ['total_permanent', 'temporary_employees', 'grand_total']

export const DEMOGRAPHIC_COLUMNS: DemographicColumn[] = [
  'african_male', 'coloured_male', 'indian_male', 'white_male',
  'african_female', 'coloured_female', 'indian_female', 'white_female',
  'foreign_national_male', 'foreign_national_female',
]

export const SKILLS_DEMOGRAPHIC_COLUMNS: DemographicColumn[] = DEMOGRAPHIC_COLUMNS.slice(0, 8)

export const DEMOGRAPHIC_COLUMN_LABELS: Record<string, string> = {
  african_male: 'African M', coloured_male: 'Coloured M', indian_male: 'Indian M', white_male: 'White M',
  african_female: 'African F', coloured_female: 'Coloured F', indian_female: 'Indian F', white_female: 'White F',
  foreign_national_male: 'Foreign National M', foreign_national_female: 'Foreign National F',
}

export const JUSTIFIABLE_REASONS: [string, string][] = [
  ['insufficient_recruitment_opportunities', 'Insufficient recruitment opportunities'],
  ['insufficient_promotion_opportunities', 'Insufficient promotion opportunities'],
  [
    'insufficient_target_individuals',
    'Insufficient target individuals with relevant qualification, prior learning, experience or capacity to acquire ability to do job',
  ],
  ['ccma_award_court_order', 'CCMA Award/Court Order'],
  ['transfer_of_business', 'Transfer of business'],
  ['mergers_acquisitions', 'Mergers/Acquisitions'],
  ['economic_conditions', 'Impact of Economic Conditions on Business'],
]

export const JUSTIFIABLE_REASON_ROW_KEYS = [...OCCUPATIONAL_LEVEL_CODES, 'disability']

export const CONSULTATION_STAKEHOLDERS: [string, string][] = [
  ['consultative_body_or_ee_forum', 'Consultative body or employment equity forum'],
  ['representative_trade_unions', 'Representative trade union(s)'],
  ['employees', 'Employees'],
]

export const BARRIER_CATEGORIES: [string, string][] = [
  ['recruitment', 'Recruitment'],
  ['advertisement_of_positions', 'Advertisement of positions'],
  ['selection_criteria', 'Selection criteria'],
  ['appointments', 'Appointments'],
  ['job_classification_and_grading', 'Job classification and grading'],
  ['remuneration_and_benefits', 'Remuneration and benefits'],
  ['terms_and_conditions_of_employment', 'Terms & conditions of employment'],
  ['job_assignments', 'Job assignments'],
  ['work_environment_and_facilities', 'Work environment and facilities'],
  ['training_and_development', 'Training and development'],
  ['performance_and_evaluation', 'Performance and evaluation'],
  ['promotions', 'Promotions'],
  ['transfers', 'Transfers'],
  ['succession_and_experience_planning', 'Succession & experience planning'],
  ['disciplinary_measures', 'Disciplinary measures'],
  ['dismissals', 'Dismissals'],
  ['retention_of_designated_groups', 'Retention of designated groups'],
  ['corporate_culture', 'Corporate culture'],
  ['reasonable_accommodation', 'Reasonable accommodation'],
  ['harassment', 'Harassment'],
  ['hiv_aids_prevention_and_wellness', 'HIV&AIDS prevention and wellness programmes'],
  ['assigned_senior_managers', 'Assigned senior manager(s) to manage EE implementation'],
  ['budget_allocation', 'Budget allocation in support of employment equity goals'],
  ['time_off_for_ee_committee', 'Time off for employment equity consultative committee to meet'],
]

export const DIFFERENTIAL_REASONS: [string, string][] = [
  ['seniority_length_of_service', 'Seniority/length of service'],
  ['qualifications', 'Qualifications'],
  ['performance', 'Performance'],
  ['demotion', 'Demotion'],
  ['experiential_training', 'Experiential training'],
  ['shortage_of_skill', 'Shortage of skill'],
  ['transfer_of_business', 'Transfer of business'],
  ['other', 'Other'],
]

export const BUSINESS_TYPES: [string, string][] = [
  ['private_sector', 'Private Sector'],
  ['national_government', 'National Government'],
  ['local_government', 'Local Government'],
  ['non_profit_organisation', 'Non-profit Organisation'],
  ['state_owned_enterprise', 'State Owned Enterprise'],
  ['provincial_government_educational_institution', 'Provincial Government Educational Institution'],
]

export const EMPLOYEE_COUNT_BANDS: [string, string][] = [
  ['1_to_49', '1 to 49'],
  ['50_to_149', '50 to 149'],
  ['150_or_more', '150 or more'],
]

export const MONITORING_FREQUENCIES: [string, string][] = [
  ['monthly', 'Monthly'],
  ['quarterly', 'Quarterly'],
  ['biannually', 'Bi-annually'],
  ['annually', 'Annually'],
]
