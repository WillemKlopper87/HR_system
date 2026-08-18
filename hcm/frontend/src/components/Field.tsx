/** Read-only detail field that renders the RBAC field-tier outcome honestly:
 * a key that is *absent* from the API payload means the caller's role may not
 * see it (rbac_audit TieredModelSerializer strips it), so show "Restricted" —
 * never an empty string, which would read as "no value". Shared by the
 * employee and applicant detail pages (H2 dedupe). */
export function Field({ label, obj, field }: { label: string; obj: object; field: string }) {
  const present = field in obj
  const value = (obj as Record<string, unknown>)[field]
  return (
    <div className="detail-field">
      <dt>{label}</dt>
      <dd>
        {!present ? (
          <span className="restricted-badge" title="Not visible to your role">
            Restricted
          </span>
        ) : value === '' || value === null || value === undefined ? (
          '—'
        ) : (
          String(value)
        )}
      </dd>
    </div>
  )
}
