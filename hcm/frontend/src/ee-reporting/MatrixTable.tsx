import type { WorkforceMatrix } from '../api/types'
import { DEMOGRAPHIC_COLUMN_LABELS, OCCUPATIONAL_LEVEL_CODES, OCCUPATIONAL_LEVEL_LABELS } from './constants'

/** Renders a level x demographic-column matrix (workforce profile,
 * disability, recruitment, promotion, termination, skills development,
 * or target-vs-actual gap) as a read-only table — the same row/column
 * shape the EEA2/EEA4 forms use (EEA-Form-Spec-Notes.md). */
export function MatrixTable({ matrix, columns, rowKeys }: { matrix: WorkforceMatrix; columns: string[]; rowKeys?: string[] }) {
  const rows = rowKeys ?? [...OCCUPATIONAL_LEVEL_CODES, 'total_permanent', 'temporary_employees', 'grand_total']
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th>Occupational level</th>
            {columns.map((col) => (
              <th key={col}>{DEMOGRAPHIC_COLUMN_LABELS[col] ?? col}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((rowKey) => (
            <tr key={rowKey}>
              <td>{OCCUPATIONAL_LEVEL_LABELS[rowKey] ?? rowKey}</td>
              {columns.map((col) => (
                <td key={col}>{matrix[rowKey]?.[col as keyof (typeof matrix)[string]] ?? 0}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
