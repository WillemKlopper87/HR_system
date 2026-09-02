import { fetchAllPages } from '../../api/client'
import { useApiQuery } from '../../api/hooks'
import type { EEPlan } from '../../api/types'

/** The plan whose period covers today — the same selection rule the equity
 * dashboard and report validation use. Shared by PlanMeasuresSection and
 * PlanSnapshotsSection, which both key off "the current plan". */
export function useCurrentPlan() {
  return useApiQuery(async () => {
    const plans = await fetchAllPages<EEPlan>('/ee-plans/')
    const today = new Date().toISOString().slice(0, 10)
    return plans.find((p) => p.plan_period_start <= today && today <= p.plan_period_end) ?? plans[0] ?? null
  }, [], { errorMessage: 'Failed to load the EE plan.' })
}
