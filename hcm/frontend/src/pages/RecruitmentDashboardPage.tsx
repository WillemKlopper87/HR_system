import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { Breakdown } from '../components/Breakdown'
import { STAGE_LABELS, type RecruitmentDashboard } from '../api/types'

export function RecruitmentDashboardPage() {
  const [data, setData] = useState<RecruitmentDashboard | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .get<RecruitmentDashboard>('/dashboards/recruitment/')
      .then(setData)
      .catch(() => setError('Failed to load the recruitment dashboard.'))
  }, [])

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
    </div>
  )
}
