import './Dashboard.css'
import { Link, useNavigate } from 'react-router-dom'
import {
  ArrowRight,
  Moon,
  Sparkles,
  Footprints,
  Droplet,
  Timer,
  Beef,
  ClipboardList,
  Dumbbell,
  Utensils,
  TrendingUp,
  TrendingDown,
  Minus,
  RotateCcw,
  Play,
  ShieldCheck,
} from 'lucide-react'
import { recommendations, profile as profileApi, activities as activitiesApi, water as waterApi, stepsApi } from '../api'
import type { Intensity, AdaptiveWorkoutBlock, AdaptiveExerciseRec } from '../api'
import { useAsync } from '../lib/useAsync'
import { capitalize, friendlyDate, greeting, pct, round, todayISO } from '../lib/format'
import {
  ActivityRings,
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  MetricTile,
  PageHeader,
  ProgressBar,
  ProgressRing,
  Skeleton,
} from '../components/ui'

const KCAL_PER_MIN: Record<Intensity, number> = { light: 5, moderate: 8, vigorous: 11 }
const MOVE_GOAL = 500

type WorkoutSummaryKey = 'increase' | 'hold' | 'reduce' | 'deload' | 'resume' | 'start' | 'rest'
const WK_SUMMARY_ICON: Record<WorkoutSummaryKey, typeof TrendingUp> = {
  increase: TrendingUp,
  hold: Minus,
  reduce: TrendingDown,
  deload: ShieldCheck,
  resume: RotateCcw,
  start: Play,
  rest: Moon,
}
const WK_SUMMARY_LABEL: Record<WorkoutSummaryKey, string> = {
  increase: 'Increase load',
  hold: 'Hold & build reps',
  reduce: 'Back off the load',
  deload: 'Deload session',
  resume: 'Ease back in',
  start: 'Get started',
  rest: 'Rest day',
}

/** Reduce the adaptive workout block to one glanceable action + its strongest reason. */
function summarizeWorkout(w: AdaptiveWorkoutBlock): { key: WorkoutSummaryKey; reason: string; delta: string | null } {
  if (w.rest_day) return { key: 'rest', reason: w.reason, delta: null }
  if (!w.exercises.length) return { key: 'start', reason: w.reason, delta: null }
  const byAction = (a: AdaptiveExerciseRec['action']) => w.exercises.find((e) => e.action === a)
  const resume = w.exercises.find((e) => e.action === 'hold' && /resuming/i.test(e.reason))
  let key: WorkoutSummaryKey
  let lead: AdaptiveExerciseRec
  if (w.deload || byAction('deload')) {
    key = 'deload'
    lead = byAction('deload') ?? w.exercises[0]
  } else if (byAction('reduce')) {
    key = 'reduce'
    lead = byAction('reduce')!
  } else if (resume) {
    key = 'resume'
    lead = resume
  } else if (byAction('increase')) {
    key = 'increase'
    lead = byAction('increase')!
  } else {
    key = 'hold'
    lead = w.exercises[0]
  }
  const d = lead.change.weight_delta_kg
  const delta =
    key === 'increase' && d ? `+${round(d, 2)} kg` : key === 'reduce' && d ? `${round(d, 2)} kg` : key === 'deload' ? 'Deload -10%' : null
  return { key, reason: lead.reason || w.reason, delta }
}

function MacroBar({
  label,
  consumed,
  target,
  variant,
}: {
  label: string
  consumed: number
  target: number
  variant: 'primary' | 'success' | 'secondary' | 'warning'
}) {
  return (
    <div className="dash-macro">
      <div className="dash-macro__meta">
        <span className="dash-macro__name">{label}</span>
        <span className="muted">
          {round(consumed)} / {round(target)} g
        </span>
      </div>
      <ProgressBar value={consumed} max={target} variant={variant} label={label} />
    </div>
  )
}

function DashboardSkeleton() {
  return (
    <div className="page" aria-busy="true" aria-label="Loading your day">
      <div className="row-between wrap">
        <div className="stack-sm">
          <Skeleton variant="text" width={130} />
          <Skeleton variant="title" width={220} />
        </div>
        <Skeleton variant="block" width={132} height={44} radius="var(--radius-md)" />
      </div>
      <Card variant="hero">
        <div className="dash-hero">
          <Skeleton variant="circle" width={220} height={220} />
          <div className="dash-skel-legend">
            {[0, 1, 2].map((i) => (
              <div key={i} className="dash-skel-row">
                <Skeleton variant="circle" width={12} height={12} />
                <div style={{ flex: 1 }}>
                  <Skeleton variant="text" lines={2} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </Card>
      <div className="dash-grid">
        {[0, 1, 2, 3].map((i) => (
          <Card key={i} variant="stat">
            <Skeleton variant="text" lines={3} />
          </Card>
        ))}
      </div>
      <div className="dash-cards">
        {[0, 1].map((i) => (
          <Card key={i}>
            <Skeleton variant="title" />
            <div style={{ marginTop: 'var(--sp-4)' }}>
              <Skeleton variant="text" lines={4} />
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}

export function Dashboard() {
  const navigate = useNavigate()

  const { data, loading, error, reload } = useAsync(async () => {
    const [rec, adaptive, prof, acts, waters, steps] = await Promise.all([
      recommendations.today(),
      // Adaptive is additive: never let its failure break the legacy dashboard.
      recommendations.adaptive().catch(() => null),
      profileApi.get().catch(() => null),
      activitiesApi.list(),
      waterApi.list(),
      stepsApi.list(),
    ])
    return { rec, adaptive, prof, acts: acts.items, waters: waters.items, steps: steps.items }
  }, [])

  if (loading) return <DashboardSkeleton />
  if (error || !data) {
    return (
      <div className="page">
        <Card>
          <EmptyState
            icon={<Sparkles size={28} aria-hidden="true" />}
            title="Couldn't load your dashboard"
            text={error ?? 'Something went wrong. Please try again.'}
            action={<Button onClick={reload}>Retry</Button>}
          />
        </Card>
      </div>
    )
  }

  const { rec, adaptive, prof, acts, waters, steps } = data
  const exerciseMin = acts.reduce((s, a) => s + a.minutes, 0)
  const stepCount = steps[0]?.steps ?? 0
  const activeKcal = Math.round(acts.reduce((s, a) => s + a.minutes * KCAL_PER_MIN[a.intensity], 0) + stepCount * 0.04)
  const waterMl = waters.reduce((s, w) => s + w.ml, 0)
  const exGoal = prof?.exercise_goal_min ?? 45
  const hydrateGoal = prof?.water_goal_ml ?? 2500
  const stepGoal = prof?.step_goal ?? 8000

  const n = rec.nutrition
  const w = rec.workout

  const rings = [
    { key: 'move' as const, value: activeKcal, goal: MOVE_GOAL },
    { key: 'exercise' as const, value: exerciseMin, goal: exGoal },
    { key: 'hydrate' as const, value: waterMl, goal: hydrateGoal },
  ]
  const closed = rings.filter((r) => r.goal > 0 && r.value >= r.goal).length

  const legend = [
    { name: 'Move', dot: 'move', value: activeKcal, max: MOVE_GOAL, unit: 'kcal', variant: 'primary' as const },
    { name: 'Exercise', dot: 'exercise', value: exerciseMin, max: exGoal, unit: 'min', variant: 'success' as const },
    { name: 'Hydrate', dot: 'hydrate', value: waterMl, max: hydrateGoal, unit: 'ml', variant: 'secondary' as const },
  ]
  // Show the leading ring in the hub (e.g. "89% Move") rather than a "0/3 closed"
  // count that visually contradicts a partial arc.
  const lead = [...legend].sort((a, b) => pct(b.value, b.max) - pct(a.value, a.max))[0]
  const leadPct = pct(lead.value, lead.max)

  const kcalPct = pct(n.consumed.kcal, n.targets.kcal)
  const hasSession = !w.rest_day && (w.exercises?.length ?? 0) > 0

  // Adaptive: what changed today because of history (best meal pick + workout action).
  const adaptWorkout = adaptive ? summarizeWorkout(adaptive.workout) : null
  const bestMeal = adaptive?.meals.suggestions[0] ?? null
  const AdaptWkIcon = adaptWorkout ? WK_SUMMARY_ICON[adaptWorkout.key] : null

  return (
    <div className="page stagger">
      <PageHeader
        eyebrow={friendlyDate(todayISO())}
        title={`${greeting()}${prof?.name ? `, ${prof.name}` : ''}`}
        subtitle="Here's where today stands."
      />

      {!prof && (
        <Card variant="hero">
          <div className="dash-setup">
            <div className="dash-setup__main">
              <span className="dash-setup__icon" aria-hidden="true">
                <ClipboardList size={22} />
              </span>
              <div>
                <strong>Finish setting up</strong>
                <p className="muted" style={{ margin: 0 }}>
                  Complete your profile to personalise your targets.
                </p>
              </div>
            </div>
            <Button onClick={() => navigate('/onboarding')}>Set up profile</Button>
          </div>
        </Card>
      )}

      {/* Hero — activity rings */}
      <Card variant="hero">
        <div className="dash-hero">
          <div className="dash-rings">
            <ActivityRings rings={rings} size={220} />
            <div className="dash-rings__center">
              <div>
                <div className="dash-rings__value num">
                  {leadPct}
                  <span className="dash-rings__pct">%</span>
                </div>
                <div className="dash-rings__label">{lead.name}</div>
                <div className="dash-rings__closed num">{closed} of 3 closed</div>
              </div>
            </div>
          </div>
          <div className="dash-legend">
            {legend.map((l) => (
              <div key={l.name} className="dash-legend__item">
                <span className={`dash-legend__dot dash-legend__dot--${l.dot}`} />
                <div className="dash-legend__body">
                  <div className="dash-legend__top">
                    <span className="dash-legend__name">{l.name}</span>
                    <span className="dash-legend__val">
                      {l.value.toLocaleString()} / {l.max.toLocaleString()} {l.unit}
                    </span>
                  </div>
                  <ProgressBar value={l.value} max={l.max} variant={l.variant} label={l.name} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </Card>

      {/* Glanceable metric tiles */}
      <div className="dash-grid">
        <MetricTile
          label="Steps"
          value={stepCount.toLocaleString()}
          icon={<Footprints size={18} aria-hidden="true" />}
          sub={`${pct(stepCount, stepGoal)}% of goal`}
        />
        <MetricTile
          label="Water"
          value={waterMl.toLocaleString()}
          unit="ml"
          icon={<Droplet size={18} aria-hidden="true" />}
          sub={`${pct(waterMl, hydrateGoal)}% of goal`}
        />
        <MetricTile
          label="Exercise"
          value={exerciseMin}
          unit="min"
          icon={<Timer size={18} aria-hidden="true" />}
          sub={`${pct(exerciseMin, exGoal)}% of goal`}
        />
        <MetricTile
          label="Protein"
          value={round(n.consumed.protein_g)}
          unit="g"
          icon={<Beef size={18} aria-hidden="true" />}
          sub={`${pct(n.consumed.protein_g, n.targets.protein_g)}% of target`}
        />
      </div>

      {/* Built from your history — what changed today because of your logs */}
      <Card className="dash-adapt">
        <CardHeader title="Built from your history" action={<Badge>From your logs</Badge>} />
        {adaptive && adaptWorkout && AdaptWkIcon ? (
          <div className="dash-adapt__rows">
            <div className="dash-adapt__row">
              <span className={`dash-adapt__icon dash-adapt__icon--${adaptWorkout.key}`} aria-hidden="true">
                <AdaptWkIcon size={18} />
              </span>
              <div className="dash-adapt__body">
                <div className="dash-adapt__top">
                  <span className="dash-adapt__label">{WK_SUMMARY_LABEL[adaptWorkout.key]}</span>
                  {adaptWorkout.delta ? <span className="dash-adapt__delta num">{adaptWorkout.delta}</span> : null}
                </div>
                <p className="dash-adapt__reason">{adaptWorkout.reason}</p>
                <span className="dash-adapt__meta">{capitalize(adaptive.workout.confidence)} confidence · from your training logs</span>
              </div>
            </div>

            {bestMeal ? (
              <div className="dash-adapt__row">
                <span className="dash-adapt__icon" aria-hidden="true">
                  <Utensils size={18} />
                </span>
                <div className="dash-adapt__body">
                  <div className="dash-adapt__top">
                    <span className="dash-adapt__label">{bestMeal.name}</span>
                    <span className="dash-adapt__macro num">
                      {round(bestMeal.kcal).toLocaleString()} kcal · P{round(bestMeal.protein_g)} C{round(bestMeal.carbs_g)} F{round(bestMeal.fat_g)}
                    </span>
                  </div>
                  <p className="dash-adapt__reason">{bestMeal.reason}</p>
                  <span className="dash-adapt__meta">
                    {bestMeal.portion !== 1 ? `${bestMeal.portion}× serving · ` : ''}
                    {bestMeal.logged_count > 0
                      ? `${capitalize(bestMeal.confidence)} confidence · eaten ${bestMeal.logged_count}×`
                      : 'Starter suggestion'}
                  </span>
                </div>
              </div>
            ) : null}
          </div>
        ) : (
          <div className="dash-adapt__unavailable">
            <p className="muted" style={{ margin: 0 }}>
              History-based recommendations are unavailable right now.
            </p>
            <Button variant="ghost" size="sm" onClick={reload}>
              Retry
            </Button>
          </div>
        )}
      </Card>

      <div className="dash-cards">
        {/* Today's workout */}
        <Card>
          <CardHeader title="Today's workout" action={<Link to="/programs">Program</Link>} />
          {w.rest_day ? (
            <div className="dash-rest">
              <span className="dash-rest__icon" aria-hidden="true">
                <Moon size={26} />
              </span>
              <strong>Rest day</strong>
              <p className="muted" style={{ margin: 0 }}>
                Recovery matters — prioritise sleep, steps, and hydration today.
              </p>
            </div>
          ) : hasSession ? (
            <div className="stack">
              <div className="row-between">
                <strong>{w.name ?? 'Session'}</strong>
                <Badge variant="primary">{w.exercises?.length ?? 0} exercises</Badge>
              </div>
              <div className="dash-ex-list">
                {(w.exercises ?? []).slice(0, 4).map((ex) => (
                  <div key={ex.exercise_id} className="dash-ex-row">
                    <span className="dash-ex-name">{ex.name}</span>
                    <span className="dash-ex-scheme">
                      {ex.target_sets}×{ex.target_reps}
                      {ex.suggested_weight ? ` · ${ex.suggested_weight}kg` : ''}
                    </span>
                  </div>
                ))}
              </div>
              <Button
                gradient
                block
                rightIcon={<ArrowRight size={18} aria-hidden="true" />}
                onClick={() => navigate('/workout')}
              >
                Start workout
              </Button>
            </div>
          ) : (
            <EmptyState
              icon={<Dumbbell size={28} aria-hidden="true" />}
              title="No session planned"
              text="Pick a program to get a tailored workout for today."
              action={<Button onClick={() => navigate('/programs')}>Browse programs</Button>}
            />
          )}
        </Card>

        {/* Nutrition */}
        <Card>
          <CardHeader title="Nutrition" action={<Link to="/nutrition">Log meal</Link>} />
          {n.targets.kcal > 0 ? (
            <div className="stack">
              <div className="dash-kcal">
                <div>
                  <div className="dash-kcal__value">{round(n.consumed.kcal).toLocaleString()}</div>
                  <div className="dash-kcal__sub">
                    of {round(n.targets.kcal).toLocaleString()} kcal · {Math.max(0, round(n.remaining.kcal)).toLocaleString()} left
                  </div>
                </div>
                <ProgressRing value={kcalPct} size={78} stroke={9} label={`${kcalPct}% of calorie target`}>
                  <span className="dash-ring-caption">{kcalPct}%</span>
                </ProgressRing>
              </div>
              <MacroBar label="Protein" consumed={n.consumed.protein_g} target={n.targets.protein_g} variant="success" />
              <MacroBar label="Carbs" consumed={n.consumed.carbs_g} target={n.targets.carbs_g} variant="secondary" />
              <MacroBar label="Fat" consumed={n.consumed.fat_g} target={n.targets.fat_g} variant="warning" />
            </div>
          ) : (
            <EmptyState
              icon={<Utensils size={28} aria-hidden="true" />}
              title="Set up your nutrition plan"
              text="Add your goals to see daily calorie and macro targets."
              action={<Button onClick={() => navigate('/nutrition')}>Go to nutrition</Button>}
            />
          )}
        </Card>
      </div>

      {/* Coach tip */}
      <Card>
        <div className="dash-coach">
          <span className="dash-coach__icon" aria-hidden="true">
            <Sparkles size={22} />
          </span>
          <div className="dash-coach__body">
            <div className="row" style={{ gap: 'var(--sp-2)' }}>
              <span className="card__title">Coach tip</span>
              <Badge variant="ai">SMART</Badge>
            </div>
            <p className="dash-coach__text">{rec.tip}</p>
            <Button
              variant="ghost"
              size="sm"
              leftIcon={<Sparkles size={16} aria-hidden="true" />}
              onClick={() => navigate('/insights')}
            >
              Ask the coach
            </Button>
          </div>
        </div>
      </Card>
    </div>
  )
}
