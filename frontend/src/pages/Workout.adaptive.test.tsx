import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { Workout } from './Workout'
import { ToastProvider } from '../components/ui'
import * as api from '../api'
import { makeExerciseRec, makeTodayWorkout, makeWorkoutBlock } from '../test/adaptiveFixtures'

function renderWorkout() {
  return render(
    <MemoryRouter>
      <ToastProvider>
        <Workout />
      </ToastProvider>
    </MemoryRouter>,
  )
}

describe('Workout — adaptive targets, prefill and deload/resume banner', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(api.workouts, 'list').mockResolvedValue({ items: [] })
  })

  it('merges adaptive action + delta + target weight into the plan rows', async () => {
    vi.spyOn(api.programs, 'today').mockResolvedValue(makeTodayWorkout())
    vi.spyOn(api.recommendations, 'workout').mockResolvedValue(makeWorkoutBlock())
    renderWorkout()

    expect(await screen.findByText("Today's session")).toBeInTheDocument()
    expect(screen.getByText('Increase')).toBeInTheDocument()
    expect(screen.getByText('+2.5 kg')).toBeInTheDocument()
    expect(screen.getByText('62.5 kg')).toBeInTheDocument()
    // Concise reason is available via disclosure.
    expect(screen.getByText('Why this target')).toBeInTheDocument()
    expect(screen.getByText(/adding 2.5 kg to 62.5 kg/)).toBeInTheDocument()
  })

  it('prefills the weight/reps fields from adaptive targets when starting today\'s workout', async () => {
    vi.spyOn(api.programs, 'today').mockResolvedValue(makeTodayWorkout())
    vi.spyOn(api.recommendations, 'workout').mockResolvedValue(makeWorkoutBlock())
    vi.spyOn(api.workouts, 'create').mockResolvedValue({ id: 1, date: '2026-07-14', name: 'Upper A', program_day_id: 10, sets: [] })

    renderWorkout()
    await userEvent.click(await screen.findByRole('button', { name: /start today's workout/i }))

    // Active logger opens with the adaptive suggestion pre-filled → logging it is the feedback loop.
    expect(await screen.findByLabelText('Weight (kg)')).toHaveValue(62.5)
    expect(screen.getByLabelText('Reps')).toHaveValue(6)
  })

  it('shows an explicit deload banner when the block is deloading', async () => {
    vi.spyOn(api.programs, 'today').mockResolvedValue(makeTodayWorkout())
    vi.spyOn(api.recommendations, 'workout').mockResolvedValue(
      makeWorkoutBlock({
        deload: true,
        reason: 'Upper A: most main lifts are deloading — an intentional lighter session to recover and rebuild.',
        exercises: [makeExerciseRec({ action: 'deload', deload: true, suggested_weight: 54, reason: 'Progress stalled for a few sessions — deloading to 54 kg (~90%) to shed fatigue and resupercompensate.' })],
      }),
    )
    renderWorkout()
    expect(await screen.findByText('Deload session')).toBeInTheDocument()
    expect(screen.getByText(/most main lifts are deloading/)).toBeInTheDocument()
  })

  it('stays graceful on a rest day (no banner, no crash)', async () => {
    vi.spyOn(api.programs, 'today').mockResolvedValue({ rest_day: true })
    vi.spyOn(api.recommendations, 'workout').mockResolvedValue(
      makeWorkoutBlock({ rest_day: true, exercises: [], name: null, program_day_id: null, reason: 'Scheduled rest day — prioritise sleep, hydration and protein to recover.' }),
    )
    renderWorkout()
    expect(await screen.findByText("Today's session")).toBeInTheDocument()
    expect(screen.getByText(/No session scheduled today/)).toBeInTheDocument()
    expect(screen.queryByText('Deload session')).not.toBeInTheDocument()
  })
})
