import { PHASE_STAGE_LABELS, type PerformanceAgreement, type PerformancePeriod } from '../../api/types'
import { CalibrationSummary } from './CalibrationSummary'
import { Feedback360Section } from './Feedback360Section'
import { ImprovementPlanSection } from './ImprovementPlanSection'
import { ReviewSection } from './ReviewSection'
import { ScorecardTable } from './ScorecardTable'
import { SignaturePanel } from './SignaturePanel'
import { WorkflowActions } from './WorkflowActions'

/** Composes one scorecard end to end, stage by stage: contracting
 * (ScorecardTable) -> mid-year/final review (ReviewSection) -> corrective
 * action if flagged (ImprovementPlanSection) -> calibration if adjusted
 * (CalibrationSummary) -> the next workflow step (WorkflowActions) ->
 * signing (SignaturePanel) -> 360 feedback (Feedback360Section). Shared
 * between MyPerformancePage (the employee's own view) and
 * TeamPerformancePage (`asHead`, a manager reviewing a report's). */
export function AgreementCard({
  agreement,
  period,
  onChanged,
  asHead = false,
}: {
  agreement: PerformanceAgreement
  period: PerformancePeriod | null
  onChanged: () => void
  asHead?: boolean
}) {
  const phase = period?.phases.find((p) => p.stage === agreement.current_stage) ?? null
  const totalWeight = Number(agreement.total_weight)
  const weightOk = Math.abs(totalWeight - 1) < 0.0005

  return (
    <>
      <section className="detail-card">
        <div className="page-header">
          <h2>
            {agreement.period_name} scorecard{agreement.revision > 1 ? ` — revision ${agreement.revision}` : ''}
          </h2>
          <span className="status-badge">{agreement.status_display}</span>
        </div>
        <dl className="detail-grid">
          <div className="detail-field">
            <dt>Employee</dt>
            <dd>{agreement.employee_name}</dd>
          </div>
          <div className="detail-field">
            <dt>Head / executive</dt>
            <dd>{agreement.head_name ?? '—'}</dd>
          </div>
          <div className="detail-field">
            <dt>Stage</dt>
            <dd>{PHASE_STAGE_LABELS[agreement.current_stage]}</dd>
          </div>
          <div className="detail-field">
            <dt>Due</dt>
            <dd>{phase ? phase.due_on : '—'}</dd>
          </div>
          <div className="detail-field">
            <dt>Total weight</dt>
            <dd className={weightOk ? undefined : 'form-error'}>
              {(totalWeight * 100).toFixed(0)}% {weightOk ? '' : '— must total 100%'}
            </dd>
          </div>
          {agreement.final_score !== null && (
            <div className="detail-field">
              <dt>Final score</dt>
              <dd>{agreement.final_score} / 5</dd>
            </div>
          )}
        </dl>
        {agreement.return_reason && (
          <p className="form-notice">Returned by your Head: {agreement.return_reason}</p>
        )}
        {agreement.amendment_reason && agreement.revision > 1 && (
          <p className="hint-text">Amendment reason: {agreement.amendment_reason}</p>
        )}
        {agreement.hr_attention && (
          <p className="form-notice">
            Flagged for HR attention: {agreement.hr_attention_reason || 'below the expected rating.'}
          </p>
        )}
      </section>

      <ScorecardTable agreement={agreement} onChanged={onChanged} />
      <ReviewSection agreement={agreement} onChanged={onChanged} />
      {(agreement.hr_attention || agreement.improvement_plans.length > 0) && (
        <ImprovementPlanSection agreement={agreement} onChanged={onChanged} asHead={asHead} />
      )}
      {agreement.calibration_adjustments.length > 0 && <CalibrationSummary agreement={agreement} />}
      <WorkflowActions agreement={agreement} onChanged={onChanged} asHead={asHead} />
      <SignaturePanel agreement={agreement} onChanged={onChanged} />
      <Feedback360Section agreement={agreement} asHead={asHead} />
    </>
  )
}
