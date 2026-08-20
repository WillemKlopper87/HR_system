import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useApiQuery, useMutation } from '../api/hooks'
import type { Notification } from '../api/types'

const POLL_INTERVAL_MS = 30_000

/** H3: the one place every notify() consumer (PC reminders, comp approvals,
 * review launch, policy publish, the liveness review queue, EE sign-off)
 * ends up visible to the person it's for. Polls rather than pushes — no
 * websocket layer exists in this app, and a 30s poll is more than fast
 * enough for "someone should eventually see this", not a live chat. */
export function NotificationBell() {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  const { data: countData, reload: reloadCount, setData: setCountData } = useApiQuery<{ count: number }>(
    () => api.get<{ count: number }>('/notifications/unread-count/'),
    [],
  )
  const { data: list, reload: reloadList, setData: setList } = useApiQuery<{ results: Notification[] }>(
    () => api.get<{ results: Notification[] }>('/notifications/'),
    [],
    { enabled: open },
  )

  useEffect(() => {
    const id = setInterval(reloadCount, POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [reloadCount])

  useEffect(() => {
    if (!open) return
    const onClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [open])

  const markRead = useMutation(
    (id: number) => api.post(`/notifications/${id}/mark-read/`),
    { onSuccess: () => { reloadCount(); reloadList() } },
  )

  /** Clicking an item both marks it read *and* navigates away in the same
   * handler, fire-and-forget (`onSuccess` reconciling from the server is
   * the belt to this belt-and-braces fix, not the only thing holding it
   * up). Previously the badge/list only updated once that POST's own
   * `reloadCount`/`reloadList` round trip happened to finish before
   * whatever read them next -- unbounded, and lost under any real
   * latency (slow network, a busy server), which is exactly what made
   * "click it, badge doesn't move" reproducible. Updating local state
   * optimistically here means the UI is correct the instant the user
   * acts, with zero dependency on that request's timing; the mutation
   * still runs in the background to persist it, and either outcome
   * (`onSuccess` above, or the resync below on failure) reconciles with
   * the server so a wrong guess never lingers past one round trip. */
  const markReadOptimistic = (id: number) => {
    setCountData((c) => (c ? { count: Math.max(0, c.count - 1) } : c))
    setList((l) => (l ? { results: l.results.map((item) => (item.id === id ? { ...item, read_at: new Date().toISOString() } : item)) } : l))
    void markRead.run(id).then((result) => {
      if (result === undefined) { reloadCount(); reloadList() }
    })
  }

  const markAllRead = useMutation(
    () => api.post('/notifications/mark-all-read/'),
    { onSuccess: () => { reloadCount(); reloadList() } },
  )

  const count = countData?.count ?? 0

  return (
    <div className="notification-bell" ref={containerRef}>
      <button
        type="button"
        className="btn-link notification-bell-toggle"
        aria-label={`Notifications${count > 0 ? ` (${count} unread)` : ''}`}
        onClick={() => setOpen((v) => !v)}
      >
        🔔{count > 0 && <span className="notification-badge">{count > 99 ? '99+' : count}</span>}
      </button>
      {open && (
        <div className="notification-dropdown">
          <div className="notification-dropdown-header">
            <span>Notifications</span>
            {count > 0 && (
              <button type="button" className="btn-link" onClick={() => void markAllRead.run()}>
                Mark all read
              </button>
            )}
          </div>
          {list === null && <p className="empty-state">Loading…</p>}
          {list !== null && list.results.length === 0 && <p className="empty-state">No notifications yet.</p>}
          <ul className="notification-list">
            {(list?.results ?? []).map((n) => (
              <li key={n.id} className={n.read_at ? undefined : 'notification-unread'}>
                <button
                  type="button"
                  className="notification-item"
                  onClick={() => {
                    if (!n.read_at) markReadOptimistic(n.id)
                    setOpen(false)
                    if (n.link) navigate(n.link)
                  }}
                >
                  <strong>{n.title}</strong>
                  {n.body && <span className="hint-text">{n.body}</span>}
                  <span className="hint-text">{new Date(n.created_at).toLocaleString()}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
