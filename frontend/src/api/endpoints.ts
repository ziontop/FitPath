import { http, toQuery } from './client'
import type {
  Achievements,
  Activity,
  ActivityInput,
  AdaptiveMealsBlock,
  AdaptiveRecommendation,
  AdaptiveWorkoutBlock,
  AiInsights,
  ChatResponse,
  Circadian,
  Exercise,
  ExerciseInput,
  ExerciseQuery,
  ExercisePerformance,
  FavoriteResponse,
  Heatmap,
  InsightsToday,
  ListResponse,
  LoginPayload,
  Meal,
  MealInput,
  MealCategory,
  MealQuickLists,
  NutritionPlan,
  NutritionToday,
  OkResponse,
  ParseLogResult,
  PerformanceSummary,
  PredictNextMeal,
  Profile,
  Program,
  ProgramSummary,
  PrRecord,
  RecommendFoods,
  RecommendationsToday,
  RegisterPayload,
  Sleep,
  SleepInput,
  Step,
  StepInput,
  Streaks,
  TodayWorkout,
  Trends,
  User,
  VolumeReport,
  Water,
  WaterInput,
  Weight,
  WeightInput,
  WorkoutInput,
  WorkoutSession,
  WorkoutSummary,
  SetInput,
  SetLog,
  GenerateProgramInput,
  AppleHealthDeleteRequest,
  AppleHealthDeleteResponse,
  AppleHealthImportResponse,
  AppleHealthImportBatch,
  AppleHealthImportType,
  AppleHealthPreview,
  AppleHealthToken,
  AppleHealthTokenCreate,
  AppleHealthTokenSecret,
} from './types'

// ---------------- Auth ----------------
export const auth = {
  register: (payload: RegisterPayload) =>
    http.post<{ user: User }>('/auth/register', payload).then((r) => r.user),
  login: (payload: LoginPayload) =>
    http.post<{ user: User }>('/auth/login', payload).then((r) => r.user),
  logout: () => http.post<void>('/auth/logout'),
  me: () => http.get<{ user: User }>('/auth/me', { redirectOn401: false }).then((r) => r.user),
}

// ---------------- Profile ----------------
export const profile = {
  get: () => http.get<Profile>('/profile', { redirectOn401: false }),
  upsert: (payload: Profile) => http.put<Profile>('/profile', payload),
}

// ---------------- Health / nutrition logs ----------------
export const meals = {
  list: (date?: string) => http.get<ListResponse<Meal>>(`/logs/meals${toQuery({ date })}`),
  recent: (limit = 10) => http.get<MealQuickLists>(`/logs/meals/recent${toQuery({ limit })}`),
  create: (payload: MealInput) => http.post<Meal>('/logs/meals', payload),
  update: (id: number, payload: MealInput) => http.put<Meal>(`/logs/meals/${id}`, payload),
  remove: (id: number) => http.del<OkResponse>(`/logs/meals/${id}`),
  toggleFavorite: (id: number) => http.post<FavoriteResponse>(`/logs/meals/${id}/favorite`),
}

export const activities = {
  list: () => http.get<ListResponse<Activity>>('/logs/activities'),
  create: (payload: ActivityInput) => http.post<Activity>('/logs/activities', payload),
  update: (id: number, payload: ActivityInput) => http.put<Activity>(`/logs/activities/${id}`, payload),
  remove: (id: number) => http.del<OkResponse>(`/logs/activities/${id}`),
}

export const sleep = {
  list: () => http.get<ListResponse<Sleep>>('/logs/sleep'),
  create: (payload: SleepInput) => http.post<Sleep>('/logs/sleep', payload),
  remove: (id: number) => http.del<OkResponse>(`/logs/sleep/${id}`),
}

export const stepsApi = {
  list: () => http.get<ListResponse<Step>>('/logs/steps'),
  upsert: (payload: StepInput) => http.post<Step>('/logs/steps', payload),
  remove: (id: number) => http.del<OkResponse>(`/logs/steps/${id}`),
}

export const water = {
  list: () => http.get<ListResponse<Water>>('/logs/water'),
  create: (payload: WaterInput) => http.post<Water>('/logs/water', payload),
  remove: (id: number) => http.del<OkResponse>(`/logs/water/${id}`),
}

export const weight = {
  list: () => http.get<ListResponse<Weight>>('/logs/weight'),
  upsert: (payload: WeightInput) => http.post<Weight>('/logs/weight', payload),
  remove: (id: number) => http.del<OkResponse>(`/logs/weight/${id}`),
}

// ---------------- Exercises ----------------
export const exercises = {
  list: (q: ExerciseQuery = {}) => http.get<ListResponse<Exercise>>(`/exercises${toQuery(q)}`),
  get: (id: number) => http.get<Exercise>(`/exercises/${id}`),
  create: (payload: ExerciseInput) => http.post<Exercise>('/exercises', payload),
}

// ---------------- Workouts ----------------
export const workouts = {
  list: (params: { from?: string; to?: string; limit?: number; offset?: number } = {}) =>
    http.get<ListResponse<WorkoutSummary>>(`/workouts${toQuery(params)}`),
  create: (payload: WorkoutInput = {}) => http.post<WorkoutSession>('/workouts', payload),
  get: (id: number) => http.get<WorkoutSession>(`/workouts/${id}`),
  update: (id: number, payload: WorkoutInput) => http.put<WorkoutSession>(`/workouts/${id}`, payload),
  remove: (id: number) => http.del<OkResponse>(`/workouts/${id}`),
  addSet: (workoutId: number, payload: SetInput) => http.post<SetLog>(`/workouts/${workoutId}/sets`, payload),
  updateSet: (workoutId: number, setId: number, payload: SetInput) =>
    http.put<SetLog>(`/workouts/${workoutId}/sets/${setId}`, payload),
  removeSet: (workoutId: number, setId: number) => http.del<OkResponse>(`/workouts/${workoutId}/sets/${setId}`),
}

// ---------------- Performance ----------------
export const performance = {
  summary: () => http.get<PerformanceSummary>('/performance/summary'),
  prs: () => http.get<ListResponse<PrRecord>>('/performance/prs'),
  exercise: (exerciseId: number) => http.get<ExercisePerformance>(`/performance/exercise/${exerciseId}`),
  volume: (params: { from?: string; to?: string } = {}) => http.get<VolumeReport>(`/performance/volume${toQuery(params)}`),
}

// ---------------- Programs ----------------
export const programs = {
  generate: (payload: GenerateProgramInput = {}) => http.post<Program>('/programs/generate', payload),
  list: () => http.get<ListResponse<ProgramSummary>>('/programs'),
  active: () => http.get<Program>('/programs/active'),
  get: (id: number) => http.get<Program>(`/programs/${id}`),
  update: (id: number, payload: Partial<Program> & { active?: boolean }) => http.put<Program>(`/programs/${id}`, payload),
  remove: (id: number) => http.del<OkResponse>(`/programs/${id}`),
  today: () => http.get<TodayWorkout>('/programs/today'),
}

// ---------------- Nutrition ----------------
export const nutrition = {
  generatePlan: () => http.post<NutritionPlan>('/nutrition/plan/generate'),
  activePlan: () => http.get<NutritionPlan>('/nutrition/plan/active'),
  today: () => http.get<NutritionToday>('/nutrition/today'),
}

// ---------------- Recommendations & AI ----------------
export const recommendations = {
  today: () => http.get<RecommendationsToday>('/recommendations/today'),
  /** Full adaptive envelope (meals + workout + tip) for the Today screen. */
  adaptive: () => http.get<AdaptiveRecommendation>('/recommendations/adaptive'),
  /** History-ranked, portion-scaled meal picks for the Nutrition screen. */
  meals: (params: { category?: MealCategory; limit?: number } = {}) =>
    http.get<AdaptiveMealsBlock>(`/recommendations/meals${toQuery(params)}`),
  /** Per-exercise adaptive workout recommendation for the Workout screen. */
  workout: (params: { program_day_id?: number } = {}) =>
    http.get<AdaptiveWorkoutBlock>(`/recommendations/workout${toQuery(params)}`),
}

export const ai = {
  insights: () => http.get<AiInsights>('/ai/insights'),
  predictNextMeal: () => http.get<PredictNextMeal>('/ai/predict-next-meal'),
  recommendFoods: () => http.get<RecommendFoods>('/ai/recommend-foods'),
  chat: (message: string) => http.post<ChatResponse>('/ai/chat', { message }),
  parseLog: (text: string) => http.post<ParseLogResult>('/ai/parse-log', { text }),
}

// ---------------- Insights ----------------
export const insights = {
  today: () => http.get<InsightsToday>('/insights/today'),
  circadian: () => http.get<Circadian>('/insights/circadian'),
  trends: (days = 14) => http.get<Trends>(`/insights/trends${toQuery({ days })}`),
  streaks: () => http.get<Streaks>('/insights/streaks'),
  achievements: () => http.get<Achievements>('/insights/achievements'),
  heatmap: (days = 84) => http.get<Heatmap>(`/insights/heatmap${toQuery({ days })}`),
}

// ---------------- Admin / demo ----------------
export const admin = {
  seedDemo: (days = 14) => http.post<OkResponse>(`/admin/seed-demo${toQuery({ days })}`),
  reset: () => http.post<OkResponse>('/admin/reset'),
  health: () => http.get<{ status: string }>('/health'),
}

// ---------------- Apple Health integration ----------------
const APPLE_HEALTH = '/integrations/apple-health'

export const appleHealth = {
  preview: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return http.upload<AppleHealthPreview>(`${APPLE_HEALTH}/preview`, form)
  },
  import: (file: File, types: AppleHealthImportType[]) => {
    const form = new FormData()
    form.append('file', file)
    form.append('types', JSON.stringify(types))
    return http.upload<AppleHealthImportResponse>(`${APPLE_HEALTH}/import`, form)
  },
  imports: () => http.get<ListResponse<AppleHealthImportBatch>>(`${APPLE_HEALTH}/imports`),
  deleteData: (payload: AppleHealthDeleteRequest = {}) =>
    http.delWithBody<AppleHealthDeleteResponse>(`${APPLE_HEALTH}/data`, payload),
}

export const appleHealthTokens = {
  list: () => http.get<ListResponse<AppleHealthToken>>(`${APPLE_HEALTH}/tokens`),
  create: (payload: AppleHealthTokenCreate) =>
    http.post<AppleHealthTokenSecret>(`${APPLE_HEALTH}/tokens`, payload),
  rotate: (id: number) => http.post<AppleHealthTokenSecret>(`${APPLE_HEALTH}/tokens/${id}/rotate`),
  revoke: (id: number) => http.del<void>(`${APPLE_HEALTH}/tokens/${id}`),
}
