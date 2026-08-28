import { useMemo, useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../api/client'
import { useApiQuery } from '../api/hooks'
import {
  EMPLOYMENT_CHANGE_TYPE_LABELS,
  PROPOSABLE_CHANGE_TYPES,
  TIERED_CHANGE_TYPES,
  type Employee,
  type EmploymentChange,
  type EmploymentChangeType,
} from '../api/types'
import { useAuth } from '../auth/useAuth'

const OPEN_STATES = ['proposed', 'confirmed'] as const

function isOpen(change: EmploymentChange): boolean {
  return (OPEN_STATES as readonly string[]).includes(change.state)
}

export function EmploymentChangesPage() {
  const { hasRole, user } = useAuth()
  // One fetch, matching CompProposalsPage/BenefitsPage/ContractRenewalsPage:
  // a single loading state and error surface, and the name lookup lands with
  // the changes rather than racing them on first paint.
  const { data, error: loadError, reload: load } = useApiQuery(
    () =>
      Promise.all([
        fetchAllPages<EmploymentChange>('/employment-changes/'),
        fetchAllPages<Employee>('/employees/'),
      ]).then(([changes, employees]) => ({ changes, employees })),
    [],
    { errorMessage: 'Failed to load employment changes.' },
  )
  const changes = data?.changes ?? null
  const employees = data?.employees ?? null
  const [showForm, setShowForm] = useState(false)

  const nameFor = useMemo(() => {
    const byId = new Map((employees ?? []).map((e) => [e.id, e]))
    return (id: number | null) => {
      if (id === null) return '—'
      const employee = byId.get(id)
      return employee ? `${employee.first_name} ${employee.last_name}` : `#${id}`
    }
  }, [employees])

  const canWrite = hasRole('hr_admin')

  const open = (changes ?? []).filter(isOpen)
  const awaitingConfirmation = open.filter((c) => c.state === 'proposed')
  const activeSuspensions = (changes ?? []).filter(
    (c) => c.state === 'executed' && c.change_type === 'suspension',
  )

  return (
    <div className="page">
      <div className="page-header">
        <h1>Employment Changes</h1>
        {canWrite && (
          <button type="button" onClick={() => setShowForm((v) => !v)}>
            {showForm ? 'Cancel' : '+ Propose change'}
          </button>
        )}
      </div>

      <p className="hint-text">
        Suspensions and exits are proposed, then confirmed before anything happens — so a change
        captured in error can be cancelled rather than undone. Confirming executes it: access is
        withdrawn on the effective date, or immediately if that date has arrived.
      </p>

      {changes !== null && (
        <div className="stat-row">
          <div className="stat-tile">
            <span className="stat-value">{awaitingConfirmation.length}</span>
            <span className="stat-label">Awaiting confirmation</span>
          </div>
          <div className="stat-tile">
            <span className="stat-value">{open.length}</span>
            <span className="stat-label">Open (not yet executed)</span>
          </div>
          <div className="stat-tile">
            <span className="stat-value">{activeSuspensions.length}</span>
            <span className="stat-label">Currently suspended</span>
          </div>
        </div>
      )}

      {showForm && canWrite && (
        <ProposeChangeForm
          employees={employees ?? []}
          onDone={() => {
            setShowForm(false)
            load()
          }}
        />
      )}

      {loadError && <p className="form-error">{loadError}</p>}

      {changes === null ? (
        <p className="empty-state">Loading…</p>
      ) : changes.length === 0 ? (
        <p className="empty-state">No employment changes recorded.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Employee</th>
                <th>Change</th>
                <th>Effective</th>
                <th>State</th>
                <th>Proposed by</th>
                <th>Confirmed by</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {changes.map((change) => (
                <ChangeRow
                  key={change.id}
                  change={change}
                  employeeName={nameFor(change.employee)}
                  proposedByName={nameFor(change.proposed_by)}
                  confirmedByName={nameFor(change.confirmed_by)}
                  currentEmployeeId={user?.employee_id ?? null}
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

function ChangeRow({
  change, employeeName, proposedByName, confirmedByName, currentEmployeeId, onChanged,
}: {
  change: EmploymentChange
  employeeName: string
  proposedByName: string
  confirmedByName: string
  currentEmployeeId: number | null
  onChanged: () => void
}) {
  const { hasRole } = useAuth()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const canWrite = hasRole('hr_admin')
  const tiered = TIERED_CHANGE_TYPES.includes(change.change_type)
  // Purely to explain the disabled button — the backend rejects a
  // same-person confirmation on a tiered type regardless of what renders.
  const wouldBeSelfConfirm =
    tiered && currentEmployeeId !== null && change.proposed_by === currentEmployeeId

  async function act(action: 'confirm' | 'cancel') {
    setBusy(true)
    setError(null)
    try {
      await api.post(`/employment-changes/${change.id}/${action}/`, {})
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : `${action} failed.`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <tr>
      <td>{employeeName}</td>
      <td>
        {EMPLOYMENT_CHANGE_TYPE_LABELS[change.change_type]}
        {tiered && <span className="hint-text"> · two-person</span>}
      </td>
      <td>{change.effective_date}</td>
      <td>
        <span className="status-badge">{change.state}</span>
      </td>
      <td>{proposedByName}</td>
      <td>{confirmedByName}</td>
      <td>
        {canWrite && change.state === 'proposed' && (
          <button
            type="button"
            onClick={() => void act('confirm')}
            disabled={busy || wouldBeSelfConfirm}
            title={
              wouldBeSelfConfirm
                ? 'This change needs a different HR administrator to confirm it.'
                : undefined
            }
          >
            Confirm
          </button>
        )}
        {canWrite && (change.state === 'proposed' || change.state === 'confirmed') && (
          <button type="button" onClick={() => void act('cancel')} disabled={busy}>
            Cancel
          </button>
        )}
        {error && <p className="form-error">{error}</p>}
      </td>
    </tr>
  )
}

function ProposeChangeForm({
  employees, onDone,
}: { employees: Employee[]; onDone: () => void }) {
  const [employee, setEmployee] = useState<number | ''>('')
  const [changeType, setChangeType] = useState<EmploymentChangeType>('suspension')
  const [effectiveDate, setEffectiveDate] = useState('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const tiered = TIERED_CHANGE_TYPES.includes(changeType)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!employee || !effectiveDate || !reason.trim()) {
      setError('Employee, effective date and reason are all required.')
      return
    }
    setSubmitting(true)
    try {
      await api.post('/employment-changes/', {
        employee, change_type: changeType, effective_date: effectiveDate, reason,
      })
      onDone()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Propose failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={(e) => void handleSubmit(e)}>
      <label>
        Employee
        <select value={employee} onChange={(e) => setEmployee(Number(e.target.value) || '')}>
          <option value="">Select…</option>
          {employees.map((e) => (
            <option key={e.id} value={e.id}>
              {e.employee_number} — {e.first_name} {e.last_name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Change
        <select
          value={changeType}
          onChange={(e) => setChangeType(e.target.value as EmploymentChangeType)}
        >
          {PROPOSABLE_CHANGE_TYPES.map((type) => (
            <option key={type} value={type}>
              {EMPLOYMENT_CHANGE_TYPE_LABELS[type]}
            </option>
          ))}
        </select>
      </label>
      <label>
        Effective date
        <input type="date" value={effectiveDate} onChange={(e) => setEffectiveDate(e.target.value)} />
      </label>
      <label>
        Reason
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={3}
          placeholder="Recorded against the change — a dismissal without a reason is not defensible."
        />
      </label>
      {tiered && (
        <p className="hint-text">
          This change needs a second HR administrator to confirm it before it takes effect.
        </p>
      )}
      {error && <p className="form-error">{error}</p>}
      <button type="submit" disabled={submitting}>
        {submitting ? 'Proposing…' : 'Propose change'}
      </button>
    </form>
  )
}
