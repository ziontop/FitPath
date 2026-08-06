import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { Insights } from './Insights'
import * as api from '../api'
import { makeEnvelope } from '../test/adaptiveFixtures'

const AI_INSIGHTS = { typical_times: {}, top_foods: {}, avg_kcal: {}, avg_macros: {}, meals_per_day: 3.4, days_observed: 21, total_meals: 72 }
const STREAKS = { meal_streak: 5, activity_streak: 2, sleep_streak: 3, water_streak: 1, workout_streak: 4, any_streak: 6 }
const CIRCADIAN = { wake_time: '07:00', first_meal: '08:10', last_meal: '19:20', sleep_target: '23:00', eating_window_hours: 11, tips: [] }

function renderInsights() {
  return render(
    <MemoryRouter>
      <Insights />
    </MemoryRouter>,
  )
}

describe('Insights — "What your history is changing" adaptive summary', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(api.ai, 'insights').mockResolvedValue(AI_INSIGHTS)
    vi.spyOn(api.insights, 'streaks').mockResolvedValue(STREAKS)
    vi.spyOn(api.insights, 'achievements').mockResolvedValue({ badges: [] })
    vi.spyOn(api.insights, 'circadian').mockResolvedValue(CIRCADIAN)
    vi.spyOn(api.recommendations, 'adaptive').mockResolvedValue(makeEnvelope())
  })

  it('shows the data-grounded tip plus adherence + confidence in the insights view', async () => {
    renderInsights()
    // Toggle from the chat view to the insights view.
    await userEvent.click(await screen.findByRole('radio', { name: /insights/i }))

    expect(await screen.findByText('What your history is changing')).toBeInTheDocument()
    expect(screen.getByText(/work up to Bench Press/)).toBeInTheDocument()
    expect(screen.getByText(/On track · 8 sessions in 14 days/)).toBeInTheDocument()
    expect(screen.getByText(/High training · High nutrition confidence/)).toBeInTheDocument()
  })
})
