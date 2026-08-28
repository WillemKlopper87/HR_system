import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../api/client'
import { useReferenceData } from '../api/useReferenceData'
import type { Employee, EmployeeVersion } from '../api/types'
import { useAuth } from '../auth/useAuth'

const RACE_OPTIONS: [string, string][] = [
  ['african', 'African'],
  ['coloured', 'Coloured'],
  ['indian', 'Indian'],
  ['white', 'White'],
  ['not_disclosed', 'Not disclosed'],
]
const GENDER_OPTIONS: [string, string][] = [
  ['male', 'Male'],
  ['female', 'Female'],
  ['not_disclosed', 'Not disclosed'],
]
const DISABILITY_OPTIONS: [string, string][] = [
  ['no', 'No disability'],
  ['yes', 'Disability'],
  ['not_disclosed', 'Not disclosed'],
]

export function MyProfilePage() {
  const { user } = useAuth()
  const employeeId = user?.employee_id ?? null
  const { departments, occupationalLevels, locations } = useReferenceData()

  const [employee, setEmployee] = useState<Employee | null>(null)
  const [version, setVersion] = useState<EmployeeVersion | null>(null)
  const [error, setError] = useState<string | null>(null)

  function load() {
    if (!employeeId) return
    setError(null)
    Promise.all([
      api.get<Employee>(`/employees/${employeeId}/`),
      fetchAllPages<EmployeeVersion>(`/employee-versions/?employee=${employeeId}&current=true`),
    ])
      .then(([emp, versions]) => {
        setEmployee(emp)
        setVersion(versions[0] ?? null)
      })
      .catch(() => setError('Failed to load your profile.'))
  }

  useEffect(load, [employeeId])

  if (!employeeId) return <p className="empty-state">Loading…</p>

  return (
    <div className="page">
      <div className="page-header">
        <h1>My Profile</h1>
      </div>

      {error && <p className="form-error">{error}</p>}

      {employee && (
        <section className="detail-card">
          <h2>Employment details</h2>
          <dl className="detail-grid">
            <div className="detail-field">
              <dt>Employee number</dt>
              <dd>{employee.employee_number}</dd>
            </div>
            <div className="detail-field">
              <dt>Name</dt>
              <dd>{employee.first_name} {employee.last_name}</dd>
            </div>
            <div className="detail-field">
              <dt>Work email</dt>
              <dd>{employee.work_email}</dd>
            </div>
            {version && (
              <>
                <div className="detail-field">
                  <dt>Department</dt>
                  <dd>{departments.get(version.department)?.name ?? '—'}</dd>
                </div>
                <div className="detail-field">
                  <dt>Occupational level</dt>
                  <dd>{occupationalLevels.get(version.occupational_level)?.name ?? '—'}</dd>
                </div>
                <div className="detail-field">
                  <dt>Location</dt>
                  <dd>{locations.get(version.location)?.name ?? '—'}</dd>
                </div>
              </>
            )}
          </dl>
          <p className="hint-text">
            Employment fields (department, level, location, manager) are HR-controlled and can't be self-edited here.
          </p>
        </section>
      )}

      {employee && <ContactDetailsForm employee={employee} onSaved={load} />}

      {employee && <SelfIdSection employee={employee} version={version} onSaved={load} />}
    </div>
  )
}

function ContactDetailsForm({ employee, onSaved }: { employee: Employee; onSaved: () => void }) {
  const [preferredName, setPreferredName] = useState(employee.preferred_name)
  const [personalEmail, setPersonalEmail] = useState(employee.personal_email ?? '')
  const [phone, setPhone] = useState(employee.phone ?? '')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    setPreferredName(employee.preferred_name)
    setPersonalEmail(employee.personal_email ?? '')
    setPhone(employee.phone ?? '')
  }, [employee])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSaved(false)
    setSaving(true)
    try {
      await api.patch(`/employees/${employee.id}/`, {
        preferred_name: preferredName, personal_email: personalEmail, phone,
      })
      setSaved(true)
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Save failed.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="detail-card">
      <h2>Contact details</h2>
      <form className="inline-form" onSubmit={handleSubmit}>
        <label>
          Preferred name
          <input value={preferredName} onChange={(e) => setPreferredName(e.target.value)} />
        </label>
        <label>
          Personal email
          <input type="email" value={personalEmail} onChange={(e) => setPersonalEmail(e.target.value)} />
        </label>
        <label>
          Phone
          <input value={phone} onChange={(e) => setPhone(e.target.value)} />
        </label>
        {error && <p className="form-error">{error}</p>}
        {saved && <p className="hint-text">Saved.</p>}
        <div className="form-actions">
          <button type="submit" className="btn-primary" disabled={saving}>
            {saving ? 'Saving…' : 'Save contact details'}
          </button>
        </div>
      </form>
    </section>
  )
}

function SelfIdSection({
  employee, version, onSaved,
}: { employee: Employee; version: EmployeeVersion | null; onSaved: () => void }) {
  const [race, setRace] = useState(version?.race ?? 'not_disclosed')
  const [gender, setGender] = useState(version?.gender ?? 'not_disclosed')
  const [disabilityStatus, setDisabilityStatus] = useState(version?.disability_status ?? 'not_disclosed')
  const [disabilityDetail, setDisabilityDetail] = useState(version?.disability_detail ?? '')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setRace(version?.race ?? 'not_disclosed')
    setGender(version?.gender ?? 'not_disclosed')
    setDisabilityStatus(version?.disability_status ?? 'not_disclosed')
    setDisabilityDetail(version?.disability_detail ?? '')
  }, [version])

  async function handleCaptureConsent() {
    setError(null)
    setBusy(true)
    try {
      await api.post(`/employees/${employee.id}/consent/`)
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to capture consent.')
    } finally {
      setBusy(false)
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await api.post(`/employees/${employee.id}/self_identify/`, {
        race, gender, disability_status: disabilityStatus, disability_detail: disabilityDetail,
      })
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Save failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="detail-card">
      <h2>Self-identification</h2>
      <p className="hint-text">
        Used for Employment Equity reporting (EEA2/EEA4) — POPIA treats this as special personal information, so it's
        only captured with your explicit consent, and only you (or HR) can set it.
      </p>

      {!employee.has_demographic_consent ? (
        <div>
          <p className="hint-text">No consent on file yet — self-identification can't be recorded until you consent.</p>
          <button type="button" className="btn-secondary" disabled={busy} onClick={() => void handleCaptureConsent()}>
            Capture consent
          </button>
        </div>
      ) : (
        <form className="inline-form" onSubmit={handleSubmit}>
          <label>
            Race
            <select value={race} onChange={(e) => setRace(e.target.value)}>
              {RACE_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
          <label>
            Gender
            <select value={gender} onChange={(e) => setGender(e.target.value)}>
              {GENDER_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
          <label>
            Disability status
            <select value={disabilityStatus} onChange={(e) => setDisabilityStatus(e.target.value)}>
              {DISABILITY_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
          <label>
            Disability detail (optional)
            <input value={disabilityDetail} onChange={(e) => setDisabilityDetail(e.target.value)} />
          </label>
          {error && <p className="form-error">{error}</p>}
          <div className="form-actions">
            <button type="submit" className="btn-primary" disabled={busy}>
              {busy ? 'Saving…' : 'Save self-identification'}
            </button>
          </div>
        </form>
      )}
    </section>
  )
}
