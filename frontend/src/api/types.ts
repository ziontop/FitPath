/* ============================================================
   API types — mirror docs/API-CONTRACT.md (v1)
   ============================================================ */

// ---- Enums ----
export type Sex = 'male' | 'female'
export type ActivityLevel = 'sedentary' | 'light' | 'moderate' | 'active' | 'very_active'
export type NutritionGoal = 'lose' | 'maintain' | 'gain'
export type TrainingGoal = 'powerlifting' | 'hypertrophy' | 'maingain'
export type ExperienceLevel = 'beginner' | 'intermediate' | 'advanced'
export type Equipment = 'full_gym' | 'home_basic' | 'bodyweight'
export type MealCategory = 'breakfast' | 'lunch' | 'dinner' | 'snack'
export type Intensity = 'light' | 'moderate' | 'vigorous'
export type ExerciseCategory = 'compound' | 'isolation'
export type Units = 'metric' | 'imperial'
export type AppleHealthImportType = 'steps' | 'weight' | 'sleep' | 'water' | 'workouts'

// ---- Auth ----
export interface User {
  id: number
  email: string
  username: string
  created_at: string
}

export interface RegisterPayload {
  email: string
  username: string
  password: string
}

export interface LoginPayload {
  identifier: string
  password: string
}

// ---- Profile ----
export interface Profile {
  name?: string
  sex: Sex
  age: number
  height_cm: number
  weight_kg: number
  activity_level: ActivityLevel
  goal: NutritionGoal
  training_goal: TrainingGoal
  experience_level: ExperienceLevel
  days_per_week: number
  equipment: Equipment
  units: Units
  wake_time: string
  water_goal_ml: number
  step_goal: number
  exercise_goal_min: number
}

// ---- Health / nutrition logs ----
export interface Meal {
  id: number
  name: string
  kcal: number
  category: MealCategory
  protein_g?: number
  carbs_g?: number
  fat_g?: number
  eaten_at?: string
  favorite?: boolean
}
export type MealInput = Omit<Meal, 'id' | 'favorite'>

export interface MealQuickItem {
  name: string
  category: MealCategory
  kcal: number
  protein_g?: number
  carbs_g?: number
  fat_g?: number
  last_at?: string
  times?: number
  favorite?: boolean
}

export interface MealQuickLists {
  recent: MealQuickItem[]
  favorites: MealQuickItem[]
  frequent: MealQuickItem[]
}

export interface Activity {
  id: number
  activity: string
  minutes: number
  intensity: Intensity
  done_at?: string
}
export type ActivityInput = Omit<Activity, 'id'>

export interface Sleep {
  id: number
  hours: number
  wake_time: string
  logged_for?: string
}
export type SleepInput = Omit<Sleep, 'id'>

export interface Step {
  id: number
  steps: number
  logged_for?: string
}
export type StepInput = Omit<Step, 'id'>

export interface Water {
  id: number
  ml: number
  logged_at?: string
}
export type WaterInput = Omit<Water, 'id'>

export interface Weight {
  id: number
  weight_kg: number
  logged_for?: string
}
export type WeightInput = Omit<Weight, 'id'>

// ---- Exercises ----
export interface Exercise {
  id: number
  name: string
  category: ExerciseCategory
  primary_muscle: string
  secondary_muscles: string[]
  equipment: Equipment
  is_main_lift: boolean
  is_custom: boolean
}
export type ExerciseQuery = {
  muscle?: string
  equipment?: Equipment
  q?: string
  limit?: number
  offset?: number
}
export type ExerciseInput = Omit<Exercise, 'id' | 'is_custom'>

// ---- Workouts & sets ----
export interface SetLog {
  id: number
  exercise_id: number
  weight: number
  reps: number
  rpe?: number
  is_warmup?: boolean
  set_index?: number
}
export type SetInput = Omit<SetLog, 'id'>

export interface WorkoutSession {
  id: number
  date: string
  name?: string
  program_day_id?: number
  notes?: string
  sets: SetLog[]
}
export interface WorkoutSummary {
  id: number
  date: string
  name?: string
  set_count: number
  total_volume: number
}
export interface WorkoutInput {
  date?: string
  name?: string
  program_day_id?: number
  notes?: string
}

// ---- Performance analytics ----
export interface E1rmHighlight {
  exercise_id: number
  exercise_name: string
  e1rm: number
}
export interface PerformanceSummary {
  total_volume: number
  sessions_count: number
  prs_count: number
  e1rm_highlights: E1rmHighlight[]
}
export interface PrRecord {
  exercise_id: number
  exercise_name: string
  best_e1rm: number
  best_weight: number
  best_reps: number
  achieved_at: string | null
}
export interface TrendPoint {
  date: string
  value: number
}
export interface ExerciseHistoryEntry {
  date: string
  weight: number
  reps: number
  rpe?: number
  e1rm: number
}
export interface ExercisePerformance {
  exercise_id: number
  exercise_name: string
  history: ExerciseHistoryEntry[]
  e1rm_trend: TrendPoint[]
  volume_trend: TrendPoint[]
  best: PrRecord
}
export interface MuscleVolume {
  muscle: string
  sets: number
  volume: number
}
export interface VolumeReport {
  weeks: { week_start: string; muscles: MuscleVolume[]; total_volume: number }[]
}

// ---- Programs ----
export type ProgressionScheme = 'linear' | 'double' | 'rpe_autoreg' | 'block' | string
export interface ProgramExercise {
  exercise_id: number
  name: string
  target_sets: number
  target_reps: string
  target_rpe: number
  rest_seconds: number
  progression: ProgressionScheme
}
export interface ProgramDay {
  id: number
  day_index: number
  name: string
  exercises: ProgramExercise[]
}
export interface Program {
  id: number
  name: string
  training_goal: TrainingGoal
  split_type: string
  days_per_week: number
  active: boolean
  days: ProgramDay[]
}
export interface ProgramSummary {
  id: number
  name: string
  training_goal: TrainingGoal
  split_type: string
  days_per_week: number
  active: boolean
}
export interface GenerateProgramInput {
  training_goal?: TrainingGoal
  days_per_week?: number
  experience?: ExperienceLevel
  equipment?: Equipment
}

/** today's recommended session (or a rest day). */
export interface TodayExercise extends ProgramExercise {
  suggested_weight?: number
}
export interface TodayWorkout {
  rest_day?: boolean
  program_day_id?: number
  name?: string
  exercises?: TodayExercise[]
}

// ---- Nutrition plan & daily targets ----
export interface Macros {
  kcal: number
  protein_g: number
  carbs_g: number
  fat_g: number
}
export interface NutritionPlan {
  id: number
  goal: NutritionGoal
  target_kcal: number
  protein_g: number
  carbs_g: number
  fat_g: number
  meals_per_day: number
  active: boolean
}
export interface MealSuggestion {
  name: string
  kcal: number
  protein_g?: number
  carbs_g?: number
  fat_g?: number
}
export interface NutritionToday {
  targets: Macros
  consumed: Macros
  remaining: Macros
  meal_suggestions: MealSuggestion[]
}

// ---- Recommendations & AI ----
export interface RecommendationsToday {
  workout: TodayWorkout
  nutrition: NutritionToday
  tip: string
}
export interface TopFood {
  name: string
  count: number
  avg_kcal: number
}
export interface CategoryMacros {
  protein_g: number
  carbs_g: number
  fat_g: number
}
/** Meal-pattern analysis from GET /ai/insights (coach.analyze_patterns). */
export interface AiInsights {
  typical_times: Record<string, string>
  top_foods: Record<string, TopFood[]>
  avg_kcal: Record<string, number>
  avg_macros: Record<string, CategoryMacros>
  meals_per_day: number
  days_observed: number
  total_meals: number
}
export interface FoodRec {
  name: string
  category?: string
  kcal: number
  protein_g: number
  carbs_g: number
  fat_g: number
  logged_count?: number
}
export interface PredictNextMeal {
  predicted_time: string
  predicted_category: string
  suggested_kcal: number
  kcal_remaining: number
  kcal_eaten_today: number
  median_interval_hours: number
  macro_gap: CategoryMacros
  macro_targets: CategoryMacros
  typical_kcal_for_category: number
  recommendations: FoodRec[]
  pattern_summary: {
    days_observed: number
    meals_per_day: number
    typical_times: Record<string, string>
  }
}
export interface RecommendFoods {
  macro_gap: CategoryMacros
  macro_targets: CategoryMacros
  recommendations: FoodRec[]
}

// ---- Adaptive recommendations (docs/ADAPTIVE-RECOMMENDATIONS.md §6.4) ----
// These mirror the live Pydantic models in app/schemas.py 1:1 and reuse the
// existing `Macros` and `MealCategory` types.
export type Confidence = 'low' | 'medium' | 'high'
export type WorkoutAction = 'start' | 'increase' | 'hold' | 'reduce' | 'deload'
export type Direction = 'up' | 'down' | 'flat'
export type Consistency = 'on_track' | 'inconsistent' | 'returning'

export interface MealPayload {
  name: string
  kcal: number
  category: MealCategory
  protein_g?: number
  carbs_g?: number
  fat_g?: number
}

export interface MealScoreComponents {
  macro_fit: number
  recency: number
  frequency: number
  adherence: number
  category_fit: number
  favorite: number
}

export interface AdaptiveMealSuggestion {
  name: string
  category: MealCategory
  kcal: number
  protein_g: number
  carbs_g: number
  fat_g: number
  portion: number
  score: number
  components: MealScoreComponents
  reason: string
  history_basis: string
  confidence: Confidence
  logged_count: number
  last_eaten_at?: string | null
  meal_payload: MealPayload
}

export interface NextMealHint {
  predicted_category: MealCategory
  predicted_time: string
  suggested_kcal: number
}

export interface MealHistoryBasis {
  window_days: number
  days_observed: number
  total_meals: number
  distinct_foods: number
  adherent_days: number
}

export interface AdaptiveMealsBlock {
  version: string
  algorithm: string
  targets: Macros
  consumed: Macros
  remaining: Macros
  next_meal: NextMealHint
  history_basis: MealHistoryBasis
  confidence: Confidence
  suggestions: AdaptiveMealSuggestion[]
}

export interface LastPerformance {
  date: string
  weight: number
  reps: number
  rpe?: number | null
  sets: number
  e1rm: number
}

export interface WeightChange {
  weight_delta_kg: number
  reps_delta: number
  direction: Direction
}

export interface E1rmTrendMini {
  first: number
  last: number
  direction: Direction
}

export interface AdaptiveExerciseRec {
  exercise_id: number
  name: string
  action: WorkoutAction
  suggested_weight?: number | null
  target_sets: number
  target_reps: string
  target_rpe?: number | null
  deload: boolean
  last_performance?: LastPerformance | null
  change: WeightChange
  e1rm_trend?: E1rmTrendMini | null
  confidence: Confidence
  reason: string
  history_basis: string
}

export interface WorkoutAdherence {
  sessions_last_14d: number
  scheduled_days_per_week: number
  consistency: Consistency
}

export interface AdaptiveWorkoutBlock {
  version: string
  algorithm: string
  rest_day: boolean
  program_day_id?: number | null
  name?: string | null
  deload: boolean
  confidence: Confidence
  adherence?: WorkoutAdherence | null
  reason: string
  exercises: AdaptiveExerciseRec[]
}

export interface AdaptiveRecommendation {
  version: string
  algorithm: string
  generated_at: string
  meals: AdaptiveMealsBlock
  workout: AdaptiveWorkoutBlock
  tip: string
}
export interface ChatResponse {
  reply: string
  intent: string
  chips: string[]
  suggestions?: string[]
}
export interface ParseLogItem {
  name: string
  qty: number
  unit: string
  kcal: number
  p: number
  c: number
  f: number
  source: string
}
export interface ParseLogResult {
  name: string
  kcal: number
  category: MealCategory
  protein_g?: number
  carbs_g?: number
  fat_g?: number
  items?: ParseLogItem[]
  unmatched?: string[]
  confidence?: string
  note?: string
}

// ---- Insights ----
/** Daily rollup from GET /insights/today. */
export interface InsightsToday {
  bmr: number
  tdee: number
  target_kcal: number
  kcal_in: number
  kcal_out_activity: number
  kcal_out_steps: number
  net_kcal: number
  remaining_to_target: number
  sleep_hours: number | null
  steps: number
  exercise_minutes: number
  water_ml: number
  macros: CategoryMacros
  goals: {
    water_goal_ml: number
    step_goal: number
    exercise_goal_min: number
  }
}
export interface Circadian {
  wake_time: string
  first_meal: string
  last_meal: string
  sleep_target: string
  eating_window_hours: number
  tips: string[]
}
export interface Trends {
  days: {
    date: string
    kcal_in?: number
    protein_g?: number
    carbs_g?: number
    fat_g?: number
    exercise_min?: number
    kcal_out_activity?: number
    weight_kg?: number
    sleep_hours?: number | null
    steps?: number
    water_ml?: number
  }[]
}
export interface Streaks {
  meal_streak: number
  activity_streak: number
  sleep_streak: number
  water_streak: number
  workout_streak: number
  any_streak: number
}
export interface Badge {
  id: string
  label: string
  icon: string
  color: string
  earned: boolean
  current: number
  target: number
  progress: number
}
export interface Achievements {
  badges: Badge[]
}
export interface HeatmapDay {
  date: string
  level: 0 | 1 | 2 | 3 | 4
  minutes?: number
}
export interface Heatmap {
  days: HeatmapDay[]
}

// ---- Generic wrappers ----
export interface ListResponse<T> {
  items: T[]
}
export interface OkResponse {
  ok: boolean
}
export interface FavoriteResponse {
  ok: boolean
  favorite: boolean
}
export interface ApiError {
  detail: string
}

// ---- Apple Health integration ----
export type AppleHealthCounts = Record<AppleHealthImportType, number>
export type AppleHealthUnitsDetected = Partial<Record<AppleHealthImportType, string[]>>
export type AppleHealthDateRange = { start: string | null; end: string | null }
export interface AppleHealthPreview {
  filename: string
  date_range: AppleHealthDateRange
  counts_by_type: AppleHealthCounts
  units_detected: AppleHealthUnitsDetected
  samples: Partial<Record<AppleHealthImportType, Record<string, unknown>[]>>
  warnings: string[]
}
export interface AppleHealthResultCounts {
  inserted: number
  updated: number
  skipped: number
  invalid: number
  conflict: number
}
export type AppleHealthImportResults = Record<AppleHealthImportType, AppleHealthResultCounts>
export interface AppleHealthImportResponse {
  batch_id: number
  source: 'export'
  status: 'completed' | 'partial' | 'failed'
  date_range: AppleHealthDateRange
  results: AppleHealthImportResults
  totals: AppleHealthResultCounts
}
export interface AppleHealthImportBatch {
  id: number
  source: 'export' | 'shortcut'
  status: 'running' | 'completed' | 'partial' | 'failed'
  date_range: AppleHealthDateRange
  records_inserted: number
  records_updated: number
  records_skipped: number
  records_invalid: number
  records_conflict?: number
  created_at: string
  completed_at?: string | null
  error?: string | null
}
export interface AppleHealthDeleteRequest {
  types?: AppleHealthImportType[]
  from?: string
  to?: string
}
export interface AppleHealthDeleteResponse {
  deleted: Partial<AppleHealthCounts>
  preserved_modified: Partial<AppleHealthCounts>
  provenance_removed: number
}
export interface AppleHealthToken {
  id: number
  name: string
  prefix: string
  created_at: string
  last_used_at?: string | null
  expires_at?: string | null
  revoked_at?: string | null
}
export interface AppleHealthTokenCreate {
  name: string
  expires_in_days?: number
}
export interface AppleHealthTokenSecret extends AppleHealthToken {
  token: string
}
