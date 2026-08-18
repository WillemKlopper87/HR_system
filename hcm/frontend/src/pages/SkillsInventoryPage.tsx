import { useState } from 'react'
import { api } from '../api/client'
import { useApiQuery } from '../api/hooks'
import { Breakdown } from '../components/Breakdown'
import type { SkillsInventoryRow } from '../api/types'

export function SkillsInventoryPage() {
  const { data: skills, error } = useApiQuery(
    () => api.get<{ skills: SkillsInventoryRow[] }>('/dashboards/learning/skills-inventory/').then((res) => res.skills),
    [],
    { errorMessage: 'Failed to load skills inventory.' },
  )
  const [year, setYear] = useState('')

  return (
    <div className="page">
      <div className="page-header">
        <h1>Skills Inventory</h1>
        <div className="row-actions">
          <input
            placeholder="Year (optional)"
            value={year}
            onChange={(e) => setYear(e.target.value)}
            style={{ width: 110 }}
          />
          <a
            className="btn-secondary"
            href={`/api/v1/dashboards/learning/wsp-atr-export/${year ? `?year=${encodeURIComponent(year)}` : ''}`}
            download
          >
            Download WSP/ATR export (CSV)
          </a>
        </div>
      </div>

      <p className="hint-text">
        Gap analysis by department and occupational level — where a skill has few or no holders, that's the gap.
      </p>

      {error && <p className="form-error">{error}</p>}

      {skills === null ? (
        <p className="empty-state">Loading…</p>
      ) : skills.length === 0 ? (
        <p className="empty-state">No skills in the catalog yet.</p>
      ) : (
        skills.map((row) => (
          <section key={row.skill} className="detail-card">
            <h2>
              {row.skill} <span className="status-badge">{row.category}</span>
            </h2>
            <p className="hint-text">{row.total_holders} employee(s) hold this skill</p>
            {row.total_holders > 0 && (
              <div className="breakdown-grid">
                <Breakdown title="By department" rows={row.by_department} />
                <Breakdown title="By occupational level" rows={row.by_occupational_level} />
              </div>
            )}
          </section>
        ))
      )}
    </div>
  )
}
