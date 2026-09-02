import { useState, type FormEvent } from 'react'
import { api } from '../../api/client'
import { useApiQuery, useMutation } from '../../api/hooks'
import { EmployeeAsyncSelect } from '../../components/EmployeeAsyncSelect'
import {
  FEEDBACK_360_RELATIONSHIP_LABELS,
  type Feedback360Rater,
  type Feedback360Request,
  type PerformanceAgreement,
} from '../../api/types'

const CONTRACTED_STATUSES = new Set([
  'agreed', 'midyear_open', 'midyear_employee_signed', 'midyear_signed',
  'final_open', 'final_employee_signed', 'final_signed', 'archived',
])

/** 360° feedback (C6). Management surface only (open/nominate/approve/
 * decline/view) -- submitting a response happens on /my-feedback-requests,
 * the one place every rater (including the subject's own self-assessment
 * and the Head's own manager response, both auto-created slots) answers.
 * Visibility masking (design spec §2.10) is entirely server-side: a peer/
 * direct_report `response` reads null for the subject regardless of
 * whether it exists, so this component never has to reimplement the rule
 * — it just renders what the API gives it. */
export function Feedback360Section({ agreement, asHead }: { agreement: PerformanceAgreement; asHead: boolean }) {
  const { data, error, reload } = useApiQuery<{ results: Feedback360Request[] }>(
    () => api.get<{ results: Feedback360Request[] }>(`/feedback-360-requests/?agreement=${agreement.id}`),
    [agreement.id],
    { errorMessage: 'Failed to load 360 feedback.' },
  )
  const open = useMutation(
    () => api.post('/feedback-360-requests/', { agreement: agreement.id }),
    { onSuccess: reload, errorMessage: 'The 360 round could not be opened.' },
  )

  const eligible = CONTRACTED_STATUSES.has(agreement.status)
  const request = data?.results[0] ?? null

  if (!eligible) return null

  return (
    <section className="detail-card">
      <div className="page-header">
        <h2>360° feedback</h2>
        {!request && (
          <button type="button" className="btn-secondary" disabled={open.busy} onClick={() => void open.run()}>
            {open.busy ? 'Opening…' : 'Open a 360 round'}
          </button>
        )}
      </div>
      {error && <p className="form-error">{error}</p>}
      {open.error && <p className="form-error">{open.error}</p>}
      {!request && data !== null && (
        <p className="hint-text">
          No 360 round has been opened for this scorecard yet. Self and manager responses are automatic once
          opened; peers and direct reports can be nominated and need the Head's (or HR's) approval before they're
          invited.
        </p>
      )}
      {request && <Feedback360RequestPanel request={request} agreement={agreement} asHead={asHead} onChanged={reload} />}
    </section>
  )
}

function Feedback360RequestPanel({
  request,
  agreement,
  asHead,
  onChanged,
}: {
  request: Feedback360Request
  agreement: PerformanceAgreement
  asHead: boolean
  onChanged: () => void
}) {
  const [showNominate, setShowNominate] = useState(false)
  const close = useMutation(
    () => api.post(`/feedback-360-requests/${request.id}/close/`),
    { onSuccess: onChanged, errorMessage: 'The round could not be closed.' },
  )

  return (
    <>
      <p>
        <span className="status-badge">{request.status_display}</span>
        {request.due_date && ` — due ${request.due_date}`}
      </p>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Rater</th>
              <th>Relationship</th>
              <th>Status</th>
              <th>Submitted</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {request.raters.map((r) => (
              <RaterRow key={r.id} rater={r} asHead={asHead} onChanged={onChanged} />
            ))}
          </tbody>
        </table>
      </div>

      {(request.peer_aggregate || request.direct_report_aggregate) && (
        <div className="detail-grid">
          {request.peer_aggregate && (
            <div className="detail-field">
              <dt>Peer average ({request.peer_aggregate.response_count} responses)</dt>
              <dd>
                Collaboration {request.peer_aggregate.collaboration_rating} · Communication{' '}
                {request.peer_aggregate.communication_rating} · Reliability {request.peer_aggregate.reliability_rating}
              </dd>
            </div>
          )}
          {request.direct_report_aggregate && (
            <div className="detail-field">
              <dt>Direct-report average ({request.direct_report_aggregate.response_count} responses)</dt>
              <dd>
                Collaboration {request.direct_report_aggregate.collaboration_rating} · Communication{' '}
                {request.direct_report_aggregate.communication_rating} · Reliability{' '}
                {request.direct_report_aggregate.reliability_rating}
              </dd>
            </div>
          )}
        </div>
      )}
      {!request.peer_aggregate && (
        <p className="hint-text">
          Peer feedback isn't summarised yet — at least 3 peer responses are needed before an anonymous average is
          shown (individual peer/direct-report responses are never shown to the person they're about).
        </p>
      )}

      {request.status === 'open' && (
        <div className="form-actions">
          <button type="button" className="btn-link" onClick={() => setShowNominate((v) => !v)}>
            {showNominate ? 'Cancel' : '+ Nominate a rater'}
          </button>
          {asHead && (
            <button type="button" className="btn-secondary" disabled={close.busy} onClick={() => void close.run()}>
              {close.busy ? 'Closing…' : 'Close round'}
            </button>
          )}
        </div>
      )}
      {close.error && <p className="form-error">{close.error}</p>}
      {showNominate && (
        <NominateForm
          requestId={request.id} agreement={agreement} existingRaterIds={request.raters.map((r) => r.rater)}
          onDone={() => { setShowNominate(false); onChanged() }}
        />
      )}
    </>
  )
}

function RaterRow({
  rater,
  asHead,
  onChanged,
}: {
  rater: Feedback360Rater
  asHead: boolean
  onChanged: () => void
}) {
  const approve = useMutation(
    () => api.post(`/feedback-360-raters/${rater.id}/approve/`),
    { onSuccess: onChanged, errorMessage: 'Could not approve that nomination.' },
  )
  const decline = useMutation(
    () => api.post(`/feedback-360-raters/${rater.id}/decline/`),
    { onSuccess: onChanged, errorMessage: 'Could not decline that nomination.' },
  )
  // Masked server-side: a peer/direct-report response reads null here for
  // any viewer who isn't the Head/hr_admin/auditor or the rater themself —
  // this row just reflects whatever the API already decided to reveal.
  const showsResponse = rater.response !== null
  return (
    <tr>
      <td>{rater.rater_name}</td>
      <td>{FEEDBACK_360_RELATIONSHIP_LABELS[rater.relationship]}</td>
      <td>{rater.status_display}</td>
      <td>{rater.has_submitted ? 'Yes' : 'No'}</td>
      <td>
        {rater.status === 'pending_approval' && asHead && (
          <>
            <button type="button" className="btn-link" disabled={approve.busy} onClick={() => void approve.run()}>
              Approve
            </button>
            <button type="button" className="btn-link" disabled={decline.busy} onClick={() => void decline.run()}>
              Decline
            </button>
          </>
        )}
        {showsResponse && rater.response && (
          <details>
            <summary className="btn-link">View response</summary>
            <p>
              Collaboration {rater.response.collaboration_rating} · Communication{' '}
              {rater.response.communication_rating} · Reliability {rater.response.reliability_rating}
            </p>
            {rater.response.strengths && <p><strong>Strengths:</strong> {rater.response.strengths}</p>}
            {rater.response.development_areas && (
              <p><strong>Development areas:</strong> {rater.response.development_areas}</p>
            )}
          </details>
        )}
      </td>
      {(approve.error || decline.error) && <td className="form-error">{approve.error ?? decline.error}</td>}
    </tr>
  )
}

function NominateForm({
  requestId,
  agreement,
  existingRaterIds,
  onDone,
}: {
  requestId: number
  agreement: PerformanceAgreement
  existingRaterIds: number[]
  onDone: () => void
}) {
  const [raterId, setRaterId] = useState<number | null>(null)
  const nominate = useMutation(
    () => api.post('/feedback-360-raters/', { request: requestId, rater: raterId }),
    { onSuccess: () => { setRaterId(null); onDone() }, errorMessage: 'That nomination could not be recorded.' },
  )

  return (
    <form
      className="inline-form"
      onSubmit={(event: FormEvent) => {
        event.preventDefault()
        void nominate.run()
      }}
    >
      <EmployeeAsyncSelect
        value={raterId}
        onChange={setRaterId}
        label="Nominate"
        excludeIds={[agreement.employee, ...existingRaterIds]}
        required
      />
      <button type="submit" className="btn-secondary" disabled={nominate.busy || !raterId}>
        {nominate.busy ? 'Nominating…' : 'Nominate'}
      </button>
      {nominate.error && <p className="form-error">{nominate.error}</p>}
    </form>
  )
}
