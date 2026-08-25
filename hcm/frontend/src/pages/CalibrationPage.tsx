import { useState, type FormEvent } from 'react'
import { api } from '../api/client'
import { useApiQuery, useMutation } from '../api/hooks'
import { useReferenceData } from '../api/ReferenceDataContext'
import type { CalibrationCandidate, CalibrationSession, PerformancePeriod } from '../api/types'

/** Calibration/moderation (C6, hr_admin-only route). Spec:
 * docs/superpowers/specs/2026-08-25-performance-calibration-360-design.md
 *
 * hr_admin records a committee's outcome after an offline meeting -- not a
 * live multi-party tool (spec §2.3). A session covers one period x
 * department cohort (blank department = org-wide, same "empty targeting =
 * everyone" shape agreement templates already use). Recording an outcome
 * never bounces the agreement back to draft for re-signing -- the original
 * signatures stand; the adjustment (with its reason) sits alongside them,
 * visible to the employee on their own scorecard (spec §2.4). */
export function CalibrationPage() {
  const ref = useReferenceData()
  const { data: periods } = useApiQuery<{ results: PerformancePeriod[] }>(
    () => api.get<{ results: PerformancePeriod[] }>('/performance-periods/'),
    [],
    { errorMessage: 'Failed to load performance periods.' },
  )
  const [periodId, setPeriodId] = useState<number | null>(null)
  const activePeriodId = periodId ?? periods?.results[0]?.id ?? null

  const { data: sessions, error, reload } = useApiQuery<{ results: CalibrationSession[] }>(
    () => api.get<{ results: CalibrationSession[] }>(`/calibration-sessions/?period=${activePeriodId}`),
    [activePeriodId],
    { errorMessage: 'Failed to load calibration sessions.', enabled: activePeriodId !== null },
  )
  const [showForm, setShowForm] = useState(false)

  return (
    <div className="page">
      <div className="page-header">
        <h1>Calibration</h1>
        {activePeriodId !== null && !showForm && (
          <button type="button" className="btn-primary" onClick={() => setShowForm(true)}>
            + Open a session
          </button>
        )}
      </div>
      <p className="hint-text">
        A department (or org-wide) cohort's final-signed scores, reviewed for consistency before the year is
        archived. Record either "reviewed, no change" or an adjustment with a reason — the employee's original
        signatures stand either way, and they'll see the adjustment and why on their own scorecard.
      </p>

      <div className="inline-form">
        <label>
          Period
          <select
            value={activePeriodId ?? ''}
            onChange={(e) => setPeriodId(Number(e.target.value))}
          >
            {(periods?.results ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <p className="form-error">{error}</p>}

      {showForm && activePeriodId !== null && (
        <NewSessionForm
          periodId={activePeriodId}
          departments={ref.departmentList}
          onCreated={() => {
            setShowForm(false)
            reload()
          }}
        />
      )}

      {sessions === null && <p className="empty-state">Loading…</p>}
      {sessions !== null && sessions.results.length === 0 && (
        <p className="empty-state">No calibration sessions yet for this period.</p>
      )}
      {(sessions?.results ?? []).map((session) => (
        <SessionCard key={session.id} session={session} onChanged={reload} />
      ))}
    </div>
  )
}

function NewSessionForm({
  periodId,
  departments,
  onCreated,
}: {
  periodId: number
  departments: { id: number; name: string }[]
  onCreated: () => void
}) {
  const [department, setDepartment] = useState('')
  const [meetingDate, setMeetingDate] = useState('')
  const [participantsNote, setParticipantsNote] = useState('')

  const create = useMutation(
    () =>
      api.post('/calibration-sessions/', {
        period: periodId,
        department: department ? Number(department) : null,
        meeting_date: meetingDate || null,
        participants_note: participantsNote,
      }),
    { onSuccess: onCreated, errorMessage: 'The session could not be opened.' },
  )

  return (
    <section className="detail-card">
      <h2>New calibration session</h2>
      <form
        className="inline-form"
        onSubmit={(event: FormEvent) => {
          event.preventDefault()
          void create.run()
        }}
      >
        <label>
          Department
          <select value={department} onChange={(e) => setDepartment(e.target.value)}>
            <option value="">— Org-wide —</option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Meeting date
          <input type="date" value={meetingDate} onChange={(e) => setMeetingDate(e.target.value)} />
        </label>
        <label>
          Who attended
          <input
            value={participantsNote} onChange={(e) => setParticipantsNote(e.target.value)}
            placeholder="Heads of Research, Sales; HR Admin"
          />
        </label>
        {create.error && <p className="form-error">{create.error}</p>}
        <button type="submit" className="btn-primary" disabled={create.busy}>
          {create.busy ? 'Opening…' : 'Open session'}
        </button>
      </form>
    </section>
  )
}

function SessionCard({ session, onChanged }: { session: CalibrationSession; onChanged: () => void }) {
  const isOpen = session.status === 'open'
  const { data: candidates, reload: reloadCandidates } = useApiQuery<CalibrationCandidate[]>(
    () => api.get<CalibrationCandidate[]>(`/calibration-sessions/${session.id}/candidates/`),
    [session.id, session.adjustments.length],
    { errorMessage: 'Failed to load the cohort.', enabled: isOpen },
  )
  const close = useMutation(
    () => api.post(`/calibration-sessions/${session.id}/close/`),
    { onSuccess: onChanged, errorMessage: 'The session could not be closed.' },
  )

  return (
    <section className="detail-card">
      <div className="page-header">
        <h2>{session.department_name ?? 'Org-wide'}</h2>
        <span className="status-badge">{session.status_display}</span>
      </div>
      <dl className="detail-grid">
        <div className="detail-field">
          <dt>Meeting date</dt>
          <dd>{session.meeting_date ?? '—'}</dd>
        </div>
        <div className="detail-field">
          <dt>Attended</dt>
          <dd>{session.participants_note || '—'}</dd>
        </div>
        <div className="detail-field">
          <dt>Convened by</dt>
          <dd>{session.convened_by_name ?? '—'}</dd>
        </div>
      </dl>

      {isOpen && (
        <>
          <h3>Cohort — not yet recorded</h3>
          {candidates === null && <p className="empty-state">Loading…</p>}
          {candidates !== null && candidates.length === 0 && (
            <p className="empty-state">Every eligible agreement in this cohort has been recorded.</p>
          )}
          {(candidates ?? []).length > 0 && (
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Employee</th>
                    <th>Department</th>
                    <th>Final score</th>
                    <th>HR attention</th>
                    <th>Outcome</th>
                  </tr>
                </thead>
                <tbody>
                  {(candidates ?? []).map((c) => (
                    <CandidateRow
                      key={c.id}
                      candidate={c}
                      sessionId={session.id}
                      onRecorded={() => {
                        reloadCandidates()
                        onChanged()
                      }}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      <h3>Recorded outcomes</h3>
      {session.adjustments.length === 0 && <p className="hint-text">None recorded yet.</p>}
      {session.adjustments.length > 0 && (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Employee</th>
                <th>Previous</th>
                <th>New</th>
                <th>Reason</th>
                <th>By</th>
              </tr>
            </thead>
            <tbody>
              {session.adjustments.map((a) => (
                <tr key={a.id}>
                  <td>{a.agreement_employee_name}</td>
                  <td>{a.previous_score ?? '—'}</td>
                  <td>{a.new_score ?? 'No change'}</td>
                  <td>{a.reason}</td>
                  <td>{a.adjusted_by_name ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {isOpen && (
        <div className="form-actions">
          {close.error && <p className="form-error">{close.error}</p>}
          <button type="button" className="btn-secondary" disabled={close.busy} onClick={() => void close.run()}>
            {close.busy ? 'Closing…' : 'Close session'}
          </button>
        </div>
      )}
    </section>
  )
}

function CandidateRow({
  candidate,
  sessionId,
  onRecorded,
}: {
  candidate: CalibrationCandidate
  sessionId: number
  onRecorded: () => void
}) {
  const [reason, setReason] = useState('')
  const [newScore, setNewScore] = useState('')

  const record = useMutation(
    () =>
      api.post(`/calibration-sessions/${sessionId}/record-outcome/`, {
        agreement: candidate.id,
        reason,
        new_score: newScore ? newScore : null,
      }),
    {
      onSuccess: () => {
        setReason('')
        setNewScore('')
        onRecorded()
      },
      errorMessage: 'The outcome could not be recorded.',
    },
  )

  return (
    <tr>
      <td>
        {candidate.employee_name} ({candidate.employee_number})
      </td>
      <td>{candidate.department_name ?? '—'}</td>
      <td>{candidate.final_score}</td>
      <td>{candidate.hr_attention ? 'Flagged' : ''}</td>
      <td>
        <form
          className="inline-form"
          onSubmit={(event: FormEvent) => {
            event.preventDefault()
            void record.run()
          }}
        >
          <input
            type="number" step="0.01" min="1" max="5" placeholder="New score (blank = no change)"
            value={newScore} onChange={(e) => setNewScore(e.target.value)}
          />
          <input
            placeholder="Reason (required)" value={reason} onChange={(e) => setReason(e.target.value)} required
          />
          <button type="submit" className="btn-secondary" disabled={record.busy || !reason.trim()}>
            {record.busy ? 'Recording…' : 'Record'}
          </button>
        </form>
        {record.error && <p className="form-error">{record.error}</p>}
      </td>
    </tr>
  )
}
