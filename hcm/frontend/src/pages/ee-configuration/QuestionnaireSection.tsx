import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError } from '../../api/client'
import {
  BARRIER_CATEGORIES,
  CONSULTATION_STAKEHOLDERS,
  DIFFERENTIAL_REASONS,
  JUSTIFIABLE_REASON_ROW_KEYS,
  JUSTIFIABLE_REASONS,
  MONITORING_FREQUENCIES,
  OCCUPATIONAL_LEVEL_LABELS,
} from '../../ee-reporting/constants'
import type { EEQuestionnaire } from '../../api/types'

function emptyQuestionnaire(reportYear: number): Partial<EEQuestionnaire> {
  return {
    report_year: reportYear, achieved_all_targets: null, justifiable_reasons: {}, consultation: {}, barriers: {},
    monitoring_frequency: '', achieved_annual_objectives: null, achieved_annual_objectives_explanation: '',
    has_remuneration_policy: null, remuneration_gap_aligned_to_policy: null, has_measures_in_ee_plan: null,
    differential_reason: '', differential_reason_other: '', vertical_gap_multiple: '',
  }
}

export function QuestionnaireForm({
  questionnaire, reportYear, onSaved,
}: { questionnaire: EEQuestionnaire | null; reportYear: number; onSaved: () => void }) {
  const [form, setForm] = useState<Partial<EEQuestionnaire>>(questionnaire ?? emptyQuestionnaire(reportYear))
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  // Same async-prop-arrives-after-mount issue as EmployerConfigForm
  // — without this, an existing questionnaire never actually populates
  // the form, and saving would overwrite it with blank defaults.
  useEffect(() => {
    setForm(questionnaire ?? emptyQuestionnaire(reportYear))
  }, [questionnaire, reportYear])

  function toggleReason(rowKey: string, reasonKey: string) {
    setForm((prev) => {
      const current = new Set(prev.justifiable_reasons?.[rowKey] ?? [])
      if (current.has(reasonKey)) current.delete(reasonKey)
      else current.add(reasonKey)
      return { ...prev, justifiable_reasons: { ...prev.justifiable_reasons, [rowKey]: [...current] } }
    })
  }

  function setConsultation(key: string, value: boolean) {
    setForm((prev) => ({ ...prev, consultation: { ...prev.consultation, [key]: value } }))
  }

  function setBarrier(key: string, field: 'barriers' | 'aa_measures' | 'start_date' | 'end_date', value: boolean | string) {
    setForm((prev) => ({
      ...prev,
      barriers: {
        ...prev.barriers,
        [key]: { barriers: false, aa_measures: false, start_date: null, end_date: null, ...prev.barriers?.[key], [field]: value },
      },
    }))
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSaving(true)
    try {
      if (questionnaire) {
        await api.patch(`/ee-questionnaires/${questionnaire.id}/`, form)
      } else {
        await api.post('/ee-questionnaires/', form)
      }
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Save failed.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit} style={{ flexDirection: 'column', alignItems: 'stretch' }}>
      <label>
        Achieved all annual numerical targets?
        <select
          value={form.achieved_all_targets === null || form.achieved_all_targets === undefined ? '' : String(form.achieved_all_targets)}
          onChange={(e) => setForm((p) => ({ ...p, achieved_all_targets: e.target.value === '' ? null : e.target.value === 'true' }))}
        >
          <option value="">— Select —</option>
          <option value="true">Yes</option>
          <option value="false">No</option>
        </select>
      </label>

      <h3>Justifiable reasons for not meeting targets</h3>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Level</th>
              {JUSTIFIABLE_REASONS.map(([key, label]) => (
                <th key={key} title={label}>{label.slice(0, 20)}…</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {JUSTIFIABLE_REASON_ROW_KEYS.map((rowKey) => (
              <tr key={rowKey}>
                <td>{OCCUPATIONAL_LEVEL_LABELS[rowKey] ?? 'Employees with disabilities'}</td>
                {JUSTIFIABLE_REASONS.map(([reasonKey]) => (
                  <td key={reasonKey}>
                    <input
                      type="checkbox"
                      checked={(form.justifiable_reasons?.[rowKey] ?? []).includes(reasonKey)}
                      onChange={() => toggleReason(rowKey, reasonKey)}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>Consultation</h3>
      {CONSULTATION_STAKEHOLDERS.map(([key, label]) => (
        <label key={key}>
          <input type="checkbox" checked={form.consultation?.[key] ?? false} onChange={(e) => setConsultation(key, e.target.checked)} />{' '}
          {label}
        </label>
      ))}

      <h3>Barriers & affirmative action measures</h3>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Category</th>
              <th>Barriers?</th>
              <th>AA measures?</th>
              <th>Start date</th>
              <th>End date</th>
            </tr>
          </thead>
          <tbody>
            {BARRIER_CATEGORIES.map(([key, label]) => {
              const row = form.barriers?.[key]
              return (
                <tr key={key}>
                  <td>{label}</td>
                  <td>
                    <input type="checkbox" checked={row?.barriers ?? false} onChange={(e) => setBarrier(key, 'barriers', e.target.checked)} />
                  </td>
                  <td>
                    <input type="checkbox" checked={row?.aa_measures ?? false} onChange={(e) => setBarrier(key, 'aa_measures', e.target.checked)} />
                  </td>
                  <td>
                    <input type="date" value={row?.start_date ?? ''} onChange={(e) => setBarrier(key, 'start_date', e.target.value)} />
                  </td>
                  <td>
                    <input type="date" value={row?.end_date ?? ''} onChange={(e) => setBarrier(key, 'end_date', e.target.value)} />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <label>
        Monitoring frequency
        <select value={form.monitoring_frequency ?? ''} onChange={(e) => setForm((p) => ({ ...p, monitoring_frequency: e.target.value }))}>
          <option value="">— Select —</option>
          {MONITORING_FREQUENCIES.map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
      </label>
      <label>
        Achieved annual objectives?
        <select
          value={form.achieved_annual_objectives === null || form.achieved_annual_objectives === undefined ? '' : String(form.achieved_annual_objectives)}
          onChange={(e) => setForm((p) => ({ ...p, achieved_annual_objectives: e.target.value === '' ? null : e.target.value === 'true' }))}
        >
          <option value="">— Select —</option>
          <option value="true">Yes</option>
          <option value="false">No</option>
        </select>
      </label>
      <label>
        Explanation
        <input
          value={form.achieved_annual_objectives_explanation ?? ''}
          onChange={(e) => setForm((p) => ({ ...p, achieved_annual_objectives_explanation: e.target.value }))}
        />
      </label>

      <h3>EEA4 — Income differential narrative</h3>
      <label>
        Has a remuneration policy?
        <select
          value={form.has_remuneration_policy === null || form.has_remuneration_policy === undefined ? '' : String(form.has_remuneration_policy)}
          onChange={(e) => setForm((p) => ({ ...p, has_remuneration_policy: e.target.value === '' ? null : e.target.value === 'true' }))}
        >
          <option value="">— Select —</option>
          <option value="true">Yes</option>
          <option value="false">No</option>
        </select>
      </label>
      <label>
        Key reason for income differentials
        <select value={form.differential_reason ?? ''} onChange={(e) => setForm((p) => ({ ...p, differential_reason: e.target.value }))}>
          <option value="">— Select —</option>
          {DIFFERENTIAL_REASONS.map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
      </label>
      <label>
        Vertical gap multiple (e.g. 12.5)
        <input
          type="number" step="0.1" value={form.vertical_gap_multiple ?? ''}
          onChange={(e) => setForm((p) => ({ ...p, vertical_gap_multiple: e.target.value }))}
        />
      </label>

      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? 'Saving…' : 'Save questionnaire'}
        </button>
      </div>
    </form>
  )
}
