import { useState, type FormEvent } from 'react'
import { api } from '../api/client'
import { useApiQuery, useMutation } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import type { PerformanceAgreement, PerformancePeriod, SigningDelegation } from '../api/types'
import { AgreementCard } from './MyPerformancePage'

/** Head's view (PC-1): who on my team is outstanding, review/approve/sign one
 * of them, and hand signing over before I go on leave (the user's rule:
 * "normally the person would do it before they go on leave, or a person
 * designated by the boss would then have authority"). */
export function TeamPerformancePage() {
  const { user } = useAuth()
  const [openId, setOpenId] = useState<number | null>(null)

  const { data, error, reload } = useApiQuery<{ results: PerformanceAgreement[] }>(
    () => api.get<{ results: PerformanceAgreement[] }>('/performance-agreements/?scope=team'),
    [],
    { errorMessage: 'Failed to load your team’s agreements.' },
  )
  const { data: periods } = useApiQuery<{ results: PerformancePeriod[] }>(
    () => api.get<{ results: PerformancePeriod[] }>('/performance-periods/'),
    [],
  )

  const agreements = data?.results ?? []
  const open = agreements.find((a) => a.id === openId) ?? null
  const outstanding = agreements.filter((a) => !isDone(a)).length

  return (
    <div className="page">
      <div className="page-header">
        <h1>Team Performance</h1>
      </div>
      <p className="hint-text">
        Agreements where you are the Head. Review what your team submits, approve it, then sign — the individual
        signs first, then you.
      </p>
      {error && <p className="form-error">{error}</p>}
      {data === null && <p className="empty-state">Loading…</p>}

      <section className="detail-card">
        <div className="page-header">
          <h2>My team’s scorecards</h2>
          <span className="status-badge">{outstanding} outstanding</span>
        </div>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Employee</th>
                <th>Period</th>
                <th>Status</th>
                <th>Weights</th>
                <th>Signed</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {agreements.length === 0 && (
                <tr>
                  <td colSpan={6}>Nobody reports to you for this period yet.</td>
                </tr>
              )}
              {agreements.map((a) => (
                <tr key={a.id}>
                  <td>{a.employee_name}</td>
                  <td>{a.period_name}</td>
                  <td>
                    <span className="status-badge">{a.status_display}</span>
                  </td>
                  <td>{(Number(a.total_weight) * 100).toFixed(0)}%</td>
                  <td>{a.signatures.filter((s) => s.revision === a.revision).length} of 2</td>
                  <td>
                    <button type="button" className="btn-link" onClick={() => setOpenId(openId === a.id ? null : a.id)}>
                      {openId === a.id ? 'Close' : 'Open'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {open && (
        <AgreementCard
          agreement={open}
          period={periods?.results.find((p) => p.id === open.period) ?? null}
          onChanged={reload}
          asHead
        />
      )}

      <DelegationSection selfId={user?.employee_id ?? null} />
    </div>
  )
}

function isDone(agreement: PerformanceAgreement): boolean {
  return ['agreed', 'midyear_signed', 'final_signed', 'archived'].includes(agreement.status)
}

function DelegationSection({ selfId }: { selfId: number | null }) {
  const { data, error, reload } = useApiQuery<{ results: SigningDelegation[] }>(
    () => api.get<{ results: SigningDelegation[] }>('/signing-delegations/'),
    [],
    { errorMessage: 'Failed to load signing delegations.' },
  )
  const [delegate, setDelegate] = useState('')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [reason, setReason] = useState('')

  const create = useMutation(
    () =>
      api.post('/signing-delegations/', {
        delegator: selfId,
        delegate: Number(delegate),
        start_date: start,
        end_date: end,
        reason,
      }),
    {
      onSuccess: () => {
        setDelegate('')
        setStart('')
        setEnd('')
        setReason('')
        reload()
      },
      errorMessage: 'The delegation could not be created.',
    },
  )

  const { data: employees } = useApiQuery<{ results: { id: number; first_name: string; last_name: string }[] }>(
    () => api.get<{ results: { id: number; first_name: string; last_name: string }[] }>('/employees/'),
    [],
  )

  return (
    <section className="detail-card">
      <h2>Signing delegation</h2>
      <p className="hint-text">
        Going on leave? Nominate someone to sign your team’s agreements for a set period. Their signature is recorded
        as “acting for you”, never as you.
      </p>
      {error && <p className="form-error">{error}</p>}
      {create.error && <p className="form-error">{create.error}</p>}

      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>From</th>
              <th>To</th>
              <th>Dates</th>
              <th>Reason</th>
              <th>Active</th>
            </tr>
          </thead>
          <tbody>
            {(data?.results ?? []).length === 0 && (
              <tr>
                <td colSpan={5}>No delegations.</td>
              </tr>
            )}
            {(data?.results ?? []).map((d) => (
              <tr key={d.id}>
                <td>{d.delegator_name}</td>
                <td>{d.delegate_name}</td>
                <td>
                  {d.start_date} → {d.end_date}
                </td>
                <td>{d.reason || '—'}</td>
                <td>
                  <span className="status-badge">{d.is_active ? 'Active' : 'Inactive'}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <form
        className="inline-form"
        onSubmit={(event: FormEvent) => {
          event.preventDefault()
          void create.run()
        }}
      >
        <label>
          Delegate to
          <select value={delegate} onChange={(e) => setDelegate(e.target.value)} required>
            <option value="">— Select —</option>
            {(employees?.results ?? [])
              .filter((e) => e.id !== selfId)
              .map((e) => (
                <option key={e.id} value={e.id}>
                  {e.first_name} {e.last_name}
                </option>
              ))}
          </select>
        </label>
        <label>
          From
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} required />
        </label>
        <label>
          To
          <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} required />
        </label>
        <label>
          Reason
          <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Annual leave" />
        </label>
        <button type="submit" className="btn-primary" disabled={create.busy || !delegate || !start || !end}>
          {create.busy ? 'Delegating…' : 'Delegate signing'}
        </button>
      </form>
    </section>
  )
}
