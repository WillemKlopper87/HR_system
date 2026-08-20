import { useMemo, useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../api/client'
import { useApiQuery } from '../api/hooks'
import {
  CONTRACT_ACTION_LABELS,
  type ContractAction,
  type Employee,
  type EmployeeVersion,
} from '../api/types'
import { useAuth } from '../auth/AuthContext'

// Mirrors config/settings.py's defaults — there is no API surface for
// reading these settings client-side, and the design spec (§9) says to
// mirror the backend defaults rather than build one just for this.
const REMINDER_THRESHOLD_DAYS = 60 // CONTRACT_REMINDER_OFFSETS_DAYS[0]
const ESCALATION_THRESHOLD_DAYS = 14 // CONTRACT_ESCALATION_DAYS

function daysUntil(dateStr: string): number {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const target = new Date(dateStr)
  target.setHours(0, 0, 0, 0)
  return Math.round((target.getTime() - today.getTime()) / 86_400_000)
}

export function ContractRenewalsPage() {
  // Combined into one fetch (matching CompProposalsPage/BenefitsPage/
  // EmployeeListPage's established pattern) rather than two independent
  // useAllPages hooks: one loading state, one error surface, and both
  // datasets land together instead of the row-name lookup racing the
  // contracts list on first paint.
  const { data, error: loadError, reload: load } = useApiQuery(
    () =>
      Promise.all([
        fetchAllPages<EmployeeVersion>('/employee-versions/?fixed_term=true&current=true'),
        fetchAllPages<Employee>('/employees/'),
      ]).then(([contracts, employees]) => ({ contracts, employees })),
    [],
    { errorMessage: 'Failed to load contracts.' },
  )
  const contracts = data?.contracts ?? null
  const employees = data?.employees ?? null

  const employeeById = useMemo(() => new Map((employees ?? []).map((e) => [e.id, e])), [employees])
  const nameFor = (id: number | null) => {
    if (id === null) return '—'
    const emp = employeeById.get(id)
    return emp ? `${emp.first_name} ${emp.last_name}` : `#${id}`
  }

  const expiringSoonCount = contracts?.filter(
    (c) => c.contract_end_date !== null && daysUntil(c.contract_end_date) <= REMINDER_THRESHOLD_DAYS,
  ).length ?? 0
  const awaitingRecommendationCount = contracts?.filter(
    (c) =>
      c.contract_renewal_decision === null &&
      c.contract_end_date !== null &&
      daysUntil(c.contract_end_date) <= ESCALATION_THRESHOLD_DAYS,
  ).length ?? 0
  // Not "decided this month": decide_contract_action always closes the
  // just-decided version as of today (core_hr/contracts.py), so it drops
  // out of this ?current=true list the instant it's decided -- a "decided"
  // count here would read 0 in practice, permanently. "Awaiting HR
  // decision" is the equivalent stat the data actually supports:
  // recommend_contract_action never calls apply_lifecycle_event, so a
  // RECOMMENDED decision does persist on a still-current version.
  const awaitingHrDecisionCount = contracts?.filter(
    (c) => c.contract_renewal_decision?.status === 'recommended',
  ).length ?? 0

  return (
    <div className="page">
      <div className="page-header">
        <h1>Contract Renewals</h1>
      </div>

      {contracts && (
        <p className="hint-text">
          {expiringSoonCount} expiring within {REMINDER_THRESHOLD_DAYS} days · {awaitingRecommendationCount} awaiting
          manager recommendation (≤{ESCALATION_THRESHOLD_DAYS} days left) · {awaitingHrDecisionCount} awaiting HR
          decision
        </p>
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
                  employeeName={nameFor(version.employee)}
                  managerName={nameFor(version.manager)}
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
