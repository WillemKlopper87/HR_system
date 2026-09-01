import { useState, type FormEvent } from 'react'
import { api } from '../api/client'
import { useApiQuery, useMutation } from '../api/hooks'
import { groupBySection } from '../lib/performance'
import {
  FEEDBACK_360_RELATIONSHIP_LABELS,
  PHASE_STAGE_LABELS,
  type AgreementElement,
  type CanSignResponse,
  type Feedback360Rater,
  type Feedback360Request,
  type ImprovementPlan,
  type PerformanceAgreement,
  type PerformancePeriod,
} from '../api/types'
import { EmployeeAsyncSelect } from '../components/EmployeeAsyncSelect'

/** Employee-facing scorecard (PC-1): draft it with your Head, submit it, sign
 * it. The signature panel deliberately explains *why* a button is disabled —
 * the employee-then-Head order is the rule staff most often trip over. */
export function MyPerformancePage() {
  const { data: agreements, error, reload } = useApiQuery<PerformanceAgreement[]>(
    () => api.get<PerformanceAgreement[]>('/performance-agreements/mine/'),
    [],
    { errorMessage: 'Failed to load your performance agreements.' },
  )
  const { data: periods } = useApiQuery<{ results: PerformancePeriod[] }>(
    () => api.get<{ results: PerformancePeriod[] }>('/performance-periods/'),
    [],
    { errorMessage: 'Failed to load performance periods.' },
  )

  const [openId, setOpenId] = useState<number | null>(null)
  // Default to the most recent year (highest period.start_date, per the
  // API's own ordering), but any past year can be opened into the same
  // full card -- calibration outcomes and 360 rounds can exist on an older,
  // already-archived agreement (C6), not just the current one, so "only the
  // latest gets the full view" would silently hide them.
  const activeId = openId ?? agreements?.[0]?.id ?? null
  const active = agreements?.find((a) => a.id === activeId) ?? null
  const period = periods?.results.find((p) => p.id === active?.period) ?? null

  return (
    <div className="page">
      <div className="page-header">
        <h1>My Performance</h1>
      </div>
      <p className="hint-text">
        Your scorecard for the financial year: agree the KPIs and their weights with your Head, then sign. Weights
        must total 100% before you can submit.
      </p>

      {error && <p className="form-error">{error}</p>}
      {agreements === null && <p className="empty-state">Loading…</p>}
      {agreements !== null && agreements.length === 0 && (
        <p className="empty-state">
          You don't have a performance agreement yet — HR creates them when contracting opens for the year.
        </p>
      )}

      {active && <AgreementCard agreement={active} period={period} onChanged={reload} />}

      {agreements && agreements.length > 1 && (
        <section className="detail-card">
          <h2>All years</h2>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Period</th>
                  <th>Status</th>
                  <th>Final score</th>
                  <th>Document</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {agreements.map((a) => (
                  <tr key={a.id}>
                    <td>{a.period_name}</td>
                    <td>{a.status_display}</td>
                    <td>{a.final_score ?? '—'}</td>
                    <td>
                      {a.documents.length > 0 ? (
                        <a className="btn-link" href={a.documents[0].download_url}>
                          Download signed PDF
                        </a>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td>
                      <button type="button" className="btn-link" onClick={() => setOpenId(a.id)}>
                        {a.id === activeId ? 'Viewing' : 'Open'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  )
}

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

/** Corrective-action stub behind hr_attention (PC-3). The Head drives it
 * (create + update outcome); the employee it's about sees the same record
 * read-only on their own /my-performance -- deliberately no self-service
 * creation, matching the backend's `is_admin or is_head_of` gate. */
function ImprovementPlanSection({
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

function ScorecardTable({ agreement, onChanged }: { agreement: PerformanceAgreement; onChanged: () => void }) {
  const sections = groupBySection(agreement.elements)
  return (
    <section className="detail-card">
      <h2>Key performance indicators</h2>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Objective</th>
              <th>KPA</th>
              <th>Key performance indicator</th>
              <th>Metric</th>
              <th>Weight</th>
              <th>1</th>
              <th>2</th>
              <th>3</th>
              <th>4</th>
              <th>5</th>
            </tr>
          </thead>
          <tbody>
            {sections.map(([title, elements]) =>
              elements.map((element, index) => (
                <tr key={element.id}>
                  {index === 0 && <td rowSpan={elements.length}>{title}</td>}
                  <td>{element.kpa_description}</td>
                  <td>{element.kpi_title}</td>
                  <td>{element.metric}</td>
                  <td>
                    <WeightCell element={element} editable={agreement.is_editable} onChanged={onChanged} />
                  </td>
                  {['1', '2', '3', '4', '5'].map((level) => (
                    <td key={level} className="scorecard-target">
                      {element.level_descriptors[level] ?? '—'}
                    </td>
                  ))}
                </tr>
              )),
            )}
          </tbody>
        </table>
      </div>
      {agreement.pdp_items.length > 0 && (
        <>
          <h2>Personal development plan</h2>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Business process</th>
                  <th>Course / training / certificate</th>
                </tr>
              </thead>
              <tbody>
                {agreement.pdp_items.map((item) => (
                  <tr key={item.id}>
                    <td>{item.business_process}</td>
                    <td>{item.course_or_training}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  )
}

/** Mid-year (Q2) and final (Q4) review, PC-2. The static KPI table above
 * (ScorecardTable) never changes once contracted; this is the part that
 * changes every review cycle -- target-check notes for Q2, ratings for Q4 --
 * editable by either party (matching the "reviewed together" pattern
 * contracting already uses) only while that stage's *_open status holds;
 * AgreementElementSerializer.validate() is the real gate, this just avoids
 * offering an edit the API would refuse. */
function ReviewSection({ agreement, onChanged }: { agreement: PerformanceAgreement; onChanged: () => void }) {
  const stage = agreement.current_stage
  if (stage === 'contracting') return null
  // The employee's own fields are only editable while the stage sits at its
  // *_open status; the Head's comment stays editable one status longer --
  // through *_employee_signed -- so the Head can add it after the employee
  // signs but before the Head signs (mirrors serializers_agreements.py).
  const notYetOpenStatus = stage === 'midyear' ? 'agreed' : 'midyear_signed'
  const openStatus = stage === 'midyear' ? 'midyear_open' : 'final_open'
  const employeeSignedStatus = stage === 'midyear' ? 'midyear_employee_signed' : 'final_employee_signed'
  const editable = agreement.status === openStatus
  const headEditable = editable || agreement.status === employeeSignedStatus
  const elements = [...agreement.elements].sort(
    (a, b) => a.section_order - b.section_order || a.order - b.order,
  )

  return (
    <section className="detail-card">
      <h2>{stage === 'midyear' ? 'Mid-year review (Q2)' : 'Final assessment (Q4)'}</h2>
      {agreement.status === notYetOpenStatus && <p className="hint-text">This review hasn’t opened yet.</p>}
      {!headEditable && agreement.status !== notYetOpenStatus && (
        <p className="hint-text">This review is signed — amend the agreement (with a reason) to reopen it.</p>
      )}
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Key performance indicator</th>
              {stage === 'midyear' ? (
                <>
                  <th>Target check</th>
                  <th>Employee comment</th>
                  <th>Head comment</th>
                </>
              ) : (
                <>
                  <th>Rating</th>
                  <th>Score</th>
                  <th>Employee comment</th>
                  <th>Head comment</th>
                </>
              )}
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {elements.map((element) => (
              <tr key={element.id}>
                <td>{element.kpi_title}</td>
                {stage === 'midyear' ? (
                  <>
                    <TextCell element={element} field="q2_target_note" editable={editable} onChanged={onChanged} />
                    <TextCell
                      element={element} field="q2_employee_comment" editable={editable} onChanged={onChanged}
                    />
                    <TextCell
                      element={element} field="q2_head_comment" editable={headEditable} onChanged={onChanged}
                    />
                  </>
                ) : (
                  <>
                    <RatingCell element={element} editable={editable} onChanged={onChanged} />
                    <td>{element.score ?? '—'}</td>
                    <TextCell
                      element={element} field="final_employee_comment" editable={editable} onChanged={onChanged}
                    />
                    <TextCell
                      element={element} field="final_head_comment" editable={headEditable} onChanged={onChanged}
                    />
                  </>
                )}
                <td>
                  <EvidencePanel element={element} onChanged={onChanged} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function TextCell({
  element,
  field,
  editable,
  onChanged,
}: {
  element: AgreementElement
  field: 'q2_target_note' | 'q2_employee_comment' | 'q2_head_comment' | 'final_employee_comment' | 'final_head_comment'
  editable: boolean
  onChanged: () => void
}) {
  const [value, setValue] = useState(element[field])
  const save = useMutation(
    (next: string) => api.patch(`/agreement-elements/${element.id}/`, { [field]: next }),
    { onSuccess: onChanged, errorMessage: 'Could not save that.' },
  )
  if (!editable) return <td>{element[field] || '—'}</td>
  return (
    <td>
      <textarea
        className="review-note"
        rows={2}
        value={value}
        aria-label={field}
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => {
          if (value !== element[field]) void save.run(value)
        }}
      />
      {save.error && <p className="form-error">{save.error}</p>}
    </td>
  )
}

function RatingCell({
  element,
  editable,
  onChanged,
}: {
  element: AgreementElement
  editable: boolean
  onChanged: () => void
}) {
  const save = useMutation(
    (rating: number) => api.patch(`/agreement-elements/${element.id}/`, { final_rating: rating }),
    { onSuccess: onChanged, errorMessage: 'Could not save the rating.' },
  )
  if (!editable) {
    return <td>{element.final_rating ?? '—'}</td>
  }
  return (
    <td>
      <select
        value={element.final_rating ?? ''}
        aria-label={`Rating for ${element.kpi_title}`}
        disabled={save.busy}
        onChange={(e) => void save.run(Number(e.target.value))}
      >
        <option value="">—</option>
        {[1, 2, 3, 4, 5].map((n) => (
          <option key={n} value={n}>
            {n}
          </option>
        ))}
      </select>
      {save.error && <p className="form-error">{save.error}</p>}
    </td>
  )
}

function EvidencePanel({
  element,
  onChanged,
}: {
  element: AgreementElement
  onChanged: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [kind, setKind] = useState<'link' | 'file'>('link')
  const [url, setUrl] = useState('')
  const [description, setDescription] = useState('')
  const [file, setFile] = useState<File | null>(null)

  const upload = useMutation(
    async () => {
      const form = new FormData()
      form.append('element', String(element.id))
      form.append('kind', kind)
      if (description) form.append('description', description)
      if (kind === 'link') form.append('url', url)
      else if (file) form.append('file', file)
      return api.postForm('/agreement-evidence/', form)
    },
    {
      onSuccess: () => {
        setUrl('')
        setDescription('')
        setFile(null)
        onChanged()
      },
      errorMessage: 'Could not add that evidence.',
    },
  )
  const remove = useMutation(
    (id: number) => api.delete(`/agreement-evidence/${id}/`),
    { onSuccess: onChanged, errorMessage: 'That evidence can no longer be removed — the stage is signed off.' },
  )

  const items = element.evidence_items
  return (
    <div className="evidence-panel">
      <button type="button" className="btn-link" onClick={() => setExpanded((v) => !v)}>
        {items.length > 0 ? `Evidence (${items.length})` : 'No evidence attached'}
      </button>
      {expanded && (
        <div className="evidence-detail">
          {items.length > 0 && (
            <ul className="evidence-list">
              {items.map((item) => (
                <li key={item.id}>
                  {item.kind === 'link' ? (
                    <a href={item.url} target="_blank" rel="noreferrer">
                      {item.description || item.url}
                    </a>
                  ) : (
                    <a href={item.download_url ?? undefined}>{item.description || 'Download'}</a>
                  )}
                  {item.added_after_signoff && <span className="hint-text"> (added after sign-off)</span>}
                  <button type="button" className="btn-link" onClick={() => void remove.run(item.id)}>
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
          <form
            className="inline-form"
            onSubmit={(event: FormEvent) => {
              event.preventDefault()
              void upload.run()
            }}
          >
            <select value={kind} onChange={(e) => setKind(e.target.value as 'link' | 'file')}>
              <option value="link">Link (OneDrive / Teams / SharePoint)</option>
              <option value="file">Upload a file</option>
            </select>
            {kind === 'link' ? (
              <input
                type="url" placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} required
              />
            ) : (
              <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
            )}
            <input
              placeholder="Description (optional)" value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
            <button type="submit" className="btn-secondary" disabled={upload.busy}>
              {upload.busy ? 'Adding…' : 'Add'}
            </button>
          </form>
          {upload.error && <p className="form-error">{upload.error}</p>}
          {remove.error && <p className="form-error">{remove.error}</p>}
        </div>
      )}
    </div>
  )
}


function WeightCell({
  element,
  editable,
  onChanged,
}: {
  element: AgreementElement
  editable: boolean
  onChanged: () => void
}) {
  const [value, setValue] = useState(String(Math.round(Number(element.weight) * 100)))
  const save = useMutation(
    (pct: number) => api.patch(`/agreement-elements/${element.id}/`, { weight: (pct / 100).toFixed(4) }),
    { onSuccess: onChanged, errorMessage: 'Could not update the weight.' },
  )

  if (!editable || element.locked) {
    return <span title={element.locked ? 'Cascaded from the corporate scorecard' : undefined}>
      {(Number(element.weight) * 100).toFixed(0)}%{element.locked ? ' 🔒' : ''}
    </span>
  }
  return (
    <span className="weight-cell">
      <input
        type="number"
        min={0}
        max={100}
        value={value}
        aria-label={`Weight for ${element.kpi_title}`}
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => {
          const pct = Number(value)
          if (!Number.isNaN(pct) && pct !== Math.round(Number(element.weight) * 100)) void save.run(pct)
        }}
      />
      %{save.error && <span className="form-error">{save.error}</span>}
    </span>
  )
}

function WorkflowActions({
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

export function SignaturePanel({
  agreement,
  onChanged,
}: {
  agreement: PerformanceAgreement
  onChanged: () => void
}) {
  const [password, setPassword] = useState('')
  const { data: canSign, reload: reloadCanSign } = useApiQuery<CanSignResponse>(
    () => api.get<CanSignResponse>(`/performance-agreements/${agreement.id}/can-sign/`),
    [agreement.id, agreement.status, agreement.revision],
    { errorMessage: 'Could not check your signing status.' },
  )
  const sign = useMutation(
    (role: 'employee' | 'head') =>
      api.post(`/performance-agreements/${agreement.id}/sign/`, { role, password }),
    {
      onSuccess: () => {
        setPassword('')
        onChanged()
        reloadCanSign()
      },
      errorMessage: 'The signature was not recorded.',
    },
  )

  const signatures = agreement.signatures.filter(
    (s) => s.stage === agreement.current_stage && s.revision === agreement.revision,
  )
  const role: 'employee' | 'head' | null = canSign?.as_employee ? 'employee' : canSign?.as_head ? 'head' : null

  return (
    <section className="detail-card">
      <h2>Signatures</h2>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Signatory</th>
              <th>Name</th>
              <th>Signed</th>
              <th>Method</th>
            </tr>
          </thead>
          <tbody>
            {(['employee', 'head'] as const).map((r) => {
              const signature = signatures.find((s) => s.role === r)
              return (
                <tr key={r}>
                  <td>{r === 'employee' ? 'Individual' : 'Manager (Head / executive)'}</td>
                  <td>
                    {signature
                      ? signature.acting_for_name
                        ? `${signature.signer_name} (acting for ${signature.acting_for_name})`
                        : signature.signer_name
                      : r === 'employee'
                        ? agreement.employee_name
                        : (agreement.head_name ?? '—')}
                  </td>
                  <td>{signature ? new Date(signature.signed_at).toLocaleString() : '— not yet signed —'}</td>
                  <td>{signature ? signature.method_display : ''}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {canSign?.blocked_reason && <p className="form-notice">{canSign.blocked_reason}</p>}
      {sign.error && <p className="form-error">{sign.error}</p>}

      {role && (
        <form
          className="inline-form"
          onSubmit={(event: FormEvent) => {
            event.preventDefault()
            void sign.run(role)
          }}
        >
          <label>
            Confirm your password to sign
            <input
              type="password"
              value={password}
              autoComplete="current-password"
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          <button type="submit" className="btn-primary" disabled={sign.busy || !password}>
            {sign.busy
              ? 'Signing…'
              : role === 'employee'
                ? 'Sign as the individual'
                : canSign?.acting_for_head
                  ? 'Sign as acting Head'
                  : 'Sign as Head'}
          </button>
          <span className="hint-text">
            Your signature is bound to the PDF of this scorecard and recorded in the audit log.
          </span>
        </form>
      )}

      {agreement.documents.length > 0 && (
        <p className="hint-text">
          {agreement.documents.map((doc) => (
            <a key={doc.id} className="btn-link" href={doc.download_url}>
              Download {doc.stage} PDF (rev {doc.revision})
            </a>
          ))}
        </p>
      )}
    </section>
  )
}

/** Calibration/moderation (C6): a signed final_score that was later
 * adjusted by a departmental committee -- never a silent overwrite (design
 * spec §2.4). The original signatures/documents above are untouched; this
 * is the visible, reasoned record layered on top. */
function CalibrationSummary({ agreement }: { agreement: PerformanceAgreement }) {
  return (
    <section className="detail-card">
      <h2>Calibration</h2>
      <p className="hint-text">
        This scorecard's final score was reviewed by a departmental calibration committee. The original signatures
        above stand — this is a recorded, reasoned adjustment layered on top, not a re-opened agreement.
      </p>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Previous</th>
              <th>New</th>
              <th>Reason</th>
              <th>By</th>
              <th>When</th>
            </tr>
          </thead>
          <tbody>
            {agreement.calibration_adjustments.map((a) => (
              <tr key={a.id}>
                <td>{a.previous_score ?? '—'}</td>
                <td>{a.new_score ?? 'No change'}</td>
                <td>{a.reason}</td>
                <td>{a.adjusted_by_name ?? '—'}</td>
                <td>{new Date(a.created_at).toLocaleDateString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

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
function Feedback360Section({ agreement, asHead }: { agreement: PerformanceAgreement; asHead: boolean }) {
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
