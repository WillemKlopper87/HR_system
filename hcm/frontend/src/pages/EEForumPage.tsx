import { useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../api/client'
import { useApiQuery } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import type { EEForumComposition, EEForumMeeting, EEForumMember, EEForumRepresentation, EEForumRole, Employee } from '../api/types'
import { EE_FORUM_REPRESENTATION_LABELS, EE_FORUM_ROLE_LABELS } from '../api/types'
import { OCCUPATIONAL_LEVEL_LABELS } from '../ee-reporting/constants'

const CURRENT_YEAR = new Date().getFullYear()

/** EE consultative forum (EEA s.16): membership, the derived composition
 * check, and the meeting/minutes evidence trail behind the questionnaire's
 * Section F "consulted with the EE forum" answer (design spec 2026-08-26).
 * hr_admin / ee_manager write; accounting_officer / auditor read. */
export function EEForumPage() {
  const { hasRole } = useAuth()
  const canWrite = hasRole('hr_admin') || hasRole('ee_manager')

  const members = useApiQuery(() => fetchAllPages<EEForumMember>('/ee-forum-members/'), [], { errorMessage: 'Failed to load forum members.' })
  const composition = useApiQuery(() => api.get<EEForumComposition>('/ee-forum-members/composition/'), [], { errorMessage: 'Failed to load the composition check.' })
  const meetings = useApiQuery(() => fetchAllPages<EEForumMeeting>('/ee-forum-meetings/'), [], { errorMessage: 'Failed to load forum meetings.' })
  const employees = useApiQuery(() => fetchAllPages<Employee>('/employees/'), [], { errorMessage: 'Failed to load employees.', enabled: canWrite })

  function reloadAll() {
    members.reload()
    composition.reload()
    meetings.reload()
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>EE Consultative Forum</h1>
      </div>
      <p className="hint-text">
        The evidence behind Section F of the EEA2: who sits on the forum, whether it reflects the workforce
        (EEA s.16(2)), and when it met. The questionnaire's consultation answer stays yours to give — report
        validation flags a "Yes" with no meeting on record for that year, and the converse.
      </p>

      <section className="detail-card">
        <h2>Composition check</h2>
        {composition.error && <p className="form-error">{composition.error}</p>}
        {composition.data ? <CompositionPanel composition={composition.data} /> : !composition.error && <p className="empty-state">Loading…</p>}
      </section>

      <section className="detail-card">
        <h2>Members</h2>
        {members.error && <p className="form-error">{members.error}</p>}
        {members.data === null ? (
          !members.error && <p className="empty-state">Loading…</p>
        ) : members.data.length === 0 ? (
          <p className="empty-state">No forum members recorded yet.</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Employee</th>
                  <th>Represents</th>
                  <th>Role</th>
                  <th>Term</th>
                  <th>Status</th>
                  {canWrite && <th />}
                </tr>
              </thead>
              <tbody>
                {members.data.map((m) => (
                  <tr key={m.id}>
                    <td>{m.employee_name} ({m.employee_number})</td>
                    <td>{m.representation ? EE_FORUM_REPRESENTATION_LABELS[m.representation] : '—'}</td>
                    <td>{EE_FORUM_ROLE_LABELS[m.role]}</td>
                    <td>{m.term_start} – {m.term_end ?? 'open'}</td>
                    <td>{m.is_active ? 'Active' : 'Inactive'}</td>
                    {canWrite && (
                      <td>{m.is_active && m.term_end === null && <EndTermButton member={m} onDone={reloadAll} />}</td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {canWrite && <AddMemberForm employees={employees.data ?? []} onSaved={reloadAll} />}
      </section>

      <section className="detail-card">
        <h2>Meetings</h2>
        {meetings.error && <p className="form-error">{meetings.error}</p>}
        {meetings.data === null ? (
          !meetings.error && <p className="empty-state">Loading…</p>
        ) : meetings.data.length === 0 ? (
          <p className="empty-state">No forum meetings recorded yet.</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Title</th>
                  <th>Report year</th>
                  <th>Attendees</th>
                  <th>Resolutions</th>
                  <th>Minutes</th>
                </tr>
              </thead>
              <tbody>
                {meetings.data.map((mt) => (
                  <tr key={mt.id}>
                    <td>{mt.meeting_date}</td>
                    <td>{mt.title}</td>
                    <td>{mt.report_year}</td>
                    <td>{mt.attendee_count}</td>
                    <td>{mt.resolutions || '—'}</td>
                    <td>
                      {mt.minutes_download_url ? (
                        <a className="btn-link" href={mt.minutes_download_url} target="_blank" rel="noreferrer">
                          Download minutes
                        </a>
                      ) : (
                        'None'
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {canWrite && <AddMeetingForm members={(members.data ?? []).filter((m) => m.is_active)} onSaved={reloadAll} />}
      </section>
    </div>
  )
}

function CompositionPanel({ composition }: { composition: EEForumComposition }) {
  return (
    <div>
      <p className={composition.adequate ? 'hint-text' : 'form-error'}>
        {composition.adequate
          ? `Forum composition is adequate (${composition.active_member_count} active members).`
          : `Forum composition needs attention (${composition.active_member_count} active members).`}
      </p>
      <ul>
        <li>
          Occupational levels without a member:{' '}
          {composition.levels_uncovered.length === 0
            ? 'none'
            : composition.levels_uncovered.map((c) => OCCUPATIONAL_LEVEL_LABELS[c] ?? c).join(', ')}
        </li>
        <li>Designated groups represented: {composition.designated_groups_represented ? 'Yes' : 'No'}</li>
        <li>Non-designated employees represented: {composition.non_designated_represented ? 'Yes' : 'No'}</li>
        <li>Union-nominated member present: {composition.union_nominated_present ? 'Yes' : 'No'}</li>
        <li>
          By representation:{' '}
          {(Object.keys(composition.by_representation) as EEForumRepresentation[])
            .map((k) => `${EE_FORUM_REPRESENTATION_LABELS[k]}: ${composition.by_representation[k]}`)
            .join(' · ')}
        </li>
      </ul>
    </div>
  )
}

function EndTermButton({ member, onDone }: { member: EEForumMember; onDone: () => void }) {
  const [busy, setBusy] = useState(false)
  async function endTerm() {
    setBusy(true)
    try {
      await api.patch(`/ee-forum-members/${member.id}/`, { term_end: new Date().toISOString().slice(0, 10) })
      onDone()
    } finally {
      setBusy(false)
    }
  }
  return (
    <button type="button" className="btn-link" disabled={busy} onClick={endTerm}>
      End term
    </button>
  )
}

function AddMemberForm({ employees, onSaved }: { employees: Employee[]; onSaved: () => void }) {
  const [employee, setEmployee] = useState('')
  const [representation, setRepresentation] = useState<EEForumRepresentation>('employee_nominated')
  const [role, setRole] = useState<EEForumRole>('member')
  const [termStart, setTermStart] = useState(new Date().toISOString().slice(0, 10))
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSaving(true)
    try {
      await api.post('/ee-forum-members/', { employee: Number(employee), representation, role, term_start: termStart, notes })
      setEmployee('')
      setNotes('')
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Save failed.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit} aria-label="Add forum member">
      <label>
        Employee
        <select value={employee} onChange={(e) => setEmployee(e.target.value)} required>
          <option value="">— Select —</option>
          {employees.map((emp) => (
            <option key={emp.id} value={emp.id}>{emp.employee_number} — {emp.first_name} {emp.last_name}</option>
          ))}
        </select>
      </label>
      <label>
        Represents
        <select value={representation} onChange={(e) => setRepresentation(e.target.value as EEForumRepresentation)}>
          {(Object.keys(EE_FORUM_REPRESENTATION_LABELS) as EEForumRepresentation[]).map((k) => (
            <option key={k} value={k}>{EE_FORUM_REPRESENTATION_LABELS[k]}</option>
          ))}
        </select>
      </label>
      <label>
        Role
        <select value={role} onChange={(e) => setRole(e.target.value as EEForumRole)}>
          {(Object.keys(EE_FORUM_ROLE_LABELS) as EEForumRole[]).map((k) => (
            <option key={k} value={k}>{EE_FORUM_ROLE_LABELS[k]}</option>
          ))}
        </select>
      </label>
      <label>
        Term start
        <input type="date" value={termStart} onChange={(e) => setTermStart(e.target.value)} required />
      </label>
      <label>
        Notes
        <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. union name" />
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={saving || !employee}>
          {saving ? 'Saving…' : 'Add member'}
        </button>
      </div>
    </form>
  )
}

function AddMeetingForm({ members, onSaved }: { members: EEForumMember[]; onSaved: () => void }) {
  const [meetingDate, setMeetingDate] = useState(new Date().toISOString().slice(0, 10))
  const [title, setTitle] = useState('')
  const [reportYear, setReportYear] = useState(String(CURRENT_YEAR))
  const [agenda, setAgenda] = useState('')
  const [resolutions, setResolutions] = useState('')
  const [attendees, setAttendees] = useState<Set<number>>(new Set())
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  function toggleAttendee(id: number) {
    setAttendees((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSaving(true)
    try {
      const form = new FormData()
      form.append('meeting_date', meetingDate)
      form.append('title', title)
      form.append('report_year', reportYear)
      form.append('agenda', agenda)
      form.append('resolutions', resolutions)
      attendees.forEach((id) => form.append('attendees', String(id)))
      if (file) form.append('minutes_file', file)
      await api.postForm('/ee-forum-meetings/', form)
      setTitle('')
      setAgenda('')
      setResolutions('')
      setAttendees(new Set())
      setFile(null)
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Save failed.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit} aria-label="Record forum meeting" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
      <h3>Record a meeting</h3>
      <label>
        Meeting date
        <input type="date" value={meetingDate} onChange={(e) => setMeetingDate(e.target.value)} required />
      </label>
      <label>
        Title
        <input value={title} onChange={(e) => setTitle(e.target.value)} required />
      </label>
      <label>
        Report year
        <input type="number" value={reportYear} onChange={(e) => setReportYear(e.target.value)} required />
      </label>
      <label>
        Agenda
        <textarea rows={2} value={agenda} onChange={(e) => setAgenda(e.target.value)} />
      </label>
      <label>
        Resolutions
        <textarea rows={2} value={resolutions} onChange={(e) => setResolutions(e.target.value)} />
      </label>
      <fieldset>
        <legend>Attendees</legend>
        {members.length === 0 && <p className="hint-text">No active members to record attendance for.</p>}
        {members.map((m) => (
          <label key={m.id}>
            <input type="checkbox" checked={attendees.has(m.id)} onChange={() => toggleAttendee(m.id)} />{' '}
            {m.employee_name}
          </label>
        ))}
      </fieldset>
      <label>
        Minutes (PDF or Word)
        <input type="file" accept=".pdf,.docx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={saving || !title}>
          {saving ? 'Saving…' : 'Record meeting'}
        </button>
      </div>
    </form>
  )
}
