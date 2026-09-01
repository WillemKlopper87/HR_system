import type { components } from './generated-types'

// Keep generated transport contracts behind a small stable facade. Pages and
// components should import from here rather than coupling themselves to the
// generator's nested ``components`` shape.
export type EmployeeSearchSummary = components['schemas']['EmployeeSearchSummary']
export type ProbationPeriod = components['schemas']['ProbationPeriod']
export type ProbationStatus = components['schemas']['ProbationPeriodStatusEnum']
export type ProbationRecommendation = components['schemas']['ProbationReviewRecommendationEnum']
export type ExitInterview = components['schemas']['ExitInterview']
export type ExitInterviewReason = components['schemas']['PrimaryReasonEnum']
export type CompProposal = components['schemas']['CompProposal']
export type CompProposalStatus = components['schemas']['CompProposalStatusEnum']
export type CompProposalType = components['schemas']['ProposalTypeEnum']
