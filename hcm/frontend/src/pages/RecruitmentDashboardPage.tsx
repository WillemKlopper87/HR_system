import { api } from '../api/client'
import { useApiQuery } from '../api/hooks'
import { Breakdown } from '../components/Breakdown'
import {
  STAGE_LABELS, type RecruitmentDashboard, type RecruitmentFunnel, type RecruitmentFunnelStageRow,
} from '../api/types'

export function RecruitmentDashboardPage() {
  const { data, error } = useApiQuery(() => api.get<RecruitmentDashboard>('/dashboards/recruitment/'), [], { errorMessage: 'Failed to load the recruitment dashboard.' })
  const funnel = useApiQuery(() => api.get<RecruitmentFunnel>('/dashboards/recruitment/funnel/'), [], { errorMessage: 'Failed to load the recruitment funnel.' })

  return (
    <div className="page">
      <div className="page-header">
        <h1>Recruitment Dashboard</h1>
      </div>

      {error && <p className="form-error">{error}</p>}

      {data && (
        <>
          <div className="stat-row">
            <div className="stat-tile">
              <span className="stat-value">{data.open_requisitions}</span>
              <span className="stat-label">Open requisitions</span>
            </div>
            <div className="stat-tile">
              <span className="stat-value">{data.total_applicants}</span>
              <span className="stat-label">Total applicants</span>
            </div>
            <div className="stat-tile">
              <span className="stat-value">{data.avg_time_to_fill_days ?? '—'}</span>
              <span className="stat-label">Avg. days to fill</span>
            </div>
            {data.small_cell_suppression_applied && (
              <p className="hint-text suppression-note">
                Demographic breakdowns below suppress any cell under 5 applicants (shown as "&lt;5") — your role
                doesn't have organisation-wide sensitive-data access.
              </p>
            )}
          </div>

          <div className="breakdown-grid">
            <Breakdown
              title="Pipeline by stage"
              rows={data.by_stage}
              labels={STAGE_LABELS as Record<string, string>}
            />
            <Breakdown title="Applicants by race" rows={data.by_race} />
            <Breakdown title="Applicants by gender" rows={data.by_gender} />
            <Breakdown title="Applicants by disability status" rows={data.by_disability_status} />
          </div>
        </>
      )}

      <div className="page-header">
        <h2>Funnel by demographic</h2>
      </div>
      <p className="hint-text">
        How far applicants get before exiting — a rejected applicant still counts at the furthest stage they
        reached, not as a blank. The Code on integrating EE into HR practice calls for tracking the pool,
        short-list, interview and offer stages by demographic; this is that view.
      </p>
      {funnel.error && <p className="form-error">{funnel.error}</p>}
      {funnel.data && (
        <>
          {funnel.data.small_cell_suppression_applied && (
            <p className="hint-text suppression-note">
              Cells under 5 applicants are suppressed (shown as "&lt;5") — your role doesn't have
              organisation-wide sensitive-data access.
            </p>
          )}
          <div className="breakdown-grid">
            <FunnelTable title="By race" rows={funnel.data.by_race} />
            <FunnelTable title="By gender" rows={funnel.data.by_gender} />
            <FunnelTable title="By disability status" rows={funnel.data.by_disability_status} />
          </div>
        </>
      )}
    </div>
  )
}

function FunnelTable({ title, rows }: { title: string; rows: RecruitmentFunnelStageRow[] }) {
  const keys = Array.from(new Set(rows.flatMap((row) => row.breakdown.map((cell) => cell.key)))).sort()
  return (
    <div className="table-scroll">
      <h3>{title}</h3>
      <table className="data-table">
        <thead>
          <tr>
            <th>Stage</th>
            {keys.map((key) => <th key={key}>{key}</th>)}
            <th>Total reached</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const byKey = Object.fromEntries(row.breakdown.map((cell) => [cell.key, cell]))
            return (
              <tr key={row.stage}>
                <td>{STAGE_LABELS[row.stage]}</td>
                {keys.map((key) => (
                  <td key={key} className={byKey[key]?.suppressed ? 'suppressed' : undefined}>
                    {byKey[key]?.count ?? 0}
                  </td>
                ))}
                <td>{row.total}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
