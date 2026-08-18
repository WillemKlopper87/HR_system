import { useMemo, useState, type FormEvent } from 'react'
import { formatZAR } from '../lib/format'
import { api, ApiError, fetchAllPages } from '../api/client'
import { useApiQuery } from '../api/hooks'
import { COMP_PROPOSAL_STATUS_LABELS, type CompProposal, type Employee } from '../api/types'

export function CompProposalsPage() {
  const [showForm, setShowForm] = useState(false)

  const { data, error: loadError, reload: load } = useApiQuery(
    () =>
      Promise.all([
        fetchAllPages<CompProposal>('/comp-proposals/'),
        fetchAllPages<Employee>('/employees/'),
      ]).then(([proposals, employees]) => ({ proposals, employees })),
    [],
    { errorMessage: 'Failed to load compensation proposals.' },
  )
  const proposals = data?.proposals ?? null
  const employees = data?.employees ?? null


  const employeeById = useMemo(() => new Map((employees ?? []).map((e) => [e.id, e])), [employees])

  return (
    <div className="page">
      <div className="page-header">
        <h1>Compensation Proposals</h1>
        <button type="button" className="btn-primary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : '+ New proposal'}
        </button>
      </div>

      {loadError && <p className="form-error">{loadError}</p>}

      {showForm && (
        <NewProposalForm
          employees={employees ?? []}
          onCreated={() => {
            setShowForm(false)
            load()
          }}
        />
      )}

      {proposals === null ? (
        <p className="empty-state">Loading…</p>
      ) : proposals.length === 0 ? (
        <p className="empty-state">No compensation proposals yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Employee</th>
                <th>Proposed salary</th>
                <th>Justification</th>
                <th>Status</th>
                <th>Pay band check</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {proposals.map((proposal) => {
                const emp = employeeById.get(proposal.employee)
                return (
                  <ProposalRow
                    key={proposal.id}
                    proposal={proposal}
                    employeeName={emp ? `${emp.first_name} ${emp.last_name}` : `#${proposal.employee}`}
                    onChanged={load}
                  />
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function ProposalRow({
  proposal, employeeName, onChanged,
}: { proposal: CompProposal; employeeName: string; onChanged: () => void }) {
  const [showOverrideInput, setShowOverrideInput] = useState(false)
  const [overrideReason, setOverrideReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleApprove() {
    if (proposal.requires_override && !showOverrideInput) {
      setShowOverrideInput(true)
      return
    }
    if (showOverrideInput && !overrideReason.trim()) {
      setError('An override reason is required to approve a proposal outside the pay band.')
      return
    }
    setError(null)
    setBusy(true)
    try {
      await api.post(`/comp-proposals/${proposal.id}/approve/`, overrideReason ? { override_reason: overrideReason } : {})
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Approval failed.')
    } finally {
      setBusy(false)
    }
  }

  async function handleReject() {
    setError(null)
    setBusy(true)
    try {
      await api.post(`/comp-proposals/${proposal.id}/reject/`)
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Rejection failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <tr>
      <td>{employeeName}</td>
      <td>{formatZAR(proposal.proposed_annual_salary)}</td>
      <td>{proposal.justification || '—'}</td>
      <td>
        <span className="status-badge">{COMP_PROPOSAL_STATUS_LABELS[proposal.status]}</span>
      </td>
      <td>
        {proposal.requires_override ? (
          <span className="warning-badge" title="Proposed salary falls outside the current pay band">
            Outside band — override required
          </span>
        ) : (
          'Within band'
        )}
        {proposal.override_reason && (
          <div className="hint-text" style={{ marginTop: 4 }}>
            Override reason: {proposal.override_reason}
          </div>
        )}
      </td>
      <td>
        {proposal.status === 'proposed' && (
          <div>
            {error && <p className="form-error">{error}</p>}
            {showOverrideInput && (
              <div className="inline-form" style={{ marginBottom: 8 }}>
                <label>
                  Override reason
                  <input value={overrideReason} onChange={(e) => setOverrideReason(e.target.value)} required />
                </label>
              </div>
            )}
            <div className="form-actions">
              <button type="button" className="btn-primary" disabled={busy} onClick={() => void handleApprove()}>
                {showOverrideInput ? 'Confirm approval' : 'Approve'}
              </button>
              <button type="button" className="btn-secondary btn-danger" disabled={busy} onClick={() => void handleReject()}>
                Reject
              </button>
            </div>
          </div>
        )}
        {proposal.status !== 'proposed' && '—'}
      </td>
    </tr>
  )
}

function NewProposalForm({ employees, onCreated }: { employees: Employee[]; onCreated: () => void }) {
  const [search, setSearch] = useState('')
  const [employee, setEmployee] = useState<number | ''>('')
  const [salary, setSalary] = useState('')
  const [justification, setJustification] = useState('')
  const [effectiveDate, setEffectiveDate] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase()
    if (!term) return employees
    return employees.filter(
      (e) =>
        e.employee_number.toLowerCase().includes(term) ||
        `${e.first_name} ${e.last_name}`.toLowerCase().includes(term),
    )
  }, [employees, search])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!employee) {
      setError('Employee is required.')
      return
    }
    setSubmitting(true)
    try {
      await api.post('/comp-proposals/', {
        employee,
        proposed_annual_salary: salary,
        justification,
        effective_date: effectiveDate || null,
      })
      onCreated()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Create failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit}>
      <label>
        Search employee
        <input placeholder="Name or employee #…" value={search} onChange={(e) => setSearch(e.target.value)} />
      </label>
      <label>
        Employee
        <select value={employee} onChange={(e) => setEmployee(e.target.value ? Number(e.target.value) : '')} required>
          <option value="">— Select —</option>
          {filtered.map((emp) => (
            <option key={emp.id} value={emp.id}>
              {emp.employee_number} — {emp.first_name} {emp.last_name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Proposed annual salary (ZAR)
        <input type="number" min={0} step="0.01" value={salary} onChange={(e) => setSalary(e.target.value)} required />
      </label>
      <label>
        Justification
        <input value={justification} onChange={(e) => setJustification(e.target.value)} />
      </label>
      <label>
        Effective date
        <input type="date" value={effectiveDate} onChange={(e) => setEffectiveDate(e.target.value)} />
      </label>

      {error && <p className="form-error">{error}</p>}

      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Creating…' : 'Propose change'}
        </button>
      </div>
    </form>
  )
}
