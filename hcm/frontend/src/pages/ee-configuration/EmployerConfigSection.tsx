import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../../api/client'
import { useApiQuery } from '../../api/hooks'
import { BUSINESS_TYPES, EMPLOYEE_COUNT_BANDS } from '../../ee-reporting/constants'
import type { EESector, EmployerConfig } from '../../api/types'

const EMPTY_EMPLOYER_CONFIG: Partial<EmployerConfig> = {
  trade_name: '', dti_registration_name: '', dti_registration_number: '', paye_sars_number: '',
  uif_reference_number: '', ee_reference_number: '', national_or_provincial_eap: '', industry_sector: '',
  sector: null,
  seta_classification: '', bargaining_council: '', telephone_number: '',
  ceo_name: '', ceo_telephone: '', ceo_email: '',
  ee_senior_manager_name: '', ee_senior_manager_telephone: '', ee_senior_manager_email: '',
  business_type: '', employee_count_band: '', is_organ_of_state: true,
}

export function EmployerConfigForm({ config, onSaved }: { config: EmployerConfig | null; onSaved: () => void }) {
  const [form, setForm] = useState<Partial<EmployerConfig>>(config ?? EMPTY_EMPLOYER_CONFIG)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  // EEA17 reference data (Gazette 52514) — picking a sector here is what
  // lets an EE Plan be seeded from gazetted targets instead of hand-typed
  // percentages (ee_reporting.services.sector_target_defaults).
  const sectors = useApiQuery(() => fetchAllPages<EESector>('/ee-sectors/'), [], { errorMessage: 'Failed to load EE sectors.' })

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
      <label>
        EEA17 sector (drives sector-target lookup)
        <select
          value={form.sector ?? ''}
          onChange={(e) => set('sector', (e.target.value ? Number(e.target.value) : null) as never)}
        >
          <option value="">— Select —</option>
          {(sectors.data ?? []).map((s) => (
            <option key={s.id} value={s.id}>{s.code} {s.name}</option>
          ))}
        </select>
      </label>
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
