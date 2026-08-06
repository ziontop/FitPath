import { createContext, useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { auth as authApi, ApiError } from '../api'
import type { LoginPayload, RegisterPayload, User } from '../api'

export type AuthStatus = 'loading' | 'authenticated' | 'guest'

interface AuthContextValue {
  user: User | null
  status: AuthStatus
  login: (payload: LoginPayload) => Promise<User>
  register: (payload: RegisterPayload) => Promise<User>
  logout: () => Promise<void>
  refresh: () => Promise<void>
}

// eslint-disable-next-line react-refresh/only-export-components
export const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [status, setStatus] = useState<AuthStatus>('loading')

  const refresh = useCallback(async () => {
    try {
      const me = await authApi.me()
      setUser(me)
      setStatus('authenticated')
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setUser(null)
        setStatus('guest')
      } else {
        // Network / server error — treat as guest so the app is still usable.
        setUser(null)
        setStatus('guest')
      }
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const login = useCallback(async (payload: LoginPayload) => {
    const me = await authApi.login(payload)
    setUser(me)
    setStatus('authenticated')
    return me
  }, [])

  const register = useCallback(async (payload: RegisterPayload) => {
    const me = await authApi.register(payload)
    setUser(me)
    setStatus('authenticated')
    return me
  }, [])

  const logout = useCallback(async () => {
    try {
      await authApi.logout()
    } finally {
      setUser(null)
      setStatus('guest')
    }
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({ user, status, login, register, logout, refresh }),
    [user, status, login, register, logout, refresh],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
