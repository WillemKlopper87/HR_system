import { useState, type FormEvent } from 'react'
import { api } from '../api/client'
import { useApiQuery, useMutation } from '../api/hooks'
import {
  PHASE_STAGE_LABELS,
  type AgreementTemplateSummary,
  type PeriodCompletion,
  type PerformancePeriod,
} from '../api/types'

/** hr_admin: performance periods (the FY, its phase windows and the reminder
 * schedule), the published scorecard templates, and contracting completion.
 * The reminder offsets are editable here on purpose — the whole point of the
 * feature is that HR controls how far in advance staff get nudged. */
export function PerformancePeriodsPage() {
  const { data, error, reload } = useApiQuery<{ results: PerformancePeriod[] }>(
    () => api.get<{ results: PerformancePeriod[] }>('/performance-periods/'),
    [],
    { errorMessage: 'Failed to load performance periods.' },
  )
  const { data: templates } = useApiQuery<{ results: AgreementTemplateSummary[] }>(
    () => api.get<{ results: AgreementTemplateSummary[] }>('/agreement-templates/'),
    [],
    { errorMessage: 'Failed to load scorecard templates.' },
  )
  const [showForm, setShowForm] = useState(false)

  const periods = data?.results ?? []

  return (
    <div className="page">
      <div className="page-header">
        <h1>Performance Periods</h1>
        <button type="button" className="btn-primary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : '+ New period'}
        </button>
      </div>
      <p className="hint-text">
        A period is one financial year (1 April – 31 March) with three phases. Each phase carries the reminder
        schedule that pushes to-dos to staff before the deadline.
      </p>
      {error && <p className="form-error">{error}</p>}
      {showForm && (
        <NewPeriodForm
          onCreated={() => {
            setShowForm(false)
            reload()
          }}
        />
      )}

      {periods.map((period) => (
        <PeriodCard key={period.id} period={period} onChanged={reload} />
      ))}

      <section className="detail-card">
        <h2>Scorecard templates</h2>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Version</th>
                <th>Status</th>
                <th>KPIs</th>
                <th>Total weight</th>
                <th>Signature</th>
              </tr>
            </thead>
            <tbody>
              {(templates?.results ?? []).length === 0 && (
                <tr>
                  <td colSpan={6}>No templates yet.</td>
                </tr>
              )}
              {(templates?.results ?? []).map((t) => (
                <tr key={t.id}>
                  <td>{t.name}</td>
                  <td>v{t.version}</td>
                  <td>
                    <span className="status-badge">{t.status_display}</span>
                  </td>
                  <td>{t.sections.reduce((n, s) => n + s.elements.length, 0)}</td>
                  <td>{(Number(t.total_default_weight) * 100).toFixed(0)}%</td>
                  <td>{t.signature_method === 'totp_stepup' ? 'Authenticator (step-up)' : 'Password'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

function PeriodCard({ period, onChanged }: { period: PerformancePeriod; onChanged: () => void }) {
  const act = useMutation(
    (action: string, body?: unknown) => api.post(`/performance-periods/${period.id}/${action}/`, body),
    { onSuccess: onChanged, errorMessage: 'The action could not be completed.' },
  )
  const { data: completion, reload: reloadCompletion } = useApiQuery<PeriodCompletion>(
    () => api.get<PeriodCompletion>(`/performance-periods/${period.id}/completion/`),
    [period.id, period.status, period.agreement_count],
  )

  return (
    <section className="detail-card">
      <div className="page-header">
        <h2>
          {period.name} <span className="status-badge">{period.status_display}</span>
        </h2>
        <span className="hint-text">
          {period.start_date} → {period.end_date} · {period.agreement_count} agreements
        </span>
      </div>
      {act.error && <p className="form-error">{act.error}</p>}

      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Phase</th>
              <th>Opens</th>
              <th>Due</th>
              <th>Reminders (days before)</th>
              <th>Overdue repeat</th>
            </tr>
          </thead>
          <tbody>
            {period.phases.map((phase) => (
              <tr key={phase.id}>
                <td>{PHASE_STAGE_LABELS[phase.stage]}</td>
                <td>{phase.opens_on}</td>
                <td>{phase.due_on}</td>
                <td>
                  <ReminderOffsets phaseId={phase.id} offsets={phase.reminder_offsets_days} onChanged={onChanged} />
                </td>
                <td>every {phase.overdue_every_days} days</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="form-actions">
        <button
          type="button"
          className="btn-secondary"
          disabled={act.busy}
          onClick={() => void act.run('open-phase', { stage: 'contracting' })}
        >
          Open contracting
        </button>
        <button
          type="button"
          className="btn-secondary"
          disabled={act.busy}
          onClick={() =>
            void act.run('generate-agreements').then(() => {
              reloadCompletion()
            })
          }
        >
          Generate agreements
        </button>
        <button
          type="button"
          className="btn-link"
          disabled={act.busy}
          onClick={() => {
            const name = window.prompt('Name for the next period (e.g. 2027/28)')
            if (name) void act.run('clone', { name })
          }}
        >
          Clone to next year
        </button>
      </div>

      {completion && completion.total > 0 && (
        <>
          <h2>Contracting completion</h2>
          <p className="hint-text">
            {completion.signed} of {completion.total} signed ({completion.completion_pct}%) ·{' '}
            {completion.outstanding} outstanding
          </p>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Division</th>
                  <th>Signed</th>
                  <th>Total</th>
                  <th>Completion</th>
                </tr>
              </thead>
              <tbody>
                {completion.by_division.map((row) => (
                  <tr key={row.division}>
                    <td>{row.division}</td>
                    <td>{row.signed}</td>
                    <td>{row.total}</td>
                    <td>{row.completion_pct}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  )
}

function ReminderOffsets({
  phaseId,
  offsets,
  onChanged,
}: {
  phaseId: number
  offsets: number[]
  onChanged: () => void
}) {
  const [value, setValue] = useState(offsets.join(', '))
  const save = useMutation(
    (text: string) =>
      api.patch(`/performance-phases/${phaseId}/`, {
        reminder_offsets_days: text
          .split(',')
          .map((part) => Number(part.trim()))
          .filter((n) => Number.isFinite(n) && n >= 0),
      }),
    { onSuccess: onChanged, errorMessage: 'Could not update the reminder schedule.' },
  )
  return (
    <span className="weight-cell">
      <input
        value={value}
        aria-label="Reminder offsets in days before the deadline"
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => {
          if (value !== offsets.join(', ')) void save.run(value)
        }}
      />
      {save.error && <span className="form-error">{save.error}</span>}
    </span>
  )
}

function NewPeriodForm({ onCreated }: { onCreated: () => void }) {
  const nextYear = new Date().getFullYear() + 1
  const [name, setName] = useState(`${nextYear}/${String(nextYear + 1).slice(2)}`)
  const [start, setStart] = useState(`${nextYear}-04-01`)
  const [end, setEnd] = useState(`${nextYear + 1}-03-31`)
  const create = useMutation(
    () => api.post('/performance-periods/', { name, start_date: start, end_date: end }),
    { onSuccess: onCreated, errorMessage: 'The period could not be created.' },
  )

  return (
    <form
      className="inline-form"
      onSubmit={(event: FormEvent) => {
        event.preventDefault()
        void create.run()
      }}
    >
      <label>
        Name
        <input value={name} onChange={(e) => setName(e.target.value)} required />
      </label>
      <label>
        Starts
        <input type="date" value={start} onChange={(e) => setStart(e.target.value)} required />
      </label>
      <label>
        Ends
        <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} required />
      </label>
      {create.error && <p className="form-error">{create.error}</p>}
      <button type="submit" className="btn-primary" disabled={create.busy}>
        {create.busy ? 'Creating…' : 'Create period'}
      </button>
    </form>
  )
}
