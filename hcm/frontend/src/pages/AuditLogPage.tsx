import { useState } from 'react'
import { api, type Paginated } from '../api/client'
import type { AuditLogEntry } from '../api/types'

const ACTIONS = [
  'read_sensitive', 'access_denied', 'create', 'update', 'delete', 'export', 'login',
  'permission_change', 'step_up_granted',
] as const
const TIERS = [
  { value: 'P', label: 'Public' },
  { value: 'I', label: 'Internal' },
  { value: 'S', label: 'Sensitive' },
  { value: 'R', label: 'Restricted' },
]

/** hr_admin + auditor (H3): every AuditLogEntry `log_access()` writes
 * across the whole app, finally readable somewhere other than Django
 * admin. Viewing this page is itself audited (views.py::AuditLogEntryViewSet.list)
 * — the auditor role's own seed description: "every auditor read is
 * itself audited". */
export function AuditLogPage() {
  const [actor, setActor] = useState('')
  const [action, setAction] = useState('')
  const [fieldTier, setFieldTier] = useState('')
  const [entityType, setEntityType] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const [entries, setEntries] = useState<AuditLogEntry[] | null>(null)
  const [next, setNext] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  function buildQuery(): string {
    const params = new URLSearchParams()
    if (actor) params.set('actor', actor)
    if (action) params.set('action', action)
    if (fieldTier) params.set('field_tier', fieldTier)
    if (entityType) params.set('entity_type', entityType)
    if (dateFrom) params.set('date_from', dateFrom)
    if (dateTo) params.set('date_to', dateTo)
    return params.toString()
  }

  async function search() {
    setBusy(true)
    setError(null)
    try {
      const page = await api.get<Paginated<AuditLogEntry>>(`/auth/audit-log/?${buildQuery()}`)
      setEntries(page.results)
      setNext(page.next)
    } catch {
      setError('Failed to load the audit log.')
    } finally {
      setBusy(false)
    }
  }

  async function loadMore() {
    if (!next) return
    setBusy(true)
    try {
      const page = await api.get<Paginated<AuditLogEntry>>(next)
      setEntries((current) => [...(current ?? []), ...page.results])
      setNext(page.next)
    } catch {
      setError('Failed to load more entries.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Audit Log</h1>
      </div>
      <p className="hint-text">
        Every sensitive read, write, and access denial recorded across the app. Viewing this page is itself
        logged.
      </p>

      <section className="detail-card">
        <form
          className="inline-form"
          onSubmit={(e) => {
            e.preventDefault()
            void search()
          }}
        >
          <label>
            Actor (employee id)
            <input value={actor} onChange={(e) => setActor(e.target.value)} placeholder="e.g. 42" />
          </label>
          <label>
            Action
            <select value={action} onChange={(e) => setAction(e.target.value)}>
              <option value="">Any</option>
              {ACTIONS.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </label>
          <label>
            Tier
            <select value={fieldTier} onChange={(e) => setFieldTier(e.target.value)}>
              <option value="">Any</option>
              {TIERS.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Subject (entity type contains)
            <input value={entityType} onChange={(e) => setEntityType(e.target.value)} placeholder="e.g. PayBand" />
          </label>
          <label>
            From
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </label>
          <label>
            To
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </label>
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? 'Searching…' : 'Search'}
          </button>
          <a className="btn-link" href={`/api/v1/auth/audit-log/export/?${buildQuery()}`}>
            Download CSV
          </a>
        </form>
        {error && <p className="form-error">{error}</p>}
      </section>

      {entries === null && <p className="empty-state">Set filters and search, or search with no filters for everything.</p>}
      {entries !== null && (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>When</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Subject</th>
                <th>Tier</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {entries.length === 0 && (
                <tr>
                  <td colSpan={6}>No matching entries.</td>
                </tr>
              )}
              {entries.map((entry) => (
                <tr key={entry.id}>
                  <td>{new Date(entry.timestamp).toLocaleString()}</td>
                  <td>
                    {entry.actor_name}
                    {entry.actor_employee_number && ` (${entry.actor_employee_number})`}
                  </td>
                  <td>{entry.action_display}</td>
                  <td>
                    {entry.entity_type}#{entry.entity_id}
                  </td>
                  <td>{entry.field_tier_display}</td>
                  <td>{entry.fields_touched}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {next && (
            <button type="button" className="btn-secondary" disabled={busy} onClick={() => void loadMore()}>
              {busy ? 'Loading…' : 'Load more'}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
