import { useState } from 'react'
import { api } from '../../api/client'
import { useMutation } from '../../api/hooks'
import { groupBySection } from '../../lib/performance'
import type { AgreementElement, PerformanceAgreement } from '../../api/types'

/** Contracting stage: the static KPI table, agreed once and never edited
 * again once contracted (see ReviewSection for what changes each cycle). */
export function ScorecardTable({ agreement, onChanged }: { agreement: PerformanceAgreement; onChanged: () => void }) {
  const sections = groupBySection(agreement.elements)
  return (
    <section className="detail-card">
      <h2>Key performance indicators</h2>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Objective</th>
              <th>KPA</th>
              <th>Key performance indicator</th>
              <th>Metric</th>
              <th>Weight</th>
              <th>1</th>
              <th>2</th>
              <th>3</th>
              <th>4</th>
              <th>5</th>
            </tr>
          </thead>
          <tbody>
            {sections.map(([title, elements]) =>
              elements.map((element, index) => (
                <tr key={element.id}>
                  {index === 0 && <td rowSpan={elements.length}>{title}</td>}
                  <td>{element.kpa_description}</td>
                  <td>{element.kpi_title}</td>
                  <td>{element.metric}</td>
                  <td>
                    <WeightCell element={element} editable={agreement.is_editable} onChanged={onChanged} />
                  </td>
                  {['1', '2', '3', '4', '5'].map((level) => (
                    <td key={level} className="scorecard-target">
                      {element.level_descriptors[level] ?? '—'}
                    </td>
                  ))}
                </tr>
              )),
            )}
          </tbody>
        </table>
      </div>
      {agreement.pdp_items.length > 0 && (
        <>
          <h2>Personal development plan</h2>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Business process</th>
                  <th>Course / training / certificate</th>
                </tr>
              </thead>
              <tbody>
                {agreement.pdp_items.map((item) => (
                  <tr key={item.id}>
                    <td>{item.business_process}</td>
                    <td>{item.course_or_training}</td>
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

function WeightCell({
  element,
  editable,
  onChanged,
}: {
  element: AgreementElement
  editable: boolean
  onChanged: () => void
}) {
  const [value, setValue] = useState(String(Math.round(Number(element.weight) * 100)))
  const save = useMutation(
    (pct: number) => api.patch(`/agreement-elements/${element.id}/`, { weight: (pct / 100).toFixed(4) }),
    { onSuccess: onChanged, errorMessage: 'Could not update the weight.' },
  )

  if (!editable || element.locked) {
    return <span title={element.locked ? 'Cascaded from the corporate scorecard' : undefined}>
      {(Number(element.weight) * 100).toFixed(0)}%{element.locked ? ' 🔒' : ''}
    </span>
  }
  return (
    <span className="weight-cell">
      <input
        type="number"
        min={0}
        max={100}
        value={value}
        aria-label={`Weight for ${element.kpi_title}`}
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => {
          const pct = Number(value)
          if (!Number.isNaN(pct) && pct !== Math.round(Number(element.weight) * 100)) void save.run(pct)
        }}
      />
      %{save.error && <span className="form-error">{save.error}</span>}
    </span>
  )
}
