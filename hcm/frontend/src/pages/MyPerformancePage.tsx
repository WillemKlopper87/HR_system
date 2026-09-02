import { useState } from 'react'
import { api } from '../api/client'
import { useApiQuery } from '../api/hooks'
import type { PerformanceAgreement, PerformancePeriod } from '../api/types'
import { AgreementCard } from './performance/AgreementCard'

/** Employee-facing scorecard (PC-1): draft it with your Head, submit it, sign
 * it. The signature panel deliberately explains *why* a button is disabled —
 * the employee-then-Head order is the rule staff most often trip over.
 *
 * The scorecard itself is composed stage by stage in ./performance/
 * AgreementCard.tsx (contracting, review, corrective action, calibration,
 * workflow actions, signing, 360 feedback) -- shared with
 * TeamPerformancePage's `asHead` view of a report's scorecard, so it isn't
 * duplicated between the two pages. */
export function MyPerformancePage() {
  const { data: agreements, error, reload } = useApiQuery<PerformanceAgreement[]>(
    () => api.get<PerformanceAgreement[]>('/performance-agreements/mine/'),
    [],
    { errorMessage: 'Failed to load your performance agreements.' },
  )
  const { data: periods } = useApiQuery<{ results: PerformancePeriod[] }>(
    () => api.get<{ results: PerformancePeriod[] }>('/performance-periods/'),
    [],
    { errorMessage: 'Failed to load performance periods.' },
  )

  const [openId, setOpenId] = useState<number | null>(null)
  // Default to the most recent year (highest period.start_date, per the
  // API's own ordering), but any past year can be opened into the same
  // full card -- calibration outcomes and 360 rounds can exist on an older,
  // already-archived agreement (C6), not just the current one, so "only the
  // latest gets the full view" would silently hide them.
  const activeId = openId ?? agreements?.[0]?.id ?? null
  const active = agreements?.find((a) => a.id === activeId) ?? null
  const period = periods?.results.find((p) => p.id === active?.period) ?? null

  return (
    <div className="page">
      <div className="page-header">
        <h1>My Performance</h1>
      </div>
      <p className="hint-text">
        Your scorecard for the financial year: agree the KPIs and their weights with your Head, then sign. Weights
        must total 100% before you can submit.
      </p>

      {error && <p className="form-error">{error}</p>}
      {agreements === null && <p className="empty-state">Loading…</p>}
      {agreements !== null && agreements.length === 0 && (
        <p className="empty-state">
          You don't have a performance agreement yet — HR creates them when contracting opens for the year.
        </p>
      )}

      {active && <AgreementCard agreement={active} period={period} onChanged={reload} />}

      {agreements && agreements.length > 1 && (
        <section className="detail-card">
          <h2>All years</h2>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Period</th>
                  <th>Status</th>
                  <th>Final score</th>
                  <th>Document</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {agreements.map((a) => (
                  <tr key={a.id}>
                    <td>{a.period_name}</td>
                    <td>{a.status_display}</td>
                    <td>{a.final_score ?? '—'}</td>
                    <td>
                      {a.documents.length > 0 ? (
                        <a className="btn-link" href={a.documents[0].download_url}>
                          Download signed PDF
                        </a>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td>
                      <button type="button" className="btn-link" onClick={() => setOpenId(a.id)}>
                        {a.id === activeId ? 'Viewing' : 'Open'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  )
}
