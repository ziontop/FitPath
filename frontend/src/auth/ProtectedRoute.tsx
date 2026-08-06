import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from './useAuth'
import { SpinnerCenter } from '../components/ui'

/** Guards nested routes: waits for the auth check, then redirects guests to /login. */
export function ProtectedRoute() {
  const { status } = useAuth()
  const location = useLocation()

  if (status === 'loading') {
    return (
      <div className="app-loading">
        <SpinnerCenter label="Loading FitPath" />
      </div>
    )
  }
  if (status === 'guest') {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return <Outlet />
}
