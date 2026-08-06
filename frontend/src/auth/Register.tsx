import './Auth.css'
import { useId, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlertCircle, Apple, Dumbbell, Eye, EyeOff, Lock, Mail, TrendingUp, User } from 'lucide-react'
import { useAuth } from './useAuth'
import { ApiError } from '../api'
import { Button, Card, Field } from '../components/ui'
import { Logo } from '../components/Logo'

export function Register() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const emailField = useId()
  const usernameField = useId()
  const pwField = useId()

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }
    setLoading(true)
    try {
      await register({ email, username, password })
      // New users go straight to onboarding to set up their profile.
      navigate('/onboarding', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Registration failed. Please try again.')
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
            <span className="auth-brand__eyebrow">Join FitPath</span>
            <h2 className="auth-brand__headline">Start your journey to stronger.</h2>
            <p className="auth-brand__tagline">
              Create an account to unlock personalised training, nutrition targets, and progress you can actually see.
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
          <p className="auth-brand__foot">Free to start. Yours to keep.</p>
        </aside>

        <main className="auth-main">
          <div className="auth-panel">
            <div className="auth-card__logo">
              <Logo />
            </div>
            <Card variant="feature" className="auth-card">
              <header className="auth-head">
                <h1 className="auth-title">Create your account</h1>
                <p className="auth-sub">Start tracking training &amp; nutrition today.</p>
              </header>

              {error ? (
                <div className="auth-alert" role="alert">
                  <AlertCircle className="auth-alert__icon" size={18} aria-hidden="true" />
                  <span>{error}</span>
                </div>
              ) : null}

              <form className="auth-form" onSubmit={onSubmit} noValidate>
                <Field label="Email" htmlFor={emailField} required>
                  <div className="auth-control">
                    <span className="auth-control__icon">
                      <Mail size={18} aria-hidden="true" />
                    </span>
                    <input
                      id={emailField}
                      className="input auth-control__input"
                      name="email"
                      type="email"
                      autoComplete="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                    />
                  </div>
                </Field>

                <Field label="Username" htmlFor={usernameField} required>
                  <div className="auth-control">
                    <span className="auth-control__icon">
                      <User size={18} aria-hidden="true" />
                    </span>
                    <input
                      id={usernameField}
                      className="input auth-control__input"
                      name="username"
                      autoComplete="username"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      required
                    />
                  </div>
                </Field>

                <Field label="Password" htmlFor={pwField} hint="At least 8 characters." required>
                  <div className="auth-control">
                    <span className="auth-control__icon">
                      <Lock size={18} aria-hidden="true" />
                    </span>
                    <input
                      id={pwField}
                      className="input auth-control__input auth-control__input--pw"
                      name="password"
                      type={showPassword ? 'text' : 'password'}
                      autoComplete="new-password"
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
                  Create account
                </Button>
              </form>

              <p className="auth-switch">
                Already have an account? <Link to="/login">Log in</Link>
              </p>
            </Card>
          </div>
        </main>
      </div>
    </div>
  )
}
