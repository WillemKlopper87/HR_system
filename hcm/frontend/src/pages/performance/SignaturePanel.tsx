import { useState, type FormEvent } from 'react'
import { api } from '../../api/client'
import { useApiQuery, useMutation } from '../../api/hooks'
import type { CanSignResponse, PerformanceAgreement } from '../../api/types'

export function SignaturePanel({
  agreement,
  onChanged,
}: {
  agreement: PerformanceAgreement
  onChanged: () => void
}) {
  const [password, setPassword] = useState('')
  const { data: canSign, reload: reloadCanSign } = useApiQuery<CanSignResponse>(
    () => api.get<CanSignResponse>(`/performance-agreements/${agreement.id}/can-sign/`),
    [agreement.id, agreement.status, agreement.revision],
    { errorMessage: 'Could not check your signing status.' },
  )
  const sign = useMutation(
    (role: 'employee' | 'head') =>
      api.post(`/performance-agreements/${agreement.id}/sign/`, { role, password }),
    {
      onSuccess: () => {
        setPassword('')
        onChanged()
        reloadCanSign()
      },
      errorMessage: 'The signature was not recorded.',
    },
  )

  const signatures = agreement.signatures.filter(
    (s) => s.stage === agreement.current_stage && s.revision === agreement.revision,
  )
  const role: 'employee' | 'head' | null = canSign?.as_employee ? 'employee' : canSign?.as_head ? 'head' : null

  return (
    <section className="detail-card">
      <h2>Signatures</h2>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Signatory</th>
              <th>Name</th>
              <th>Signed</th>
              <th>Method</th>
            </tr>
          </thead>
          <tbody>
            {(['employee', 'head'] as const).map((r) => {
              const signature = signatures.find((s) => s.role === r)
              return (
                <tr key={r}>
                  <td>{r === 'employee' ? 'Individual' : 'Manager (Head / executive)'}</td>
                  <td>
                    {signature
                      ? signature.acting_for_name
                        ? `${signature.signer_name} (acting for ${signature.acting_for_name})`
                        : signature.signer_name
                      : r === 'employee'
                        ? agreement.employee_name
                        : (agreement.head_name ?? '—')}
                  </td>
                  <td>{signature ? new Date(signature.signed_at).toLocaleString() : '— not yet signed —'}</td>
                  <td>{signature ? signature.method_display : ''}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {canSign?.blocked_reason && <p className="form-notice">{canSign.blocked_reason}</p>}
      {sign.error && <p className="form-error">{sign.error}</p>}

      {role && (
        <form
          className="inline-form"
          onSubmit={(event: FormEvent) => {
            event.preventDefault()
            void sign.run(role)
          }}
        >
          <label>
            Confirm your password to sign
            <input
              type="password"
              value={password}
              autoComplete="current-password"
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          <button type="submit" className="btn-primary" disabled={sign.busy || !password}>
            {sign.busy
              ? 'Signing…'
              : role === 'employee'
                ? 'Sign as the individual'
                : canSign?.acting_for_head
                  ? 'Sign as acting Head'
                  : 'Sign as Head'}
          </button>
          <span className="hint-text">
            Your signature is bound to the PDF of this scorecard and recorded in the audit log.
          </span>
        </form>
      )}

      {agreement.documents.length > 0 && (
        <p className="hint-text">
          {agreement.documents.map((doc) => (
            <a key={doc.id} className="btn-link" href={doc.download_url}>
              Download {doc.stage} PDF (rev {doc.revision})
            </a>
          ))}
        </p>
      )}
    </section>
  )
}
