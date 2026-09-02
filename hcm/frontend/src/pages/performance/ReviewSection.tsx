import { useState, type FormEvent } from 'react'
import { api } from '../../api/client'
import { useMutation } from '../../api/hooks'
import type { AgreementElement, PerformanceAgreement } from '../../api/types'

/** Mid-year (Q2) and final (Q4) review, PC-2. The static KPI table
 * (ScorecardTable) never changes once contracted; this is the part that
 * changes every review cycle -- target-check notes for Q2, ratings for Q4 --
 * editable by either party (matching the "reviewed together" pattern
 * contracting already uses) only while that stage's *_open status holds;
 * AgreementElementSerializer.validate() is the real gate, this just avoids
 * offering an edit the API would refuse. */
export function ReviewSection({ agreement, onChanged }: { agreement: PerformanceAgreement; onChanged: () => void }) {
  const stage = agreement.current_stage
  if (stage === 'contracting') return null
  // The employee's own fields are only editable while the stage sits at its
  // *_open status; the Head's comment stays editable one status longer --
  // through *_employee_signed -- so the Head can add it after the employee
  // signs but before the Head signs (mirrors serializers_agreements.py).
  const notYetOpenStatus = stage === 'midyear' ? 'agreed' : 'midyear_signed'
  const openStatus = stage === 'midyear' ? 'midyear_open' : 'final_open'
  const employeeSignedStatus = stage === 'midyear' ? 'midyear_employee_signed' : 'final_employee_signed'
  const editable = agreement.status === openStatus
  const headEditable = editable || agreement.status === employeeSignedStatus
  const elements = [...agreement.elements].sort(
    (a, b) => a.section_order - b.section_order || a.order - b.order,
  )

  return (
    <section className="detail-card">
      <h2>{stage === 'midyear' ? 'Mid-year review (Q2)' : 'Final assessment (Q4)'}</h2>
      {agreement.status === notYetOpenStatus && <p className="hint-text">This review hasn’t opened yet.</p>}
      {!headEditable && agreement.status !== notYetOpenStatus && (
        <p className="hint-text">This review is signed — amend the agreement (with a reason) to reopen it.</p>
      )}
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Key performance indicator</th>
              {stage === 'midyear' ? (
                <>
                  <th>Target check</th>
                  <th>Employee comment</th>
                  <th>Head comment</th>
                </>
              ) : (
                <>
                  <th>Rating</th>
                  <th>Score</th>
                  <th>Employee comment</th>
                  <th>Head comment</th>
                </>
              )}
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {elements.map((element) => (
              <tr key={element.id}>
                <td>{element.kpi_title}</td>
                {stage === 'midyear' ? (
                  <>
                    <TextCell element={element} field="q2_target_note" editable={editable} onChanged={onChanged} />
                    <TextCell
                      element={element} field="q2_employee_comment" editable={editable} onChanged={onChanged}
                    />
                    <TextCell
                      element={element} field="q2_head_comment" editable={headEditable} onChanged={onChanged}
                    />
                  </>
                ) : (
                  <>
                    <RatingCell element={element} editable={editable} onChanged={onChanged} />
                    <td>{element.score ?? '—'}</td>
                    <TextCell
                      element={element} field="final_employee_comment" editable={editable} onChanged={onChanged}
                    />
                    <TextCell
                      element={element} field="final_head_comment" editable={headEditable} onChanged={onChanged}
                    />
                  </>
                )}
                <td>
                  <EvidencePanel element={element} onChanged={onChanged} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function TextCell({
  element,
  field,
  editable,
  onChanged,
}: {
  element: AgreementElement
  field: 'q2_target_note' | 'q2_employee_comment' | 'q2_head_comment' | 'final_employee_comment' | 'final_head_comment'
  editable: boolean
  onChanged: () => void
}) {
  const [value, setValue] = useState(element[field])
  const save = useMutation(
    (next: string) => api.patch(`/agreement-elements/${element.id}/`, { [field]: next }),
    { onSuccess: onChanged, errorMessage: 'Could not save that.' },
  )
  if (!editable) return <td>{element[field] || '—'}</td>
  return (
    <td>
      <textarea
        className="review-note"
        rows={2}
        value={value}
        aria-label={field}
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => {
          if (value !== element[field]) void save.run(value)
        }}
      />
      {save.error && <p className="form-error">{save.error}</p>}
    </td>
  )
}

function RatingCell({
  element,
  editable,
  onChanged,
}: {
  element: AgreementElement
  editable: boolean
  onChanged: () => void
}) {
  const save = useMutation(
    (rating: number) => api.patch(`/agreement-elements/${element.id}/`, { final_rating: rating }),
    { onSuccess: onChanged, errorMessage: 'Could not save the rating.' },
  )
  if (!editable) {
    return <td>{element.final_rating ?? '—'}</td>
  }
  return (
    <td>
      <select
        value={element.final_rating ?? ''}
        aria-label={`Rating for ${element.kpi_title}`}
        disabled={save.busy}
        onChange={(e) => void save.run(Number(e.target.value))}
      >
        <option value="">—</option>
        {[1, 2, 3, 4, 5].map((n) => (
          <option key={n} value={n}>
            {n}
          </option>
        ))}
      </select>
      {save.error && <p className="form-error">{save.error}</p>}
    </td>
  )
}

function EvidencePanel({
  element,
  onChanged,
}: {
  element: AgreementElement
  onChanged: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [kind, setKind] = useState<'link' | 'file'>('link')
  const [url, setUrl] = useState('')
  const [description, setDescription] = useState('')
  const [file, setFile] = useState<File | null>(null)

  const upload = useMutation(
    async () => {
      const form = new FormData()
      form.append('element', String(element.id))
      form.append('kind', kind)
      if (description) form.append('description', description)
      if (kind === 'link') form.append('url', url)
      else if (file) form.append('file', file)
      return api.postForm('/agreement-evidence/', form)
    },
    {
      onSuccess: () => {
        setUrl('')
        setDescription('')
        setFile(null)
        onChanged()
      },
      errorMessage: 'Could not add that evidence.',
    },
  )
  const remove = useMutation(
    (id: number) => api.delete(`/agreement-evidence/${id}/`),
    { onSuccess: onChanged, errorMessage: 'That evidence can no longer be removed — the stage is signed off.' },
  )

  const items = element.evidence_items
  return (
    <div className="evidence-panel">
      <button type="button" className="btn-link" onClick={() => setExpanded((v) => !v)}>
        {items.length > 0 ? `Evidence (${items.length})` : 'No evidence attached'}
      </button>
      {expanded && (
        <div className="evidence-detail">
          {items.length > 0 && (
            <ul className="evidence-list">
              {items.map((item) => (
                <li key={item.id}>
                  {item.kind === 'link' ? (
                    <a href={item.url} target="_blank" rel="noreferrer">
                      {item.description || item.url}
                    </a>
                  ) : (
                    <a href={item.download_url ?? undefined}>{item.description || 'Download'}</a>
                  )}
                  {item.added_after_signoff && <span className="hint-text"> (added after sign-off)</span>}
                  <button type="button" className="btn-link" onClick={() => void remove.run(item.id)}>
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
          <form
            className="inline-form"
            onSubmit={(event: FormEvent) => {
              event.preventDefault()
              void upload.run()
            }}
          >
            <select value={kind} onChange={(e) => setKind(e.target.value as 'link' | 'file')}>
              <option value="link">Link (OneDrive / Teams / SharePoint)</option>
              <option value="file">Upload a file</option>
            </select>
            {kind === 'link' ? (
              <input
                type="url" placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} required
              />
            ) : (
              <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
            )}
            <input
              placeholder="Description (optional)" value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
            <button type="submit" className="btn-secondary" disabled={upload.busy}>
              {upload.busy ? 'Adding…' : 'Add'}
            </button>
          </form>
          {upload.error && <p className="form-error">{upload.error}</p>}
          {remove.error && <p className="form-error">{remove.error}</p>}
        </div>
      )}
    </div>
  )
}
