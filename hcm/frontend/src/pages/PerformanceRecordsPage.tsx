import { useState } from 'react'
import { api } from '../api/client'
import { useAllPages, useApiQuery } from '../api/hooks'
import type { PerformanceAgreement, PerformancePeriod } from '../api/types'

/** hr_admin + auditor (PC-3): every agreement in a period, org-wide, with its
 * full signature trail and evidence manifest -- the page neither role had
 * before. `/team-performance` is Head-scoped and `/my-performance` is
 * self-scoped; this is deliberately unscoped (the list endpoint already
 * returns everyone for these two roles server-side, `can_read_all`), so
 * there's nothing to fetch beyond the one paginated list -- every document,
 * signature and evidence item is already nested on each agreement. */
export function PerformanceRecordsPage() {
  const { data: periods } = useApiQuery<{ results: PerformancePeriod[] }>(
    () => api.get<{ results: PerformancePeriod[] }>('/performance-periods/'),
    [],
    { errorMessage: 'Failed to load performance periods.' },
  )
  const sortedPeriods = [...(periods?.results ?? [])].sort((a, b) => b.start_date.localeCompare(a.start_date))
  const [periodId, setPeriodId] = useState<number | null>(null)
  const activePeriodId = periodId ?? sortedPeriods[0]?.id ?? null

  const { data: agreements, error } = useAllPages<PerformanceAgreement>(
    activePeriodId !== null ? `/performance-agreements/?period=${activePeriodId}` : null,
    [activePeriodId],
    'Failed to load performance agreements.',
  )
  const [openId, setOpenId] = useState<number | null>(null)
  const open = agreements?.find((a) => a.id === openId) ?? null

  return (
    <div className="page">
      <div className="page-header">
        <h1>Performance Records</h1>
      </div>
      <p className="hint-text">
        Every performance agreement for a period, org-wide — the signed PDF and full signature trail for any
        employee, for the auditor's or HR's own review. Read-only.
      </p>
      {error && <p className="form-error">{error}</p>}
      {sortedPeriods.length > 0 && (
        <label className="hint-text">
          Period
          <select
            value={activePeriodId ?? ''}
            onChange={(e) => setPeriodId(Number(e.target.value))}
            aria-label="Period"
          >
            {sortedPeriods.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
      )}
      {agreements === null && <p className="empty-state">Loading…</p>}

      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Employee</th>
              <th>Status</th>
              <th>Final score</th>
              <th>HR attention</th>
              <th>Documents</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {agreements !== null && agreements.length === 0 && (
              <tr>
                <td colSpan={6}>No agreements for this period.</td>
              </tr>
            )}
            {(agreements ?? []).map((a) => (
              <tr key={a.id}>
                <td>{a.employee_name}</td>
                <td>
                  <span className="status-badge">{a.status_display}</span>
                </td>
                <td>{a.final_score ?? '—'}</td>
                <td>{a.hr_attention ? <span className="status-badge">Flagged</span> : '—'}</td>
                <td>{a.documents.length}</td>
                <td>
                  <button type="button" className="btn-link" onClick={() => setOpenId(openId === a.id ? null : a.id)}>
                    {openId === a.id ? 'Close' : 'Open'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {open && <AgreementManifest agreement={open} />}
    </div>
  )
}

function AgreementManifest({ agreement }: { agreement: PerformanceAgreement }) {
  const evidenceItems = agreement.elements.flatMap((element) =>
    element.evidence_items.map((item) => ({ ...item, kpi_title: element.kpi_title })),
  )
  return (
    <section className="detail-card">
      <h2>{agreement.employee_name} — {agreement.period_name}</h2>

      <h3>Signed documents</h3>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Stage</th>
              <th>Revision</th>
              <th>SHA-256</th>
              <th>Generated</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {agreement.documents.length === 0 && (
              <tr>
                <td colSpan={5}>No documents yet.</td>
              </tr>
            )}
            {agreement.documents.map((doc) => (
              <tr key={doc.id}>
                <td>{doc.stage}</td>
                <td>{doc.revision}</td>
                <td>
                  <code>{doc.sha256.slice(0, 16)}…</code>
                </td>
                <td>{new Date(doc.generated_at).toLocaleString()}</td>
                <td>
                  <a className="btn-link" href={doc.download_url}>
                    Download PDF
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>Signature trail</h3>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Stage</th>
              <th>Revision</th>
              <th>Role</th>
              <th>Signer</th>
              <th>Signed</th>
              <th>Method</th>
            </tr>
          </thead>
          <tbody>
            {agreement.signatures.length === 0 && (
              <tr>
                <td colSpan={6}>No signatures yet.</td>
              </tr>
            )}
            {agreement.signatures.map((sig) => (
              <tr key={sig.id}>
                <td>{sig.stage}</td>
                <td>{sig.revision}</td>
                <td>{sig.role_display}</td>
                <td>
                  {sig.signer_name}
                  {sig.acting_for_name && <span className="hint-text"> (acting for {sig.acting_for_name})</span>}
                </td>
                <td>{new Date(sig.signed_at).toLocaleString()}</td>
                <td>{sig.method_display}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>Evidence manifest</h3>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>KPI</th>
              <th>Stage</th>
              <th>Kind</th>
              <th>Description / link</th>
              <th>Uploaded by</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {evidenceItems.length === 0 && (
              <tr>
                <td colSpan={6}>No evidence attached.</td>
              </tr>
            )}
            {evidenceItems.map((item) => (
              <tr key={item.id}>
                <td>{item.kpi_title}</td>
                <td>{item.stage}</td>
                <td>{item.kind}</td>
                <td>
                  {item.kind === 'link' ? (
                    <a href={item.url} target="_blank" rel="noreferrer">
                      {item.description || item.url}
                    </a>
                  ) : (
                    item.description || 'Uploaded file'
                  )}
                  {item.added_after_signoff && <span className="hint-text"> (added after sign-off)</span>}
                </td>
                <td>{item.uploaded_by_name ?? '—'}</td>
                <td>
                  {item.kind === 'file' && item.download_url && (
                    <a className="btn-link" href={item.download_url}>
                      Download
                    </a>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
