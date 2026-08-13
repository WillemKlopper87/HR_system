import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../api/client'
import type { EEQuestionnaire, EmployerConfig, RemunerationRecord } from '../api/types'
import {
  BARRIER_CATEGORIES,
  BUSINESS_TYPES,
  CONSULTATION_STAKEHOLDERS,
  DIFFERENTIAL_REASONS,
  EMPLOYEE_COUNT_BANDS,
  JUSTIFIABLE_REASON_ROW_KEYS,
  JUSTIFIABLE_REASONS,
  MONITORING_FREQUENCIES,
  OCCUPATIONAL_LEVEL_LABELS,
} from '../ee-reporting/constants'

const CURRENT_YEAR = new Date().getFullYear()

export function EEConfigurationPage() {
  const [config, setConfig] = useState<EmployerConfig | null>(null)
  const [questionnaire, setQuestionnaire] = useState<EEQuestionnaire | null>(null)
  const [records, setRecords] = useState<RemunerationRecord[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  function load() {
    setError(null)
    Promise.all([
      fetchAllPages<EmployerConfig>('/employer-config/'),
      fetchAllPages<EEQuestionnaire>(`/ee-questionnaires/?report_year=${CURRENT_YEAR}`),
      fetchAllPages<RemunerationRecord>('/remuneration-records/'),
    ])
      .then(([configs, questionnaires, remRecords]) => {
        setConfig(configs[0] ?? null)
        setQuestionnaire(questionnaires[0] ?? null)
        setRecords(remRecords)
      })
      .catch(() => setError('Failed to load EE configuration.'))
  }

  useEffect(load, [])

  return (
    <div className="page">
      <div className="page-header">
        <h1>EE Reporting Configuration</h1>
      </div>
      <p className="hint-text">
        Section A (employer identity), the questionnaire sections, and remuneration data all feed into report
        generation on the Reports page. hr_admin can edit here; ee_manager/accounting_officer/auditor can view.
      </p>

      {error && <p className="form-error">{error}</p>}

      <section className="detail-card">
        <h2>Employer Configuration (Section A)</h2>
        {config === undefined ? <p className="empty-state">Loading…</p> : <EmployerConfigForm config={config} onSaved={load} />}
      </section>

      <section className="detail-card">
        <h2>EE Questionnaire — {CURRENT_YEAR}</h2>
        <QuestionnaireForm questionnaire={questionnaire} reportYear={CURRENT_YEAR} onSaved={load} />
      </section>

      <section className="detail-card">
        <h2>Remuneration Records</h2>
        <RemunerationSection records={records} onImported={load} />
      </section>
    </div>
  )
}

const EMPTY_EMPLOYER_CONFIG: Partial<EmployerConfig> = {
  trade_name: '', dti_registration_name: '', dti_registration_number: '', paye_sars_number: '',
  uif_reference_number: '', ee_reference_number: '', national_or_provincial_eap: '', industry_sector: '',
  seta_classification: '', bargaining_council: '', telephone_number: '',
  ceo_name: '', ceo_telephone: '', ceo_email: '',
  ee_senior_manager_name: '', ee_senior_manager_telephone: '', ee_senior_manager_email: '',
  business_type: '', employee_count_band: '', is_organ_of_state: true,
}

function EmployerConfigForm({ config, onSaved }: { config: EmployerConfig | null; onSaved: () => void }) {
  const [form, setForm] = useState<Partial<EmployerConfig>>(config ?? EMPTY_EMPLOYER_CONFIG)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  // `config` arrives asynchronously (fetched after mount), but useState's
  // initial value only applies once — without this, the form permanently
  // keeps the blank EMPTY_EMPLOYER_CONFIG it captured on first render, and
  // saving would silently overwrite real data with empty strings. Same
  // resync pattern as ReviewDetailPage's rating/comments editor.
  useEffect(() => {
    setForm(config ?? EMPTY_EMPLOYER_CONFIG)
  }, [config])

  function set<K extends keyof EmployerConfig>(key: K, value: EmployerConfig[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSaving(true)
    try {
      if (config) {
        await api.patch(`/employer-config/${config.id}/`, form)
      } else {
        await api.post('/employer-config/', form)
      }
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Save failed.')
    } finally {
      setSaving(false)
    }
  }

  const textField = (key: keyof EmployerConfig, label: string) => (
    <label key={key}>
      {label}
      <input value={(form[key] as string) ?? ''} onChange={(e) => set(key, e.target.value as never)} />
    </label>
  )

  return (
    <form className="inline-form" onSubmit={handleSubmit}>
      {textField('trade_name', 'Trade name')}
      {textField('dti_registration_name', 'DTI registration name')}
      {textField('dti_registration_number', 'DTI registration number')}
      {textField('paye_sars_number', 'PAYE/SARS number')}
      {textField('uif_reference_number', 'UIF reference number')}
      {textField('ee_reference_number', 'EE reference number')}
      {textField('national_or_provincial_eap', 'National or Provincial EAP')}
      {textField('industry_sector', 'Industry/Sector')}
      {textField('seta_classification', 'SETA classification')}
      {textField('bargaining_council', 'Bargaining Council')}
      {textField('telephone_number', 'Telephone number')}
      {textField('ceo_name', 'CEO/Accounting Officer name')}
      {textField('ceo_telephone', 'CEO telephone')}
      {textField('ceo_email', 'CEO email')}
      {textField('ee_senior_manager_name', 'EE Senior Manager name')}
      {textField('ee_senior_manager_telephone', 'EE Senior Manager telephone')}
      {textField('ee_senior_manager_email', 'EE Senior Manager email')}
      <label>
        Business type
        <select value={form.business_type ?? ''} onChange={(e) => set('business_type', e.target.value)}>
          <option value="">— Select —</option>
          {BUSINESS_TYPES.map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
      </label>
      <label>
        Employee count band
        <select value={form.employee_count_band ?? ''} onChange={(e) => set('employee_count_band', e.target.value)}>
          <option value="">— Select —</option>
          {EMPLOYEE_COUNT_BANDS.map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
      </label>
      <label>
        <input
          type="checkbox" checked={form.is_organ_of_state ?? false}
          onChange={(e) => set('is_organ_of_state', e.target.checked)}
        />{' '}
        Organ of state / designated by collective agreement
      </label>

      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? 'Saving…' : 'Save employer configuration'}
        </button>
      </div>
    </form>
  )
}

function emptyQuestionnaire(reportYear: number): Partial<EEQuestionnaire> {
  return {
    report_year: reportYear, achieved_all_targets: null, justifiable_reasons: {}, consultation: {}, barriers: {},
    monitoring_frequency: '', achieved_annual_objectives: null, achieved_annual_objectives_explanation: '',
    has_remuneration_policy: null, remuneration_gap_aligned_to_policy: null, has_measures_in_ee_plan: null,
    differential_reason: '', differential_reason_other: '', vertical_gap_multiple: '',
  }
}

function QuestionnaireForm({
  questionnaire, reportYear, onSaved,
}: { questionnaire: EEQuestionnaire | null; reportYear: number; onSaved: () => void }) {
  const [form, setForm] = useState<Partial<EEQuestionnaire>>(questionnaire ?? emptyQuestionnaire(reportYear))
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  // Same async-prop-arrives-after-mount issue as EmployerConfigForm above
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

function RemunerationSection({ records, onImported }: { records: RemunerationRecord[] | null; onImported: () => void }) {
  const [csvText, setCsvText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<string | null>(null)
  const [importing, setImporting] = useState(false)

  async function handleImport(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setResult(null)
    setImporting(true)
    try {
      const response = await api.post<{ created: number; updated: number; errors: string[] }>(
        '/remuneration-records/import_csv/', { csv: csvText },
      )
      setResult(`Imported: ${response.created} created, ${response.updated} updated, ${response.errors.length} errors.`)
      setCsvText('')
      onImported()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Import failed.')
    } finally {
      setImporting(false)
    }
  }

  return (
    <div>
      <p className="hint-text">
        Stand-in for the real SAP payroll extract (no vendor integration exists yet). Expected columns:
        employee_number,period_start,period_end,fixed_remuneration,variable_remuneration
      </p>
      <form className="inline-form" onSubmit={handleImport} style={{ flexDirection: 'column', alignItems: 'stretch' }}>
        <label>
          CSV content
          <textarea
            rows={5} value={csvText} onChange={(e) => setCsvText(e.target.value)}
            placeholder="employee_number,period_start,period_end,fixed_remuneration,variable_remuneration&#10;E00001,2025-09-01,2026-08-31,350000,20000"
          />
        </label>
        {error && <p className="form-error">{error}</p>}
        {result && <p className="hint-text">{result}</p>}
        <div className="form-actions">
          <button type="submit" className="btn-primary" disabled={importing || !csvText.trim()}>
            {importing ? 'Importing…' : 'Import CSV'}
          </button>
        </div>
      </form>

      {records === null ? (
        <p className="empty-state">Loading…</p>
      ) : records.length === 0 ? (
        <p className="empty-state">No remuneration records imported yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Employee</th>
                <th>Period</th>
                <th>Fixed</th>
                <th>Variable</th>
                <th>Total</th>
              </tr>
            </thead>
            <tbody>
              {records.slice(0, 20).map((r) => (
                <tr key={r.id}>
                  <td>{r.employee_number}</td>
                  <td>{r.period_start} – {r.period_end}</td>
                  <td>R {r.fixed_remuneration.toLocaleString()}</td>
                  <td>R {r.variable_remuneration.toLocaleString()}</td>
                  <td>R {r.total_remuneration.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {records.length > 20 && <p className="hint-text">Showing first 20 of {records.length} records.</p>}
        </div>
      )}
    </div>
  )
}
