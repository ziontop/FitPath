/* Shared, typed fixtures for adaptive-recommendation UI tests.
   Not a spec file — vitest only runs *.test.* so this is import-only. */
import type {
  AdaptiveExerciseRec,
  AdaptiveMealSuggestion,
  AdaptiveMealsBlock,
  AdaptiveRecommendation,
  AdaptiveWorkoutBlock,
  Macros,
  NutritionToday,
  Profile,
  RecommendationsToday,
  TodayWorkout,
} from '../api'

const macros = (kcal: number, p: number, c: number, f: number): Macros => ({ kcal, protein_g: p, carbs_g: c, fat_g: f })

export function makeProfile(over: Partial<Profile> = {}): Profile {
  return {
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
    ...over,
  }
}

export function makeTodayWorkout(over: Partial<TodayWorkout> = {}): TodayWorkout {
  return {
    rest_day: false,
    program_day_id: 10,
    name: 'Upper A',
    exercises: [
      { exercise_id: 2, name: 'Bench Press', target_sets: 4, target_reps: '6-10', target_rpe: 8, rest_seconds: 150, progression: 'rpe_autoreg', suggested_weight: 60 },
    ],
    ...over,
  }
}

export function makeNutritionToday(over: Partial<NutritionToday> = {}): NutritionToday {
  return {
    targets: macros(2100, 140, 230, 65),
    consumed: macros(1120, 106, 110, 27),
    remaining: macros(980, 34, 120, 38),
    meal_suggestions: [],
    ...over,
  }
}

export function makeRecommendationsToday(over: Partial<RecommendationsToday> = {}): RecommendationsToday {
  return {
    workout: makeTodayWorkout(),
    nutrition: makeNutritionToday(),
    tip: 'Front-load protein at breakfast to make hitting 140g easier.',
    ...over,
  }
}

export function makeMealSuggestion(over: Partial<AdaptiveMealSuggestion> = {}): AdaptiveMealSuggestion {
  const base: AdaptiveMealSuggestion = {
    name: 'Grilled salmon & rice',
    category: 'dinner',
    kcal: 480,
    protein_g: 31.5,
    carbs_g: 45,
    fat_g: 15,
    portion: 0.75,
    score: 0.62,
    components: { macro_fit: 0.9, recency: 0.9, frequency: 0.7, adherence: 0.72, category_fit: 1, favorite: 1 },
    reason: "Fits your remaining 38g fat / 34g protein gap, a go-to dinner you've logged 7×, and it's a favorite.",
    history_basis: 'From 72 meals over 21 days · eaten 7× (last 2 days ago) · on 6 of 7 logged day(s) on-target.',
    confidence: 'high',
    logged_count: 7,
    last_eaten_at: '2026-07-12T19:20',
    meal_payload: { name: 'Grilled salmon & rice', kcal: 480, category: 'dinner', protein_g: 31.5, carbs_g: 45, fat_g: 15 },
  }
  const merged = { ...base, ...over }
  // Keep the payload consistent with the (possibly overridden) macros unless the
  // caller supplied one explicitly.
  if (!over.meal_payload) {
    merged.meal_payload = { name: merged.name, kcal: merged.kcal, category: merged.category, protein_g: merged.protein_g, carbs_g: merged.carbs_g, fat_g: merged.fat_g }
  }
  return merged
}

export function makeMealsBlock(over: Partial<AdaptiveMealsBlock> = {}): AdaptiveMealsBlock {
  return {
    version: 'adaptive-v1',
    algorithm: 'history-adaptive-deterministic',
    targets: macros(2100, 140, 230, 65),
    consumed: macros(1120, 106, 110, 27),
    remaining: macros(980, 34, 120, 38),
    next_meal: { predicted_category: 'dinner', predicted_time: '19:20', suggested_kcal: 640 },
    history_basis: { window_days: 30, days_observed: 21, total_meals: 72, distinct_foods: 14, adherent_days: 12 },
    confidence: 'high',
    suggestions: [makeMealSuggestion()],
    ...over,
  }
}

export function makeExerciseRec(over: Partial<AdaptiveExerciseRec> = {}): AdaptiveExerciseRec {
  return {
    exercise_id: 2,
    name: 'Bench Press',
    action: 'increase',
    suggested_weight: 62.5,
    target_sets: 4,
    target_reps: '6-10',
    target_rpe: 8,
    deload: false,
    last_performance: { date: '2026-07-12', weight: 60, reps: 10, rpe: 8, sets: 3, e1rm: 80 },
    change: { weight_delta_kg: 2.5, reps_delta: -4, direction: 'up' },
    e1rm_trend: { first: 72, last: 80, direction: 'up' },
    confidence: 'high',
    reason: 'You hit 10 reps @ RPE 8 last time (top of range with reps to spare) — adding 2.5 kg to 62.5 kg and resetting to 6 reps.',
    history_basis: 'Based on your last 5 Bench Press session(s); e1RM 72 → 80 kg.',
    ...over,
  }
}

export function makeWorkoutBlock(over: Partial<AdaptiveWorkoutBlock> = {}): AdaptiveWorkoutBlock {
  return {
    version: 'adaptive-v1',
    algorithm: 'history-adaptive-deterministic',
    rest_day: false,
    program_day_id: 10,
    name: 'Upper A',
    deload: false,
    confidence: 'high',
    adherence: { sessions_last_14d: 8, scheduled_days_per_week: 4, consistency: 'on_track' },
    reason: 'Upper A: work up to Bench Press at the prescribed RPE; loads below are adapted from your recent logs.',
    exercises: [makeExerciseRec()],
    ...over,
  }
}

export function makeEnvelope(over: Partial<AdaptiveRecommendation> = {}): AdaptiveRecommendation {
  return {
    version: 'adaptive-v1',
    algorithm: 'history-adaptive-deterministic',
    generated_at: '2026-07-14T18:40:00',
    meals: makeMealsBlock(),
    workout: makeWorkoutBlock(),
    tip: 'Today is Upper A — work up to Bench Press at RPE 8 (try 62.5 kg). You have 980 kcal and 34 g protein left; a grilled salmon & rice would close most of it.',
    ...over,
  }
}
