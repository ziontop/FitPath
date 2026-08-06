import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { Nutrition } from './Nutrition'
import { ToastProvider } from '../components/ui'
import * as api from '../api'
import { makeMealsBlock, makeMealSuggestion, makeNutritionToday } from '../test/adaptiveFixtures'

function renderNutrition() {
  return render(
    <MemoryRouter>
      <ToastProvider>
        <Nutrition />
      </ToastProvider>
    </MemoryRouter>,
  )
}

describe('Nutrition — "Based on your eating history" adaptive picks', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(api.nutrition, 'today').mockResolvedValue(makeNutritionToday())
    vi.spyOn(api.meals, 'list').mockResolvedValue({ items: [] })
    vi.spyOn(api.meals, 'recent').mockResolvedValue({ recent: [], favorites: [], frequent: [] })
  })

  it('one-tap "Log this" posts the exact meal_payload and reloads', async () => {
    const suggestion = makeMealSuggestion()
    const mealsSpy = vi.spyOn(api.recommendations, 'meals').mockResolvedValue(makeMealsBlock({ suggestions: [suggestion] }))
    const createSpy = vi
      .spyOn(api.meals, 'create')
      .mockResolvedValue({ id: 99, favorite: false, ...suggestion.meal_payload })

    renderNutrition()
    const logBtn = await screen.findByRole('button', { name: /log this/i })
    await userEvent.click(logBtn)

    // Sends the suggestion's payload verbatim (this log is the feedback loop).
    await waitFor(() => expect(createSpy).toHaveBeenCalledWith(suggestion.meal_payload))
    // Reloads afterwards, re-fetching adaptive picks (called on mount + after log).
    await waitFor(() => expect(mealsSpy.mock.calls.length).toBeGreaterThanOrEqual(2))
  })

  it('shows the reason and history sample for a personalised pick', async () => {
    vi.spyOn(api.recommendations, 'meals').mockResolvedValue(makeMealsBlock())
    renderNutrition()
    expect(await screen.findByText('Based on your eating history')).toBeInTheDocument()
    expect(screen.getByText('Grilled salmon & rice')).toBeInTheDocument()
    expect(screen.getByText(/0.75× serving/)).toBeInTheDocument()
    expect(screen.getByText(/From your logs · eaten 7×/)).toBeInTheDocument()
  })

  it('labels cold-start picks as "Starter suggestion" instead of faking history', async () => {
    vi.spyOn(api.recommendations, 'meals').mockResolvedValue(
      makeMealsBlock({
        confidence: 'low',
        history_basis: { window_days: 30, days_observed: 0, total_meals: 0, distinct_foods: 0, adherent_days: 0 },
        suggestions: [
          makeMealSuggestion({
            name: 'Grilled chicken & greens',
            logged_count: 0,
            confidence: 'low',
            portion: 1,
            reason: 'Starter suggestion picked to match your remaining macros.',
            history_basis: 'No logged meals yet — starter suggestions.',
            last_eaten_at: null,
          }),
        ],
      }),
    )
    renderNutrition()
    expect(await screen.findByText('Grilled chicken & greens')).toBeInTheDocument()
    expect(screen.getByText('Starter suggestion')).toBeInTheDocument()
  })
})
