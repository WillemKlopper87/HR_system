import { createContext } from 'react'
import type { MeResponse } from '../api/types'

export interface AuthContextValue {
  user: MeResponse | null
  loading: boolean
  sessionExpired: boolean
  explicitLogout: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  hasRole: (role: string) => boolean
}

export const AuthContext = createContext<AuthContextValue | null>(null)
