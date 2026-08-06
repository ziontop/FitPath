import { lazy, Suspense } from 'react'
import type { ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { ThemeProvider } from './theme/ThemeProvider'
import { ToastProvider, SpinnerCenter } from './components/ui'
import { AuthProvider } from './auth/AuthProvider'
import { ProtectedRoute } from './auth/ProtectedRoute'
import { Login } from './auth/Login'
import { Register } from './auth/Register'
import { AppShell } from './layout/AppShell'
import { Dashboard } from './pages/Dashboard'
import { Onboarding } from './pages/Onboarding'
import { Workout } from './pages/Workout'
import { Nutrition } from './pages/Nutrition'
import { Programs } from './pages/Programs'
import { Insights } from './pages/Insights'
import { Settings } from './pages/Settings'

// Code-split the chart-heavy Performance page (Recharts) into its own chunk.
const Performance = lazy(() => import('./pages/Performance').then((m) => ({ default: m.Performance })))

const Lazy = ({ children }: { children: ReactNode }) => (
  <Suspense fallback={<div className="app-loading"><SpinnerCenter label="Loading" /></div>}>{children}</Suspense>
)

export default function App() {
  return (
    <ThemeProvider>
      <ToastProvider>
        <AuthProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />

              <Route element={<ProtectedRoute />}>
                <Route path="/onboarding" element={<Onboarding />} />
                <Route element={<AppShell />}>
                  <Route index element={<Dashboard />} />
                  <Route path="/workout" element={<Workout />} />
                  <Route path="/nutrition" element={<Nutrition />} />
                  <Route path="/programs" element={<Programs />} />
                  <Route path="/performance" element={<Lazy><Performance /></Lazy>} />
                  <Route path="/insights" element={<Insights />} />
                  <Route path="/settings" element={<Settings />} />
                </Route>
              </Route>

              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </ToastProvider>
    </ThemeProvider>
  )
}
