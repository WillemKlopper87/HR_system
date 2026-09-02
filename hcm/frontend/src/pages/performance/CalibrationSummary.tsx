import type { PerformanceAgreement } from '../../api/types'

/** Calibration/moderation (C6): a signed final_score that was later
 * adjusted by a departmental committee -- never a silent overwrite (design
 * spec §2.4). The original signatures/documents are untouched; this is the
 * visible, reasoned record layered on top. */
export function CalibrationSummary({ agreement }: { agreement: PerformanceAgreement }) {
  return (
    <section className="detail-card">
      <h2>Calibration</h2>
      <p className="hint-text">
        This scorecard's final score was reviewed by a departmental calibration committee. The original signatures
        above stand — this is a recorded, reasoned adjustment layered on top, not a re-opened agreement.
      </p>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Previous</th>
              <th>New</th>
              <th>Reason</th>
              <th>By</th>
              <th>When</th>
            </tr>
          </thead>
          <tbody>
            {agreement.calibration_adjustments.map((a) => (
              <tr key={a.id}>
                <td>{a.previous_score ?? '—'}</td>
                <td>{a.new_score ?? 'No change'}</td>
                <td>{a.reason}</td>
                <td>{a.adjusted_by_name ?? '—'}</td>
                <td>{new Date(a.created_at).toLocaleDateString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
