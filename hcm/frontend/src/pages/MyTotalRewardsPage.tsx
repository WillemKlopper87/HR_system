import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useApiQuery } from '../api/hooks'
import { formatZAR } from '../lib/format'
import { BENEFIT_CATEGORY_LABELS, BENEFITS_ELECTION_STATUS_LABELS, type TotalRewardsStatement } from '../api/types'
import { useAuth } from '../auth/AuthContext'

/** Design spec 2026-08-26 §3 -- a genuinely self-scoped, narrow statement:
 * your OWN current salary (from the SAP-sourced RemunerationRecord, never
 * a CompProposal -- see the spec §4), your OWN pay-band position, your OWN
 * benefits, and your OWN latest performance score. There's no id parameter
 * anywhere on this page or the endpoint it reads -- it can only ever be
 * about the logged-in employee. */
export function MyTotalRewardsPage() {
  const { user } = useAuth()
  const employeeId = user?.employee_id ?? null

  const { data: statement, error } = useApiQuery(
    () => api.get<TotalRewardsStatement>('/my-total-rewards/'),
    [employeeId],
    { errorMessage: 'Failed to load your total-rewards statement.', enabled: employeeId !== null },
  )

  if (!employeeId || statement === null) {
    return error ? <p className="form-error">{error}</p> : <p className="empty-state">Loading…</p>
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>My Total Rewards</h1>
      </div>
      <p className="hint-text">
        A consolidated view of your current pay and benefits. This is a summary for your own reference — it never
        includes any pending or historical compensation proposal.
      </p>

      {error && <p className="form-error">{error}</p>}

      <section className="detail-card">
        <h2>Current salary</h2>
        {statement.salary ? (
          <dl className="detail-grid">
            <div className="detail-field">
              <dt>Fixed remuneration</dt>
              <dd>{formatZAR(statement.salary.fixed_remuneration)}</dd>
            </div>
            <div className="detail-field">
              <dt>Variable remuneration</dt>
              <dd>{formatZAR(statement.salary.variable_remuneration)}</dd>
            </div>
            <div className="detail-field">
              <dt>Total remuneration</dt>
              <dd>{formatZAR(statement.salary.total_remuneration)}</dd>
            </div>
            <div className="detail-field">
              <dt>As of</dt>
              <dd>{statement.salary.period_start} – {statement.salary.period_end}</dd>
            </div>
          </dl>
        ) : (
          <p className="empty-state">No remuneration record is on file for you yet.</p>
        )}
      </section>

      <section className="detail-card">
        <h2>Pay-band position</h2>
        {statement.pay_band_position ? (
          <>
            <dl className="detail-grid">
              <div className="detail-field">
                <dt>Grade</dt>
                <dd>{statement.pay_band_position.job_grade_code}</dd>
              </div>
              <div className="detail-field">
                <dt>Band</dt>
                <dd>
                  {formatZAR(statement.pay_band_position.min_salary)} – {formatZAR(statement.pay_band_position.max_salary)}
                  {' '}(mid {formatZAR(statement.pay_band_position.mid_salary)})
                </dd>
              </div>
              <div className="detail-field">
                <dt>Your position in the band</dt>
                <dd>
                  {statement.pay_band_position.percentile === null
                    ? '—'
                    : statement.pay_band_position.percentile < 0
                      ? 'Below band'
                      : statement.pay_band_position.percentile > 100
                        ? 'Above band'
                        : `${Number(statement.pay_band_position.percentile).toFixed(0)}th percentile`}
                </dd>
              </div>
            </dl>
            <div style={{ background: 'var(--border, #ddd)', borderRadius: 4, height: 8, overflow: 'hidden', marginTop: 8 }}>
              <div
                style={{
                  width: `${Math.max(0, Math.min(100, Number(statement.pay_band_position.percentile ?? 0)))}%`,
                  height: '100%', background: 'var(--accent, #2e7d32)',
                }}
              />
            </div>
          </>
        ) : (
          <p className="empty-state">Not enough data yet to show your position in your grade's pay band.</p>
        )}
      </section>

      <section className="detail-card">
        <h2>Benefits</h2>
        {statement.benefits.length === 0 ? (
          <p className="empty-state">No benefits elected yet. Visit My Benefits to enroll.</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Benefit</th>
                  <th>Category</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {statement.benefits.map((b) => (
                  <tr key={b.benefit_id}>
                    <td>{b.benefit_name}</td>
                    <td>{BENEFIT_CATEGORY_LABELS[b.category]}</td>
                    <td><span className="status-badge">{BENEFITS_ELECTION_STATUS_LABELS[b.status]}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="hint-text" style={{ marginTop: 8 }}>
          Manage your elections on the <Link to="/my-benefits">My Benefits</Link> page.
        </p>
      </section>

      <section className="detail-card">
        <h2>Performance context</h2>
        {statement.performance_context ? (
          <dl className="detail-grid">
            <div className="detail-field">
              <dt>Latest final score</dt>
              <dd>{statement.performance_context.final_score} ({statement.performance_context.period_name})</dd>
            </div>
          </dl>
        ) : (
          <p className="empty-state">No scored performance agreement on file yet.</p>
        )}
      </section>
    </div>
  )
}
