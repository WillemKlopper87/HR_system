import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../api/client'
import { useApiQuery } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { RequirePayrollStepUp } from '../auth/RequirePayrollStepUp'
import type {
  EEPlan, EEPlanMeasure, EEPlanMeasureStatus, EEPlanProgressSnapshot, EEQuestionnaire, Employee, EmployerConfig, RemunerationRecord,
} from '../api/types'
import { EE_PLAN_MEASURE_STATUS_LABELS } from '../api/types'
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
  const { hasRole } = useAuth()
  // Raw remuneration is Restricted payroll data: hr_admin (import/read) and
  // auditor (read) only — ee_manager/accounting_officer work from the generated
  // report, never the per-employee rows (RemunerationRecordPermission).
  const canSeeRemuneration = hasRole('hr_admin') || hasRole('auditor')
  // Plan measures / snapshots are the EE manager's operational records
  // (design spec 2026-08-26 §5) — unlike the form data above, ee_manager
  // writes them too.
  const canWriteOperational = hasRole('hr_admin') || hasRole('ee_manager')
  const [config, setConfig] = useState<EmployerConfig | null>(null)
  const [questionnaire, setQuestionnaire] = useState<EEQuestionnaire | null>(null)
  const [error, setError] = useState<string | null>(null)

  function load() {
    setError(null)
    Promise.all([
      fetchAllPages<EmployerConfig>('/employer-config/'),
      fetchAllPages<EEQuestionnaire>(`/ee-questionnaires/?report_year=${CURRENT_YEAR}`),
    ])
      .then(([configs, questionnaires]) => {
        setConfig(configs[0] ?? null)
        setQuestionnaire(questionnaires[0] ?? null)
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
        <h2>EE Plan measures</h2>
        <PlanMeasuresSection canWrite={canWriteOperational} />
      </section>

      <section className="detail-card">
        <h2>EE Plan progress snapshots</h2>
        <PlanSnapshotsSection canWrite={canWriteOperational} />
      </section>

      {canSeeRemuneration && (
        <section className="detail-card">
          <h2>Remuneration Records</h2>
          {/* Restricted-tier (Data-Dictionary.md) — gated separately from
              the rest of this page so a missing step-up grant doesn't break
              employer config/questionnaire loading above, which aren't
              payroll data. */}
          <RequirePayrollStepUp>
            <RemunerationRecordsLoader />
          </RequirePayrollStepUp>
        </section>
      )}
    </div>
  )
}

function RemunerationRecordsLoader() {
  const [records, setRecords] = useState<RemunerationRecord[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  function load() {
    setError(null)
    fetchAllPages<RemunerationRecord>('/remuneration-records/')
      .then(setRecords)
      .catch(() => setError('Failed to load remuneration records.'))
  }

  useEffect(load, [])

  if (error) return <p className="form-error">{error}</p>
  return <RemunerationSection records={records} onImported={load} />
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

/** The plan whose period covers today — the same selection rule the equity
 * dashboard and report validation use. */
function useCurrentPlan() {
  return useApiQuery(async () => {
    const plans = await fetchAllPages<EEPlan>('/ee-plans/')
    const today = new Date().toISOString().slice(0, 10)
    return plans.find((p) => p.plan_period_start <= today && today <= p.plan_period_end) ?? plans[0] ?? null
  }, [], { errorMessage: 'Failed to load the EE plan.' })
}

function PlanMeasuresSection({ canWrite }: { canWrite: boolean }) {
  const plan = useCurrentPlan()
  const planId = plan.data?.id ?? null
  const measures = useApiQuery(
    () => fetchAllPages<EEPlanMeasure>(`/ee-plan-measures/?plan=${planId}`), [planId],
    { errorMessage: 'Failed to load plan measures.', enabled: planId !== null },
  )
  const employees = useApiQuery(() => fetchAllPages<Employee>('/employees/'), [], { errorMessage: 'Failed to load employees.', enabled: canWrite })

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
      {canWrite && <AddMeasureForm plan={plan.data} employees={employees.data ?? []} onSaved={measures.reload} />}
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

function AddMeasureForm({ plan, employees, onSaved }: { plan: EEPlan; employees: Employee[]; onSaved: () => void }) {
  const [category, setCategory] = useState(BARRIER_CATEGORIES[0][0])
  const [barrier, setBarrier] = useState('')
  const [measure, setMeasure] = useState('')
  const [owner, setOwner] = useState('')
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
        owner: Number(owner), target_start: start, target_end: end,
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
      <label>
        Responsible person
        <select value={owner} onChange={(e) => setOwner(e.target.value)} required>
          <option value="">— Select —</option>
          {employees.map((emp) => (
            <option key={emp.id} value={emp.id}>{emp.employee_number} — {emp.first_name} {emp.last_name}</option>
          ))}
        </select>
      </label>
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

const FLAG_LABELS: Record<EEPlanProgressSnapshot['flags'][number]['basis'], string> = {
  annual_target_shortfall: 'below annual target',
  over_eap: 'over-represented vs EAP',
  disability_target_shortfall: 'below disability target',
}

function PlanSnapshotsSection({ canWrite }: { canWrite: boolean }) {
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
