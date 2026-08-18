import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, setUnauthorizedHandler } from '../api/client'
import type { MeResponse } from '../api/types'

interface AuthContextValue {
  user: MeResponse | null
  loading: boolean
  /** True after the server answered 401 to an authenticated request —
   * i.e. the session expired or was revoked. Cleared by the next login. */
  sessionExpired: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  hasRole: (role: string) => boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<MeResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [sessionExpired, setSessionExpired] = useState(false)

  useEffect(() => {
    api
      .get<MeResponse>('/auth/me/')
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  // Any 401 from the API (other than login/me) means the session is gone:
  // drop the user so RequireAuth redirects to /login, and remember why so
  // the login page can say "your session expired" instead of a bare form.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser((current) => {
        if (current) setSessionExpired(true)
        return null
      })
    })
    return () => setUnauthorizedHandler(null)
  }, [])

  async function login(username: string, password: string) {
    const me = await api.post<MeResponse>('/auth/login/', { username, password })
    setSessionExpired(false)
    setUser(me)
  }

  async function logout() {
    try {
      await api.post('/auth/logout/')
    } finally {
      setSessionExpired(false)
      setUser(null)
    }
  }

  function hasRole(role: string) {
    return user?.roles.includes(role) ?? false
  }

  return <AuthContext.Provider value={{ user, loading, sessionExpired, login, logout, hasRole }}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
