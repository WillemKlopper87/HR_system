import { useEffect, useState } from 'react'
import { fetchAllPages } from '../../api/client'
import { useAuth } from '../../auth/useAuth'
import {
  SUCCESSION_READINESS_LABELS,
  type CriticalPost,
  type Position,
  type SuccessionCandidate,
} from '../../api/types'

// C6 (docs/superpowers/specs/2026-08-25-succession-talent-pools-design.md
// §2.5/§2.6): read-only "career path" view for hr_admin/auditor only, and
// never for the employee viewing their own record — even for an hr_admin
// looking at their own row. This client-side gate is belt-and-braces; the
// real guarantee is the backend's own get_queryset self-exclusion (spec
// §5.2), which holds even if this check were bypassed entirely.

export function SuccessionSection({ employeeId }: { employeeId: number }) {
  const { hasRole, user } = useAuth()
  const [candidates, setCandidates] = useState<SuccessionCandidate[] | null>(null)
  const [criticalPosts, setCriticalPosts] = useState<CriticalPost[]>([])
  const [positions, setPositions] = useState<Position[]>([])
  const [error, setError] = useState<string | null>(null)

  const canView = (hasRole('hr_admin') || hasRole('auditor')) && employeeId !== user?.employee_id

  useEffect(() => {
    if (!canView) return
    let cancelled = false
    Promise.all([
      fetchAllPages<SuccessionCandidate>(`/succession-candidates/?employee=${employeeId}&active=true`),
      fetchAllPages<CriticalPost>('/critical-posts/'),
      fetchAllPages<Position>('/positions/'),
    ])
      .then(([c, cp, p]) => {
        if (cancelled) return
        setCandidates(c)
        setCriticalPosts(cp)
        setPositions(p)
      })
      .catch(() => !cancelled && setError('Failed to load succession data.'))
    return () => {
      cancelled = true
    }
  }, [employeeId, canView])

  if (!canView) return null

  const criticalPostById = new Map(criticalPosts.map((c) => [c.id, c]))
  const positionById = new Map(positions.map((p) => [p.id, p]))

  return (
    <section className="detail-card">
      <h2>Succession</h2>
      <p className="hint-text">
        Critical posts this employee is currently an active successor candidate for. Visible to hr_admin/auditor
        only — not to this employee, and not on their own record even for you.
      </p>
      {error && <p className="form-error">{error}</p>}
      {candidates === null ? (
        <p className="empty-state">Loading…</p>
      ) : candidates.length === 0 ? (
        <p className="empty-state">Not currently nominated as a successor for any critical post.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Post</th>
                <th>Readiness</th>
                <th>Notes</th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((c) => {
                const criticalPost = criticalPostById.get(c.critical_post)
                const position = criticalPost ? positionById.get(criticalPost.position) : undefined
                return (
                  <tr key={c.id}>
                    <td>{position ? `${position.post_number} — ${position.title}` : `#${c.critical_post}`}</td>
                    <td>
                      <span className="status-badge">{SUCCESSION_READINESS_LABELS[c.readiness]}</span>
                    </td>
                    <td>{c.notes || '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
