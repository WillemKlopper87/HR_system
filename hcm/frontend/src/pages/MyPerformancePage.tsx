import { useState, type FormEvent } from 'react'
import { api } from '../api/client'
import { useApiQuery, useMutation } from '../api/hooks'
import { groupBySection } from '../lib/performance'
import {
  PHASE_STAGE_LABELS,
  type AgreementElement,
  type CanSignResponse,
  type PerformanceAgreement,
  type PerformancePeriod,
} from '../api/types'

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

  const current = agreements?.[0] ?? null
  const period = periods?.results.find((p) => p.id === current?.period) ?? null

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
      {agreements !== null && agreements.length === 0 && (
        <p className="empty-state">
          You don't have a performance agreement yet — HR creates them when contracting opens for the year.
        </p>
      )}

      {current && <AgreementCard agreement={current} period={period} onChanged={reload} />}

      {agreements && agreements.length > 1 && (
        <section className="detail-card">
          <h2>Previous years</h2>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Period</th>
                  <th>Status</th>
                  <th>Final score</th>
                  <th>Document</th>
                </tr>
              </thead>
              <tbody>
                {agreements.slice(1).map((a) => (
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
        </dl>
        {agreement.return_reason && (
          <p className="form-notice">Returned by your Head: {agreement.return_reason}</p>
        )}
        {agreement.amendment_reason && agreement.revision > 1 && (
          <p className="hint-text">Amendment reason: {agreement.amendment_reason}</p>
        )}
      </section>

      <ScorecardTable agreement={agreement} onChanged={onChanged} />
      <WorkflowActions agreement={agreement} onChanged={onChanged} asHead={asHead} />
      <SignaturePanel agreement={agreement} onChanged={onChanged} />
    </>
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
