import { useMemo, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError, fetchAllPages, type Paginated } from '../api/client'
import { useApiQuery } from '../api/hooks'
import { STAGE_LABELS, type Applicant, type ApplicantStage, type Requisition } from '../api/types'

export function ApplicantsPage() {
  const [stageFilter, setStageFilter] = useState<ApplicantStage | ''>('')
  const [search, setSearch] = useState('')
  const [pagePath, setPagePath] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)

  const applicantParams = new URLSearchParams()
  if (stageFilter) applicantParams.set('stage', stageFilter)
  if (search.trim()) applicantParams.set('search', search.trim())
  const applicantPath = `/applicants/${applicantParams.size ? `?${applicantParams.toString()}` : ''}`
  const requestPath = pagePath ?? applicantPath

  const { data: applicantResponse, error: loadError, reload: load } = useApiQuery(
    () => api.get<Paginated<Applicant>>(requestPath).then((page) => ({ requestPath, page })),
    [requestPath],
    { errorMessage: 'Failed to load applicants.' },
  )
  const { data: requisitions } = useApiQuery(
    () => fetchAllPages<Requisition>('/requisitions/'),
    [],
    { errorMessage: 'Failed to load requisitions.' },
  )
  const applicantPage = applicantResponse?.requestPath === requestPath ? applicantResponse.page : null
  const applicants = applicantPage?.results ?? null


  const requisitionById = useMemo(() => new Map((requisitions ?? []).map((r) => [r.id, r])), [requisitions])

  return (
    <div className="page">
      <div className="page-header">
        <h1>Applicants</h1>
        <div className="row-actions">
          <input
            className="search-input"
            type="search"
            placeholder="Search candidates or requisitions…"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPagePath(null)
            }}
          />
          <select
            aria-label="Filter applicants by stage"
            value={stageFilter}
            onChange={(e) => {
              setStageFilter(e.target.value as ApplicantStage | '')
              setPagePath(null)
            }}
          >
            <option value="">All stages</option>
            {Object.entries(STAGE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <button type="button" className="btn-primary" onClick={() => setShowForm((v) => !v)}>
            {showForm ? 'Cancel' : '+ New applicant'}
          </button>
        </div>
      </div>

      {loadError && <p className="form-error">{loadError}</p>}

      {showForm && requisitions && (
        <NewApplicantForm
          requisitions={requisitions}
          onCreated={() => {
            setShowForm(false)
            load()
          }}
        />
      )}

      {applicants === null ? (
        <p className="empty-state">Loading…</p>
      ) : applicants.length === 0 ? (
        <p className="empty-state">No applicants.</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Requisition</th>
                <th>Stage</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {applicants.map((a) => (
                <tr key={a.id}>
                  <td>
                    <Link to={`/applicants/${a.id}`}>
                      {a.first_name} {a.last_name}
                    </Link>
                  </td>
                  <td>{a.email}</td>
                  <td>{requisitionById.get(a.requisition)?.title ?? '—'}</td>
                  <td>
                    <span className="status-badge">{STAGE_LABELS[a.current_stage]}</span>
                  </td>
                  <td>{a.source === 'portal' ? 'Careers site' : 'Internal'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {applicantPage && (applicantPage.previous || applicantPage.next) && (
        <nav className="form-actions" aria-label="Applicant pages">
          <button
            type="button"
            className="btn-secondary"
            disabled={!applicantPage.previous}
            onClick={() => setPagePath(applicantPage.previous)}
          >
            Previous
          </button>
          <button
            type="button"
            className="btn-secondary"
            disabled={!applicantPage.next}
            onClick={() => setPagePath(applicantPage.next)}
          >
            Next
          </button>
        </nav>
      )}
    </div>
  )
}

function NewApplicantForm({
  requisitions, onCreated,
}: { requisitions: Requisition[]; onCreated: () => void }) {
  const [requisition, setRequisition] = useState<number | ''>('')
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [dateOfBirth, setDateOfBirth] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!requisition) {
      setError('Requisition is required.')
      return
    }
    setSubmitting(true)
    try {
      await api.post('/applicants/', {
        requisition, first_name: firstName, last_name: lastName, email, phone, date_of_birth: dateOfBirth,
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
      <label>
        Requisition
        <select value={requisition} onChange={(e) => setRequisition(e.target.value ? Number(e.target.value) : '')} required>
          <option value="">— Select —</option>
          {requisitions.map((r) => (
            <option key={r.id} value={r.id}>
              {r.title}
            </option>
          ))}
        </select>
      </label>
      <label>
        First name
        <input value={firstName} onChange={(e) => setFirstName(e.target.value)} required />
      </label>
      <label>
        Last name
        <input value={lastName} onChange={(e) => setLastName(e.target.value)} required />
      </label>
      <label>
        Email
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
      </label>
      <label>
        Phone
        <input value={phone} onChange={(e) => setPhone(e.target.value)} />
      </label>
      <label>
        Date of birth
        <input type="date" value={dateOfBirth} onChange={(e) => setDateOfBirth(e.target.value)} required />
      </label>

      {error && <p className="form-error">{error}</p>}

      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Adding…' : 'Add applicant'}
        </button>
      </div>
    </form>
  )
}
