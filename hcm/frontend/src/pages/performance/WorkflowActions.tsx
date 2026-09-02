import { useState, type FormEvent } from 'react'
import { api } from '../../api/client'
import { useMutation } from '../../api/hooks'
import type { PerformanceAgreement } from '../../api/types'

export function WorkflowActions({
  agreement,
  onChanged,
  asHead,
}: {
  agreement: PerformanceAgreement
  onChanged: () => void
  asHead: boolean
}) {
  const [reason, setReason] = useState('')
  const act = useMutation(
    (action: string, body?: unknown) => api.post(`/performance-agreements/${agreement.id}/${action}/`, body),
    { onSuccess: onChanged, errorMessage: 'The action could not be completed.' },
  )

  const canSubmit = agreement.is_editable && !asHead
  const canReview = asHead && agreement.status === 'submitted'
  const canAmend = ['agreed', 'midyear_signed', 'final_signed'].includes(agreement.status)

  if (!canSubmit && !canReview && !canAmend) return null

  return (
    <section className="detail-card">
      <h2>Next step</h2>
      {act.error && <p className="form-error">{act.error}</p>}
      {canSubmit && (
        <div className="form-actions">
          <button type="button" className="btn-primary" disabled={act.busy} onClick={() => void act.run('submit')}>
            {act.busy ? 'Submitting…' : 'Submit to my Head'}
          </button>
          <span className="hint-text">Your Head reviews it, then you both sign — you first.</span>
        </div>
      )}
      {canReview && (
        <form
          className="inline-form"
          onSubmit={(event: FormEvent) => {
            event.preventDefault()
            void act.run('return', { reason })
          }}
        >
          <label>
            Return for changes — reason
            <input value={reason} onChange={(e) => setReason(e.target.value)} required />
          </label>
          <div className="form-actions">
            <button type="submit" className="btn-secondary" disabled={act.busy || !reason.trim()}>
              Return for changes
            </button>
            <button type="button" className="btn-primary" disabled={act.busy} onClick={() => void act.run('approve')}>
              Approve — ready for signature
            </button>
          </div>
        </form>
      )}
      {canAmend && (
        <form
          className="inline-form"
          onSubmit={(event: FormEvent) => {
            event.preventDefault()
            void act.run('amend', { reason })
          }}
        >
          <label>
            Amend this agreement — reason
            <input value={reason} onChange={(e) => setReason(e.target.value)} required />
          </label>
          <button type="submit" className="btn-secondary" disabled={act.busy || !reason.trim()}>
            {act.busy ? 'Amending…' : 'Amend (new revision, re-sign)'}
          </button>
        </form>
      )}
    </section>
  )
}
