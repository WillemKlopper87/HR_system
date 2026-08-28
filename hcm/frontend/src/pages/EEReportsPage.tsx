import { useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import { useAllPages } from '../api/hooks'
import {
  EE_FORM_TYPE_LABELS,
  EE_REPORT_STATUS_LABELS,
  type EEFormType,
  type EEReport,
  type WorkforceMatrix,
} from '../api/types'
import { useAuth } from '../auth/useAuth'
import { DEMOGRAPHIC_COLUMNS, SKILLS_DEMOGRAPHIC_COLUMNS } from '../ee-reporting/constants'
import { MatrixTable } from '../ee-reporting/MatrixTable'

const EEA2_SECTIONS: [string, string, string[]][] = [
  ['workforce_profile', 'Workforce Profile (Section B)', DEMOGRAPHIC_COLUMNS],
  ['disability_workforce', 'Employees with Disabilities (Section B)', DEMOGRAPHIC_COLUMNS],
  ['recruitment', 'Recruitment (Section C)', DEMOGRAPHIC_COLUMNS],
  ['promotion', 'Promotion (Section C)', DEMOGRAPHIC_COLUMNS],
  ['termination', 'Termination (Section C)', DEMOGRAPHIC_COLUMNS],
  ['skills_development', 'Skills Development (Section D)', SKILLS_DEMOGRAPHIC_COLUMNS],
]

export function EEReportsPage() {
  const { hasRole } = useAuth()
  const { data: reports, error: loadError, reload: load } = useAllPages<EEReport>('/ee-reports/', [], 'Failed to load EE reports.')
  const [showForm, setShowForm] = useState(false)
  const [expanded, setExpanded] = useState<number | null>(null)

  const canGenerate = hasRole('hr_admin')

  return (
    <div className="page">
      <div className="page-header">
        <h1>EEA2 / EEA4 Reports</h1>
        {canGenerate && (
          <button type="button" className="btn-primary" onClick={() => setShowForm((v) => !v)}>
            {showForm ? 'Cancel' : '+ Generate report'}
          </button>
        )}
      </div>

      <p className="hint-text">
        Every generation creates a new, frozen, versioned snapshot — a later data correction never silently changes
        an already-generated report. hr_admin generates and submits; ee_manager reviews; the Accounting Officer
        signs off last, per EEA-Form-Spec-Notes.md.
      </p>

      {loadError && <p className="form-error">{loadError}</p>}

      {showForm && (
        <GenerateReportForm
          onCreated={() => {
            setShowForm(false)
            load()
          }}
        />
      )}

      {reports === null ? (
        <p className="empty-state">Loading…</p>
      ) : reports.length === 0 ? (
        <p className="empty-state">No reports generated yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Form</th>
                <th>Year</th>
                <th>Version</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((report) => (
                <ReportRow
                  key={report.id}
                  report={report}
                  expanded={expanded === report.id}
                  onToggleExpand={() => setExpanded(expanded === report.id ? null : report.id)}
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

function ReportRow({
  report, expanded, onToggleExpand, onChanged,
}: { report: EEReport; expanded: boolean; onToggleExpand: () => void; onChanged: () => void }) {
  const { hasRole } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [place, setPlace] = useState('')
  const [validation, setValidation] = useState<'idle' | 'checking' | string[]>('idle')

  async function act(action: string, body?: Record<string, unknown>) {
    setError(null)
    setBusy(true)
    try {
      await api.post(`/ee-reports/${report.id}/${action}/`, body)
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Action failed.')
    } finally {
      setBusy(false)
    }
  }

  async function validate() {
    setValidation('checking')
    try {
      const result = await api.get<{ issues: string[] }>(`/ee-reports/${report.id}/validate/`)
      setValidation(result.issues)
    } catch (err) {
      setValidation([err instanceof ApiError ? err.message : 'Validation check failed.'])
    }
  }

  function exportUrl(format: string) {
    return `/api/v1/ee-reports/${report.id}/export/?export_format=${format}`
  }

  return (
    <>
      <tr>
        <td>{EE_FORM_TYPE_LABELS[report.form_type]}</td>
        <td>{report.report_year}</td>
        <td>v{report.version}</td>
        <td>
          <span className="status-badge">{EE_REPORT_STATUS_LABELS[report.status]}</span>
        </td>
        <td>
          {error && <p className="form-error">{error}</p>}
          <div className="form-actions">
            <button type="button" className="btn-link" onClick={onToggleExpand}>
              {expanded ? 'Hide detail' : 'View detail'}
            </button>
            <button type="button" className="btn-link" disabled={validation === 'checking'} onClick={() => void validate()}>
              {validation === 'checking' ? 'Validating…' : 'Validate'}
            </button>
            {report.status === 'draft' && hasRole('hr_admin') && (
              <button type="button" className="btn-secondary" disabled={busy} onClick={() => void act('submit_for_review')}>
                Submit for review
              </button>
            )}
            {report.status === 'pending_ee_review' && hasRole('ee_manager') && (
              <button type="button" className="btn-secondary" disabled={busy} onClick={() => void act('ee_review')}>
                Approve (EE manager)
              </button>
            )}
            {report.status === 'pending_signoff' && hasRole('accounting_officer') && (
              <>
                <input
                  placeholder="Place (e.g. Johannesburg)" value={place} onChange={(e) => setPlace(e.target.value)}
                  style={{ width: 140 }}
                />
                <button type="button" className="btn-primary" disabled={busy} onClick={() => void act('sign_off', { place })}>
                  Sign off
                </button>
              </>
            )}
            <a className="btn-link" href={exportUrl('csv')} target="_blank" rel="noreferrer">CSV</a>
            <a className="btn-link" href={exportUrl('xlsx')} target="_blank" rel="noreferrer">Excel</a>
            <a className="btn-link" href={exportUrl('pdf')} target="_blank" rel="noreferrer">PDF</a>
            <a className="btn-link" href={exportUrl('xml')} target="_blank" rel="noreferrer">XML</a>
          </div>
          {Array.isArray(validation) && (
            validation.length === 0 ? (
              <p className="hint-text">✓ No validation issues found.</p>
            ) : (
              <ul className="form-error">
                {validation.map((issue) => (
                  <li key={issue}>{issue}</li>
                ))}
              </ul>
            )
          )}
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={5}>
            <ReportDetail report={report} />
          </td>
        </tr>
      )}
    </>
  )
}

function ReportDetail({ report }: { report: EEReport }) {
  if (report.form_type === 'eea2') {
    return (
      <div>
        {EEA2_SECTIONS.map(([key, title, columns]) => (
          <div key={key} style={{ marginBottom: 16 }}>
            <h3>{title}</h3>
            <MatrixTable matrix={(report.data[key] as WorkforceMatrix) ?? {}} columns={columns} />
          </div>
        ))}
      </div>
    )
  }

  const gap = (report.data.median_and_gap as Record<string, unknown>) ?? {}
  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <h3>Number of employees (Section C)</h3>
        <MatrixTable matrix={(report.data.number_of_employees as WorkforceMatrix) ?? {}} columns={DEMOGRAPHIC_COLUMNS} />
      </div>
      <div style={{ marginBottom: 16 }}>
        <h3>Total remuneration (Section C)</h3>
        <MatrixTable matrix={(report.data.total_remuneration as WorkforceMatrix) ?? {}} columns={DEMOGRAPHIC_COLUMNS} />
      </div>
      <div>
        <h3>Median and gap statistics (Section E)</h3>
        <dl className="detail-grid">
          {Object.entries(gap).map(([key, value]) => (
            <div className="detail-field" key={key}>
              <dt>{key}</dt>
              <dd>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  )
}

function GenerateReportForm({ onCreated }: { onCreated: () => void }) {
  const [formType, setFormType] = useState<EEFormType>('eea2')
  const [reportYear, setReportYear] = useState(new Date().getFullYear())
  const [periodStart, setPeriodStart] = useState('')
  const [periodEnd, setPeriodEnd] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [issues, setIssues] = useState<string[]>([])
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setIssues([])
    setSubmitting(true)
    try {
      await api.post('/ee-reports/generate/', {
        form_type: formType, report_year: reportYear, period_start: periodStart, period_end: periodEnd,
      })
      onCreated()
    } catch (err) {
      if (err instanceof ApiError && err.body && typeof err.body === 'object' && 'issues' in err.body) {
        setIssues((err.body as { issues: string[] }).issues)
      }
      setError(err instanceof ApiError ? err.message : 'Generate failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit}>
      <label>
        Form
        <select value={formType} onChange={(e) => setFormType(e.target.value as EEFormType)}>
          <option value="eea2">EEA2</option>
          <option value="eea4">EEA4</option>
        </select>
      </label>
      <label>
        Report year
        <input type="number" value={reportYear} onChange={(e) => setReportYear(Number(e.target.value))} required />
      </label>
      <label>
        Period start
        <input type="date" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} required />
      </label>
      <label>
        Period end
        <input type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} required />
      </label>

      {error && <p className="form-error">{error}</p>}
      {issues.length > 0 && (
        <ul className="form-error">
          {issues.map((issue) => (
            <li key={issue}>{issue}</li>
          ))}
        </ul>
      )}

      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Generating…' : 'Generate report'}
        </button>
      </div>
    </form>
  )
}
