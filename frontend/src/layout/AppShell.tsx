import { NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import {
  Home,
  Dumbbell,
  Apple,
  ClipboardList,
  TrendingUp,
  Sparkles,
  Settings as SettingsIcon,
  Flame,
  Plus,
  LogOut,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useAuth } from '../auth/useAuth'
import { insights } from '../api'
import { Logo } from '../components/Logo'
import { ThemeToggle } from '../components/ThemeToggle'
import { Button } from '../components/ui'
import { QuickAddSheet } from '../components/QuickAddSheet'

interface NavItem {
  to: string
  label: string
  Icon: LucideIcon
  primary: boolean // shown in the mobile bottom nav
}

const NAV: NavItem[] = [
  { to: '/', label: 'Today', Icon: Home, primary: true },
  { to: '/workout', label: 'Workout', Icon: Dumbbell, primary: true },
  { to: '/nutrition', label: 'Nutrition', Icon: Apple, primary: true },
  { to: '/programs', label: 'Programs', Icon: ClipboardList, primary: true },
  { to: '/performance', label: 'Progress', Icon: TrendingUp, primary: true },
  { to: '/insights', label: 'Coach', Icon: Sparkles, primary: false },
  { to: '/settings', label: 'Settings', Icon: SettingsIcon, primary: false },
]

function StreakChip() {
  const [streak, setStreak] = useState<number | null>(null)
  useEffect(() => {
    let alive = true
    insights
      .streaks()
      .then((s) => alive && setStreak(s.any_streak))
      .catch(() => alive && setStreak(null))
    return () => {
      alive = false
    }
  }, [])
  if (streak === null || streak < 1) return null
  return (
    <span className="streak-chip" title={`${streak}-day logging streak`}>
      <Flame size={15} aria-hidden="true" />
      {streak}
    </span>
  )
}

export function AppShell() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [quickOpen, setQuickOpen] = useState(false)

  const initials = (user?.username ?? 'U').trim().charAt(0).toUpperCase() || 'U'

  // The global quick-add FAB would overlap the Coach composer's send button,
  // so hide it on that route. Routes/behavior are otherwise unchanged.
  const showFab = location.pathname !== '/insights'

  async function onLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="shell">
      {/* Desktop sidebar */}
      <aside className="sidebar">
        <div className="sidebar__brand">
          <Logo />
        </div>
        <Button
          className="sidebar__quick"
          gradient
          block
          leftIcon={<Plus size={18} aria-hidden="true" />}
          onClick={() => setQuickOpen(true)}
        >
          Quick add
        </Button>
        <nav className="sidebar__nav" aria-label="Primary">
          {NAV.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) => `sidebar__item${isActive ? ' is-active' : ''}`}
            >
              <span className="sidebar__indicator" aria-hidden="true" />
              <Icon className="nav-ico" size={20} aria-hidden="true" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar__footer">
          <div className="profile">
            <span className="avatar" aria-hidden="true">
              {initials}
            </span>
            <div className="profile__meta">
              <span className="profile__name">{user?.username ?? 'Signed in'}</span>
              <span className="profile__sub">FitPath member</span>
            </div>
            <ThemeToggle />
          </div>
          <Button
            variant="ghost"
            size="sm"
            block
            leftIcon={<LogOut size={16} aria-hidden="true" />}
            onClick={onLogout}
          >
            Log out
          </Button>
        </div>
      </aside>

      <div className="shell__body">
        {/* Mobile top bar */}
        <header className="topbar">
          <Logo />
          <div className="topbar__actions">
            <StreakChip />
            <ThemeToggle />
            <NavLink to="/insights" className="icon-btn" aria-label="Coach">
              <Sparkles size={18} aria-hidden="true" />
            </NavLink>
            <NavLink to="/settings" className="icon-btn" aria-label="Settings">
              <SettingsIcon size={18} aria-hidden="true" />
            </NavLink>
          </div>
        </header>

        <main className="content">
          <Outlet />
        </main>
      </div>

      {/* Mobile bottom nav */}
      <nav className="bottom-nav" aria-label="Primary">
        {NAV.filter((n) => n.primary).map(({ to, label, Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) => `bottom-nav__item${isActive ? ' is-active' : ''}`}
          >
            <Icon className="nav-ico" size={22} aria-hidden="true" />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Prominent global quick-add (floats above the mobile bottom nav).
          Hidden on Coach to avoid overlapping the chat send button. */}
      {showFab && (
        <button className="quick-fab" onClick={() => setQuickOpen(true)} aria-label="Quick add">
          <Plus size={24} strokeWidth={2.4} aria-hidden="true" />
        </button>
      )}

      <QuickAddSheet open={quickOpen} onClose={() => setQuickOpen(false)} />
    </div>
  )
}
