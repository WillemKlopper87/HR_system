import { useMemo, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError, fetchAllPages } from '../api/client'
import { useApiQuery } from '../api/hooks'
import { useReferenceData } from '../api/ReferenceDataContext'
import {
  SUCCESSION_READINESS_LABELS,
  type CriticalPost,
  type Employee,
  type Position,
  type SuccessionCandidate,
  type SuccessionReadiness,
} from '../api/types'

const READINESS_OPTIONS: SuccessionReadiness[] = [
  'ready_now', 'ready_1_2_years', 'ready_3_plus_years', 'development_needed',
]

/** Talent Pools management page (C6, hr_admin-only route). Spec:
 * docs/superpowers/specs/2026-08-25-succession-talent-pools-design.md
 *
 * hr_admin manages both CriticalPost (which posts matter enough to plan
 * continuity for) and SuccessionCandidate (who's a potential successor,
 * how ready) directly here — no second approver, matching Course/
 * CourseRequirement's own single-actor shape (spec §2.6). This is also the
 * only page that can see the successor-candidate data at all: not even the
 * nominated employee's own login, or their line_manager, can reach it
 * (spec §5.2) — the backend enforces that regardless of what this page
 * does or doesn't render. */
export function TalentPoolsPage() {
  const ref = useReferenceData()
  const { data, error, reload: load } = useApiQuery(
    () =>
      Promise.all([
        fetchAllPages<Position>('/positions/'),
        fetchAllPages<CriticalPost>('/critical-posts/'),
        fetchAllPages<SuccessionCandidate>('/succession-candidates/'),
        fetchAllPages<Employee>('/employees/'),
      ]).then(([positions, criticalPosts, candidates, employees]) => ({ positions, criticalPosts, candidates, employees })),
    [],
    { errorMessage: 'Failed to load talent pools.' },
  )
  const [showFlagForm, setShowFlagForm] = useState(false)

  const positions = data?.positions ?? []
  const criticalPosts = data?.criticalPosts ?? []
  const candidates = data?.candidates ?? []
  const employees = data?.employees ?? []

  // Keyed off `data` itself (stable between renders, only changes on
  // reload), not the `?? []`-derived locals above -- those are a fresh
  // array literal every render, which would defeat the memoization.
  const positionById = useMemo(() => new Map((data?.positions ?? []).map((p) => [p.id, p])), [data])
  const employeeById = useMemo(() => new Map((data?.employees ?? []).map((e) => [e.id, e])), [data])
  const employeeName = (id: number | null) => {
    if (id === null) return '—'
    const e = employeeById.get(id)
    return e ? `${e.employee_number} — ${e.first_name} ${e.last_name}` : `#${id}`
  }

  const activeFlags = criticalPosts.filter((c) => c.active)
  const flaggedPositionIds = new Set(criticalPosts.filter((c) => c.active).map((c) => c.position))
  const flaggableApprovedPositions = positions.filter((p) => p.status === 'approved' && !flaggedPositionIds.has(p.id))

  return (
    <div className="page">
      <div className="page-header">
        <h1>Talent Pools</h1>
        <button type="button" className="btn-primary" onClick={() => setShowFlagForm((v) => !v)}>
          {showFlagForm ? 'Cancel' : '+ Flag a critical post'}
        </button>
      </div>
      <p className="hint-text">
        Flag the establishment posts whose continuity matters most, then nominate and rate potential successors.
        This data is not visible to the nominated employees themselves, their line managers, or anyone outside
        hr_admin/auditor — see the design spec for why.
      </p>

      {error && <p className="form-error">{error}</p>}

      {showFlagForm && (
        <FlagPositionForm
          positions={flaggableApprovedPositions}
          departments={ref.departments}
          onCreated={() => { setShowFlagForm(false); load() }}
        />
      )}

      {data === null ? (
        <p className="empty-state">Loading…</p>
      ) : activeFlags.length === 0 ? (
        <p className="empty-state">No critical posts flagged yet.</p>
      ) : (
        activeFlags.map((flag) => {
          const position = positionById.get(flag.position)
          return (
            <CriticalPostCard
              key={flag.id}
              flag={flag}
              position={position}
              departmentName={position ? (ref.departments.get(position.department)?.name ?? '—') : '—'}
              candidates={candidates.filter((c) => c.critical_post === flag.id && c.active)}
              employees={employees}
              employeeName={employeeName}
              onChanged={load}
            />
          )
        })
      )}
    </div>
  )
}

function FlagPositionForm({
  positions, departments, onCreated,
}: { positions: Position[]; departments: Map<number, { name: string }>; onCreated: () => void }) {
  const [positionId, setPositionId] = useState<number | ''>('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!positionId) {
      setError('Choose a position.')
      return
    }
    setSubmitting(true)
    try {
      await api.post('/critical-posts/', { position: positionId, reason })
      onCreated()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Flag failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit} style={{ flexDirection: 'column', alignItems: 'stretch' }}>
      <label>
        Position (approved posts only)
        <select value={positionId} onChange={(e) => setPositionId(e.target.value ? Number(e.target.value) : '')} required>
          <option value="">— Select —</option>
          {positions.map((p) => (
            <option key={p.id} value={p.id}>
              {p.post_number} — {p.title} ({departments.get(p.department)?.name ?? '—'})
            </option>
          ))}
        </select>
        {positions.length === 0 && (
          <span className="hint-text">Every approved position is already flagged, or none are approved yet.</span>
        )}
      </label>
      <label>
        Why this post is succession-critical
        <textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Flagging…' : 'Flag as critical'}
        </button>
      </div>
    </form>
  )
}

function CriticalPostCard({
  flag, position, departmentName, candidates, employees, employeeName, onChanged,
}: {
  flag: CriticalPost
  position: Position | undefined
  departmentName: string
  candidates: SuccessionCandidate[]
  employees: Employee[]
  employeeName: (id: number | null) => string
  onChanged: () => void
}) {
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [showNominateForm, setShowNominateForm] = useState(false)

  async function handleUnflag() {
    if (!window.confirm('Unflag this post? Its nomination history is kept, not deleted.')) return
    setError(null)
    setBusy(true)
    try {
      await api.patch(`/critical-posts/${flag.id}/`, { active: false })
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unflag failed.')
    } finally {
      setBusy(false)
    }
  }

  const alreadyNominatedIds = new Set(candidates.map((c) => c.employee))
  const currentOccupantNumber = position?.current_incumbent_number ?? null
  const nominatable = employees.filter(
    (e) => !alreadyNominatedIds.has(e.id) && e.employee_number !== currentOccupantNumber,
  )

  return (
    <section className="detail-card">
      <div className="page-header">
        <h2>{position ? `${position.post_number} — ${position.title}` : `Position #${flag.position}`}</h2>
        <button type="button" className="btn-secondary" disabled={busy} onClick={() => void handleUnflag()}>
          Unflag
        </button>
      </div>
      <p className="hint-text">
        {departmentName}
        {' · '}
        Incumbent: {currentOccupantNumber ?? 'Vacant'}
      </p>
      {flag.reason && <p>{flag.reason}</p>}
      {error && <p className="form-error">{error}</p>}

      <div className="page-header" style={{ marginTop: '1rem' }}>
        <h3>Successor candidates</h3>
        <button type="button" className="btn-secondary" onClick={() => setShowNominateForm((v) => !v)}>
          {showNominateForm ? 'Cancel' : '+ Nominate'}
        </button>
      </div>

      {showNominateForm && (
        <NominateForm
          criticalPostId={flag.id}
          candidates={nominatable}
          onCreated={() => { setShowNominateForm(false); onChanged() }}
        />
      )}

      {candidates.length === 0 ? (
        <p className="empty-state">No successor candidates nominated yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Candidate</th>
                <th>Readiness</th>
                <th>Skills</th>
                <th>Latest performance</th>
                <th>Notes</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((c) => (
                <CandidateRow key={c.id} candidate={c} employeeName={employeeName} onChanged={onChanged} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function NominateForm({
  criticalPostId, candidates, onCreated,
}: { criticalPostId: number; candidates: Employee[]; onCreated: () => void }) {
  const [employeeId, setEmployeeId] = useState<number | ''>('')
  const [readiness, setReadiness] = useState<SuccessionReadiness>('development_needed')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!employeeId) {
      setError('Choose an employee.')
      return
    }
    setSubmitting(true)
    try {
      await api.post('/succession-candidates/', {
        critical_post: criticalPostId, employee: employeeId, readiness, notes,
      })
      onCreated()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Nominate failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit} style={{ flexDirection: 'column', alignItems: 'stretch' }}>
      <label>
        Employee
        <select value={employeeId} onChange={(e) => setEmployeeId(e.target.value ? Number(e.target.value) : '')} required>
          <option value="">— Select —</option>
          {candidates.map((e) => (
            <option key={e.id} value={e.id}>{e.employee_number} — {e.first_name} {e.last_name}</option>
          ))}
        </select>
      </label>
      <label>
        Readiness
        <select value={readiness} onChange={(e) => setReadiness(e.target.value as SuccessionReadiness)}>
          {READINESS_OPTIONS.map((r) => (
            <option key={r} value={r}>{SUCCESSION_READINESS_LABELS[r]}</option>
          ))}
        </select>
      </label>
      <label>
        Notes
        <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Nominating…' : 'Nominate'}
        </button>
      </div>
    </form>
  )
}

function CandidateRow({
  candidate, employeeName, onChanged,
}: { candidate: SuccessionCandidate; employeeName: (id: number | null) => string; onChanged: () => void }) {
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleReadinessChange(readiness: SuccessionReadiness) {
    setError(null)
    setBusy(true)
    try {
      await api.patch(`/succession-candidates/${candidate.id}/`, { readiness })
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Update failed.')
    } finally {
      setBusy(false)
    }
  }

  async function handleWithdraw() {
    if (!window.confirm(`Withdraw ${employeeName(candidate.employee)} as a successor candidate?`)) return
    setError(null)
    setBusy(true)
    try {
      await api.patch(`/succession-candidates/${candidate.id}/`, { active: false })
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Withdraw failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <tr>
      <td>
        <Link to={`/employees/${candidate.employee}`}>{employeeName(candidate.employee)}</Link>
      </td>
      <td>
        <select
          value={candidate.readiness} disabled={busy}
          onChange={(e) => void handleReadinessChange(e.target.value as SuccessionReadiness)}
        >
          {READINESS_OPTIONS.map((r) => (
            <option key={r} value={r}>{SUCCESSION_READINESS_LABELS[r]}</option>
          ))}
        </select>
      </td>
      <td>{candidate.skill_names.length > 0 ? candidate.skill_names.join(', ') : '—'}</td>
      <td>
        {candidate.latest_performance
          ? `${candidate.latest_performance.final_score} (${candidate.latest_performance.period_name})`
          : '—'}
      </td>
      <td>{candidate.notes || '—'}</td>
      <td>
        {error && <p className="form-error">{error}</p>}
        <button type="button" className="btn-link" disabled={busy} onClick={() => void handleWithdraw()}>
          Withdraw
        </button>
      </td>
    </tr>
  )
}
