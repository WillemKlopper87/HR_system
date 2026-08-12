import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError, fetchAllPages } from '../api/client'
import { EXCEPTION_TYPE_LABELS, type DataQualityException } from '../api/types'

export function DataQualityPage() {
  const [exceptions, setExceptions] = useState<DataQualityException[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [resolvingId, setResolvingId] = useState<number | null>(null)

  function load() {
    setExceptions(null)
    setError(null)
    fetchAllPages<DataQualityException>('/data-quality-exceptions/')
      .then(setExceptions)
      .catch(() => setError('Failed to load the data-quality queue.'))
  }

  useEffect(load, [])

  async function handleRunChecks() {
    setRunning(true)
    setError(null)
    try {
      await api.post('/data-quality-exceptions/run_checks/')
      load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Run failed.')
    } finally {
      setRunning(false)
    }
  }

  async function handleResolve(id: number) {
    setResolvingId(id)
    setError(null)
    try {
      await api.post(`/data-quality-exceptions/${id}/resolve/`)
      setExceptions((prev) => prev?.filter((exc) => exc.id !== id) ?? null)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Resolve failed.')
    } finally {
      setResolvingId(null)
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Data Quality</h1>
        <button type="button" className="btn-secondary" onClick={() => void handleRunChecks()} disabled={running}>
          {running ? 'Running…' : 'Re-run checks'}
        </button>
      </div>

      <p className="hint-text">
        Open exceptions detected by the data-quality checker — missing job grades, missing demographics, and
        orphan records. Resolving here dismisses this occurrence; if the underlying data is still incomplete,
        the next check re-opens it.
      </p>

      {error && <p className="form-error">{error}</p>}

      {exceptions === null ? (
        <p className="empty-state">Loading…</p>
      ) : exceptions.length === 0 ? (
        <p className="empty-state">No open exceptions.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Employee</th>
                <th>Exception</th>
                <th>Detail</th>
                <th>Detected</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {exceptions.map((exc) => (
                <tr key={exc.id}>
                  <td>
                    <Link to={`/employees/${exc.employee}`}>
                      {exc.employee_number} — {exc.employee_name}
                    </Link>
                  </td>
                  <td>{EXCEPTION_TYPE_LABELS[exc.exception_type]}</td>
                  <td>{exc.detail}</td>
                  <td>{new Date(exc.detected_at).toLocaleDateString()}</td>
                  <td>
                    <button
                      type="button"
                      className="btn-link"
                      onClick={() => void handleResolve(exc.id)}
                      disabled={resolvingId === exc.id}
                    >
                      {resolvingId === exc.id ? 'Resolving…' : 'Resolve'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
