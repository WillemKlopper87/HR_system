import { useState } from 'react'
import { api, ApiError, fetchAllPages } from '../../api/client'
import { useApiQuery } from '../../api/hooks'
import type { EEPlanProgressSnapshot } from '../../api/types'
import { useCurrentPlan } from './useCurrentPlan'

const FLAG_LABELS: Record<EEPlanProgressSnapshot['flags'][number]['basis'], string> = {
  annual_target_shortfall: 'below annual target',
  over_eap: 'over-represented vs EAP',
  disability_target_shortfall: 'below disability target',
}

export function PlanSnapshotsSection({ canWrite }: { canWrite: boolean }) {
  const plan = useCurrentPlan()
  const planId = plan.data?.id ?? null
  const snapshots = useApiQuery(
    () => fetchAllPages<EEPlanProgressSnapshot>(`/ee-plan-snapshots/?plan=${planId}`), [planId],
    { errorMessage: 'Failed to load snapshots.', enabled: planId !== null },
  )
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [taking, setTaking] = useState(false)

  async function takeSnapshot() {
    if (planId === null) return
    setError(null)
    setTaking(true)
    try {
      await api.post('/ee-plan-snapshots/take/', { plan: planId, note })
      setNote('')
      snapshots.reload()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Snapshot failed.')
    } finally {
      setTaking(false)
    }
  }

  if (plan.error) return <p className="form-error">{plan.error}</p>
  if (plan.data === null) return <p className="empty-state">{plan.loading ? 'Loading…' : 'No EE Plan exists yet.'}</p>

  const ordered = [...(snapshots.data ?? [])].sort((a, b) => a.as_of.localeCompare(b.as_of))
  const suppressed = ordered.some((s) => s.small_cell_suppression_applied)

  return (
    <div>
      <p className="hint-text">
        Frozen actual-vs-target readings over the plan period — what the forum tabled, not a live recomputation.
        Shortfalls against the plan's annual targets and over-representation above the EAP are both flagged
        (EE Regulations 2025 reg. 9(10)–(13)). Disability target: {plan.data.disability_5yr_target_pct ?? '—'}%.
        {suppressed && ' Small cells (n < 5) are suppressed for your role.'}
      </p>
      {canWrite && (
        <div className="inline-form">
          <label>
            Note
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Q3 forum meeting" />
          </label>
          <div className="form-actions">
            <button type="button" className="btn-primary" disabled={taking} onClick={takeSnapshot}>
              {taking ? 'Taking…' : 'Take snapshot now'}
            </button>
          </div>
        </div>
      )}
      {error && <p className="form-error">{error}</p>}
      {snapshots.error && <p className="form-error">{snapshots.error}</p>}
      {snapshots.data === null ? (
        !snapshots.error && <p className="empty-state">Loading…</p>
      ) : ordered.length === 0 ? (
        <p className="empty-state">No snapshots taken yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>As of</th>
                <th>Note</th>
                <th>Disability %</th>
                <th>Designated % (Top)</th>
                <th>Designated % (Senior)</th>
                <th>Flags</th>
              </tr>
            </thead>
            <tbody>
              {ordered.map((s) => (
                <tr key={s.id}>
                  <td>{s.as_of}</td>
                  <td>{s.note || '—'}</td>
                  <td>{s.disability_pct ?? '—'}</td>
                  <td>{s.designated_group_pct.TOP?.total ?? '—'}</td>
                  <td>{s.designated_group_pct.SENIOR?.total ?? '—'}</td>
                  <td>
                    {s.flags.length === 0
                      ? 'None'
                      : `${s.flags.length}: ` + s.flags.slice(0, 4).map((f) => `${f.row}/${f.col} ${FLAG_LABELS[f.basis]} (${f.gap_pct > 0 ? '+' : ''}${f.gap_pct})`).join('; ') + (s.flags.length > 4 ? '; …' : '')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
