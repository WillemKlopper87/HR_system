import { useState, type FormEvent } from 'react'
import { api, ApiError } from '../../api/client'
import {
  BACKGROUND_CHECK_STATUS_LABELS,
  BACKGROUND_CHECK_TYPE_LABELS,
  type BackgroundCheck,
  type BackgroundCheckStatus,
  type BackgroundCheckType,
} from '../../api/types'

// C6: background / reference checks

export function BackgroundChecksSection({
  applicantId, checks, onChanged,
}: { applicantId: number; checks: BackgroundCheck[] | null; onChanged: () => void }) {
  const [showForm, setShowForm] = useState(false)

  return (
    <div>
      {checks && checks.length > 0 && (
        <div className="table-scroll" style={{ marginBottom: 12 }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Status</th>
                <th>Notes</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {checks.map((check) => (
                <BackgroundCheckRow key={check.id} check={check} onChanged={onChanged} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!showForm ? (
        <button type="button" className="btn-secondary" onClick={() => setShowForm(true)}>
          + Log a check
        </button>
      ) : (
        <NewBackgroundCheckForm
          applicantId={applicantId}
          onCreated={() => {
            setShowForm(false)
            onChanged()
          }}
          onCancel={() => setShowForm(false)}
        />
      )}
    </div>
  )
}

function NewBackgroundCheckForm({
  applicantId, onCreated, onCancel,
}: { applicantId: number; onCreated: () => void; onCancel: () => void }) {
  const [checkType, setCheckType] = useState<BackgroundCheckType>('reference')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await api.post('/background-checks/', {
        applicant: applicantId, check_type: checkType, status: 'requested',
        requested_at: new Date().toISOString(),
      })
      onCreated()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to log check.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit}>
      <label>
        Check type
        <select value={checkType} onChange={(e) => setCheckType(e.target.value as BackgroundCheckType)}>
          {Object.entries(BACKGROUND_CHECK_TYPE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Logging…' : 'Log check'}
        </button>
        <button type="button" className="btn-secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}

function BackgroundCheckRow({ check, onChanged }: { check: BackgroundCheck; onChanged: () => void }) {
  const [status, setStatus] = useState<BackgroundCheckStatus>(check.status)
  const [notes, setNotes] = useState(check.notes)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function handleSave() {
    setError(null)
    setSaving(true)
    try {
      const completedAt = status === 'cleared' || status === 'flagged' ? new Date().toISOString() : check.completed_at
      await api.patch(`/background-checks/${check.id}/`, { status, notes, completed_at: completedAt })
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Save failed.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <tr>
      <td>{BACKGROUND_CHECK_TYPE_LABELS[check.check_type]}</td>
      <td>
        <select value={status} onChange={(e) => setStatus(e.target.value as BackgroundCheckStatus)}>
          {Object.entries(BACKGROUND_CHECK_STATUS_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </td>
      <td>
        <input type="text" value={notes} onChange={(e) => setNotes(e.target.value)} style={{ width: '100%' }} />
      </td>
      <td>
        {error && <p className="form-error">{error}</p>}
        <button type="button" className="btn-secondary" disabled={saving} onClick={() => void handleSave()}>
          {saving ? 'Saving…' : 'Save'}
        </button>
      </td>
    </tr>
  )
}
