import { useState } from 'react'
import { api, ApiError, fetchAllPages } from '../api/client'
import { useApiQuery } from '../api/hooks'
import { BENEFIT_CATEGORY_LABELS, BENEFITS_ELECTION_STATUS_LABELS, type Benefit, type BenefitsElection } from '../api/types'
import { useAuth } from '../auth/AuthContext'

export function MyBenefitsPage() {
  const { user } = useAuth()
  const employeeId = user?.employee_id ?? null

  const [error, setError] = useState<string | null>(null)
  const [busyBenefitId, setBusyBenefitId] = useState<number | null>(null)

  const { data, error: loadError, reload: load } = useApiQuery(
    () =>
      Promise.all([
        fetchAllPages<Benefit>('/benefits/'),
        fetchAllPages<BenefitsElection>('/benefits-elections/'),
      ]).then(([benefits, elections]) => {
        benefits = benefits.filter((b) => b.active)
        return { benefits, elections }
      }),
    [employeeId],
    { errorMessage: 'Failed to load your benefits.' },
  )
  const benefits = data?.benefits ?? null
  const elections = data?.elections ?? null


  async function setElection(benefit: Benefit, status: 'enrolled' | 'waived') {
    if (!employeeId) return
    setError(null)
    setBusyBenefitId(benefit.id)
    try {
      const existing = elections?.find((e) => e.benefit === benefit.id)
      if (existing) {
        await api.patch(`/benefits-elections/${existing.id}/`, { status, effective_date: new Date().toISOString().slice(0, 10) })
      } else {
        await api.post('/benefits-elections/', {
          employee: employeeId, benefit: benefit.id, status, effective_date: new Date().toISOString().slice(0, 10),
        })
      }
      load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not update your election.')
    } finally {
      setBusyBenefitId(null)
    }
  }

  if (!employeeId || benefits === null || elections === null) return <p className="empty-state">Loading…</p>

  return (
    <div className="page">
      <div className="page-header">
        <h1>My Benefits</h1>
      </div>
      <p className="hint-text">Elect or waive each benefit below. Changes take effect from today.</p>

      {loadError && <p className="form-error">{loadError}</p>}
      {error && <p className="form-error">{error}</p>}

      {benefits.length === 0 ? (
        <p className="empty-state">No benefits are currently available to elect.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Benefit</th>
                <th>Category</th>
                <th>My status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {benefits.map((benefit) => {
                const election = elections.find((e) => e.benefit === benefit.id)
                const busy = busyBenefitId === benefit.id
                return (
                  <tr key={benefit.id}>
                    <td>{benefit.name}</td>
                    <td>{BENEFIT_CATEGORY_LABELS[benefit.category]}</td>
                    <td>
                      <span className="status-badge">
                        {election ? BENEFITS_ELECTION_STATUS_LABELS[election.status] : 'Not elected'}
                      </span>
                    </td>
                    <td>
                      <div className="form-actions">
                        <button
                          type="button" className="btn-secondary" disabled={busy || election?.status === 'enrolled'}
                          onClick={() => void setElection(benefit, 'enrolled')}
                        >
                          Enroll
                        </button>
                        <button
                          type="button" className="btn-secondary" disabled={busy || election?.status === 'waived'}
                          onClick={() => void setElection(benefit, 'waived')}
                        >
                          Waive
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
