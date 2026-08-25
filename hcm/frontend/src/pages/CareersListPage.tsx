import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchAllPages } from '../api/client'
import type { PublicPosting } from '../api/types'

/** Genuinely public -- no login, no session, no AuthProvider gating (design
 * spec §5.2). Rendered outside RequireAuth in App.tsx, sibling to /login. */
export function CareersListPage() {
  const [postings, setPostings] = useState<PublicPosting[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchAllPages<PublicPosting>('/careers/postings/')
      .then(setPostings)
      .catch(() => setError('Failed to load open positions. Please try again shortly.'))
  }, [])

  return (
    <div className="page" style={{ maxWidth: 800, margin: '0 auto' }}>
      <div className="page-header">
        <h1>Careers</h1>
      </div>
      <p className="hint-text">Current openings. Select a role below to view details and apply.</p>

      {error && <p className="form-error">{error}</p>}
      {postings === null ? (
        <p className="empty-state">Loading…</p>
      ) : postings.length === 0 ? (
        <p className="empty-state">No open positions right now — please check back later.</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {postings.map((posting) => (
            <Link
              key={posting.id}
              to={`/careers/${posting.id}`}
              className="detail-card"
              style={{ display: 'block', textDecoration: 'none', color: 'inherit' }}
            >
              <strong>{posting.title}</strong>
              <p className="hint-text" style={{ margin: '4px 0 0' }}>
                {posting.department} · {posting.location}
                {posting.occupational_level ? ` · ${posting.occupational_level}` : ''}
              </p>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
