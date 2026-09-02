import { useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../../api/client'
import { useApiQuery } from '../../api/hooks'
import { EmployeeAsyncSelect } from '../../components/EmployeeAsyncSelect'
import { BARRIER_CATEGORIES } from '../../ee-reporting/constants'
import { EE_PLAN_MEASURE_STATUS_LABELS, type EEPlan, type EEPlanMeasure, type EEPlanMeasureStatus } from '../../api/types'
import { useCurrentPlan } from './useCurrentPlan'

export function PlanMeasuresSection({ canWrite }: { canWrite: boolean }) {
  const plan = useCurrentPlan()
  const planId = plan.data?.id ?? null
  const measures = useApiQuery(
    () => fetchAllPages<EEPlanMeasure>(`/ee-plan-measures/?plan=${planId}`), [planId],
    { errorMessage: 'Failed to load plan measures.', enabled: planId !== null },
  )

  if (plan.error) return <p className="form-error">{plan.error}</p>
  if (plan.data === null) return <p className="empty-state">{plan.loading ? 'Loading…' : 'No EE Plan exists yet — create one first.'}</p>

  return (
    <div>
      <p className="hint-text">
        EEA13: every barrier / affirmative-action measure on the {plan.data.plan_period_start} – {plan.data.plan_period_end} plan
        carries a responsible person and a time frame inside the plan period. Report validation cross-checks these against
        the questionnaire's Section F grid.
      </p>
      {measures.error && <p className="form-error">{measures.error}</p>}
      {measures.data === null ? (
        !measures.error && <p className="empty-state">Loading…</p>
      ) : measures.data.length === 0 ? (
        <p className="empty-state">No measures recorded on this plan yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Category</th>
                <th>Barrier</th>
                <th>Measure</th>
                <th>Responsible</th>
                <th>Time frame</th>
                <th>Status</th>
                {canWrite && <th />}
              </tr>
            </thead>
            <tbody>
              {measures.data.map((m) => (
                <tr key={m.id}>
                  <td>{m.category_label}</td>
                  <td>{m.barrier_description || '—'}</td>
                  <td>{m.measure_description}</td>
                  <td>{m.owner_name} ({m.owner_number})</td>
                  <td>{m.target_start} – {m.target_end}</td>
                  <td>
                    {EE_PLAN_MEASURE_STATUS_LABELS[m.status]}
                    {m.is_overdue && <span className="warning-badge"> Overdue</span>}
                  </td>
                  {canWrite && <td><MeasureStatusSelect measure={m} onChanged={measures.reload} /></td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {canWrite && <AddMeasureForm plan={plan.data} onSaved={measures.reload} />}
    </div>
  )
}

function MeasureStatusSelect({ measure, onChanged }: { measure: EEPlanMeasure; onChanged: () => void }) {
  const [busy, setBusy] = useState(false)
  async function change(status: EEPlanMeasureStatus) {
    setBusy(true)
    try {
      await api.patch(`/ee-plan-measures/${measure.id}/`, { status })
      onChanged()
    } finally {
      setBusy(false)
    }
  }
  return (
    <select aria-label={`Status for ${measure.category_label}`} value={measure.status} disabled={busy} onChange={(e) => change(e.target.value as EEPlanMeasureStatus)}>
      {(Object.keys(EE_PLAN_MEASURE_STATUS_LABELS) as EEPlanMeasureStatus[]).map((s) => (
        <option key={s} value={s}>{EE_PLAN_MEASURE_STATUS_LABELS[s]}</option>
      ))}
    </select>
  )
}

function AddMeasureForm({ plan, onSaved }: { plan: EEPlan; onSaved: () => void }) {
  const [category, setCategory] = useState(BARRIER_CATEGORIES[0][0])
  const [barrier, setBarrier] = useState('')
  const [measure, setMeasure] = useState('')
  const [owner, setOwner] = useState<number | null>(null)
  const [start, setStart] = useState(plan.plan_period_start)
  const [end, setEnd] = useState(plan.plan_period_end)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSaving(true)
    try {
      await api.post('/ee-plan-measures/', {
        plan: plan.id, category, barrier_description: barrier, measure_description: measure,
        owner, target_start: start, target_end: end,
      })
      setBarrier('')
      setMeasure('')
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Save failed.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit} aria-label="Add plan measure">
      <label>
        Category
        <select value={category} onChange={(e) => setCategory(e.target.value)}>
          {BARRIER_CATEGORIES.map(([key, label]) => (
            <option key={key} value={key}>{label}</option>
          ))}
        </select>
      </label>
      <label>
        Barrier
        <input value={barrier} onChange={(e) => setBarrier(e.target.value)} />
      </label>
      <label>
        Measure
        <input value={measure} onChange={(e) => setMeasure(e.target.value)} required />
      </label>
      <EmployeeAsyncSelect value={owner} onChange={setOwner} label="Responsible person" required />
      <label>
        Start
        <input type="date" value={start} onChange={(e) => setStart(e.target.value)} required />
      </label>
      <label>
        End
        <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} required />
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={saving || !measure || !owner}>
          {saving ? 'Saving…' : 'Add measure'}
        </button>
      </div>
    </form>
  )
}
