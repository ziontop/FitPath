import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { Settings } from './Settings'
import { AuthProvider } from '../auth/AuthProvider'
import { ThemeProvider } from '../theme/ThemeProvider'
import { ToastProvider } from '../components/ui'
import * as api from '../api'
import { appleHealth, appleHealthTokens } from '../api/endpoints'
import type { Profile } from '../api'

const profile: Profile = {
  name: 'Zina',
  sex: 'female',
  age: 24,
  height_cm: 168,
  weight_kg: 62,
  activity_level: 'moderate',
  goal: 'maintain',
  training_goal: 'hypertrophy',
  experience_level: 'intermediate',
  days_per_week: 4,
  equipment: 'full_gym',
  units: 'metric',
  wake_time: '07:00',
  water_goal_ml: 2500,
  step_goal: 8000,
  exercise_goal_min: 45,
}

function renderSettings() {
  return render(
    <MemoryRouter>
      <ToastProvider>
        <ThemeProvider>
          <AuthProvider>
            <Settings />
          </AuthProvider>
        </ThemeProvider>
      </ToastProvider>
    </MemoryRouter>,
  )
}

describe('Settings Apple Health card', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    Object.defineProperty(window, 'matchMedia', { writable: true, value: vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }) })
    vi.spyOn(api.auth, 'me').mockResolvedValue({ id: 1, email: 'z@fit.dev', username: 'zina', created_at: '2026-01-01T00:00:00' })
    vi.spyOn(api.profile, 'get').mockResolvedValue(profile)
    vi.spyOn(appleHealth, 'imports').mockResolvedValue({ items: [] })
    vi.spyOn(appleHealthTokens, 'list').mockResolvedValue({ items: [] })
  })

  it('explains web HealthKit limits and previews before importing the retained file', async () => {
    const file = new File(['<HealthData />'], 'export.xml', { type: 'text/xml' })
    const previewSpy = vi.spyOn(appleHealth, 'preview').mockResolvedValue({
      filename: 'export.xml',
      date_range: { start: '2026-07-14', end: '2026-07-14' },
      counts_by_type: { steps: 1, weight: 1, sleep: 1, water: 1, workouts: 1 },
      units_detected: { weight: ['kg'] },
      samples: {},
      warnings: ['Synthetic warning'],
    })
    const importSpy = vi.spyOn(appleHealth, 'import').mockResolvedValue({
      batch_id: 42,
      source: 'export',
      status: 'completed',
      date_range: { start: '2026-07-14', end: '2026-07-14' },
      results: {
        steps: { inserted: 1, updated: 0, skipped: 0, invalid: 0, conflict: 0 },
        weight: { inserted: 1, updated: 0, skipped: 0, invalid: 0, conflict: 0 },
        sleep: { inserted: 1, updated: 0, skipped: 0, invalid: 0, conflict: 0 },
        water: { inserted: 1, updated: 0, skipped: 0, invalid: 0, conflict: 0 },
        workouts: { inserted: 1, updated: 0, skipped: 0, invalid: 0, conflict: 0 },
      },
      totals: { inserted: 5, updated: 0, skipped: 0, invalid: 0, conflict: 0 },
    })
    renderSettings()

    expect(await screen.findByText(/cannot read HealthKit directly/i)).toBeInTheDocument()
    await userEvent.upload(screen.getByLabelText(/Apple Health export file/i), file)

    expect(previewSpy).toHaveBeenCalledWith(file)
    expect(await screen.findByText(/re-uploaded for import/i)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /import selected/i }))

    await waitFor(() => expect(importSpy).toHaveBeenCalledWith(file, ['steps', 'weight', 'sleep', 'water', 'workouts']))
    expect(await screen.findByText(/preserved manual edits/i)).toBeInTheDocument()
  })

  it('shows a newly generated Shortcut token once and listed tokens without secrets', async () => {
    vi.spyOn(appleHealthTokens, 'create').mockResolvedValue({
      id: 1,
      name: 'iPhone Shortcut',
      prefix: 'fpk_demo1234',
      token: 'fpk_demo1234_secretShownOnce',
      created_at: '2026-01-01T00:00:00',
      last_used_at: null,
      expires_at: null,
      revoked_at: null,
    })
    renderSettings()

    await userEvent.click(await screen.findByRole('button', { name: /generate token/i }))

    expect(await screen.findByText(/shown once/i)).toBeInTheDocument()
    expect(screen.getByText('fpk_demo1234_secretShownOnce')).toBeInTheDocument()
    expect(screen.getByText(/requires HTTPS/i)).toBeInTheDocument()
  })
})
