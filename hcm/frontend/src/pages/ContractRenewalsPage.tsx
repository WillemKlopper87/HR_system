import { useMemo, useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../api/client'
import { useApiQuery } from '../api/hooks'
import {
  CONTRACT_ACTION_LABELS,
  type ContractAction,
  type EmployeeVersion,
} from '../api/types'
import { useAuth } from '../auth/useAuth'

// Mirrors config/settings.py's defaults — there is no API surface for
// reading these settings client-side, and the design spec (§9) says to
// mirror the backend defaults rather than build one just for this.
const REMINDER_THRESHOLD_DAYS = 60 // CONTRACT_REMINDER_OFFSETS_DAYS[0]
const ESCALATION_THRESHOLD_DAYS = 14 // CONTRACT_ESCALATION_DAYS
// The decided-outcome summary is a stat with a few supporting lines, not
// a history view — cap it rather than growing an unbounded list.
const RECENTLY_DECIDED_LIMIT = 5

function daysUntil(dateStr: string): number {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const target = new Date(dateStr)
  target.setHours(0, 0, 0, 0)
  return Math.round((target.getTime() - today.getTime()) / 86_400_000)
}

export function ContractRenewalsPage() {
  // Combined into one fetch (matching CompProposalsPage/BenefitsPage/
  // EmployeeListPage's established pattern) rather than independent
  // useAllPages hooks: one loading state, one error surface, and every
  // dataset lands together instead of the row-name lookup racing the
  // contracts list on first paint.
  //
  // The second employee-versions call deliberately omits `current=true`.
  // Every decided outcome closes its version (decide_contract_action
  // always calls apply_lifecycle_event), so a decided row drops out of the
  // `current=true` list the instant it is decided — which left the app
  // with no read surface anywhere for a decided outcome: from the user's
  // seat, submitting a decision made it vanish. `?fixed_term=true` on its
  // own still returns those closed versions with their nested decision, so
  // restoring the outcome needs no new endpoint.
  const { data, error: loadError, reload: load } = useApiQuery(
    () =>
      Promise.all([
        fetchAllPages<EmployeeVersion>('/employee-versions/?fixed_term=true&current=true'),
        fetchAllPages<EmployeeVersion>('/employee-versions/?fixed_term=true'),
      ]).then(([contracts, allVersions]) => ({ contracts, allVersions })),
    [],
    { errorMessage: 'Failed to load contracts.' },
  )
  const contracts = data?.contracts ?? null

  const expiringSoonCount = contracts?.filter(
    (c) =>
      c.contract_end_date !== null &&
      // Lower bound matters: without it an already-EXPIRED contract
      // (negative days remaining) is counted under a label that reads
      // "expiring within 60 days".
      daysUntil(c.contract_end_date) >= 0 &&
      daysUntil(c.contract_end_date) <= REMINDER_THRESHOLD_DAYS,
  ).length ?? 0
  const awaitingRecommendationCount = contracts?.filter(
    (c) =>
      c.contract_renewal_decision === null &&
      c.contract_end_date !== null &&
      daysUntil(c.contract_end_date) <= ESCALATION_THRESHOLD_DAYS,
  ).length ?? 0
  // recommend_contract_action never calls apply_lifecycle_event, so a
  // RECOMMENDED decision persists on a still-current version — this stat
  // reads straight off the ?current=true list.
  const awaitingHrDecisionCount = contracts?.filter(
    (c) => c.contract_renewal_decision?.status === 'recommended',
  ).length ?? 0

  // Decided outcomes live on CLOSED versions, so they come from the second
  // (non-current) fetch. Newest first. `decided_at` is an ISO timestamp
  // already carrying the server's offset, so its YYYY-MM / YYYY-MM-DD
  // prefixes are the calendar values to compare and display — no re-parse
  // through Date, no UTC shift.
  const decided = useMemo(
    () =>
      (data?.allVersions ?? [])
        .filter((v) => v.contract_renewal_decision?.status === 'decided')
        .sort((a, b) =>
          (b.contract_renewal_decision?.decided_at ?? '').localeCompare(
            a.contract_renewal_decision?.decided_at ?? '',
          ),
        ),
    [data],
  )
  const now = new Date()
  const thisMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  const decidedThisMonth = decided.filter((v) =>
    (v.contract_renewal_decision?.decided_at ?? '').startsWith(thisMonth),
  )

  return (
    <div className="page">
      <div className="page-header">
        <h1>Contract Renewals</h1>
      </div>

      {contracts && (
        <p className="hint-text">
          {expiringSoonCount} expiring within {REMINDER_THRESHOLD_DAYS} days · {awaitingRecommendationCount} awaiting
          manager recommendation (≤{ESCALATION_THRESHOLD_DAYS} days left) · {awaitingHrDecisionCount} awaiting HR
          decision · {decidedThisMonth.length} decided this month
        </p>
      )}

      {decidedThisMonth.length > 0 && (
        <div className="breakdown-card">
          <h2 style={{ margin: '0 0 8px', fontSize: 14 }}>Decided this month</h2>
          {/* Deliberately a list, not a second table: this is the only
              read surface a decided outcome has anywhere in the app, kept
              compact. A full decision history is out of scope. */}
          <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
            {decidedThisMonth.slice(0, RECENTLY_DECIDED_LIMIT).map((version) => {
              const decision = version.contract_renewal_decision
              return (
                <li key={version.id} className="hint-text">
                  {(decision?.decided_at ?? '').slice(0, 10)} · {version.employee_name} ·{' '}
                  {decision?.decided_action ? CONTRACT_ACTION_LABELS[decision.decided_action] : '—'}
                  {decision?.decided_action === 'renew' && decision.decided_end_date
                    ? ` to ${decision.decided_end_date}`
                    : ''}
                </li>
              )
            })}
          </ul>
          {decidedThisMonth.length > RECENTLY_DECIDED_LIMIT && (
            <p className="hint-text" style={{ marginTop: 8 }}>
              …and {decidedThisMonth.length - RECENTLY_DECIDED_LIMIT} more.
            </p>
          )}
        </div>
      )}

      {loadError && <p className="form-error">{loadError}</p>}

      {contracts === null ? (
        <p className="empty-state">Loading…</p>
      ) : contracts.length === 0 ? (
        <p className="empty-state">No fixed-term contracts with an end date.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Employee</th>
                <th>Manager</th>
                <th>Contract end date</th>
                <th>Days remaining</th>
                <th>Decision status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {contracts.map((version) => (
                <ContractRow
                  key={version.id}
                  version={version}
                  employeeName={version.employee_name}
                  managerName={version.manager_name ?? '—'}
                  onChanged={load}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function ContractRow({
  version, employeeName, managerName, onChanged,
}: { version: EmployeeVersion; employeeName: string; managerName: string; onChanged: () => void }) {
  const { hasRole, user } = useAuth()
  const [mode, setMode] = useState<'none' | 'recommend' | 'decide'>('none')

  const decision = version.contract_renewal_decision
  const daysRemaining = version.contract_end_date !== null ? daysUntil(version.contract_end_date) : null

  // Deliberately stricter than the API, which since the final review
  // requires `has_role('line_manager') && is_in_reporting_chain(...)` --
  // and is_in_reporting_chain is transitive, so a skip-level manager may
  // recommend too. The UI offers the affordance only to the DIRECT
  // manager (the person who actually knows the contract), while the API
  // permits the whole chain; a skip-level manager acting is a deliberate
  // exception, not the default path, so it doesn't need a button.
  const canRecommend = hasRole('line_manager') && version.manager === (user?.employee_id ?? null) && decision === null
  const canDecide = hasRole('hr_admin') && decision?.status !== 'decided'

  function handleDone() {
    setMode('none')
    onChanged()
  }

  return (
    <tr>
      <td>{employeeName}</td>
      <td>{managerName}</td>
      <td>{version.contract_end_date ?? '—'}</td>
      <td>{daysRemaining !== null ? `${daysRemaining} days` : '—'}</td>
      <td>
        <span className="status-badge">{decision?.status ?? 'none'}</span>
      </td>
      <td>
        <div className="form-actions">
          {canRecommend && (
            <button
              type="button"
              className="btn-primary"
              onClick={() => setMode((m) => (m === 'recommend' ? 'none' : 'recommend'))}
            >
              {mode === 'recommend' ? 'Cancel' : 'Recommend'}
            </button>
          )}
          {canDecide && (
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setMode((m) => (m === 'decide' ? 'none' : 'decide'))}
            >
              {mode === 'decide' ? 'Cancel' : 'Decide'}
            </button>
          )}
        </div>

        {mode === 'recommend' && (
          <ContractActionForm
            endpoint={`/employee-versions/${version.id}/recommend_contract/`}
            submitLabel="Submit recommendation"
            initialAction={null}
            initialEndDate={null}
            onCancel={() => setMode('none')}
            onDone={handleDone}
          />
        )}
        {mode === 'decide' && (
          <ContractActionForm
            endpoint={`/employee-versions/${version.id}/decide_contract/`}
            submitLabel="Submit decision"
            initialAction={decision?.recommended_action ?? null}
            initialEndDate={decision?.recommended_end_date ?? null}
            onCancel={() => setMode('none')}
            onDone={handleDone}
          />
        )}
      </td>
    </tr>
  )
}

function ContractActionForm({
  endpoint, submitLabel, initialAction, initialEndDate, onCancel, onDone,
}: {
  endpoint: string
  submitLabel: string
  initialAction: ContractAction | null
  initialEndDate: string | null
  onCancel: () => void
  onDone: () => void
}) {
  const [action, setAction] = useState<ContractAction | ''>(initialAction ?? '')
  const [endDate, setEndDate] = useState(initialEndDate ?? '')
  const [comment, setComment] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!action) {
      setError('Choose an action.')
      return
    }
    if (action === 'renew' && !endDate) {
      setError('A new end date is required when renewing.')
      return
    }
    setSubmitting(true)
    try {
      await api.post(endpoint, {
        action,
        end_date: action === 'renew' ? endDate : null,
        comment,
      })
      onDone()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Action failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit} style={{ marginTop: 8 }}>
      <label>
        Action
        <select value={action} onChange={(e) => setAction(e.target.value as ContractAction)} required>
          <option value="">— Select —</option>
          {(Object.entries(CONTRACT_ACTION_LABELS) as [ContractAction, string][]).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      {action === 'renew' && (
        <label>
          New end date
          <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} required />
        </label>
      )}
      <label>
        Comment
        <input value={comment} onChange={(e) => setComment(e.target.value)} />
      </label>

      {error && <p className="form-error">{error}</p>}

      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Submitting…' : submitLabel}
        </button>
        <button type="button" className="btn-secondary" disabled={submitting} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}
