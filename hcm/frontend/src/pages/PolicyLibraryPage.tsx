import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import { useAllPages } from '../api/hooks'
import { POLICY_CATEGORY_LABELS, POLICY_STATUS_LABELS, type Policy, type PolicyCategory } from '../api/types'
import { useAuth } from '../auth/useAuth'

export function PolicyLibraryPage() {
  const { data: policies, error: loadError, reload: load } = useAllPages<Policy>('/policies/', [], 'Failed to load the policy library.')
  const [showForm, setShowForm] = useState(false)
  const [expanded, setExpanded] = useState<number | null>(null)

  return (
    <div className="page">
      <div className="page-header">
        <h1>Policy Library</h1>
        <button type="button" className="btn-primary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : '+ New policy'}
        </button>
      </div>
      <p className="hint-text">
        Type the policy text directly, or upload a PDF/DOCX/TXT document to have its text extracted automatically.
        Publishing a new version auto-archives whichever version was previously published under the same policy.
      </p>

      {loadError && <p className="form-error">{loadError}</p>}

      {showForm && (
        <NewPolicyForm
          onCreated={() => {
            setShowForm(false)
            load()
          }}
        />
      )}

      {policies === null ? (
        <p className="empty-state">Loading…</p>
      ) : policies.length === 0 ? (
        <p className="empty-state">No policies yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Category</th>
                <th>Version</th>
                <th>Status</th>
                <th>Passages</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {policies.map((policy) => (
                <PolicyRow
                  key={policy.id}
                  policy={policy}
                  expanded={expanded === policy.id}
                  onToggleExpand={() => setExpanded(expanded === policy.id ? null : policy.id)}
                  onChanged={load}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function PolicyRow({
  policy, expanded, onToggleExpand, onChanged,
}: { policy: Policy; expanded: boolean; onToggleExpand: () => void; onChanged: () => void }) {
  const { user, hasRole } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function act(action: 'publish' | 'archive') {
    setError(null)
    setBusy(true)
    try {
      await api.post(`/policies/${policy.id}/${action}/`)
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Action failed.')
    } finally {
      setBusy(false)
    }
  }

  async function approve() {
    setError(null)
    setBusy(true)
    try {
      await api.post(`/policies/${policy.id}/approve/`)
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Approval failed.')
    } finally {
      setBusy(false)
    }
  }

  const isDraft = policy.status === 'draft'
  const hasPendingApprovals = isDraft && policy.pending_committee_approvals.length > 0
  const alreadyApproved = policy.approvals.some((a) => a.approved_by === (user?.employee_id ?? null))

  return (
    <>
      <tr>
        <td>{policy.title}</td>
        <td>{POLICY_CATEGORY_LABELS[policy.category]}</td>
        <td>v{policy.version}</td>
        <td>
          <span className="status-badge">{POLICY_STATUS_LABELS[policy.status]}</span>
        </td>
        <td>{policy.chunk_count}</td>
        <td>
          {error && <p className="form-error">{error}</p>}
          {hasPendingApprovals && (
            <p className="hint-text">Waiting on committee approval: {policy.pending_committee_approvals.join(', ')}</p>
          )}
          <div className="form-actions">
            <button type="button" className="btn-link" onClick={onToggleExpand}>
              {expanded ? 'Hide detail' : 'View detail'}
            </button>
            {isDraft && hasRole('policy_committee_member') && (
              <button type="button" className="btn-secondary" disabled={busy || alreadyApproved} onClick={() => void approve()}>
                {alreadyApproved ? 'Approved' : 'Approve'}
              </button>
            )}
            {isDraft && (
              <button
                type="button"
                className="btn-secondary"
                disabled={busy || hasPendingApprovals}
                title={hasPendingApprovals ? 'Every policy committee member must approve first.' : undefined}
                onClick={() => void act('publish')}
              >
                Publish
              </button>
            )}
            {policy.status === 'published' && (
              <button type="button" className="btn-secondary" disabled={busy} onClick={() => void act('archive')}>
                Archive
              </button>
            )}
            {policy.status !== 'draft' && <NewVersionButton policy={policy} onCreated={onChanged} />}
            {policy.download_url && (
              <a className="btn-link" href={policy.download_url} target="_blank" rel="noreferrer">
                Download
              </a>
            )}
          </div>
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={6}>
            {isDraft ? (
              <EditDraftForm policy={policy} onSaved={onChanged} />
            ) : (
              <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 300, overflow: 'auto' }}>{policy.body}</pre>
            )}
            {policy.approvals.length > 0 && (
              <div className="hint-text" style={{ marginTop: 8 }}>
                Approved by: {policy.approvals.map((a) => a.approved_by_name).join(', ')}
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

function NewVersionButton({ policy, onCreated }: { policy: Policy; onCreated: () => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleClick() {
    setError(null)
    setBusy(true)
    try {
      await api.post(`/policies/${policy.id}/new_version/`, { body: policy.body })
      onCreated()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not draft a new version.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <button type="button" className="btn-secondary" disabled={busy} onClick={() => void handleClick()}>
        New version
      </button>
      {error && <p className="form-error">{error}</p>}
    </>
  )
}

function EditDraftForm({ policy, onSaved }: { policy: Policy; onSaved: () => void }) {
  const [body, setBody] = useState(policy.body)
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => setBody(policy.body), [policy])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSaving(true)
    try {
      if (file) {
        const form = new FormData()
        form.append('source_file', file)
        await api.patchForm(`/policies/${policy.id}/`, form)
      } else {
        await api.patch(`/policies/${policy.id}/`, { body })
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
        Body text
        <textarea rows={8} value={body} onChange={(e) => setBody(e.target.value)} />
      </label>
      <label>
        Or replace with an uploaded document (PDF/DOCX/TXT) — overwrites the body text above
        <input type="file" accept=".pdf,.docx,.txt,.md" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? 'Saving…' : 'Save draft'}
        </button>
      </div>
    </form>
  )
}

function NewPolicyForm({ onCreated }: { onCreated: () => void }) {
  const [title, setTitle] = useState('')
  const [category, setCategory] = useState<PolicyCategory>('other')
  const [effectiveDate, setEffectiveDate] = useState('')
  const [mode, setMode] = useState<'text' | 'file'>('text')
  const [body, setBody] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      if (mode === 'file' && file) {
        const form = new FormData()
        form.append('title', title)
        form.append('category', category)
        if (effectiveDate) form.append('effective_date', effectiveDate)
        form.append('source_file', file)
        await api.postForm('/policies/', form)
      } else {
        await api.post('/policies/', {
          title, category, body, effective_date: effectiveDate || null,
        })
      }
      onCreated()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Create failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit} style={{ flexDirection: 'column', alignItems: 'stretch' }}>
      <label>
        Title
        <input value={title} onChange={(e) => setTitle(e.target.value)} required />
      </label>
      <label>
        Category
        <select value={category} onChange={(e) => setCategory(e.target.value as PolicyCategory)}>
          {Object.entries(POLICY_CATEGORY_LABELS).map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
      </label>
      <label>
        Effective date
        <input type="date" value={effectiveDate} onChange={(e) => setEffectiveDate(e.target.value)} />
      </label>

      <div className="form-actions">
        <label>
          <input type="radio" checked={mode === 'text'} onChange={() => setMode('text')} /> Type text
        </label>
        <label>
          <input type="radio" checked={mode === 'file'} onChange={() => setMode('file')} /> Upload document
        </label>
      </div>

      {mode === 'text' ? (
        <label>
          Body text
          <textarea rows={8} value={body} onChange={(e) => setBody(e.target.value)} />
        </label>
      ) : (
        <label>
          Document (PDF/DOCX/TXT)
          <input type="file" accept=".pdf,.docx,.txt,.md" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
        </label>
      )}

      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Creating…' : 'Create draft policy'}
        </button>
      </div>
    </form>
  )
}
