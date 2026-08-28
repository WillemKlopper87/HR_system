import { useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../api/client'
import { useAllPages, useApiQuery } from '../api/hooks'
import {
  CHECKLIST_DIRECTION_LABELS,
  CHECKLIST_OWNER_ROLE_LABELS,
  type ChecklistDirection,
  type ChecklistInstance,
  type ChecklistInstanceItem,
  type Employee,
} from '../api/types'
import { useAuth } from '../auth/useAuth'

const DIRECTIONS: ChecklistDirection[] = ['onboarding', 'offboarding']

/** Onboarding/offboarding checklists (design spec §5, §7). Visibility is
 * scoped server-side (hr_admin/auditor see everything; a line_manager sees
 * their reporting chain; anyone else sees only their own checklist) — this
 * page just renders whatever /checklist-instances/ returns. Completing a
 * task is likewise enforced server-side (owner_role + reporting chain);
 * the buttons here are hidden for combinations that would obviously 403
 * (an employee never gets a complete button on their own checklist) but
 * the backend is the real authority. */
export function ChecklistsPage() {
  const { hasRole, user } = useAuth()
  const [direction, setDirection] = useState<ChecklistDirection>('onboarding')
  const { data: instances, error, reload: load } = useApiQuery(
    () => fetchAllPages<ChecklistInstance>(`/checklist-instances/?direction=${direction}`),
    [direction],
    { errorMessage: 'Failed to load checklists.' },
  )
  const [showForm, setShowForm] = useState(false)
  const { data: employees, error: employeeError } = useAllPages<Employee>(
    showForm ? '/employees/' : null,
    [showForm],
    'Failed to load employees.',
  )

  const canManage = hasRole('hr_admin')

  return (
    <div className="page">
      <div className="page-header">
        <h1>Checklists</h1>
        {canManage && (
          <button type="button" onClick={() => setShowForm((v) => !v)}>
            {showForm ? 'Cancel' : '+ Create checklist'}
          </button>
        )}
      </div>

      <p className="hint-text">
        Onboarding checklists are created automatically when someone is hired; offboarding checklists are
        created automatically when an exit is confirmed. Manually creating one here is only for backfilling —
        e.g. a template published after the fact.
      </p>

      <div className="form-actions">
        {DIRECTIONS.map((d) => (
          <button
            key={d}
            type="button"
            className={d === direction ? 'btn-primary' : 'btn-secondary'}
            onClick={() => setDirection(d)}
          >
            {CHECKLIST_DIRECTION_LABELS[d]}
          </button>
        ))}
      </div>

      {showForm && canManage && (
        <CreateInstanceForm
          direction={direction}
          employees={employees ?? []}
          onDone={() => {
            setShowForm(false)
            load()
          }}
        />
      )}
      {showForm && employeeError && <p className="form-error">{employeeError}</p>}

      {error && <p className="form-error">{error}</p>}

      {instances === null ? (
        <p className="empty-state">Loading…</p>
      ) : instances.length === 0 ? (
        <p className="empty-state">No {CHECKLIST_DIRECTION_LABELS[direction].toLowerCase()} checklists visible to you.</p>
      ) : (
        instances.map((instance) => (
          <InstanceCard
            key={instance.id}
            instance={instance}
            employeeName={instance.employee_display}
            currentEmployeeId={user?.employee_id ?? null}
            onChanged={load}
          />
        ))
      )}
    </div>
  )
}

function CreateInstanceForm({
  direction, employees, onDone,
}: { direction: ChecklistDirection; employees: Employee[]; onDone: () => void }) {
  const [employee, setEmployee] = useState<number | ''>('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!employee) {
      setError('Choose an employee.')
      return
    }
    setSubmitting(true)
    try {
      await api.post('/checklist-instances/', { employee, direction })
      onDone()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Create failed.')
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
      {error && <p className="form-error">{error}</p>}
      <button type="submit" disabled={submitting}>
        {submitting ? 'Creating…' : 'Create'}
      </button>
    </form>
  )
}

function InstanceCard({
  instance, employeeName, currentEmployeeId, onChanged,
}: {
  instance: ChecklistInstance
  employeeName: string
  currentEmployeeId: number | null
  onChanged: () => void
}) {
  const done = instance.items.filter((i) => i.is_complete).length
  return (
    <div className="detail-card">
      <div className="page-header">
        <h3>{employeeName}</h3>
        <div>
          <span className="status-badge">{instance.status}</span>{' '}
          <span className="hint-text">
            {done}/{instance.items.length} done · template v{instance.template_version}
          </span>
        </div>
      </div>
      <table className="data-table">
        <thead>
          <tr>
            <th>Task</th>
            <th>Owner</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {instance.items.map((item) => (
            <ItemRow
              key={item.id}
              item={item}
              instanceEmployeeId={instance.employee}
              currentEmployeeId={currentEmployeeId}
              onChanged={onChanged}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ItemRow({
  item, instanceEmployeeId, currentEmployeeId, onChanged,
}: {
  item: ChecklistInstanceItem
  instanceEmployeeId: number
  currentEmployeeId: number | null
  onChanged: () => void
}) {
  const { hasRole } = useAuth()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Client-side hint only — the backend is the real authority (design spec
  // §7): hr_admin can act on anything; a line_manager only on their own
  // reporting chain's line_manager-owned tasks (which this component can't
  // verify client-side, so it's offered here and the server may still
  // 403). Nobody self-completes, so the button never renders for the
  // subject of their own checklist.
  const isSelf = currentEmployeeId !== null && instanceEmployeeId === currentEmployeeId
  const canAttempt = !isSelf && (hasRole('hr_admin') || (hasRole('line_manager') && item.owner_role === 'line_manager'))

  async function act(action: 'complete' | 'reopen') {
    setBusy(true)
    setError(null)
    try {
      await api.post(`/checklist-items/${item.id}/${action}/`, {})
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : `${action} failed.`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <tr>
      <td>
        {item.label}
        {item.description && <div className="hint-text">{item.description}</div>}
        {item.notes && <div className="hint-text">Note: {item.notes}</div>}
      </td>
      <td>{CHECKLIST_OWNER_ROLE_LABELS[item.owner_role]}</td>
      <td>
        <span className="status-badge">{item.is_complete ? 'Done' : 'Pending'}</span>
      </td>
      <td>
        {canAttempt && !item.is_complete && (
          <button type="button" onClick={() => void act('complete')} disabled={busy}>
            Complete
          </button>
        )}
        {canAttempt && item.is_complete && (
          <button type="button" onClick={() => void act('reopen')} disabled={busy}>
            Reopen
          </button>
        )}
        {error && <p className="form-error">{error}</p>}
      </td>
    </tr>
  )
}
