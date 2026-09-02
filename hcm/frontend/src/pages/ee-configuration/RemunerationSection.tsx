import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../../api/client'
import type { RemunerationRecord } from '../../api/types'

export function RemunerationRecordsLoader() {
  const [records, setRecords] = useState<RemunerationRecord[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  function load() {
    setError(null)
    fetchAllPages<RemunerationRecord>('/remuneration-records/')
      .then(setRecords)
      .catch(() => setError('Failed to load remuneration records.'))
  }

  useEffect(load, [])

  if (error) return <p className="form-error">{error}</p>
  return <RemunerationSection records={records} onImported={load} />
}

function RemunerationSection({ records, onImported }: { records: RemunerationRecord[] | null; onImported: () => void }) {
  const [csvText, setCsvText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<string | null>(null)
  const [importing, setImporting] = useState(false)

  async function handleImport(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setResult(null)
    setImporting(true)
    try {
      const response = await api.post<{ created: number; updated: number; errors: string[] }>(
        '/remuneration-records/import_csv/', { csv: csvText },
      )
      setResult(`Imported: ${response.created} created, ${response.updated} updated, ${response.errors.length} errors.`)
      setCsvText('')
      onImported()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Import failed.')
    } finally {
      setImporting(false)
    }
  }

  return (
    <div>
      <p className="hint-text">
        Stand-in for the real SAP payroll extract (no vendor integration exists yet). Expected columns:
        employee_number,period_start,period_end,fixed_remuneration,variable_remuneration
      </p>
      <form className="inline-form" onSubmit={handleImport} style={{ flexDirection: 'column', alignItems: 'stretch' }}>
        <label>
          CSV content
          <textarea
            rows={5} value={csvText} onChange={(e) => setCsvText(e.target.value)}
            placeholder="employee_number,period_start,period_end,fixed_remuneration,variable_remuneration&#10;E00001,2025-09-01,2026-08-31,350000,20000"
          />
        </label>
        {error && <p className="form-error">{error}</p>}
        {result && <p className="hint-text">{result}</p>}
        <div className="form-actions">
          <button type="submit" className="btn-primary" disabled={importing || !csvText.trim()}>
            {importing ? 'Importing…' : 'Import CSV'}
          </button>
        </div>
      </form>

      {records === null ? (
        <p className="empty-state">Loading…</p>
      ) : records.length === 0 ? (
        <p className="empty-state">No remuneration records imported yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Employee</th>
                <th>Period</th>
                <th>Fixed</th>
                <th>Variable</th>
                <th>Total</th>
              </tr>
            </thead>
            <tbody>
              {records.slice(0, 20).map((r) => (
                <tr key={r.id}>
                  <td>{r.employee_number}</td>
                  <td>{r.period_start} – {r.period_end}</td>
                  <td>R {r.fixed_remuneration.toLocaleString()}</td>
                  <td>R {r.variable_remuneration.toLocaleString()}</td>
                  <td>R {r.total_remuneration.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {records.length > 20 && <p className="hint-text">Showing first 20 of {records.length} records.</p>}
        </div>
      )}
    </div>
  )
}
