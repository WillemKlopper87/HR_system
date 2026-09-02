import { useState, type FormEvent } from 'react'
import { api } from '../../api/client'
import { useMutation } from '../../api/hooks'
import type { ImprovementPlan, PerformanceAgreement } from '../../api/types'

/** Corrective-action stub behind hr_attention (PC-3). The Head drives it
 * (create + update outcome); the employee it's about sees the same record
 * read-only on their own /my-performance -- deliberately no self-service
 * creation, matching the backend's `is_admin or is_head_of` gate. */
export function ImprovementPlanSection({
  agreement,
  onChanged,
  asHead,
}: {
  agreement: PerformanceAgreement
  onChanged: () => void
  asHead: boolean
}) {
  const [showForm, setShowForm] = useState(false)
  const [reasons, setReasons] = useState('')
  const [actions, setActions] = useState('')
  const [reviewDate, setReviewDate] = useState('')

  const create = useMutation(
    () =>
      api.post('/improvement-plans/', {
        agreement: agreement.id,
        owner: agreement.head,
        reasons,
        actions,
        review_date: reviewDate,
      }),
    {
      onSuccess: () => {
        setShowForm(false)
        setReasons('')
        setActions('')
        setReviewDate('')
        onChanged()
      },
      errorMessage: 'The improvement plan could not be created.',
    },
  )

  return (
    <section className="detail-card">
      <div className="page-header">
        <h2>Improvement plan</h2>
        {asHead && !showForm && (
          <button type="button" className="btn-secondary" onClick={() => setShowForm(true)}>
            + New plan
          </button>
        )}
      </div>
      {agreement.improvement_plans.length === 0 && !showForm && (
        <p className="hint-text">No improvement plan opened yet.</p>
      )}
      {agreement.improvement_plans.map((plan) => (
        <ImprovementPlanRow key={plan.id} plan={plan} asHead={asHead} onChanged={onChanged} />
      ))}
      {showForm && (
        <form
          className="inline-form"
          onSubmit={(event: FormEvent) => {
            event.preventDefault()
            void create.run()
          }}
        >
          <label>
            Reasons
            <textarea rows={2} value={reasons} onChange={(e) => setReasons(e.target.value)} required />
          </label>
          <label>
            Actions
            <textarea rows={2} value={actions} onChange={(e) => setActions(e.target.value)} required />
          </label>
          <label>
            Review date
            <input type="date" value={reviewDate} onChange={(e) => setReviewDate(e.target.value)} required />
          </label>
          {create.error && <p className="form-error">{create.error}</p>}
          <div className="form-actions">
            <button type="submit" className="btn-primary" disabled={create.busy}>
              {create.busy ? 'Saving…' : 'Open plan'}
            </button>
            <button type="button" className="btn-link" onClick={() => setShowForm(false)}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </section>
  )
}

function ImprovementPlanRow({
  plan,
  asHead,
  onChanged,
}: {
  plan: ImprovementPlan
  asHead: boolean
  onChanged: () => void
}) {
  const [outcome, setOutcome] = useState(plan.outcome)
  const [notes, setNotes] = useState(plan.outcome_notes)
  const save = useMutation(
    () => api.patch(`/improvement-plans/${plan.id}/`, { outcome, outcome_notes: notes }),
    { onSuccess: onChanged, errorMessage: 'The outcome could not be saved.' },
  )
  return (
    <div className="detail-card">
      <dl className="detail-grid">
        <div className="detail-field">
          <dt>Owner</dt>
          <dd>{plan.owner_name}</dd>
        </div>
        <div className="detail-field">
          <dt>Review date</dt>
          <dd>{plan.review_date}</dd>
        </div>
        <div className="detail-field">
          <dt>Opened</dt>
          <dd>{new Date(plan.created_at).toLocaleDateString()} by {plan.created_by_name ?? '—'}</dd>
        </div>
      </dl>
      <p>
        <strong>Reasons:</strong> {plan.reasons}
      </p>
      <p>
        <strong>Actions:</strong> {plan.actions}
      </p>
      {asHead ? (
        <div className="inline-form">
          <label>
            Outcome
            <select value={outcome} onChange={(e) => setOutcome(e.target.value as typeof outcome)}>
              <option value="open">Open</option>
              <option value="resolved">Resolved</option>
              <option value="escalated">Escalated</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </label>
          <label>
            Outcome notes
            <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>
          <button type="button" className="btn-secondary" disabled={save.busy} onClick={() => void save.run()}>
            {save.busy ? 'Saving…' : 'Save outcome'}
          </button>
          {save.error && <p className="form-error">{save.error}</p>}
        </div>
      ) : (
        <p>
          <strong>Outcome:</strong> {plan.outcome_display}
          {plan.outcome_notes && ` — ${plan.outcome_notes}`}
        </p>
      )}
    </div>
  )
}
