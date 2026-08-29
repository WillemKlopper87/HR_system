import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useApiQuery } from '../api/hooks'
import { Breakdown } from '../components/Breakdown'
import { STAGE_LABELS, type OverviewDashboard, type OverviewTone } from '../api/types'

const TONE_CLASS: Record<OverviewTone, string> = {
  good: 'stat-delta-good',
  warn: 'stat-delta-warn',
  bad: 'stat-delta-bad',
  neutral: 'stat-delta-neutral',
}

const SCOPE_LABEL = {
  employee: 'My overview',
  line_manager: 'Team overview',
  hr_admin: 'Organisation overview',
} as const

/** The role-adaptive landing dashboard (Wireframe all features spec(4),
 * "HCM Dashboard Styles.dc.html", Style A). One page, one endpoint,
 * three payloads — what renders below is entirely driven by which
 * optional fields GET /dashboards/overview/ included for this viewer's
 * row scope, not a client-side role check. */
export function OverviewPage() {
  const { data, error } = useApiQuery(
    () => api.get<OverviewDashboard>('/dashboards/overview/'),
    [],
    { errorMessage: 'Failed to load your overview.' },
  )

  return (
    <div className="page">
      <div className="page-header">
        <h1>{data ? SCOPE_LABEL[data.row_scope] : 'Overview'}</h1>
      </div>

      {error && <p className="form-error">{error}</p>}

      {data && (
        <>
          <p className="hint-text">
            As of {data.as_of} · {data.scope_note}
          </p>

          <div className="stat-row">
            {data.kpis.map((kpi) => (
              <div className="stat-tile" key={kpi.label}>
                <span className="stat-label">{kpi.label}</span>
                <span className="stat-value">{kpi.value}</span>
                {kpi.delta && <span className={TONE_CLASS[kpi.tone]}>{kpi.delta}</span>}
              </div>
            ))}
          </div>

          <section className="detail-card">
            <div className="page-header" style={{ marginBottom: 12 }}>
              <h2 style={{ margin: 0, fontSize: 16 }}>
                Needs your action
                {data.queue_count > 0 && <span className="queue-count-badge">{data.queue_count}</span>}
              </h2>
            </div>
            {data.queue.length === 0 ? (
              <p className="empty-state">Nothing needs your attention right now.</p>
            ) : (
              <ul className="queue-list">
                {data.queue.map((item) => (
                  <li className="queue-item" key={item.ref}>
                    <div className="queue-item-body">
                      <span className="queue-item-title">{item.title}</span>
                      <span className="queue-item-meta">
                        {item.meta} · {item.age}
                      </span>
                    </div>
                    <div className="row-actions">
                      <Link to={item.href} className="btn-primary">
                        {item.primary}
                      </Link>
                      {item.secondary && (
                        <Link to={item.href} className="btn-secondary">
                          {item.secondary}
                        </Link>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <p className="hint-text" style={{ marginTop: 12, marginBottom: 0 }}>
              Every decision here writes an audit event; reads of sensitive and restricted fields are audited too.
            </p>
          </section>

          {data.departments && (
            <div className="breakdown-grid">
              <Breakdown title="Headcount by department" rows={data.departments} />
              {data.occupational_levels && (
                <Breakdown title="By occupational level" rows={data.occupational_levels} />
              )}
            </div>
          )}

          {data.occupational_levels && data.small_cell_suppression_applied && (
            <p className="hint-text suppression-note">
              Occupational-level counts above suppress any cell under 5 employees — your role doesn't have
              organisation-wide sensitive-data access. The full workforce profile matrix is in EE Reports.
            </p>
          )}

          {(data.recruitment_funnel || data.training_compliance || data.policy_acknowledgment) && (
            <div className="breakdown-grid">
              {data.recruitment_funnel && (
                <Breakdown title="Recruitment funnel" rows={data.recruitment_funnel} labels={STAGE_LABELS} />
              )}

              {data.training_compliance && (
                <div className="breakdown-card">
                  <h3>Mandatory training compliance</h3>
                  <div className="stat-row">
                    <div className="stat-tile">
                      <span className="stat-label">Compliant</span>
                      <span className="stat-value">{data.training_compliance.compliant}</span>
                    </div>
                    <div className="stat-tile">
                      <span className="stat-label">Due</span>
                      <span className="stat-value">{data.training_compliance.due}</span>
                    </div>
                    <div className="stat-tile">
                      <span className="stat-label">Overdue</span>
                      <span className="stat-value">{data.training_compliance.overdue}</span>
                    </div>
                  </div>
                  {data.training_compliance.compliant_pct !== null && (
                    <p className="hint-text" style={{ marginTop: 12, marginBottom: 0 }}>
                      {data.training_compliance.compliant_pct}% of employee-requirement pairs compliant, org-wide.
                    </p>
                  )}
                </div>
              )}

              {data.policy_acknowledgment && (
                <div className="breakdown-card">
                  <h3>Policy acknowledgment</h3>
                  <ul className="breakdown-list">
                    {data.policy_acknowledgment.map((row) => (
                      <li key={row.title}>
                        <span className="breakdown-label">{row.title}</span>
                        <span className="breakdown-bar-track">
                          <span className="breakdown-bar" style={{ width: `${row.acknowledged_pct}%` }} />
                        </span>
                        <span className="breakdown-count">{row.acknowledged_pct}%</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
