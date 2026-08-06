import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ThemeProvider } from './ThemeProvider'
import { ThemeToggle } from '../components/ThemeToggle'

function renderToggle() {
  return render(
    <ThemeProvider>
      <ThemeToggle />
    </ThemeProvider>,
  )
}

describe('ThemeToggle + ThemeProvider (dark-mode persistence)', () => {
  beforeEach(() => {
    window.localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
  })

  it('defaults to light and toggles to dark, persisting the choice', async () => {
    renderToggle()

    // matchMedia is stubbed to "not dark", so a fresh visitor starts light.
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(window.localStorage.getItem('fitpath-theme')).toBe('light')

    await userEvent.click(screen.getByRole('button', { name: /switch to dark mode/i }))

    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(window.localStorage.getItem('fitpath-theme')).toBe('dark')
    // The affordance flips to offer the reverse action.
    expect(screen.getByRole('button', { name: /switch to light mode/i })).toBeInTheDocument()
  })

  it('restores a persisted dark theme on next mount', () => {
    window.localStorage.setItem('fitpath-theme', 'dark')

    renderToggle()

    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(screen.getByRole('button', { name: /switch to light mode/i })).toBeInTheDocument()
  })
})
