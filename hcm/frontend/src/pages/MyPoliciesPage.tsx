import { useState } from 'react'
import { api, ApiError, fetchAllPages } from '../api/client'
import { useApiQuery } from '../api/hooks'
import { POLICY_CATEGORY_LABELS, type Policy, type PolicyAcknowledgment } from '../api/types'
import { useAuth } from '../auth/AuthContext'

export function MyPoliciesPage() {
  const { user } = useAuth()
  const employeeId = user?.employee_id ?? null

  const [expanded, setExpanded] = useState<number | null>(null)

  const { data, error: loadError, reload: load } = useApiQuery(
    () =>
      Promise.all([
        fetchAllPages<Policy>('/policies/?status=published'),
        fetchAllPages<PolicyAcknowledgment>('/policy-acknowledgments/'),
      ]).then(([policies, acknowledgments]) => ({ policies, acknowledgments })),
    [employeeId],
    { errorMessage: 'Failed to load policies.' },
  )
  const policies = data?.policies ?? null
  const acknowledgments = data?.acknowledgments ?? null


  if (!employeeId || policies === null || acknowledgments === null) return <p className="empty-state">Loading…</p>

  const acknowledgedPolicyIds = new Set(acknowledgments.map((a) => a.policy))

  return (
    <div className="page">
      <div className="page-header">
        <h1>My Policies</h1>
      </div>
      <p className="hint-text">
        Current published policies. Read each one and acknowledge it — acknowledgments are always recorded for
        yourself only, and are tracked per exact version.
      </p>

      {loadError && <p className="form-error">{loadError}</p>}

      {policies.length === 0 ? (
        <p className="empty-state">No published policies yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Category</th>
                <th>Version</th>
                <th>Acknowledged</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {policies.map((policy) => (
                <PolicyRow
                  key={policy.id}
                  policy={policy}
                  acknowledged={acknowledgedPolicyIds.has(policy.id)}
                  expanded={expanded === policy.id}
                  onToggleExpand={() => setExpanded(expanded === policy.id ? null : policy.id)}
                  onAcknowledged={load}
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
  policy, acknowledged, expanded, onToggleExpand, onAcknowledged,
}: {
  policy: Policy
  acknowledged: boolean
  expanded: boolean
  onToggleExpand: () => void
  onAcknowledged: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleAcknowledge() {
    setError(null)
    setBusy(true)
    try {
      await api.post('/policy-acknowledgments/', { policy: policy.id })
      onAcknowledged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not record acknowledgment.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <tr>
        <td>{policy.title}</td>
        <td>{POLICY_CATEGORY_LABELS[policy.category]}</td>
        <td>v{policy.version}</td>
        <td>
          <span className="status-badge">{acknowledged ? 'Acknowledged' : 'Not yet'}</span>
        </td>
        <td>
          {error && <p className="form-error">{error}</p>}
          <div className="form-actions">
            <button type="button" className="btn-link" onClick={onToggleExpand}>
              {expanded ? 'Hide' : 'Read'}
            </button>
            {!acknowledged && (
              <button type="button" className="btn-primary" disabled={busy} onClick={() => void handleAcknowledge()}>
                {busy ? 'Recording…' : 'Acknowledge'}
              </button>
            )}
            {policy.download_url && (
              <a className="btn-link" href={policy.download_url} target="_blank" rel="noreferrer">
                Original document
              </a>
            )}
          </div>
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={5}>
            <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 300, overflow: 'auto' }}>{policy.body}</pre>
          </td>
        </tr>
      )}
    </>
  )
}
