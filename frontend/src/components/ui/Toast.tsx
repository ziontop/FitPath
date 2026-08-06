import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { CheckCircle2, AlertTriangle, Info } from 'lucide-react'

export type ToastKind = 'success' | 'error' | 'info'

interface ToastItem {
  id: number
  message: string
  kind: ToastKind
}

interface ToastContextValue {
  show: (message: string, kind?: ToastKind) => void
  success: (message: string) => void
  error: (message: string) => void
  info: (message: string) => void
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined)

const ICON: Record<ToastKind, ReactNode> = {
  success: <CheckCircle2 size={18} aria-hidden="true" />,
  error: <AlertTriangle size={18} aria-hidden="true" />,
  info: <Info size={18} aria-hidden="true" />,
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const idRef = useRef(0)

  const remove = useCallback((id: number) => {
    setToasts((list) => list.filter((t) => t.id !== id))
  }, [])

  const show = useCallback(
    (message: string, kind: ToastKind = 'success') => {
      const id = ++idRef.current
      setToasts((list) => [...list, { id, message, kind }])
      window.setTimeout(() => remove(id), 2800)
    },
    [remove],
  )

  const value = useMemo<ToastContextValue>(
    () => ({
      show,
      success: (m: string) => show(m, 'success'),
      error: (m: string) => show(m, 'error'),
      info: (m: string) => show(m, 'info'),
    }),
    [show],
  )

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-wrap" role="region" aria-live="polite" aria-label="Notifications">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast--${t.kind}`} onClick={() => remove(t.id)}>
            <span className={`toast__icon toast__icon--${t.kind}`} aria-hidden="true">
              {ICON[t.kind]}
            </span>
            <span>{t.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within a ToastProvider')
  return ctx
}
