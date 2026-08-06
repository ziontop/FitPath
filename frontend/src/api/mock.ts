/* ============================================================
   In-memory mock backend (dev flag). Implements the API
   contract with realistic, typed, seeded data so every screen
   is demoable before the real backend is live.
   ============================================================ */
import { ApiError } from './client'
import type {
  Achievements,
  Activity,
  ActivityInput,
  AdaptiveExerciseRec,
  AdaptiveMealSuggestion,
  AdaptiveMealsBlock,
  AdaptiveRecommendation,
  AdaptiveWorkoutBlock,
  AiInsights,
  ChatResponse,
  Circadian,
  Confidence,
  Direction,
  Exercise,
  ExerciseInput,
  Heatmap,
  Macros,
  Meal,
  MealCategory,
  MealInput,
  MealQuickLists,
  NutritionPlan,
  NutritionToday,
  ParseLogResult,
  PerformanceSummary,
  PredictNextMeal,
  Profile,
  Program,
  ProgramSummary,
  RecommendFoods,
  RecommendationsToday,
  Sleep,
  SleepInput,
  Step,
  StepInput,
  Trends,
  Streaks,
  TodayWorkout,
  User,
  VolumeReport,
  Water,
  WaterInput,
  Weight,
  WeightInput,
  WorkoutAction,
  WorkoutSession,
  WorkoutSummary,
  SetInput,
  ExercisePerformance,
  PrRecord,
  InsightsToday,
  AppleHealthImportBatch,
  AppleHealthImportResponse,
  AppleHealthImportType,
  AppleHealthPreview,
  AppleHealthToken,
  AppleHealthTokenSecret,
} from './types'

// ---------------- date helpers ----------------
const pad = (n: number) => String(n).padStart(2, '0')
const toISODate = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
const todayISO = () => toISODate(new Date())
const daysAgoISO = (n: number) => {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return toISODate(d)
}
const nowISO = () => new Date().toISOString().slice(0, 19)
const epley = (weight: number, reps: number) => Math.round(weight * (1 + reps / 30))

// ---------------- id counters ----------------
const counters: Record<string, number> = {}
function nextId(key: string, start = 1): number {
  counters[key] = (counters[key] ?? start - 1) + 1
  return counters[key]
}

// ---------------- seed: exercises ----------------
const exercises: Exercise[] = [
  { id: 1, name: 'Back Squat', category: 'compound', primary_muscle: 'quads', secondary_muscles: ['glutes', 'hamstrings'], equipment: 'full_gym', is_main_lift: true, is_custom: false },
  { id: 2, name: 'Bench Press', category: 'compound', primary_muscle: 'chest', secondary_muscles: ['triceps', 'shoulders'], equipment: 'full_gym', is_main_lift: true, is_custom: false },
  { id: 3, name: 'Deadlift', category: 'compound', primary_muscle: 'back', secondary_muscles: ['glutes', 'hamstrings'], equipment: 'full_gym', is_main_lift: true, is_custom: false },
  { id: 4, name: 'Overhead Press', category: 'compound', primary_muscle: 'shoulders', secondary_muscles: ['triceps'], equipment: 'full_gym', is_main_lift: false, is_custom: false },
  { id: 5, name: 'Barbell Row', category: 'compound', primary_muscle: 'back', secondary_muscles: ['biceps'], equipment: 'full_gym', is_main_lift: false, is_custom: false },
  { id: 6, name: 'Pull-up', category: 'compound', primary_muscle: 'back', secondary_muscles: ['biceps'], equipment: 'bodyweight', is_main_lift: false, is_custom: false },
  { id: 7, name: 'Incline Dumbbell Press', category: 'compound', primary_muscle: 'chest', secondary_muscles: ['shoulders', 'triceps'], equipment: 'full_gym', is_main_lift: false, is_custom: false },
  { id: 8, name: 'Romanian Deadlift', category: 'compound', primary_muscle: 'hamstrings', secondary_muscles: ['glutes', 'back'], equipment: 'full_gym', is_main_lift: false, is_custom: false },
  { id: 9, name: 'Leg Press', category: 'compound', primary_muscle: 'quads', secondary_muscles: ['glutes'], equipment: 'full_gym', is_main_lift: false, is_custom: false },
  { id: 10, name: 'Lat Pulldown', category: 'compound', primary_muscle: 'back', secondary_muscles: ['biceps'], equipment: 'full_gym', is_main_lift: false, is_custom: false },
  { id: 11, name: 'Dumbbell Curl', category: 'isolation', primary_muscle: 'biceps', secondary_muscles: [], equipment: 'home_basic', is_main_lift: false, is_custom: false },
  { id: 12, name: 'Triceps Pushdown', category: 'isolation', primary_muscle: 'triceps', secondary_muscles: [], equipment: 'full_gym', is_main_lift: false, is_custom: false },
  { id: 13, name: 'Lateral Raise', category: 'isolation', primary_muscle: 'shoulders', secondary_muscles: [], equipment: 'home_basic', is_main_lift: false, is_custom: false },
  { id: 14, name: 'Leg Curl', category: 'isolation', primary_muscle: 'hamstrings', secondary_muscles: [], equipment: 'full_gym', is_main_lift: false, is_custom: false },
  { id: 15, name: 'Cable Fly', category: 'isolation', primary_muscle: 'chest', secondary_muscles: [], equipment: 'full_gym', is_main_lift: false, is_custom: false },
]
counters.exercise = exercises.length
const exName = (id: number) => exercises.find((e) => e.id === id)?.name ?? `Exercise ${id}`

// ---------------- seed: profile ----------------
let profile: Profile | null = {
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

// ---------------- seed: program ----------------
function buildProgram(): Program {
  return {
    id: 1,
    name: 'Hypertrophy Upper/Lower',
    training_goal: 'hypertrophy',
    split_type: 'upper_lower',
    days_per_week: 4,
    active: true,
    days: [
      {
        id: 10,
        day_index: 0,
        name: 'Upper A',
        exercises: [
          { exercise_id: 2, name: 'Bench Press', target_sets: 4, target_reps: '6-10', target_rpe: 8, rest_seconds: 150, progression: 'rpe_autoreg' },
          { exercise_id: 5, name: 'Barbell Row', target_sets: 4, target_reps: '8-12', target_rpe: 8, rest_seconds: 120, progression: 'rpe_autoreg' },
          { exercise_id: 4, name: 'Overhead Press', target_sets: 3, target_reps: '8-12', target_rpe: 8, rest_seconds: 120, progression: 'rpe_autoreg' },
          { exercise_id: 10, name: 'Lat Pulldown', target_sets: 3, target_reps: '10-15', target_rpe: 9, rest_seconds: 90, progression: 'rpe_autoreg' },
          { exercise_id: 13, name: 'Lateral Raise', target_sets: 3, target_reps: '12-20', target_rpe: 9, rest_seconds: 60, progression: 'rpe_autoreg' },
          { exercise_id: 12, name: 'Triceps Pushdown', target_sets: 3, target_reps: '10-15', target_rpe: 9, rest_seconds: 60, progression: 'rpe_autoreg' },
        ],
      },
      {
        id: 11,
        day_index: 1,
        name: 'Lower A',
        exercises: [
          { exercise_id: 1, name: 'Back Squat', target_sets: 4, target_reps: '5-8', target_rpe: 8, rest_seconds: 180, progression: 'rpe_autoreg' },
          { exercise_id: 8, name: 'Romanian Deadlift', target_sets: 3, target_reps: '8-12', target_rpe: 8, rest_seconds: 150, progression: 'rpe_autoreg' },
          { exercise_id: 9, name: 'Leg Press', target_sets: 3, target_reps: '10-15', target_rpe: 9, rest_seconds: 120, progression: 'rpe_autoreg' },
          { exercise_id: 14, name: 'Leg Curl', target_sets: 3, target_reps: '12-15', target_rpe: 9, rest_seconds: 75, progression: 'rpe_autoreg' },
        ],
      },
      {
        id: 12,
        day_index: 2,
        name: 'Upper B',
        exercises: [
          { exercise_id: 7, name: 'Incline Dumbbell Press', target_sets: 4, target_reps: '8-12', target_rpe: 8, rest_seconds: 120, progression: 'rpe_autoreg' },
          { exercise_id: 6, name: 'Pull-up', target_sets: 4, target_reps: '6-10', target_rpe: 9, rest_seconds: 120, progression: 'rpe_autoreg' },
          { exercise_id: 4, name: 'Overhead Press', target_sets: 3, target_reps: '10-12', target_rpe: 8, rest_seconds: 120, progression: 'rpe_autoreg' },
          { exercise_id: 15, name: 'Cable Fly', target_sets: 3, target_reps: '12-15', target_rpe: 9, rest_seconds: 60, progression: 'rpe_autoreg' },
          { exercise_id: 11, name: 'Dumbbell Curl', target_sets: 3, target_reps: '10-15', target_rpe: 9, rest_seconds: 60, progression: 'rpe_autoreg' },
        ],
      },
      {
        id: 13,
        day_index: 3,
        name: 'Lower B',
        exercises: [
          { exercise_id: 3, name: 'Deadlift', target_sets: 4, target_reps: '3-6', target_rpe: 8, rest_seconds: 210, progression: 'rpe_autoreg' },
          { exercise_id: 1, name: 'Back Squat', target_sets: 3, target_reps: '8-12', target_rpe: 7, rest_seconds: 150, progression: 'rpe_autoreg' },
          { exercise_id: 14, name: 'Leg Curl', target_sets: 3, target_reps: '12-15', target_rpe: 9, rest_seconds: 75, progression: 'rpe_autoreg' },
          { exercise_id: 9, name: 'Leg Press', target_sets: 3, target_reps: '12-20', target_rpe: 9, rest_seconds: 120, progression: 'rpe_autoreg' },
        ],
      },
    ],
  }
}
let programs: Program[] = [buildProgram()]
counters.program = 1
counters.programDay = 20
counters.programExercise = 100

// ---------------- seed: workout history ----------------
const workouts: WorkoutSession[] = []
counters.workout = 0
counters.set = 0

// base top-set weights (kg) per main/compound lift, progressed weekly
const baseWeights: Record<number, number> = {
  1: 70, 2: 45, 3: 90, 4: 30, 5: 50, 6: 0, 7: 22, 8: 70, 9: 140, 10: 45, 11: 12, 12: 25, 13: 8, 14: 35, 15: 15,
}

function seedWorkoutHistory() {
  // ~8 weeks, 4 sessions/week landing on recent days
  let sessionCounter = 0
  for (let week = 7; week >= 0; week--) {
    for (let d = 0; d < 4; d++) {
      const dayOffset = week * 7 + (6 - d * 2)
      if (dayOffset < 0) continue
      const dayTemplate = programs[0].days[d]
      const wId = nextId('workout')
      const sets = []
      for (const pe of dayTemplate.exercises) {
        const base = baseWeights[pe.exercise_id] ?? 20
        const progressed = Math.round((base + (7 - week) * (base > 40 ? 2.5 : 1)) * 2) / 2
        // Vary the top-set reps per exercise so PRs read as real, distinct lifts
        // (heavy compounds in the 5-6 range, accessories 8-11) rather than a wall
        // of identical "x10" records.
        const topReps = 5 + (pe.exercise_id % 5)
        for (let s = 0; s < Math.min(pe.target_sets, 3); s++) {
          sets.push({
            id: nextId('set'),
            exercise_id: pe.exercise_id,
            weight: progressed,
            reps: topReps + (s === 0 ? 2 : 0),
            rpe: 7 + s * 0.5,
            is_warmup: false,
            set_index: s,
          })
        }
      }
      workouts.push({
        id: wId,
        date: daysAgoISO(dayOffset),
        name: dayTemplate.name,
        program_day_id: dayTemplate.id,
        notes: undefined,
        sets,
      })
      sessionCounter++
    }
  }
  void sessionCounter
}
seedWorkoutHistory()

// ---------------- seed: nutrition plan + logs ----------------
let nutritionPlan: NutritionPlan | null = {
  id: 1,
  goal: 'maintain',
  target_kcal: 2100,
  protein_g: 140,
  carbs_g: 230,
  fat_g: 65,
  meals_per_day: 4,
  active: true,
}
counters.plan = 1

const meals: Meal[] = [
  { id: nextId('meal'), name: 'Greek yogurt & berries', kcal: 320, category: 'breakfast', protein_g: 28, carbs_g: 34, fat_g: 8, eaten_at: `${todayISO()}T08:10:00`, favorite: true },
  { id: nextId('meal'), name: 'Chicken rice bowl', kcal: 620, category: 'lunch', protein_g: 48, carbs_g: 70, fat_g: 16, eaten_at: `${todayISO()}T13:00:00`, favorite: true },
  { id: nextId('meal'), name: 'Protein shake', kcal: 180, category: 'snack', protein_g: 30, carbs_g: 6, fat_g: 3, eaten_at: `${todayISO()}T16:30:00`, favorite: false },
]
const activities: Activity[] = [
  { id: nextId('activity'), activity: 'Morning walk', minutes: 24, intensity: 'moderate', done_at: `${todayISO()}T08:15:00` },
  { id: nextId('activity'), activity: 'Mobility & stretch', minutes: 12, intensity: 'light', done_at: `${todayISO()}T09:05:00` },
]
const sleeps: Sleep[] = [{ id: nextId('sleep'), hours: 7.4, wake_time: '07:00', logged_for: todayISO() }]
const steps: Step[] = [{ id: nextId('step'), steps: 4800, logged_for: todayISO() }]
const waters: Water[] = [
  { id: nextId('water'), ml: 500, logged_at: `${todayISO()}T09:00:00` },
  { id: nextId('water'), ml: 750, logged_at: `${todayISO()}T13:30:00` },
  { id: nextId('water'), ml: 400, logged_at: `${todayISO()}T17:00:00` },
]
const weights: Weight[] = []
for (let i = 60; i >= 0; i -= 3) {
  weights.push({ id: nextId('weight'), weight_kg: Math.round((62.8 - (60 - i) * 0.01) * 10) / 10, logged_for: daysAgoISO(i) })
}

// ---------------- auth state ----------------
const AUTH_KEY = 'fitpath-mock-auth'
function loadAuth(): User | null {
  try {
    const raw = localStorage.getItem(AUTH_KEY)
    return raw ? (JSON.parse(raw) as User) : null
  } catch {
    return null
  }
}
let currentUser: User | null = loadAuth()
const appleHealthTypes: AppleHealthImportType[] = ['steps', 'weight', 'sleep', 'water', 'workouts']
const appleHealthBatches: AppleHealthImportBatch[] = []
const appleHealthTokens: AppleHealthToken[] = []

function mockApplePreview(file?: File): AppleHealthPreview {
  return {
    filename: file?.name ?? 'export.xml',
    date_range: { start: '2026-07-14', end: '2026-07-14' },
    counts_by_type: { steps: 1, weight: 1, sleep: 1, water: 1, workouts: 1 },
    units_detected: { steps: ['count'], weight: ['kg'], water: ['mL'] },
    samples: {
      steps: [{ date: '2026-07-14', value: 1200, sources: ['iPhone'] }],
      weight: [{ date: '2026-07-14', kg: 80.1 }],
      sleep: [{ wake_date: '2026-07-14', hours: 7.25, wake_time: '06:45' }],
      water: [{ date: '2026-07-14', ml: 500 }],
      workouts: [{ activity: 'Running', date: '2026-07-14', minutes: 32, intensity: 'vigorous' }],
    },
    warnings: ['Demo preview uses a synthetic Apple Health export.'],
  }
}

function setAuth(user: User | null) {
  currentUser = user
  if (user) {
    localStorage.setItem(AUTH_KEY, JSON.stringify(user))
    document.cookie = `fitpath_csrf=mock-csrf-${user.id}; path=/; SameSite=Lax`
  } else {
    localStorage.removeItem(AUTH_KEY)
    document.cookie = 'fitpath_csrf=; path=/; Max-Age=0'
  }
}

function requireAuth() {
  if (!currentUser) throw new ApiError(401, 'Not authenticated')
  return currentUser
}

// ---------------- derived helpers ----------------
function macrosConsumedToday() {
  const today = todayISO()
  const todays = meals.filter((m) => (m.eaten_at ?? '').startsWith(today))
  return todays.reduce(
    (acc, m) => ({
      kcal: acc.kcal + m.kcal,
      protein_g: acc.protein_g + (m.protein_g ?? 0),
      carbs_g: acc.carbs_g + (m.carbs_g ?? 0),
      fat_g: acc.fat_g + (m.fat_g ?? 0),
    }),
    { kcal: 0, protein_g: 0, carbs_g: 0, fat_g: 0 },
  )
}

function nutritionToday(): NutritionToday {
  const targets = nutritionPlan
    ? { kcal: nutritionPlan.target_kcal, protein_g: nutritionPlan.protein_g, carbs_g: nutritionPlan.carbs_g, fat_g: nutritionPlan.fat_g }
    : { kcal: 2100, protein_g: 140, carbs_g: 230, fat_g: 65 }
  const consumed = macrosConsumedToday()
  return {
    targets,
    consumed,
    remaining: {
      kcal: targets.kcal - consumed.kcal,
      protein_g: targets.protein_g - consumed.protein_g,
      carbs_g: targets.carbs_g - consumed.carbs_g,
      fat_g: targets.fat_g - consumed.fat_g,
    },
    meal_suggestions: [
      { name: 'Grilled salmon & greens', kcal: 480, protein_g: 42, carbs_g: 12, fat_g: 28 },
      { name: 'Turkey wrap', kcal: 430, protein_g: 34, carbs_g: 44, fat_g: 12 },
      { name: 'Cottage cheese & pineapple', kcal: 240, protein_g: 26, carbs_g: 20, fat_g: 5 },
    ],
  }
}

function todayWorkout(): TodayWorkout {
  const dow = new Date().getDay()
  // Rest on Sundays for the demo.
  if (dow === 0) return { rest_day: true }
  const idx = dow % programs[0].days.length
  const day = programs[0].days[idx]
  return {
    program_day_id: day.id,
    name: day.name,
    exercises: day.exercises.map((pe) => {
      const base = baseWeights[pe.exercise_id] ?? 20
      const suggested = base > 0 ? Math.round((base + 8 * (base > 40 ? 2.5 : 1)) * 2) / 2 : undefined
      return { ...pe, suggested_weight: suggested }
    }),
  }
}

// ---------------- adaptive recommendations (history-based, deterministic) ----------------
// Mirrors app/services/adaptive.py: same envelope shapes, cold/rest/no-history
// fallbacks, portion scaling and confidence tiers — built from the seeded mock
// history so every screen is demoable. Deterministic (no randomness).
const ADAPT_VERSION = 'adaptive-v1'
const ADAPT_ALGO = 'history-adaptive-deterministic'

const normName = (s: string) => s.trim().toLowerCase().replace(/\s+/g, ' ')
const round1 = (n: number) => Math.round(n * 10) / 10
const round2 = (n: number) => Math.round(n * 100) / 100
const round4 = (n: number) => Math.round(n * 1e4) / 1e4
const roundStep = (n: number, step: number) => Math.round(n / step) * step
const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n))

interface AdaptFood {
  name: string
  category: MealCategory
  kcal: number
  protein_g: number
  carbs_g: number
  fat_g: number
  logged_count: number
  days_since: number
  favorite: boolean
  adherence: number
}

// The persona's recurring foods (what Zina actually logs), used to rank picks
// against today's remaining macros. Foods already eaten today are excluded, so
// each suggestion is genuinely "what fits the rest of today".
const ADAPT_FOOD_POOL: AdaptFood[] = [
  { name: 'Grilled salmon & rice', category: 'dinner', kcal: 640, protein_g: 42, carbs_g: 60, fat_g: 20, logged_count: 7, days_since: 2, favorite: true, adherence: 0.72 },
  { name: 'Turkey chili', category: 'dinner', kcal: 520, protein_g: 45, carbs_g: 48, fat_g: 14, logged_count: 5, days_since: 4, favorite: false, adherence: 0.64 },
  { name: 'Beef stir-fry & noodles', category: 'dinner', kcal: 680, protein_g: 44, carbs_g: 66, fat_g: 22, logged_count: 4, days_since: 6, favorite: false, adherence: 0.5 },
  { name: 'Tofu veggie stir-fry', category: 'dinner', kcal: 460, protein_g: 28, carbs_g: 50, fat_g: 16, logged_count: 3, days_since: 8, favorite: false, adherence: 0.42 },
  { name: 'Chicken rice bowl', category: 'lunch', kcal: 620, protein_g: 48, carbs_g: 70, fat_g: 16, logged_count: 11, days_since: 1, favorite: true, adherence: 0.8 },
  { name: 'Egg & avocado toast', category: 'breakfast', kcal: 380, protein_g: 22, carbs_g: 34, fat_g: 18, logged_count: 8, days_since: 2, favorite: false, adherence: 0.6 },
  { name: 'Greek yogurt & berries', category: 'breakfast', kcal: 320, protein_g: 28, carbs_g: 34, fat_g: 8, logged_count: 9, days_since: 0, favorite: true, adherence: 0.75 },
  { name: 'Cottage cheese & pineapple', category: 'snack', kcal: 240, protein_g: 26, carbs_g: 20, fat_g: 5, logged_count: 6, days_since: 3, favorite: false, adherence: 0.55 },
  { name: 'Protein shake', category: 'snack', kcal: 180, protein_g: 30, carbs_g: 6, fat_g: 3, logged_count: 8, days_since: 0, favorite: false, adherence: 0.7 },
]

// Curated starter foods used only when there is no matching history (cold start).
const ADAPT_STARTERS: Omit<AdaptFood, 'logged_count' | 'days_since' | 'favorite' | 'adherence'>[] = [
  { name: 'Grilled chicken & greens', category: 'dinner', kcal: 480, protein_g: 42, carbs_g: 12, fat_g: 28 },
  { name: 'Turkey & rice bowl', category: 'lunch', kcal: 560, protein_g: 44, carbs_g: 62, fat_g: 14 },
  { name: 'Greek yogurt (0%)', category: 'snack', kcal: 150, protein_g: 25, carbs_g: 9, fat_g: 0 },
  { name: 'Oats & whey', category: 'breakfast', kcal: 420, protein_g: 34, carbs_g: 56, fat_g: 8 },
]

const CATEGORY_TIME: Record<MealCategory, string> = { breakfast: '08:10', lunch: '13:00', dinner: '19:20', snack: '16:15' }

function macroCosine(a: [number, number, number], b: [number, number, number]): number {
  const dot = a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
  const na = Math.hypot(a[0], a[1], a[2])
  const nb = Math.hypot(b[0], b[1], b[2])
  if (na === 0 || nb === 0) return 0
  return clamp(dot / (na * nb), 0, 1)
}

function portionFactor(baseKcal: number, budget: number): number {
  if (baseKcal <= 0) return 1
  const raw = budget > 0 ? budget / baseKcal : 1
  return clamp(roundStep(raw, 0.25) || 0.5, 0.5, 2.0)
}

function lastEatenPhrase(daysSince: number): string {
  if (daysSince <= 0) return 'today'
  if (daysSince === 1) return '1 day ago'
  return `${daysSince} days ago`
}

function mealReason(f: AdaptFood, gap: [number, number, number], predicted: MealCategory): string {
  const named: [string, number][] = [['protein', gap[0]], ['carbs', gap[1]], ['fat', gap[2]]]
  const top = named.filter(([, g]) => g > 0).sort((a, b) => b[1] - a[1]).slice(0, 2)
  const parts: string[] = []
  parts.push(top.length ? `fits your remaining ${top.map(([n, g]) => `${Math.round(g)}g ${n}`).join(' / ')} gap` : 'rounds out an already on-target day')
  if (f.logged_count >= 6) parts.push(`a go-to ${f.category} you've logged ${f.logged_count}×`)
  else if (f.category === predicted) parts.push(`a typical ${f.category} choice for now`)
  if (f.adherence >= 0.6) parts.push('and it shows up on your on-target days')
  if (f.favorite) parts.push("and it's a favorite")
  const s = parts.join(', ')
  return s[0].toUpperCase() + s.slice(1) + '.'
}

function scaledSuggestion(f: AdaptFood, budget: number, gap: [number, number, number], predicted: MealCategory, confidence: Confidence): AdaptiveMealSuggestion {
  const recency = Math.pow(0.5, f.days_since / 14)
  const frequency = f.logged_count / (f.logged_count + 3)
  const macroFit = macroCosine([f.protein_g, f.carbs_g, f.fat_g], gap[0] + gap[1] + gap[2] > 0 ? gap : [f.protein_g, f.carbs_g, f.fat_g])
  const categoryFit = f.category === predicted ? 1.0 : 0.5
  const favorite = f.favorite ? 1 : 0
  const score = 0.35 * macroFit + 0.2 * f.adherence + 0.15 * recency + 0.15 * frequency + 0.15 * categoryFit + 0.05 * favorite
  const portion = portionFactor(f.kcal, budget)
  const kcal = Math.round(f.kcal * portion)
  const protein = round1(f.protein_g * portion)
  const carbs = round1(f.carbs_g * portion)
  const fat = round1(f.fat_g * portion)
  const eatenDays = Math.min(f.logged_count, 12)
  const adherentHits = Math.round(f.adherence * eatenDays)
  return {
    name: f.name,
    category: f.category,
    kcal,
    protein_g: protein,
    carbs_g: carbs,
    fat_g: fat,
    portion: round2(portion),
    score: round4(score),
    components: {
      macro_fit: round4(macroFit),
      recency: round4(recency),
      frequency: round4(frequency),
      adherence: round4(f.adherence),
      category_fit: round4(categoryFit),
      favorite,
    },
    reason: mealReason(f, gap, predicted),
    history_basis: `From 72 meals over 21 days · eaten ${f.logged_count}× (last ${lastEatenPhrase(f.days_since)}) · on ${adherentHits} of ${eatenDays} logged day(s) on-target.`,
    confidence,
    logged_count: f.logged_count,
    last_eaten_at: `${daysAgoISO(f.days_since)}T${CATEGORY_TIME[f.category]}`,
    meal_payload: { name: f.name, kcal, category: f.category, protein_g: protein, carbs_g: carbs, fat_g: fat },
  }
}

function starterSuggestions(category: MealCategory | undefined, budget: number, limit: number, exclude: Set<string>): AdaptiveMealSuggestion[] {
  return ADAPT_STARTERS.filter((s) => (!category || s.category === category) && !exclude.has(normName(s.name)))
    .slice(0, limit)
    .map((s) => {
      const portion = portionFactor(s.kcal, budget)
      const kcal = Math.round(s.kcal * portion)
      const protein = round1(s.protein_g * portion)
      const carbs = round1(s.carbs_g * portion)
      const fat = round1(s.fat_g * portion)
      return {
        name: s.name,
        category: s.category,
        kcal,
        protein_g: protein,
        carbs_g: carbs,
        fat_g: fat,
        portion: round2(portion),
        score: 0,
        components: { macro_fit: 0, recency: 0, frequency: 0, adherence: 0, category_fit: 0, favorite: 0 },
        reason: 'Starter suggestion picked to match your remaining macros.',
        history_basis: 'No logged meals yet — starter suggestions.',
        confidence: 'low' as Confidence,
        logged_count: 0,
        last_eaten_at: null,
        meal_payload: { name: s.name, kcal, category: s.category, protein_g: protein, carbs_g: carbs, fat_g: fat },
      }
    })
}

function adaptiveMeals(category?: MealCategory, limit = 3): AdaptiveMealsBlock {
  const lim = clamp(limit, 1, 10)
  const targets: Macros = nutritionPlan
    ? { kcal: nutritionPlan.target_kcal, protein_g: nutritionPlan.protein_g, carbs_g: nutritionPlan.carbs_g, fat_g: nutritionPlan.fat_g }
    : { kcal: 2100, protein_g: 140, carbs_g: 230, fat_g: 65 }
  const consumed = macrosConsumedToday()
  const remaining: Macros = {
    kcal: round1(targets.kcal - consumed.kcal),
    protein_g: round1(targets.protein_g - consumed.protein_g),
    carbs_g: round1(targets.carbs_g - consumed.carbs_g),
    fat_g: round1(targets.fat_g - consumed.fat_g),
  }
  const gap: [number, number, number] = [Math.max(0, remaining.protein_g), Math.max(0, remaining.carbs_g), Math.max(0, remaining.fat_g)]
  const remainingKcal = Math.max(0, remaining.kcal)
  const predicted: MealCategory = 'dinner'
  const typicalKcal = 620
  const mealsLeft = remainingKcal > 0 ? Math.max(1, Math.round(remainingKcal / typicalKcal)) : 1
  const budget = mealsLeft ? remainingKcal / mealsLeft : remainingKcal

  const eatenToday = new Set(meals.filter((m) => (m.eaten_at ?? '').startsWith(todayISO())).map((m) => normName(m.name)))
  let pool = ADAPT_FOOD_POOL.filter((f) => !eatenToday.has(normName(f.name)))
  if (category) pool = pool.filter((f) => f.category === category)

  const scored = pool
    .map((f) => {
      const recency = Math.pow(0.5, f.days_since / 14)
      const frequency = f.logged_count / (f.logged_count + 3)
      const macroFit = macroCosine([f.protein_g, f.carbs_g, f.fat_g], gap[0] + gap[1] + gap[2] > 0 ? gap : [f.protein_g, f.carbs_g, f.fat_g])
      const categoryFit = f.category === predicted ? 1.0 : 0.5
      const score = 0.35 * macroFit + 0.2 * f.adherence + 0.15 * recency + 0.15 * frequency + 0.15 * categoryFit + 0.05 * (f.favorite ? 1 : 0)
      return { f, score }
    })
    .sort((a, b) => b.score - a.score || normName(a.f.name).localeCompare(normName(b.f.name)))

  const hasHistory = meals.length > 0 && scored.length > 0
  const confidence: Confidence = hasHistory ? 'high' : 'low'
  let suggestions: AdaptiveMealSuggestion[] = scored.slice(0, lim).map((s) => scaledSuggestion(s.f, budget, gap, predicted, confidence))
  if (suggestions.length < lim) {
    const exclude = new Set(suggestions.map((s) => normName(s.name)))
    suggestions = suggestions.concat(starterSuggestions(category, budget, lim - suggestions.length, exclude))
  }

  return {
    version: ADAPT_VERSION,
    algorithm: ADAPT_ALGO,
    targets,
    consumed,
    remaining,
    next_meal: { predicted_category: predicted, predicted_time: '19:20', suggested_kcal: 640 },
    history_basis: { window_days: 30, days_observed: 21, total_meals: 72, distinct_foods: hasHistory ? 14 : 0, adherent_days: hasHistory ? 12 : 0 },
    confidence,
    suggestions,
  }
}

function parseReps(r: string): [number, number] {
  const m = r.match(/(\d+)\s*-\s*(\d+)/)
  if (m) return [Number(m[1]), Number(m[2])]
  const n = Number(r) || 8
  return [n, n]
}

function workoutConfidence(n: number): Confidence {
  if (n >= 4) return 'high'
  if (n >= 1) return 'medium'
  return 'low'
}

function topSetFor(w: WorkoutSession, exId: number) {
  const sets = w.sets.filter((s) => s.exercise_id === exId && !s.is_warmup)
  if (!sets.length) return null
  return sets.reduce((best, s) => (!best || s.weight > best.weight || (s.weight === best.weight && s.reps > best.reps) ? s : best), sets[0])
}

function sessionsFor(exId: number): WorkoutSession[] {
  return workouts
    .filter((w) => w.sets.some((s) => s.exercise_id === exId && !s.is_warmup))
    .sort((a, b) => a.date.localeCompare(b.date))
}

function directionOf(delta: number): Direction {
  if (delta > 1e-6) return 'up'
  if (delta < -1e-6) return 'down'
  return 'flat'
}

function adaptiveExerciseRec(pe: Program['days'][number]['exercises'][number], base: number): AdaptiveExerciseRec {
  const [repLow, repHigh] = parseReps(pe.target_reps)
  const increment = base >= 40 ? 2.5 : 1.25
  const sessions = sessionsFor(pe.exercise_id).slice(-5)
  const confidence = workoutConfidence(sessions.length)

  if (sessions.length === 0) {
    const startWeight = base > 0 ? roundStep(base, increment) : null
    return {
      exercise_id: pe.exercise_id,
      name: pe.name,
      action: 'start',
      suggested_weight: startWeight,
      target_sets: pe.target_sets,
      target_reps: pe.target_reps,
      target_rpe: pe.target_rpe,
      deload: false,
      last_performance: null,
      change: { weight_delta_kg: 0, reps_delta: 0, direction: 'flat' },
      e1rm_trend: null,
      confidence,
      reason:
        startWeight != null
          ? `First ${pe.name} session on this program — start around ${startWeight} kg for ${repLow}-${repHigh} reps and we'll adapt from your logs.`
          : `No ${pe.name} history yet — pick a comfortable weight for ${repLow}-${repHigh} reps; the engine adapts once you log a set.`,
      history_basis: `No logged ${pe.name} sessions yet — using the program prescription.`,
    }
  }

  const last = sessions[sessions.length - 1]
  const lastTop = topSetFor(last, pe.exercise_id)!
  const lastWeight = lastTop.weight
  const lastReps = lastTop.reps
  const lastRpe = lastTop.rpe ?? null
  const lastE1rm = round1(epley(lastWeight, lastReps))
  const firstTop = topSetFor(sessions[0], pe.exercise_id)!
  const firstE1rm = round1(epley(firstTop.weight, firstTop.reps))

  const progresses = lastReps >= repHigh
  const action: WorkoutAction = progresses ? 'increase' : 'hold'
  const suggested = progresses ? roundStep(lastWeight + increment, increment) : lastWeight
  const weightDelta = round2(suggested - lastWeight)
  const repsDelta = progresses ? repLow - lastReps : 0
  const direction = directionOf(Math.abs(weightDelta) > 1e-6 ? weightDelta : repsDelta)
  const workingSets = last.sets.filter((s) => s.exercise_id === pe.exercise_id && !s.is_warmup).length

  return {
    exercise_id: pe.exercise_id,
    name: pe.name,
    action,
    suggested_weight: suggested,
    target_sets: pe.target_sets,
    target_reps: pe.target_reps,
    target_rpe: pe.target_rpe,
    deload: false,
    last_performance: { date: last.date, weight: lastWeight, reps: lastReps, rpe: lastRpe, sets: workingSets, e1rm: lastE1rm },
    change: { weight_delta_kg: weightDelta, reps_delta: repsDelta, direction },
    e1rm_trend: { first: firstE1rm, last: lastE1rm, direction: directionOf(lastE1rm - firstE1rm) },
    confidence,
    reason: progresses
      ? `You hit ${lastReps} reps${lastRpe != null ? ` @ RPE ${lastRpe}` : ''} last time (top of range with reps to spare) — adding ${increment} kg to ${suggested} kg and resetting to ${repLow} reps.`
      : `Inside your ${repLow}-${repHigh} range — hold ${suggested} kg and add a rep toward the top before the next load bump.`,
    history_basis: `Based on your last ${sessions.length} ${pe.name} session(s); e1RM ${firstE1rm} → ${lastE1rm} kg.`,
  }
}

function workoutAdherence(): NonNullable<AdaptiveWorkoutBlock['adherence']> {
  const now = Date.now()
  const sessions14 = workouts.filter((w) => (now - new Date(`${w.date}T00:00:00`).getTime()) / 86_400_000 <= 14).length
  const scheduled = programs[0]?.days_per_week ?? 0
  const consistency: NonNullable<AdaptiveWorkoutBlock['adherence']>['consistency'] =
    sessions14 === 0 ? 'returning' : sessions14 >= Math.ceil(Math.max(1, scheduled) * 2 * 0.7) ? 'on_track' : 'inconsistent'
  return { sessions_last_14d: sessions14, scheduled_days_per_week: scheduled, consistency }
}

function adaptiveWorkout(programDayId?: number): AdaptiveWorkoutBlock {
  const adherence = workoutAdherence()
  const program = programs[0]
  const base = {
    version: ADAPT_VERSION,
    algorithm: ADAPT_ALGO,
    program_day_id: null as number | null,
    name: null as string | null,
    deload: false,
    adherence,
  }
  if (!program || !program.days.length) {
    return { ...base, rest_day: false, confidence: 'low', reason: 'No active program yet — generate one to get adaptive workout guidance.', exercises: [] }
  }
  const days = program.days
  let day: Program['days'][number] | null
  if (programDayId != null) {
    day = days.find((d) => d.id === programDayId) ?? null
    if (!day) return { ...base, rest_day: false, confidence: 'low', reason: 'That program day is not in your active program.', exercises: [] }
  } else {
    const dow = new Date().getDay()
    day = dow === 0 ? null : days[dow % days.length]
  }
  if (!day) {
    return { ...base, rest_day: true, confidence: workoutConfidence(adherence.sessions_last_14d), reason: 'Scheduled rest day — prioritise sleep, hydration and protein to recover.', exercises: [] }
  }

  const exercises = day.exercises.map((pe) => adaptiveExerciseRec(pe, baseWeights[pe.exercise_id] ?? 20))
  const deloadCount = exercises.filter((e) => e.deload).length
  const sessionDeload = exercises.length > 0 && deloadCount > exercises.length / 2
  const order: Confidence[] = ['low', 'medium', 'high']
  const confidence = exercises.length ? order[Math.min(...exercises.map((e) => order.indexOf(e.confidence)))] : 'low'
  const lead = exercises[0]?.name ?? 'your main lift'
  return {
    ...base,
    rest_day: false,
    program_day_id: day.id,
    name: day.name,
    deload: sessionDeload,
    confidence,
    reason: sessionDeload
      ? `${day.name}: most main lifts are deloading — an intentional lighter session to recover and rebuild.`
      : `${day.name}: work up to ${lead} at the prescribed RPE; loads below are adapted from your recent logs.`,
    exercises,
  }
}

function adaptiveTip(mealsBlock: AdaptiveMealsBlock, workout: AdaptiveWorkoutBlock): string {
  const kcalLeft = Math.max(0, Math.round(mealsBlock.remaining.kcal))
  const proteinLeft = Math.max(0, Math.round(mealsBlock.remaining.protein_g))
  const topMeal = mealsBlock.suggestions[0]?.name
  let bpart: string
  if (workout.rest_day) bpart = 'Rest day — prioritise sleep and hydration.'
  else if (!workout.exercises.length) bpart = workout.reason || 'No active program yet.'
  else {
    const l = workout.exercises[0]
    let piece = `Today is ${workout.name ?? 'your session'} — work up to ${l.name}`
    if (l.target_rpe != null) piece += ` at RPE ${l.target_rpe}`
    if (l.suggested_weight != null) piece += ` (try ${l.suggested_weight} kg)`
    bpart = `${piece}.`
  }
  let tail = ` You have ${kcalLeft} kcal and ${proteinLeft} g protein left`
  tail += topMeal ? `; a ${topMeal.toLowerCase()} would close most of it.` : " to hit today's target."
  return bpart + tail
}

function adaptiveEnvelope(): AdaptiveRecommendation {
  const mealsBlock = adaptiveMeals()
  const workout = adaptiveWorkout()
  return {
    version: ADAPT_VERSION,
    algorithm: ADAPT_ALGO,
    generated_at: nowISO(),
    meals: mealsBlock,
    workout,
    tip: adaptiveTip(mealsBlock, workout),
  }
}

function performanceSummary(): PerformanceSummary {
  const totalVolume = workouts.reduce((sum, w) => sum + w.sets.reduce((s, set) => s + set.weight * set.reps, 0), 0)
  const highlights = [1, 2, 3].map((id) => {
    const best = bestForExercise(id)
    return { exercise_id: id, exercise_name: exName(id), e1rm: best?.best_e1rm ?? 0 }
  })
  return {
    total_volume: Math.round(totalVolume),
    sessions_count: workouts.length,
    prs_count: prList().length,
    e1rm_highlights: highlights,
  }
}

function bestForExercise(exerciseId: number): PrRecord | null {
  let best: PrRecord | null = null
  for (const w of workouts) {
    for (const set of w.sets) {
      if (set.exercise_id !== exerciseId || set.is_warmup) continue
      const e1 = epley(set.weight, set.reps)
      if (!best || e1 > best.best_e1rm) {
        best = {
          exercise_id: exerciseId,
          exercise_name: exName(exerciseId),
          best_e1rm: e1,
          best_weight: set.weight,
          best_reps: set.reps,
          achieved_at: w.date,
        }
      }
    }
  }
  return best
}

function prList(): PrRecord[] {
  const ids = Array.from(new Set(workouts.flatMap((w) => w.sets.map((s) => s.exercise_id))))
  return ids
    .map((id) => bestForExercise(id))
    .filter((p): p is PrRecord => p !== null && p.best_e1rm > 0)
    .sort((a, b) => b.best_e1rm - a.best_e1rm)
}

function exercisePerformance(exerciseId: number): ExercisePerformance {
  const history = workouts
    .flatMap((w) =>
      w.sets
        .filter((s) => s.exercise_id === exerciseId && !s.is_warmup)
        .map((s) => ({ date: w.date, weight: s.weight, reps: s.reps, rpe: s.rpe, e1rm: epley(s.weight, s.reps) })),
    )
    .sort((a, b) => a.date.localeCompare(b.date))
  const byDate = new Map<string, { e1rm: number; volume: number }>()
  for (const w of workouts) {
    const sets = w.sets.filter((s) => s.exercise_id === exerciseId && !s.is_warmup)
    if (!sets.length) continue
    const e1rm = Math.max(...sets.map((s) => epley(s.weight, s.reps)))
    const volume = sets.reduce((sum, s) => sum + s.weight * s.reps, 0)
    byDate.set(w.date, { e1rm, volume })
  }
  const dates = Array.from(byDate.keys()).sort()
  return {
    exercise_id: exerciseId,
    exercise_name: exName(exerciseId),
    history,
    e1rm_trend: dates.map((d) => ({ date: d, value: byDate.get(d)!.e1rm })),
    volume_trend: dates.map((d) => ({ date: d, value: Math.round(byDate.get(d)!.volume) })),
    best: bestForExercise(exerciseId) ?? {
      exercise_id: exerciseId,
      exercise_name: exName(exerciseId),
      best_e1rm: 0,
      best_weight: 0,
      best_reps: 0,
      achieved_at: todayISO(),
    },
  }
}

function volumeReport(): VolumeReport {
  const weeksMap = new Map<string, Map<string, { sets: number; volume: number }>>()
  for (const w of workouts) {
    const dt = new Date(w.date)
    const monday = new Date(dt)
    monday.setDate(dt.getDate() - ((dt.getDay() + 6) % 7))
    const wk = toISODate(monday)
    if (!weeksMap.has(wk)) weeksMap.set(wk, new Map())
    const muscleMap = weeksMap.get(wk)!
    for (const set of w.sets) {
      if (set.is_warmup) continue
      const muscle = exercises.find((e) => e.id === set.exercise_id)?.primary_muscle ?? 'other'
      const cur = muscleMap.get(muscle) ?? { sets: 0, volume: 0 }
      cur.sets += 1
      cur.volume += set.weight * set.reps
      muscleMap.set(muscle, cur)
    }
  }
  const weeks = Array.from(weeksMap.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([week_start, muscleMap]) => {
      const muscles = Array.from(muscleMap.entries()).map(([muscle, v]) => ({ muscle, sets: v.sets, volume: Math.round(v.volume) }))
      return { week_start, muscles, total_volume: muscles.reduce((s, m) => s + m.volume, 0) }
    })
  return { weeks }
}

function trends(days: number): Trends {
  const out: Trends['days'] = []
  for (let i = days - 1; i >= 0; i--) {
    const date = daysAgoISO(i)
    const w = weights.find((x) => x.logged_for === date)
    out.push({
      date,
      kcal_in: 1800 + Math.round(Math.sin(i / 2) * 180) + (i % 3) * 60,
      weight_kg: w?.weight_kg ?? Math.round((62.5 - i * 0.005) * 10) / 10,
      sleep_hours: Math.round((7 + Math.sin(i / 3) * 0.8) * 10) / 10,
      steps: 6000 + ((i * 733) % 4200),
    })
  }
  return { days: out }
}

function heatmap(days: number): Heatmap {
  const out: Heatmap['days'] = []
  for (let i = days - 1; i >= 0; i--) {
    const level = (Math.floor(Math.abs(Math.sin(i / 2) * 5)) % 5) as 0 | 1 | 2 | 3 | 4
    out.push({ date: daysAgoISO(i), level })
  }
  return { days: out }
}

// ---------------- router ----------------
function firstMeal(body: unknown): MealInput {
  return body as MealInput
}

// Simulate network latency slightly for realism.
const delay = () => new Promise<void>((r) => setTimeout(r, 120))

export async function mockRequest(method: string, rawPath: string, body?: unknown): Promise<unknown> {
  await delay()
  const path = rawPath.split('?')[0]
  const query = new URLSearchParams(rawPath.includes('?') ? rawPath.slice(rawPath.indexOf('?') + 1) : '')
  const seg = path.split('/').filter(Boolean) // e.g. ['auth','me']

  // ---- public ----
  if (path === '/health') return { status: 'ok' }

  // ---- auth ----
  if (path === '/auth/register' && method === 'POST') {
    const b = body as { email: string; username: string }
    const user: User = { id: 1, email: b.email, username: b.username, created_at: nowISO() }
    setAuth(user)
    return { user }
  }
  if (path === '/auth/login' && method === 'POST') {
    const b = body as { identifier: string }
    const user: User = { id: 1, email: b.identifier.includes('@') ? b.identifier : 'zina@fitpath.dev', username: b.identifier.includes('@') ? 'zina' : b.identifier, created_at: nowISO() }
    setAuth(user)
    return { user }
  }
  if (path === '/auth/logout' && method === 'POST') {
    setAuth(null)
    return undefined
  }
  if (path === '/auth/me' && method === 'GET') {
    return { user: requireAuth() }
  }

  // everything below requires auth
  requireAuth()

  // ---- Apple Health integration ----
  if (path === '/integrations/apple-health/preview' && method === 'POST') {
    const file = body instanceof FormData ? (body.get('file') as File | null) : null
    return mockApplePreview(file ?? undefined)
  }
  if (path === '/integrations/apple-health/import' && method === 'POST') {
    const selected = body instanceof FormData && typeof body.get('types') === 'string'
      ? (JSON.parse(body.get('types') as string) as AppleHealthImportType[])
      : appleHealthTypes
    const results = Object.fromEntries(
      appleHealthTypes.map((t) => [
        t,
        selected.includes(t)
          ? { inserted: 1, updated: 0, skipped: 0, invalid: 0, conflict: 0 }
          : { inserted: 0, updated: 0, skipped: 0, invalid: 0, conflict: 0 },
      ]),
    ) as AppleHealthImportResponse['results']
    const totals = Object.values(results).reduce(
      (a, r) => ({
        inserted: a.inserted + r.inserted,
        updated: a.updated + r.updated,
        skipped: a.skipped + r.skipped,
        invalid: a.invalid + r.invalid,
        conflict: a.conflict + r.conflict,
      }),
      { inserted: 0, updated: 0, skipped: 0, invalid: 0, conflict: 0 },
    )
    const batch: AppleHealthImportBatch = {
      id: nextId('appleBatch'),
      source: 'export',
      status: 'completed',
      date_range: { start: '2026-07-14', end: '2026-07-14' },
      records_inserted: totals.inserted,
      records_updated: totals.updated,
      records_skipped: totals.skipped,
      records_invalid: totals.invalid,
      records_conflict: totals.conflict,
      created_at: nowISO(),
      completed_at: nowISO(),
      error: null,
    }
    appleHealthBatches.unshift(batch)
    return { batch_id: batch.id, source: 'export', status: 'completed', date_range: batch.date_range, results, totals }
  }
  if (path === '/integrations/apple-health/imports' && method === 'GET') return { items: appleHealthBatches }
  if (path === '/integrations/apple-health/data' && method === 'DELETE') {
    return { deleted: { steps: 1, weight: 1, sleep: 1, water: 1, workouts: 1 }, preserved_modified: { workouts: 1 }, provenance_removed: 5 }
  }
  if (path === '/integrations/apple-health/tokens' && method === 'GET') return { items: appleHealthTokens }
  if (path === '/integrations/apple-health/tokens' && method === 'POST') {
    const b = body as { name?: string; expires_in_days?: number }
    const created = new Date()
    const expires = b.expires_in_days ? new Date(created.getTime() + b.expires_in_days * 86_400_000) : null
    const secret: AppleHealthTokenSecret = {
      id: nextId('appleToken'),
      name: b.name || 'iPhone Shortcut',
      prefix: `fpk_demo${String(nextId('applePrefix')).padStart(4, '0')}`,
      token: `fpk_demo000000_${crypto.randomUUID().replaceAll('-', '')}demoSecret`,
      created_at: nowISO(),
      last_used_at: null,
      expires_at: expires?.toISOString().slice(0, 19) ?? null,
      revoked_at: null,
    }
    const { token: _token, ...meta } = secret
    appleHealthTokens.unshift(meta)
    return secret
  }
  if (seg[0] === 'integrations' && seg[1] === 'apple-health' && seg[2] === 'tokens' && seg[4] === 'rotate' && method === 'POST') {
    const id = Number(seg[3])
    const token = appleHealthTokens.find((t) => t.id === id)
    if (!token) throw new ApiError(404, 'Token not found')
    const rotated: AppleHealthTokenSecret = { ...token, prefix: `${token.prefix.slice(0, 8)}r${id}`, token: `fpk_rotate${id}_${crypto.randomUUID().replaceAll('-', '')}demoSecret` }
    Object.assign(token, { prefix: rotated.prefix, created_at: nowISO(), last_used_at: null })
    return rotated
  }
  if (seg[0] === 'integrations' && seg[1] === 'apple-health' && seg[2] === 'tokens' && seg[3] && method === 'DELETE') {
    const token = appleHealthTokens.find((t) => t.id === Number(seg[3]))
    if (token) token.revoked_at = nowISO()
    return undefined
  }

  // ---- profile ----
  if (path === '/profile' && method === 'GET') {
    if (!profile) throw new ApiError(404, 'Profile not found')
    return profile
  }
  if (path === '/profile' && method === 'PUT') {
    profile = body as Profile
    return profile
  }

  // ---- meals ----
  if (path === '/logs/meals/recent' && method === 'GET') {
    const lists: MealQuickLists = {
      recent: meals.slice(-6).reverse(),
      favorites: meals.filter((m) => m.favorite),
      frequent: meals.slice(0, 4),
    }
    return lists
  }
  if (path === '/logs/meals' && method === 'GET') {
    const date = query.get('date') ?? todayISO()
    return { items: meals.filter((m) => (m.eaten_at ?? todayISO()).startsWith(date)) }
  }
  if (path === '/logs/meals' && method === 'POST') {
    const input = firstMeal(body)
    const meal: Meal = { id: nextId('meal'), favorite: false, eaten_at: input.eaten_at ?? nowISO(), ...input }
    meals.push(meal)
    return meal
  }
  if (seg[0] === 'logs' && seg[1] === 'meals' && seg[3] === 'favorite' && method === 'POST') {
    const id = Number(seg[2])
    const meal = meals.find((m) => m.id === id)
    if (!meal) throw new ApiError(404, 'Meal not found')
    meal.favorite = !meal.favorite
    return { ok: true, favorite: meal.favorite }
  }
  if (seg[0] === 'logs' && seg[1] === 'meals' && seg[2] && method === 'PUT') {
    const id = Number(seg[2])
    const idx = meals.findIndex((m) => m.id === id)
    if (idx < 0) throw new ApiError(404, 'Meal not found')
    meals[idx] = { ...meals[idx], ...(body as MealInput) }
    return meals[idx]
  }
  if (seg[0] === 'logs' && seg[1] === 'meals' && seg[2] && method === 'DELETE') {
    const id = Number(seg[2])
    const idx = meals.findIndex((m) => m.id === id)
    if (idx >= 0) meals.splice(idx, 1)
    return { ok: true }
  }

  // ---- activities ----
  if (path === '/logs/activities' && method === 'GET') return { items: activities }
  if (path === '/logs/activities' && method === 'POST') {
    const a: Activity = { id: nextId('activity'), done_at: nowISO(), ...(body as ActivityInput) }
    activities.push(a)
    return a
  }
  if (seg[0] === 'logs' && seg[1] === 'activities' && seg[2] && method === 'PUT') {
    const id = Number(seg[2])
    const idx = activities.findIndex((x) => x.id === id)
    if (idx < 0) throw new ApiError(404, 'Activity not found')
    activities[idx] = { ...activities[idx], ...(body as ActivityInput) }
    return activities[idx]
  }
  if (seg[0] === 'logs' && seg[1] === 'activities' && seg[2] && method === 'DELETE') {
    const id = Number(seg[2])
    const idx = activities.findIndex((x) => x.id === id)
    if (idx >= 0) activities.splice(idx, 1)
    return { ok: true }
  }

  // ---- sleep / steps / water / weight ----
  if (path === '/logs/sleep' && method === 'GET') return { items: sleeps }
  if (path === '/logs/sleep' && method === 'POST') {
    const s: Sleep = { id: nextId('sleep'), logged_for: todayISO(), ...(body as SleepInput) }
    sleeps.push(s)
    return s
  }
  if (path === '/logs/steps' && method === 'GET') return { items: steps }
  if (path === '/logs/steps' && method === 'POST') {
    const input = body as StepInput
    const date = input.logged_for ?? todayISO()
    const existing = steps.find((s) => s.logged_for === date)
    if (existing) {
      existing.steps = input.steps
      return existing
    }
    const s: Step = { id: nextId('step'), logged_for: date, steps: input.steps }
    steps.push(s)
    return s
  }
  if (path === '/logs/water' && method === 'GET') return { items: waters }
  if (path === '/logs/water' && method === 'POST') {
    const w: Water = { id: nextId('water'), logged_at: nowISO(), ...(body as WaterInput) }
    waters.push(w)
    return w
  }
  if (path === '/logs/weight' && method === 'GET') return { items: weights }
  if (path === '/logs/weight' && method === 'POST') {
    const input = body as WeightInput
    const date = input.logged_for ?? todayISO()
    const existing = weights.find((w) => w.logged_for === date)
    if (existing) {
      existing.weight_kg = input.weight_kg
      return existing
    }
    const w: Weight = { id: nextId('weight'), logged_for: date, weight_kg: input.weight_kg }
    weights.push(w)
    return w
  }

  // ---- exercises ----
  if (path === '/exercises' && method === 'GET') {
    const q = (query.get('q') ?? '').toLowerCase()
    const muscle = query.get('muscle') ?? ''
    const equipment = query.get('equipment') ?? ''
    let list = exercises
    if (q) list = list.filter((e) => e.name.toLowerCase().includes(q))
    if (muscle) list = list.filter((e) => e.primary_muscle === muscle || e.secondary_muscles.includes(muscle))
    if (equipment) list = list.filter((e) => e.equipment === equipment)
    const limit = Number(query.get('limit') ?? 50)
    const offset = Number(query.get('offset') ?? 0)
    return { items: list.slice(offset, offset + limit) }
  }
  if (seg[0] === 'exercises' && seg[1] && method === 'GET') {
    const ex = exercises.find((e) => e.id === Number(seg[1]))
    if (!ex) throw new ApiError(404, 'Exercise not found')
    return ex
  }
  if (path === '/exercises' && method === 'POST') {
    const ex: Exercise = { id: nextId('exercise'), is_custom: true, ...(body as ExerciseInput) }
    exercises.push(ex)
    return ex
  }

  // ---- workouts ----
  if (path === '/workouts' && method === 'GET') {
    const items: WorkoutSummary[] = workouts
      .slice()
      .sort((a, b) => b.date.localeCompare(a.date))
      .map((w) => ({ id: w.id, date: w.date, name: w.name, set_count: w.sets.length, total_volume: Math.round(w.sets.reduce((s, x) => s + x.weight * x.reps, 0)) }))
    return { items }
  }
  if (path === '/workouts' && method === 'POST') {
    const b = (body ?? {}) as { date?: string; name?: string; program_day_id?: number; notes?: string }
    const w: WorkoutSession = { id: nextId('workout'), date: b.date ?? todayISO(), name: b.name, program_day_id: b.program_day_id, notes: b.notes, sets: [] }
    workouts.push(w)
    return w
  }
  if (seg[0] === 'workouts' && seg[1] && seg.length === 2 && method === 'GET') {
    const w = workouts.find((x) => x.id === Number(seg[1]))
    if (!w) throw new ApiError(404, 'Workout not found')
    return w
  }
  if (seg[0] === 'workouts' && seg[1] && seg.length === 2 && method === 'PUT') {
    const w = workouts.find((x) => x.id === Number(seg[1]))
    if (!w) throw new ApiError(404, 'Workout not found')
    Object.assign(w, body as object)
    return w
  }
  if (seg[0] === 'workouts' && seg[1] && seg.length === 2 && method === 'DELETE') {
    const idx = workouts.findIndex((x) => x.id === Number(seg[1]))
    if (idx >= 0) workouts.splice(idx, 1)
    return { ok: true }
  }
  if (seg[0] === 'workouts' && seg[2] === 'sets' && seg.length === 3 && method === 'POST') {
    const w = workouts.find((x) => x.id === Number(seg[1]))
    if (!w) throw new ApiError(404, 'Workout not found')
    const input = body as SetInput
    const set = { id: nextId('set'), set_index: input.set_index ?? w.sets.length, is_warmup: false, ...input }
    w.sets.push(set)
    return set
  }
  if (seg[0] === 'workouts' && seg[2] === 'sets' && seg[3] && method === 'PUT') {
    const w = workouts.find((x) => x.id === Number(seg[1]))
    if (!w) throw new ApiError(404, 'Workout not found')
    const idx = w.sets.findIndex((s) => s.id === Number(seg[3]))
    if (idx < 0) throw new ApiError(404, 'Set not found')
    w.sets[idx] = { ...w.sets[idx], ...(body as SetInput) }
    return w.sets[idx]
  }
  if (seg[0] === 'workouts' && seg[2] === 'sets' && seg[3] && method === 'DELETE') {
    const w = workouts.find((x) => x.id === Number(seg[1]))
    if (!w) throw new ApiError(404, 'Workout not found')
    const idx = w.sets.findIndex((s) => s.id === Number(seg[3]))
    if (idx >= 0) w.sets.splice(idx, 1)
    return { ok: true }
  }

  // ---- performance ----
  if (path === '/performance/summary' && method === 'GET') return performanceSummary()
  if (path === '/performance/prs' && method === 'GET') return { items: prList() }
  if (path === '/performance/volume' && method === 'GET') return volumeReport()
  if (seg[0] === 'performance' && seg[1] === 'exercise' && seg[2] && method === 'GET') {
    return exercisePerformance(Number(seg[2]))
  }

  // ---- programs ----
  if (path === '/programs/generate' && method === 'POST') {
    const fresh = buildProgram()
    fresh.id = nextId('program')
    programs.forEach((p) => (p.active = false))
    fresh.active = true
    programs.push(fresh)
    return fresh
  }
  if (path === '/programs/today' && method === 'GET') return todayWorkout()
  if (path === '/programs/active' && method === 'GET') {
    const active = programs.find((p) => p.active)
    if (!active) throw new ApiError(404, 'No active program')
    return active
  }
  if (path === '/programs' && method === 'GET') {
    const items: ProgramSummary[] = programs.map((p) => ({ id: p.id, name: p.name, training_goal: p.training_goal, split_type: p.split_type, days_per_week: p.days_per_week, active: p.active }))
    return { items }
  }
  if (seg[0] === 'programs' && seg[1] && seg.length === 2 && method === 'GET') {
    const p = programs.find((x) => x.id === Number(seg[1]))
    if (!p) throw new ApiError(404, 'Program not found')
    return p
  }
  if (seg[0] === 'programs' && seg[1] && seg.length === 2 && method === 'PUT') {
    const p = programs.find((x) => x.id === Number(seg[1]))
    if (!p) throw new ApiError(404, 'Program not found')
    const b = body as Partial<Program> & { active?: boolean }
    if (b.active) programs.forEach((x) => (x.active = false))
    Object.assign(p, b)
    return p
  }
  if (seg[0] === 'programs' && seg[1] && seg.length === 2 && method === 'DELETE') {
    const idx = programs.findIndex((x) => x.id === Number(seg[1]))
    if (idx >= 0) programs.splice(idx, 1)
    return { ok: true }
  }

  // ---- nutrition ----
  if (path === '/nutrition/plan/generate' && method === 'POST') {
    nutritionPlan = { id: nextId('plan'), goal: profile?.goal ?? 'maintain', target_kcal: 2100, protein_g: 140, carbs_g: 230, fat_g: 65, meals_per_day: 4, active: true }
    return nutritionPlan
  }
  if (path === '/nutrition/plan/active' && method === 'GET') {
    if (!nutritionPlan) throw new ApiError(404, 'No active plan')
    return nutritionPlan
  }
  if (path === '/nutrition/today' && method === 'GET') return nutritionToday()

  // ---- recommendations & AI ----
  if (path === '/recommendations/today' && method === 'GET') {
    const rec: RecommendationsToday = {
      workout: todayWorkout(),
      nutrition: nutritionToday(),
      tip: 'You are trending 8% below your protein target this week — front-load protein at breakfast to make hitting 140g easier.',
    }
    return rec
  }
  if (path === '/recommendations/adaptive' && method === 'GET') {
    return adaptiveEnvelope()
  }
  if (path === '/recommendations/meals' && method === 'GET') {
    const cat = query.get('category') as MealCategory | null
    const limit = query.get('limit') ? Number(query.get('limit')) : 3
    return adaptiveMeals(cat ?? undefined, limit)
  }
  if (path === '/recommendations/workout' && method === 'GET') {
    const pid = query.get('program_day_id')
    return adaptiveWorkout(pid ? Number(pid) : undefined)
  }
  if (path === '/ai/insights' && method === 'GET') {
    const data: AiInsights = {
      typical_times: { breakfast: '08:10', lunch: '13:00', dinner: '19:20', snack: '16:15' },
      top_foods: {
        breakfast: [{ name: 'greek yogurt & berries', count: 9, avg_kcal: 320 }, { name: 'oats', count: 5, avg_kcal: 410 }],
        lunch: [{ name: 'chicken rice bowl', count: 11, avg_kcal: 620 }],
        dinner: [{ name: 'salmon & greens', count: 7, avg_kcal: 560 }],
        snack: [{ name: 'protein shake', count: 8, avg_kcal: 180 }],
      },
      avg_kcal: { breakfast: 360, lunch: 620, dinner: 640, snack: 190 },
      avg_macros: {
        breakfast: { protein_g: 26, carbs_g: 40, fat_g: 9 },
        lunch: { protein_g: 46, carbs_g: 62, fat_g: 17 },
        dinner: { protein_g: 42, carbs_g: 45, fat_g: 24 },
        snack: { protein_g: 22, carbs_g: 10, fat_g: 4 },
      },
      meals_per_day: 3.4,
      days_observed: 21,
      total_meals: 72,
    }
    return data
  }
  if (path === '/ai/predict-next-meal' && method === 'GET') {
    const data: PredictNextMeal = {
      predicted_time: '19:20',
      predicted_category: 'dinner',
      suggested_kcal: 640,
      kcal_remaining: 980,
      kcal_eaten_today: 1120,
      median_interval_hours: 4.5,
      macro_gap: { protein_g: 34, carbs_g: 120, fat_g: 38 },
      macro_targets: { protein_g: 140, carbs_g: 230, fat_g: 65 },
      typical_kcal_for_category: 620,
      recommendations: [
        { name: 'Grilled salmon & rice', category: 'dinner', kcal: 640, protein_g: 42, carbs_g: 60, fat_g: 20, logged_count: 6 },
        { name: 'Chicken rice bowl', category: 'dinner', kcal: 620, protein_g: 48, carbs_g: 70, fat_g: 16, logged_count: 11 },
      ],
      pattern_summary: { days_observed: 21, meals_per_day: 3.4, typical_times: { breakfast: '08:10', lunch: '13:00', dinner: '19:20' } },
    }
    return data
  }
  if (path === '/ai/recommend-foods' && method === 'GET') {
    const data: RecommendFoods = {
      macro_gap: { protein_g: 34, carbs_g: 120, fat_g: 38 },
      macro_targets: { protein_g: 140, carbs_g: 230, fat_g: 65 },
      recommendations: [
        { name: 'Grilled chicken breast', category: 'lunch', kcal: 165, protein_g: 31, carbs_g: 0, fat_g: 4, logged_count: 12 },
        { name: 'Greek yogurt (0%)', category: 'snack', kcal: 90, protein_g: 17, carbs_g: 6, fat_g: 0, logged_count: 9 },
        { name: 'Lentils', category: 'dinner', kcal: 180, protein_g: 13, carbs_g: 30, fat_g: 1, logged_count: 4 },
      ],
    }
    return data
  }
  if (path === '/ai/chat' && method === 'POST') {
    const msg = ((body as { message?: string }).message ?? '').toLowerCase()
    let reply = "I read your logs directly. Ask me about your training, nutrition targets, or what to eat next."
    let intent = 'general'
    const chips = ['What should I eat next?', 'How is my bench progressing?', 'Am I hitting protein?']
    if (msg.includes('eat') || msg.includes('meal') || msg.includes('protein')) {
      const n = nutritionToday()
      reply = `You have ${Math.max(0, n.remaining.kcal)} kcal and ${Math.max(0, n.remaining.protein_g)}g protein left today. A lean protein + carb dinner like salmon and rice fits well.`
      intent = 'nutrition'
    } else if (msg.includes('bench') || msg.includes('squat') || msg.includes('progress') || msg.includes('1rm')) {
      const b = bestForExercise(2)
      reply = `Your best estimated bench 1RM is ${b?.best_e1rm ?? 0}kg. You're using RPE autoregulation — pick a load that leaves ~2 reps in reserve at your target reps, and nudge it up as it feels easier.`
      intent = 'training'
    } else if (msg.includes('workout') || msg.includes('today')) {
      const t = todayWorkout()
      reply = t.rest_day ? 'Today is a rest day — prioritise sleep and hydration.' : `Today is ${t.name}. Start with your main lift and aim for RPE 8.`
      intent = 'training'
    }
    const data: ChatResponse = { reply, intent, chips }
    return data
  }
  if (path === '/ai/parse-log' && method === 'POST') {
    const text = ((body as { text?: string }).text ?? '').trim()
    const kcalMatch = text.match(/(\d+)\s?(kcal|cal)/i)
    const kcal = kcalMatch ? Number(kcalMatch[1]) : 350
    const lower = text.toLowerCase()
    const category = lower.includes('breakfast') ? 'breakfast' : lower.includes('lunch') ? 'lunch' : lower.includes('dinner') ? 'dinner' : 'snack'
    const data: ParseLogResult = {
      name: text.replace(/\d+\s?(kcal|cal)/i, '').trim() || 'Logged meal',
      kcal,
      category,
      protein_g: Math.round(kcal * 0.08),
      carbs_g: Math.round(kcal * 0.1),
      fat_g: Math.round(kcal * 0.03),
    }
    return data
  }

  // ---- insights ----
  if (path === '/insights/today' && method === 'GET') {
    const n = nutritionToday()
    // Derive movement rollups from the same in-memory logs the dashboard reads,
    // so the ring inputs and this summary always agree (no contradictory numbers).
    const stepsToday = steps[0]?.steps ?? 0
    const waterToday = waters.reduce((s, w) => s + w.ml, 0)
    const exerciseToday = activities.reduce((s, a) => s + a.minutes, 0)
    const kcalOutActivity = Math.round(exerciseToday * 7)
    const kcalOutSteps = Math.round(stepsToday * 0.04)
    const data: InsightsToday = {
      bmr: 1420,
      tdee: 2050,
      target_kcal: n.targets.kcal,
      kcal_in: n.consumed.kcal,
      kcal_out_activity: kcalOutActivity,
      kcal_out_steps: kcalOutSteps,
      net_kcal: Math.round(n.consumed.kcal - kcalOutActivity - kcalOutSteps),
      remaining_to_target: Math.round(n.targets.kcal - n.consumed.kcal),
      sleep_hours: sleeps[0]?.hours ?? 7.4,
      steps: stepsToday,
      exercise_minutes: exerciseToday,
      water_ml: waterToday,
      macros: { protein_g: n.consumed.protein_g, carbs_g: n.consumed.carbs_g, fat_g: n.consumed.fat_g },
      goals: {
        water_goal_ml: profile?.water_goal_ml ?? 2500,
        step_goal: profile?.step_goal ?? 8000,
        exercise_goal_min: profile?.exercise_goal_min ?? 45,
      },
    }
    return data
  }
  if (path === '/insights/circadian' && method === 'GET') {
    const data: Circadian = {
      wake_time: profile?.wake_time ?? '07:00',
      first_meal: '08:30',
      last_meal: '18:30',
      sleep_target: '21:30',
      eating_window_hours: 10,
      tips: [
        'Get 10-20 minutes of morning sunlight to anchor your circadian rhythm.',
        'Aim for your first meal around 08:30 once cortisol naturally rises.',
        'Try to finish your last meal by 18:30 so digestion is not competing with sleep.',
        'Caffeine half-life is ~5-6h. Cut it 8-10h before bed.',
      ],
    }
    return data
  }
  if (path === '/insights/trends' && method === 'GET') return trends(Number(query.get('days') ?? 14))
  if (path === '/insights/heatmap' && method === 'GET') return heatmap(Number(query.get('days') ?? 84))
  if (path === '/insights/streaks' && method === 'GET') {
    const data: Streaks = { meal_streak: 12, activity_streak: 6, sleep_streak: 9, water_streak: 4, workout_streak: 5, any_streak: 14 }
    return data
  }
  if (path === '/insights/achievements' && method === 'GET') {
    const data: Achievements = {
      badges: [
        { id: 'first_meal', label: 'First Bite', icon: '', color: '#0e8aa3', earned: true, current: 72, target: 1, progress: 1 },
        { id: 'ten_workouts', label: 'Athlete', icon: '', color: '#7c78f0', earned: true, current: 14, target: 10, progress: 1 },
        { id: 'week_streak', label: 'Consistent', icon: '', color: '#7cb518', earned: true, current: 14, target: 7, progress: 1 },
        { id: 'consistent_lifter', label: 'Consistent Lifter', icon: '', color: '#5b57e0', earned: false, current: 5, target: 7, progress: 5 / 7 },
        { id: 'hydration_master', label: 'Hydration Hero', icon: '', color: '#38bdf8', earned: false, current: 32000, target: 50000, progress: 0.64 },
      ],
    }
    return data
  }

  // ---- admin ----
  if (path === '/admin/seed-demo' && method === 'POST') return { ok: true }
  if (path === '/admin/reset' && method === 'POST') {
    meals.length = 0
    activities.length = 0
    waters.length = 0
    return { ok: true }
  }

  throw new ApiError(404, `Mock: no handler for ${method} ${path}`)
}
