import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { AUTH_EXPIRED_EVENT, api, getToken, setToken } from '../lib/api'
import type { User } from '../lib/types'

type AuthState = {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, displayName?: string) => Promise<void>
  logout: () => void
  refresh: () => Promise<void>
  setUser: (user: User) => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setUserState(null)
      setLoading(false)
      return
    }
    try {
      setUserState(await api.me())
    } catch {
      setToken(null)
      setUserState(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
    const onExpired = () => setUserState(null)
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired)
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired)
  }, [refresh])

  const login = useCallback(async (email: string, password: string) => {
    const result = await api.login(email, password)
    setToken(result.access_token)
    setUserState(result.user)
  }, [])

  const register = useCallback(async (email: string, password: string, displayName?: string) => {
    const result = await api.register(email, password, displayName)
    setToken(result.access_token)
    setUserState(result.user)
  }, [])

  const logout = useCallback(() => {
    setToken(null)
    setUserState(null)
  }, [])

  const value = useMemo<AuthState>(
    () => ({ user, loading, login, register, logout, refresh, setUser: setUserState }),
    [user, loading, login, register, logout, refresh],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth doit être utilisé dans AuthProvider')
  return context
}
