import type {
  CompProposalStatus,
  CompProposalType,
  ExitInterviewReason,
  ProbationRecommendation,
  ProbationStatus,
} from './contracts'

// Presentation-only labels for generated-contract enums (api/contracts.ts).
// Kept in their own module rather than merged into either contracts.ts
// (transport declarations only) or api/types.ts (legacy handwritten
// declarations) -- see docs/frontend/generated-api-contracts.md for the
// migration pattern this follows.
export const PROBATION_STATUS_LABELS: Record<ProbationStatus, string> = {
  in_progress: 'In progress',
  confirmed: 'Confirmed',
  extended: 'Extended',
  terminated: 'Terminated',
}

export const PROBATION_RECOMMENDATION_LABELS: Record<ProbationRecommendation, string> = {
  continue: 'Continue probation',
  extend: 'Recommend extension',
  confirm: 'Recommend confirmation',
  terminate: 'Recommend termination',
}

export const EXIT_INTERVIEW_REASON_LABELS: Record<ExitInterviewReason, string> = {
  compensation: 'Compensation',
  career_growth: 'Career growth',
  management: 'Management or relationship with manager',
  work_life_balance: 'Work-life balance',
  relocation: 'Relocation',
  health: 'Health or personal',
  role_fit: 'Role fit',
  other: 'Other',
}

export const COMP_PROPOSAL_STATUS_LABELS: Record<CompProposalStatus, string> = {
  proposed: 'Proposed',
  approved: 'Approved',
  rejected: 'Rejected',
}

export const COMP_PROPOSAL_TYPE_LABELS: Record<CompProposalType, string> = {
  increase: 'Salary increase',
  bonus: 'Bonus',
}
