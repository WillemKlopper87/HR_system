import { useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../api/client'
import { useApiQuery } from '../api/hooks'
import {
  CHECKLIST_DIRECTION_LABELS,
  CHECKLIST_OWNER_ROLE_LABELS,
  type ChecklistDirection,
  type ChecklistOwnerRole,
  type ChecklistTemplate,
} from '../api/types'
import { useAuth } from '../auth/useAuth'

const DIRECTIONS: ChecklistDirection[] = ['onboarding', 'offboarding']
const OWNER_ROLES: ChecklistOwnerRole[] = ['hr', 'it', 'line_manager', 'employee', 'other']

/** Template management (design spec §2.3, §7): read is hr_admin + auditor,
 * every write is hr_admin only (buttons hide accordingly; the backend is
 * the real gate). A template is a flat ordered list of tasks — deliberately
 * simpler than performance's AgreementTemplate (no sections, no
 * signing/scoring). Editing a template's tasks is only possible while it
 * is still 'draft'; publishing freezes the task list so existing checklist
 * instances (which hold their own snapshot) are never retroactively
 * rewritten — to change the process, publish a new version under the same
 * name. */
export function ChecklistTemplatesPage() {
  const { hasRole } = useAuth()
  const canWrite = hasRole('hr_admin')
  const [direction, setDirection] = useState<ChecklistDirection>('onboarding')
  const { data: templates, error, reload: load } = useApiQuery(
    () => fetchAllPages<ChecklistTemplate>(`/checklist-templates/?direction=${direction}`),
    [direction],
    { errorMessage: 'Failed to load checklist templates.' },
  )
  const [showForm, setShowForm] = useState(false)

  return (
    <div className="page">
      <div className="page-header">
        <h1>Checklist Templates</h1>
        {canWrite && (
          <button type="button" onClick={() => setShowForm((v) => !v)}>
            {showForm ? 'Cancel' : '+ New template'}
          </button>
        )}
      </div>

      <p className="hint-text">
        A template is a versioned, ordered list of tasks. Publishing freezes its task list — an existing
        employee's checklist keeps the tasks it was created with, so editing the process means publishing a
        new version, never rewriting one already in progress.
      </p>

      <div className="form-actions">
        {DIRECTIONS.map((d) => (
          <button
            key={d}
            type="button"
            className={d === direction ? 'btn-primary' : 'btn-secondary'}
            onClick={() => setDirection(d)}
          >
            {CHECKLIST_DIRECTION_LABELS[d]}
          </button>
        ))}
      </div>

      {showForm && canWrite && (
        <NewTemplateForm
          direction={direction}
          onDone={() => {
            setShowForm(false)
            load()
          }}
        />
      )}

      {error && <p className="form-error">{error}</p>}

      {templates === null ? (
        <p className="empty-state">Loading…</p>
      ) : templates.length === 0 ? (
        <p className="empty-state">No {CHECKLIST_DIRECTION_LABELS[direction].toLowerCase()} templates yet.</p>
      ) : (
        templates.map((template) => (
          <TemplateCard key={template.id} template={template} onChanged={load} />
        ))
      )}
    </div>
  )
}

function NewTemplateForm({ direction, onDone }: { direction: ChecklistDirection; onDone: () => void }) {
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!name.trim()) {
      setError('A name is required.')
      return
    }
    setSubmitting(true)
    try {
      await api.post('/checklist-templates/', { name, direction })
      onDone()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Create failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={(e) => void handleSubmit(e)}>
      <label>
        Name
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Standard onboarding"
        />
      </label>
      <p className="hint-text">
        Creating a second template with this name auto-assigns the next version — HR never needs to track
        version numbers by hand.
      </p>
      {error && <p className="form-error">{error}</p>}
      <button type="submit" disabled={submitting}>
        {submitting ? 'Creating…' : 'Create draft'}
      </button>
    </form>
  )
}

function TemplateCard({ template, onChanged }: { template: ChecklistTemplate; onChanged: () => void }) {
  const { hasRole } = useAuth()
  const canWrite = hasRole('hr_admin')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const draft = template.status === 'draft'
  const showItemActions = draft && canWrite
  // Mirrors the server's own rule (services.publish_template): a template
  // needs at least one task before it can be published.
  const canPublish = draft && canWrite && template.items.length > 0

  async function publish() {
    setBusy(true)
    setError(null)
    try {
      await api.post(`/checklist-templates/${template.id}/publish/`)
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Publish failed.')
    } finally {
      setBusy(false)
    }
  }

  async function retire() {
    setBusy(true)
    setError(null)
    try {
      await api.post(`/checklist-templates/${template.id}/retire/`)
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Retire failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="detail-card">
      <div className="page-header">
        <h3>
          {template.name} <span className="hint-text">v{template.version}</span>
        </h3>
        <div>
          <span className="status-badge">{template.status}</span>{' '}
          {canPublish && (
            <button type="button" onClick={() => void publish()} disabled={busy}>
              Publish
            </button>
          )}
          {template.status === 'published' && canWrite && (
            <button type="button" onClick={() => void retire()} disabled={busy}>
              Retire
            </button>
          )}
        </div>
      </div>
      {error && <p className="form-error">{error}</p>}

      <table className="data-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Task</th>
            <th>Description</th>
            <th>Owner</th>
            {showItemActions && <th>Actions</th>}
          </tr>
        </thead>
        <tbody>
          {template.items.map((item) => (
            <tr key={item.id}>
              <td>{item.order}</td>
              <td>{item.label}</td>
              <td>{item.description}</td>
              <td>{CHECKLIST_OWNER_ROLE_LABELS[item.owner_role]}</td>
              {showItemActions && (
                <td>
                  <RemoveItemButton itemId={item.id} onChanged={onChanged} />
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>

      {showItemActions && <AddItemForm templateId={template.id} onChanged={onChanged} />}
    </div>
  )
}

function RemoveItemButton({ itemId, onChanged }: { itemId: number; onChanged: () => void }) {
  const [busy, setBusy] = useState(false)
  async function remove() {
    setBusy(true)
    try {
      await api.delete(`/checklist-template-items/${itemId}/`)
      onChanged()
    } finally {
      setBusy(false)
    }
  }
  return (
    <button type="button" onClick={() => void remove()} disabled={busy}>
      Remove
    </button>
  )
}

function AddItemForm({ templateId, onChanged }: { templateId: number; onChanged: () => void }) {
  const [label, setLabel] = useState('')
  const [description, setDescription] = useState('')
  const [ownerRole, setOwnerRole] = useState<ChecklistOwnerRole>('hr')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!label.trim()) {
      setError('A task label is required.')
      return
    }
    setSubmitting(true)
    try {
      await api.post('/checklist-template-items/', {
        template: templateId, label, description, owner_role: ownerRole,
      })
      setLabel('')
      setDescription('')
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Add task failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={(e) => void handleSubmit(e)}>
      <label>
        Task
        <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. Issue laptop" />
      </label>
      <label>
        Description
        <input value={description} onChange={(e) => setDescription(e.target.value)} />
      </label>
      <label>
        Owner
        <select value={ownerRole} onChange={(e) => setOwnerRole(e.target.value as ChecklistOwnerRole)}>
          {OWNER_ROLES.map((role) => (
            <option key={role} value={role}>
              {CHECKLIST_OWNER_ROLE_LABELS[role]}
            </option>
          ))}
        </select>
      </label>
      {error && <p className="form-error">{error}</p>}
      <button type="submit" disabled={submitting}>
        {submitting ? 'Adding…' : '+ Add task'}
      </button>
    </form>
  )
}
