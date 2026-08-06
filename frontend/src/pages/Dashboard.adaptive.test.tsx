import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Dashboard } from './Dashboard'
import * as api from '../api'
import { makeEnvelope, makeProfile, makeRecommendationsToday, makeWorkoutBlock, makeExerciseRec } from '../test/adaptiveFixtures'

function renderDashboard() {
  return render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>,
  )
}

describe('Dashboard — "Built from your history" adaptive card', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(api.recommendations, 'today').mockResolvedValue(makeRecommendationsToday())
    vi.spyOn(api.profile, 'get').mockResolvedValue(makeProfile())
    vi.spyOn(api.activities, 'list').mockResolvedValue({ items: [] })
    vi.spyOn(api.water, 'list').mockResolvedValue({ items: [] })
    vi.spyOn(api.stepsApi, 'list').mockResolvedValue({ items: [] })
  })

  it('surfaces the workout action summary + best meal pick from the adaptive envelope', async () => {
    vi.spyOn(api.recommendations, 'adaptive').mockResolvedValue(makeEnvelope())
    renderDashboard()

    expect(await screen.findByText('Built from your history')).toBeInTheDocument()
    // Workout action summary + delta chip.
    expect(screen.getByText('Increase load')).toBeInTheDocument()
    expect(screen.getByText('+2.5 kg')).toBeInTheDocument()
    // Best meal pick surfaced with its reason.
    expect(screen.getByText('Grilled salmon & rice')).toBeInTheDocument()
    expect(screen.getByText(/go-to dinner you've logged 7×/)).toBeInTheDocument()
    // Confidence shows up as quiet metadata, not a loud badge.
    expect(screen.getByText(/High confidence · from your training logs/)).toBeInTheDocument()
  })

  it('renders a rest-day summary without breaking when the athlete is resting', async () => {
    vi.spyOn(api.recommendations, 'adaptive').mockResolvedValue(
      makeEnvelope({ workout: makeWorkoutBlock({ rest_day: true, exercises: [], name: null, program_day_id: null, reason: 'Scheduled rest day — prioritise sleep, hydration and protein to recover.' }) }),
    )
    renderDashboard()
    expect(await screen.findByText('Built from your history')).toBeInTheDocument()
    expect(screen.getByText('Rest day')).toBeInTheDocument()
  })

  it('maps a layoff hold to a "resume" summary', async () => {
    vi.spyOn(api.recommendations, 'adaptive').mockResolvedValue(
      makeEnvelope({
        workout: makeWorkoutBlock({
          exercises: [makeExerciseRec({ action: 'hold', suggested_weight: 57.5, change: { weight_delta_kg: 0, reps_delta: 0, direction: 'flat' }, reason: 'Resuming after 12 days off — starting a touch lighter at 57.5 kg for 6 reps. Not a stall, just easing back in.' })],
        }),
      }),
    )
    renderDashboard()
    expect(await screen.findByText('Ease back in')).toBeInTheDocument()
  })

  it('shows a small unavailable state (without breaking the dashboard) when adaptive fails', async () => {
    vi.spyOn(api.recommendations, 'adaptive').mockRejectedValue(new api.ApiError(500, 'boom'))
    renderDashboard()
    // Legacy dashboard still renders …
    expect(await screen.findByText('Built from your history')).toBeInTheDocument()
    expect(screen.getByText("Today's workout")).toBeInTheDocument()
    // … and the adaptive block degrades to an explicit unavailable note.
    expect(screen.getByText(/History-based recommendations are unavailable/)).toBeInTheDocument()
  })
})
