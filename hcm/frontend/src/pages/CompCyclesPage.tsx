import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { formatZAR } from '../lib/format'
import { api, ApiError } from '../api/client'
import { useAllPages } from '../api/hooks'
import { useReferenceData } from '../api/ReferenceDataContext'
import type { CompCycle } from '../api/types'

export function CompCyclesPage() {
  const { data: cycles, error: loadError, reload: load } = useAllPages<CompCycle>(
    '/comp-cycles/', [], 'Failed to load compensation cycles.',
  )
  const [showForm, setShowForm] = useState(false)
  const ref = useReferenceData()

  return (
    <div className="page">
      <div className="page-header">
        <h1>Compensation Cycles</h1>
        <button type="button" className="btn-primary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : '+ New cycle'}
        </button>
      </div>
      <p className="hint-text">
        Batch salary-increase and bonus proposals against a budget for one review round. A proposal reserves its
        share of the budget the moment it's raised — an "over budget" flag on a proposal doesn't block it, but
        approving it needs a stated reason, the same as an out-of-band pay-band proposal.
      </p>

      {loadError && <p className="form-error">{loadError}</p>}

      {showForm && (
        <NewCycleForm
          onCreated={() => {
            setShowForm(false)
            load()
          }}
        />
      )}

      {cycles === null ? (
        <p className="empty-state">Loading…</p>
      ) : cycles.length === 0 ? (
        <p className="empty-state">No compensation cycles yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Period</th>
                <th>Scope</th>
                <th>Budget</th>
                <th>Utilization</th>
                <th>Proposals</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {cycles.map((cycle) => (
                <CycleRow
                  key={cycle.id}
                  cycle={cycle}
                  departmentName={cycle.department ? ref.departments.get(cycle.department)?.name ?? `#${cycle.department}` : 'Org-wide'}
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

function CycleRow({
  cycle, departmentName, onChanged,
}: { cycle: CompCycle; departmentName: string; onChanged: () => void }) {
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleOpen() {
    setError(null)
    setBusy(true)
    try {
      await api.post(`/comp-cycles/${cycle.id}/open/`)
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not open the cycle.')
    } finally {
      setBusy(false)
    }
  }

  async function handleClose() {
    if (!window.confirm('Close this cycle? Any proposal still awaiting a decision will be automatically rejected.')) return
    setError(null)
    setBusy(true)
    try {
      await api.post(`/comp-cycles/${cycle.id}/close/`)
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not close the cycle.')
    } finally {
      setBusy(false)
    }
  }

  const used = Number(cycle.utilization.total_used)
  const budget = Number(cycle.budget_amount)
  const pct = budget > 0 ? Math.min(100, (used / budget) * 100) : 0

  return (
    <tr>
      <td>{cycle.name}</td>
      <td>{cycle.period_start} – {cycle.period_end}</td>
      <td>{departmentName}</td>
      <td>{formatZAR(cycle.budget_amount)}</td>
      <td>
        <div style={{ minWidth: 160 }}>
          <div style={{ background: 'var(--border, #ddd)', borderRadius: 4, height: 8, overflow: 'hidden' }}>
            <div
              style={{
                width: `${pct}%`, height: '100%',
                background: cycle.utilization.over_budget ? 'var(--danger, #c0392b)' : 'var(--accent, #2e7d32)',
              }}
            />
          </div>
          <div className="hint-text" style={{ marginTop: 2 }}>
            {formatZAR(cycle.utilization.total_used)} of {formatZAR(cycle.budget_amount)}
            {cycle.utilization.over_budget && ' — over budget'}
          </div>
        </div>
      </td>
      <td>
        <Link to={`/comp-proposals?cycle=${cycle.id}`}>{cycle.proposal_count}</Link>
      </td>
      <td>
        <span className="status-badge">{cycle.status_display}</span>
      </td>
      <td>
        {error && <p className="form-error">{error}</p>}
        <div className="form-actions">
          {cycle.status === 'draft' && (
            <button type="button" className="btn-secondary" disabled={busy} onClick={() => void handleOpen()}>
              Open
            </button>
          )}
          {cycle.status !== 'closed' && (
            <button type="button" className="btn-secondary btn-danger" disabled={busy} onClick={() => void handleClose()}>
              Close
            </button>
          )}
          {cycle.status === 'closed' && '—'}
        </div>
      </td>
    </tr>
  )
}

function NewCycleForm({ onCreated }: { onCreated: () => void }) {
  const ref = useReferenceData()
  const [name, setName] = useState('')
  const [periodStart, setPeriodStart] = useState('')
  const [periodEnd, setPeriodEnd] = useState('')
  const [budget, setBudget] = useState('')
  const [department, setDepartment] = useState<number | ''>('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await api.post('/comp-cycles/', {
        name, period_start: periodStart, period_end: periodEnd, budget_amount: budget,
        department: department || null,
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
        Name
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. FY2026 Annual Review" required />
      </label>
      <label>
        Period start
        <input type="date" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} required />
      </label>
      <label>
        Period end
        <input type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} required />
      </label>
      <label>
        Budget (ZAR)
        <input type="number" min={0} step="0.01" value={budget} onChange={(e) => setBudget(e.target.value)} required />
      </label>
      <label>
        Department scope
        <select value={department} onChange={(e) => setDepartment(e.target.value ? Number(e.target.value) : '')}>
          <option value="">— Org-wide —</option>
          {ref.departmentList.map((d) => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </select>
      </label>

      {error && <p className="form-error">{error}</p>}

      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Creating…' : 'Create cycle'}
        </button>
      </div>
    </form>
  )
}
