const API_BASE = '/api/v1'

function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

export class ApiError extends Error {
  status: number
  body: unknown

  constructor(status: number, body: unknown) {
    super(typeof body === 'object' && body && 'detail' in body ? String((body as { detail: unknown }).detail) : `Request failed (${status})`)
    this.status = status
    this.body = body
  }
}

/** Global "session is gone" hook (brief D3). DRF's SessionAuthentication
 * answers a dead/expired session with **403** ("Authentication credentials
 * were not provided"), not 401 — the same status a real permission denial
 * uses. So: a 401 is always treated as session-lost; a 403 triggers one
 * cheap re-probe of /auth/me/ (deduplicated across concurrent requests) and
 * only if *that* fails do we declare the session gone. The AuthProvider
 * then clears the user and RequireAuth bounces to /login once, instead of
 * every page showing its own "Failed to load …". Login/me/csrf themselves
 * are exempt — there, an auth failure just means "not signed in yet". */
type UnauthorizedHandler = (info: { path: string }) => void
let unauthorizedHandler: UnauthorizedHandler | null = null
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler
}
const UNAUTHORIZED_EXEMPT = ['/auth/login/', '/auth/me/', '/auth/csrf/']
let sessionProbe: Promise<boolean> | null = null
function probeSessionAlive(): Promise<boolean> {
  if (!sessionProbe) {
    sessionProbe = fetch(`${API_BASE}/auth/me/`, { credentials: 'same-origin' })
      .then((r) => r.ok)
      .catch(() => false)
      .finally(() => {
        sessionProbe = null
      })
  }
  return sessionProbe
}

let csrfCookieEnsured = false

async function ensureCsrfCookie(): Promise<void> {
  if (csrfCookieEnsured && getCookie('csrftoken')) return
  await fetch(`${API_BASE}/auth/csrf/`, { credentials: 'same-origin' })
  csrfCookieEnsured = true
}

/** DRF's CursorPagination returns absolute next/previous URLs. Reduced to
 * a same-origin path+query so they still route through the Vite proxy
 * regardless of what host Django's request.build_absolute_uri() used. */
function toRequestPath(pathOrUrl: string): string {
  if (!pathOrUrl.startsWith('http')) return pathOrUrl
  const url = new URL(pathOrUrl)
  return `${url.pathname}${url.search}`
}

async function request<T>(pathOrUrl: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase()
  const isMutating = method !== 'GET' && method !== 'HEAD'
  if (isMutating) await ensureCsrfCookie()

  const headers = new Headers(options.headers)
  if (isMutating) {
    const token = getCookie('csrftoken')
    if (token) headers.set('X-CSRFToken', token)
  }
  // FormData bodies (file uploads) must NOT get an explicit Content-Type —
  // the browser sets multipart/form-data with the correct boundary itself;
  // overriding it here would corrupt the upload.
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const path = toRequestPath(pathOrUrl)
  const url = path.startsWith('/api/') ? path : `${API_BASE}${path}`

  const response = await fetch(url, { ...options, method, headers, credentials: 'same-origin' })

  if (response.status === 204) return undefined as T

  const contentType = response.headers.get('content-type') ?? ''
  const body = contentType.includes('application/json') ? await response.json() : await response.text()

  if (
    (response.status === 401 || response.status === 403) &&
    unauthorizedHandler &&
    !UNAUTHORIZED_EXEMPT.some((p) => path.endsWith(p))
  ) {
    const gone = response.status === 401 ? true : !(await probeSessionAlive())
    if (gone) unauthorizedHandler({ path })
  }
  if (!response.ok) throw new ApiError(response.status, body)
  return body as T
}

export const api = {
  get: <T>(pathOrUrl: string, options: RequestInit = {}) => request<T>(pathOrUrl, options),
  post: <T>(path: string, data?: unknown) => request<T>(path, { method: 'POST', body: data !== undefined ? JSON.stringify(data) : undefined }),
  patch: <T>(path: string, data?: unknown) => request<T>(path, { method: 'PATCH', body: data !== undefined ? JSON.stringify(data) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  // For multipart file uploads (e.g. policies.Policy.source_file) — pass a
  // FormData directly, never JSON.stringify'd.
  postForm: <T>(path: string, data: FormData) => request<T>(path, { method: 'POST', body: data }),
  patchForm: <T>(path: string, data: FormData) => request<T>(path, { method: 'PATCH', body: data }),
}

export interface Paginated<T> {
  results: T[]
  next: string | null
  previous: string | null
}

/** Follows DRF's cursor pagination to completion. Fine at the hundreds-of-
 * rows scale Sprint 3's synthetic dataset targets; a production-scale
 * employee list should switch to server-side paging with a real "load
 * more" / virtualized table instead of accumulating every page client-side. */
export async function fetchAllPages<T>(path: string): Promise<T[]> {
  const results: T[] = []
  let next: string | null = path
  while (next) {
    const page: Paginated<T> = await api.get<Paginated<T>>(next)
    results.push(...page.results)
    next = page.next
  }
  return results
}
