import { useMemo, useState, type FormEvent } from 'react'
import { api, ApiError, fetchAllPages } from '../api/client'
import { useApiQuery } from '../api/hooks'
import {
  BENEFIT_CATEGORY_LABELS,
  BENEFITS_ELECTION_STATUS_LABELS,
  type Benefit,
  type BenefitCategory,
  type BenefitsElection,
  type BenefitsElectionStatus,
} from '../api/types'
import { EmployeeAsyncSelect } from '../components/EmployeeAsyncSelect'

const CATEGORY_OPTIONS = Object.entries(BENEFIT_CATEGORY_LABELS) as [BenefitCategory, string][]
const ELECTION_STATUS_OPTIONS = Object.entries(BENEFITS_ELECTION_STATUS_LABELS) as [BenefitsElectionStatus, string][]

export function BenefitsPage() {
  const [showBenefitForm, setShowBenefitForm] = useState(false)
  const [showElectionForm, setShowElectionForm] = useState(false)

  const { data, error: loadError, reload: load } = useApiQuery(
    () =>
      Promise.all([
        fetchAllPages<Benefit>('/benefits/'),
        fetchAllPages<BenefitsElection>('/benefits-elections/'),
      ]).then(([benefits, elections]) => ({ benefits, elections })),
    [],
    { errorMessage: 'Failed to load benefits.' },
  )
  const benefits = data?.benefits ?? null
  const elections = data?.elections ?? null
  const benefitById = useMemo(() => new Map((benefits ?? []).map((b) => [b.id, b])), [benefits])

  return (
    <div className="page">
      <div className="page-header">
        <h1>Benefits</h1>
      </div>

      {loadError && <p className="form-error">{loadError}</p>}

      <section className="detail-card">
        <div className="page-header">
          <h2>Benefits catalog</h2>
          <button type="button" className="btn-primary" onClick={() => setShowBenefitForm((v) => !v)}>
            {showBenefitForm ? 'Cancel' : '+ New benefit'}
          </button>
        </div>

        {showBenefitForm && (
          <NewBenefitForm
            onCreated={() => {
              setShowBenefitForm(false)
              load()
            }}
          />
        )}

        {benefits === null ? (
          <p className="empty-state">Loading…</p>
        ) : benefits.length === 0 ? (
          <p className="empty-state">No benefits in the catalog yet.</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Category</th>
                  <th>Description</th>
                  <th>Active</th>
                </tr>
              </thead>
              <tbody>
                {benefits.map((b) => (
                  <tr key={b.id}>
                    <td>{b.name}</td>
                    <td>{BENEFIT_CATEGORY_LABELS[b.category]}</td>
                    <td>{b.description || '—'}</td>
                    <td>{b.active ? 'Yes' : 'No'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="detail-card">
        <div className="page-header">
          <h2>Elections</h2>
          <button type="button" className="btn-primary" onClick={() => setShowElectionForm((v) => !v)}>
            {showElectionForm ? 'Cancel' : '+ Record election'}
          </button>
        </div>

        {showElectionForm && (
          <NewElectionForm
            benefits={benefits ?? []}
            onCreated={() => {
              setShowElectionForm(false)
              load()
            }}
          />
        )}

        {elections === null ? (
          <p className="empty-state">Loading…</p>
        ) : elections.length === 0 ? (
          <p className="empty-state">No elections recorded yet.</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Employee</th>
                  <th>Benefit</th>
                  <th>Status</th>
                  <th>Effective date</th>
                </tr>
              </thead>
              <tbody>
                {elections.map((el) => {
                  return (
                    <tr key={el.id}>
                      <td>{el.employee_name}</td>
                      <td>{benefitById.get(el.benefit)?.name ?? `#${el.benefit}`}</td>
                      <td>
                        <span className="status-badge">{BENEFITS_ELECTION_STATUS_LABELS[el.status]}</span>
                      </td>
                      <td>{el.effective_date ?? '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}

function NewBenefitForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState('')
  const [category, setCategory] = useState<BenefitCategory>('medical')
  const [description, setDescription] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await api.post('/benefits/', { name, category, description })
      onCreated()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Create failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit}>
      <label>
        Name
        <input value={name} onChange={(e) => setName(e.target.value)} required />
      </label>
      <label>
        Category
        <select value={category} onChange={(e) => setCategory(e.target.value as BenefitCategory)}>
          {CATEGORY_OPTIONS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Description
        <input value={description} onChange={(e) => setDescription(e.target.value)} />
      </label>

      {error && <p className="form-error">{error}</p>}

      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Creating…' : 'Create benefit'}
        </button>
      </div>
    </form>
  )
}

function NewElectionForm({
  benefits, onCreated,
}: { benefits: Benefit[]; onCreated: () => void }) {
  const [employee, setEmployee] = useState<number | null>(null)
  const [benefit, setBenefit] = useState<number | ''>('')
  const [status, setStatus] = useState<BenefitsElectionStatus>('enrolled')
  const [effectiveDate, setEffectiveDate] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!employee || !benefit) {
      setError('Employee and benefit are required.')
      return
    }
    setSubmitting(true)
    try {
      await api.post('/benefits-elections/', {
        employee, benefit, status, effective_date: effectiveDate || null,
      })
      onCreated()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Create failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit}>
      <EmployeeAsyncSelect value={employee} onChange={setEmployee} required />
      <label>
        Benefit
        <select value={benefit} onChange={(e) => setBenefit(e.target.value ? Number(e.target.value) : '')} required>
          <option value="">— Select —</option>
          {benefits.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Status
        <select value={status} onChange={(e) => setStatus(e.target.value as BenefitsElectionStatus)}>
          {ELECTION_STATUS_OPTIONS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Effective date
        <input type="date" value={effectiveDate} onChange={(e) => setEffectiveDate(e.target.value)} />
      </label>

      {error && <p className="form-error">{error}</p>}

      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Saving…' : 'Record election'}
        </button>
      </div>
    </form>
  )
}
