import { useState, type FormEvent } from 'react'
import { api, ApiError } from '../../api/client'
import type { Applicant } from '../../api/types'

export function DemographicsForm({ applicant, onSaved }: { applicant: Applicant; onSaved: () => void }) {
  const [race, setRace] = useState(applicant.race ?? 'not_disclosed')
  const [gender, setGender] = useState(applicant.gender ?? 'not_disclosed')
  const [disabilityStatus, setDisabilityStatus] = useState(applicant.disability_status ?? 'not_disclosed')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSaving(true)
    try {
      await api.patch(`/applicants/${applicant.id}/`, {
        race, gender, disability_status: disabilityStatus,
      })
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Save failed.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit}>
      <label>
        Race
        <select value={race} onChange={(e) => setRace(e.target.value)}>
          <option value="african">African</option>
          <option value="coloured">Coloured</option>
          <option value="indian">Indian</option>
          <option value="white">White</option>
          <option value="not_disclosed">Not disclosed</option>
        </select>
      </label>
      <label>
        Gender
        <select value={gender} onChange={(e) => setGender(e.target.value)}>
          <option value="male">Male</option>
          <option value="female">Female</option>
          <option value="not_disclosed">Not disclosed</option>
        </select>
      </label>
      <label>
        Disability status
        <select value={disabilityStatus} onChange={(e) => setDisabilityStatus(e.target.value)}>
          <option value="no">No disability</option>
          <option value="yes">Disability</option>
          <option value="not_disclosed">Not disclosed</option>
        </select>
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </form>
  )
}
