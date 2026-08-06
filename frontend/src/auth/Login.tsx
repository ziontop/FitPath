import './Auth.css'
import { useId, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { AlertCircle, Apple, Dumbbell, Eye, EyeOff, Lock, TrendingUp, User } from 'lucide-react'
import { useAuth } from './useAuth'
import { ApiError } from '../api'
import { Button, Card, Field } from '../components/ui'
import { Logo } from '../components/Logo'

interface LocationState {
  from?: string
}

export function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const idField = useId()
  const pwField = useId()

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await login({ identifier, password })
      const dest = (location.state as LocationState | null)?.from ?? '/'
      navigate(dest, { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Login failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-shell">
      <div className="auth-split">
        <aside className="auth-brand" aria-hidden="true">
          <div className="auth-brand__bg" />
          <div className="auth-brand__logo">
            <Logo size={40} />
          </div>
          <div className="auth-brand__body">
            <span className="auth-brand__eyebrow">Train with intent</span>
            <h2 className="auth-brand__headline">Your whole fitness journey, one path.</h2>
            <p className="auth-brand__tagline">
              Adaptive programs, smart nutrition targets, and daily rings that keep you moving toward your goals.
            </p>
            <ul className="auth-brand__features">
              <li className="auth-brand__feature">
                <span className="auth-brand__feature-ic">
                  <Dumbbell size={20} />
                </span>
                Programs that progress with you
              </li>
              <li className="auth-brand__feature">
                <span className="auth-brand__feature-ic">
                  <Apple size={20} />
                </span>
                Smart calorie &amp; macro targets
              </li>
              <li className="auth-brand__feature">
                <span className="auth-brand__feature-ic">
                  <TrendingUp size={20} />
                </span>
                Track every rep, step, and PR
              </li>
            </ul>
          </div>
          <p className="auth-brand__foot">Build the habit. Trust the process.</p>
        </aside>

        <main className="auth-main">
          <div className="auth-panel">
            <div className="auth-card__logo">
              <Logo />
            </div>
            <Card variant="feature" className="auth-card">
              <header className="auth-head">
                <h1 className="auth-title">Welcome back</h1>
                <p className="auth-sub">Log in to keep your streak alive.</p>
              </header>

              {error ? (
                <div className="auth-alert" role="alert">
                  <AlertCircle className="auth-alert__icon" size={18} aria-hidden="true" />
                  <span>{error}</span>
                </div>
              ) : null}

              <form className="auth-form" onSubmit={onSubmit} noValidate>
                <Field label="Email or username" htmlFor={idField} required>
                  <div className="auth-control">
                    <span className="auth-control__icon">
                      <User size={18} aria-hidden="true" />
                    </span>
                    <input
                      id={idField}
                      className="input auth-control__input"
                      name="identifier"
                      autoComplete="username"
                      value={identifier}
                      onChange={(e) => setIdentifier(e.target.value)}
                      required
                    />
                  </div>
                </Field>

                <Field label="Password" htmlFor={pwField} required>
                  <div className="auth-control">
                    <span className="auth-control__icon">
                      <Lock size={18} aria-hidden="true" />
                    </span>
                    <input
                      id={pwField}
                      className="input auth-control__input auth-control__input--pw"
                      name="password"
                      type={showPassword ? 'text' : 'password'}
                      autoComplete="current-password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                    />
                    <button
                      type="button"
                      className="auth-control__toggle"
                      onClick={() => setShowPassword((s) => !s)}
                      aria-pressed={showPassword}
                      aria-controls={pwField}
                    >
                      {showPassword ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}
                      <span className="visually-hidden">{showPassword ? 'Hide password' : 'Show password'}</span>
                    </button>
                  </div>
                </Field>

                <Button type="submit" size="lg" block loading={loading} className="auth-submit">
                  Log in
                </Button>
              </form>

              <p className="auth-switch">
                New to FitPath? <Link to="/register">Create an account</Link>
              </p>
            </Card>
          </div>
        </main>
      </div>
    </div>
  )
}
