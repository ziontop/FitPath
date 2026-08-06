import './Workout.css'
import { useState } from 'react'
import {
  ArrowRight,
  CalendarDays,
  Check,
  Dumbbell,
  Flame,
  Minus,
  Moon,
  Pencil,
  Play,
  Plus,
  RotateCcw,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
  Trash2,
  X,
} from 'lucide-react'
import { programs as programsApi, recommendations, workouts as workoutsApi } from '../api'
import type { AdaptiveExerciseRec, Exercise, SetLog, TodayWorkout, WorkoutSession, WorkoutSummary } from '../api'
import { useAsync } from '../lib/useAsync'
import { formatDateLabel, friendlyDate, round, todayISO } from '../lib/format'
import {
  Badge,
  Button,
  Card,
  CardHeader,
  Checkbox,
  EmptyState,
  IconButton,
  Input,
  List,
  ListRow,
  PageHeader,
  ProgressBar,
  Skeleton,
  StatusChip,
  useToast,
} from '../components/ui'
import { RestTimer } from '../components/RestTimer'
import { ExercisePicker } from '../components/ExercisePicker'

interface Tracked {
  exercise_id: number
  name: string
  target_sets?: number
  target_reps?: string
  target_rpe?: number
  rest_seconds?: number
  suggested_weight?: number
}

interface AddForm {
  weight: string
  reps: string
  rpe: string
  warmup: boolean
}
const emptyForm: AddForm = { weight: '', reps: '', rpe: '', warmup: false }

type ExActionKey = 'increase' | 'hold' | 'reduce' | 'deload' | 'resume' | 'start'
const EX_ACTION_META: Record<ExActionKey, { label: string; Icon: typeof TrendingUp }> = {
  increase: { label: 'Increase', Icon: TrendingUp },
  hold: { label: 'Hold', Icon: Minus },
  reduce: { label: 'Reduce', Icon: TrendingDown },
  deload: { label: 'Deload', Icon: ShieldCheck },
  resume: { label: 'Resume', Icon: RotateCcw },
  start: { label: 'Start', Icon: Play },
}

/** Classify a per-exercise adaptive rec into a UI action (resume = a layoff hold). */
function exActionKey(a: AdaptiveExerciseRec): ExActionKey {
  if (a.deload || a.action === 'deload') return 'deload'
  if (a.action === 'hold' && /resuming/i.test(a.reason)) return 'resume'
  return a.action
}

/** Human delta suffix for the action chip, e.g. "+2.5 kg" / "-5 kg". */
function actionDelta(key: ExActionKey, a: AdaptiveExerciseRec): string | null {
  const d = round(a.change.weight_delta_kg, 2)
  if (key === 'increase' && d) return `+${d} kg`
  if (key === 'reduce' && d) return `${d} kg`
  if (key === 'deload') return '-10%'
  return null
}

/** Lower bound of a rep range like "6-10" → 6 (used to prefill the reps field). */
function repLowOf(reps?: string): number | null {
  if (!reps) return null
  const m = reps.match(/\d+/)
  return m ? Number(m[0]) : null
}

function WorkoutSkeleton() {
  return (
    <div className="page" aria-busy="true" aria-label="Loading workout">
      <div className="stack-sm">
        <Skeleton variant="text" width={120} />
        <Skeleton variant="title" width={190} />
      </div>
      <Card variant="feature">
        <Skeleton variant="title" width={160} />
        <div className="wk-skel-list">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="wk-skel-row">
              <Skeleton variant="text" width="58%" />
              <Skeleton variant="text" width="18%" />
            </div>
          ))}
        </div>
        <div style={{ marginTop: 'var(--sp-4)' }}>
          <Skeleton variant="block" height={44} radius="var(--radius-md)" />
        </div>
      </Card>
      <Card>
        <Skeleton variant="title" width={140} />
        <div className="wk-skel-list">
          {[0, 1, 2].map((i) => (
            <div key={i} className="wk-skel-row">
              <Skeleton variant="text" width="50%" />
              <Skeleton variant="text" width="22%" />
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}

export function Workout() {
  const toast = useToast()
  const { data, loading, error, reload } = useAsync(async () => {
    const [today, recent] = await Promise.all([
      programsApi.today(),
      workoutsApi.list({ limit: 8 }),
    ])
    // Adaptive workout — align to today's program day when we have one so the
    // per-exercise targets merge cleanly. Additive: failure must not break logging.
    const adaptive = await (today && !today.rest_day && today.program_day_id != null
      ? recommendations.workout({ program_day_id: today.program_day_id })
      : recommendations.workout()
    ).catch(() => null)
    // Build a Hevy-style "Previous" set map from the most recent logged sessions
    // we already list here (existing /workouts/:id endpoint — no new backend
    // calls) so the active logger can show what you did last time, per set.
    const details = await Promise.all(
      recent.items.slice(0, 5).map((w) => workoutsApi.get(w.id).catch(() => null)),
    )
    const previous: Record<number, { weight: number; reps: number }[]> = {}
    for (const s of details) {
      if (!s) continue
      const byEx: Record<number, { weight: number; reps: number }[]> = {}
      for (const set of s.sets) {
        if (set.is_warmup) continue
        ;(byEx[set.exercise_id] ??= []).push({ weight: set.weight, reps: set.reps })
      }
      for (const [id, sets] of Object.entries(byEx)) {
        if (!previous[Number(id)]) previous[Number(id)] = sets
      }
    }
    return { today, adaptive, recent: recent.items, previous }
  }, [])

  const [session, setSession] = useState<WorkoutSession | null>(null)
  const [tracked, setTracked] = useState<Tracked[]>([])
  const [forms, setForms] = useState<Record<number, AddForm>>({})
  const [rest, setRest] = useState<number | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [editingSet, setEditingSet] = useState<number | null>(null)
  const [editForm, setEditForm] = useState<AddForm>(emptyForm)

  const getForm = (id: number) => forms[id] ?? emptyForm
  const setForm = (id: number, patch: Partial<AddForm>) =>
    setForms((f) => ({ ...f, [id]: { ...getForm(id), ...patch } }))

  async function startSession(today: TodayWorkout | null, empty = false) {
    setBusy(true)
    try {
      const s = await workoutsApi.create(
        empty || !today || today.rest_day
          ? { name: 'Workout' }
          : { name: today.name, program_day_id: today.program_day_id },
      )
      setSession(s)
      if (!empty && today && !today.rest_day && today.exercises) {
        // Merge adaptive per-exercise targets (weight/reps/sets/RPE) over the
        // program prescription; fall back to the program's suggested weight.
        const adaptMap = new Map<number, AdaptiveExerciseRec>((data?.adaptive?.exercises ?? []).map((e) => [e.exercise_id, e]))
        setTracked(
          today.exercises.map((ex) => {
            const a = adaptMap.get(ex.exercise_id)
            return {
              exercise_id: ex.exercise_id,
              name: ex.name,
              target_sets: a?.target_sets ?? ex.target_sets,
              target_reps: a?.target_reps ?? ex.target_reps,
              target_rpe: a?.target_rpe ?? ex.target_rpe,
              rest_seconds: ex.rest_seconds,
              suggested_weight: a?.suggested_weight ?? ex.suggested_weight,
            }
          }),
        )
        // Prefill weight/reps from the adaptive target so logging the suggested
        // set *is* the feedback loop. Preserve the program weight as fallback.
        const prefill: Record<number, AddForm> = {}
        for (const ex of today.exercises) {
          const a = adaptMap.get(ex.exercise_id)
          const weight = a?.suggested_weight ?? ex.suggested_weight
          const repLow = repLowOf(a?.target_reps ?? ex.target_reps)
          prefill[ex.exercise_id] = {
            weight: weight != null ? String(weight) : '',
            reps: repLow != null ? String(repLow) : '',
            rpe: '',
            warmup: false,
          }
        }
        setForms(prefill)
      } else {
        setTracked([])
        setForms({})
      }
    } catch {
      toast.error('Could not start session.')
    } finally {
      setBusy(false)
    }
  }

  function addExercise(ex: Exercise) {
    if (tracked.some((t) => t.exercise_id === ex.id)) return
    setTracked((t) => [...t, { exercise_id: ex.id, name: ex.name }])
  }

  async function addSet(t: Tracked) {
    if (!session) return
    const form = getForm(t.exercise_id)
    const weight = Number(form.weight)
    const reps = Number(form.reps)
    if (!reps) {
      toast.error('Enter reps first.')
      return
    }
    try {
      const set = await workoutsApi.addSet(session.id, {
        exercise_id: t.exercise_id,
        weight,
        reps,
        rpe: form.rpe ? Number(form.rpe) : undefined,
        is_warmup: form.warmup,
      })
      setSession((s) => (s ? { ...s, sets: [...s.sets, set] } : s))
      setForm(t.exercise_id, { reps: '', rpe: '' })
      if (!form.warmup && t.rest_seconds) setRest(t.rest_seconds)
    } catch {
      toast.error('Could not add set.')
    }
  }

  async function removeSet(setId: number) {
    if (!session) return
    try {
      await workoutsApi.removeSet(session.id, setId)
      setSession((s) => (s ? { ...s, sets: s.sets.filter((x) => x.id !== setId) } : s))
    } catch {
      toast.error('Could not delete set.')
    }
  }

  function beginEdit(set: SetLog) {
    setEditingSet(set.id)
    setEditForm({ weight: String(set.weight), reps: String(set.reps), rpe: set.rpe ? String(set.rpe) : '', warmup: !!set.is_warmup })
  }

  async function saveEdit(set: SetLog) {
    if (!session) return
    try {
      const updated = await workoutsApi.updateSet(session.id, set.id, {
        exercise_id: set.exercise_id,
        weight: Number(editForm.weight),
        reps: Number(editForm.reps),
        rpe: editForm.rpe ? Number(editForm.rpe) : undefined,
        is_warmup: editForm.warmup,
      })
      setSession((s) => (s ? { ...s, sets: s.sets.map((x) => (x.id === set.id ? updated : x)) } : s))
      setEditingSet(null)
    } catch {
      toast.error('Could not update set.')
    }
  }

  function finishSession() {
    const count = session?.sets.length ?? 0
    toast.success(count ? `Great session — ${count} sets logged!` : 'Session saved.')
    setSession(null)
    setTracked([])
    setForms({})
    setRest(null)
    reload()
  }

  if (loading) return <WorkoutSkeleton />
  if (error || !data) {
    return (
      <div className="page">
        <Card>
          <EmptyState
            icon={<Dumbbell size={28} aria-hidden="true" />}
            title="Couldn't load your workout"
            text={error ?? 'Something went wrong. Please try again.'}
            action={<Button onClick={reload}>Retry</Button>}
          />
        </Card>
      </div>
    )
  }

  // -------- Active session view --------
  if (session) {
    const workingDone = session.sets.filter((s) => !s.is_warmup).length
    const plannedSets = tracked.reduce((n, t) => n + (t.target_sets ?? 0), 0)
    const totalVolume = session.sets.reduce((v, s) => v + s.weight * s.reps, 0)
    const previousByEx = data.previous

    return (
      <div className={`page wk-page${rest !== null ? ' wk-page--resting' : ''}`}>
        <div className="wk-bar">
          <div className="wk-bar__row">
            <div className="wk-bar__title-wrap">
              <span className="wk-bar__icon" aria-hidden="true">
                <Dumbbell size={20} />
              </span>
              <div className="wk-bar__head">
                <h1 className="wk-bar__title">{session.name ?? 'Workout'}</h1>
                <p className="wk-bar__meta">
                  <CalendarDays size={14} aria-hidden="true" />
                  {formatDateLabel(session.date)}
                  <span className="wk-bar__sep" aria-hidden="true" />
                  {session.sets.length} {session.sets.length === 1 ? 'set' : 'sets'}
                  {totalVolume > 0 ? (
                    <>
                      <span className="wk-bar__sep" aria-hidden="true" />
                      {round(totalVolume).toLocaleString()} kg
                    </>
                  ) : null}
                </p>
              </div>
            </div>
            <Button variant="primary" leftIcon={<Check size={18} aria-hidden="true" />} onClick={finishSession}>
              Finish
            </Button>
          </div>
          {plannedSets > 0 ? (
            <div className="wk-bar__progress">
              <div className="wk-bar__progress-head">
                <span>Session progress</span>
                <span className="wk-bar__count">
                  {Math.min(workingDone, plannedSets)} / {plannedSets} sets
                </span>
              </div>
              <ProgressBar value={workingDone} max={plannedSets} gradient label="Session progress" />
            </div>
          ) : null}
        </div>

        {tracked.length === 0 ? (
          <Card>
            <EmptyState
              icon={<Dumbbell size={28} aria-hidden="true" />}
              title="No exercises yet"
              text="Add an exercise to start logging your sets."
              action={
                <Button leftIcon={<Plus size={18} aria-hidden="true" />} onClick={() => setPickerOpen(true)}>
                  Add exercise
                </Button>
              }
            />
          </Card>
        ) : (
          <div className="wk-exercises">
            {tracked.map((t) => {
              const sets = session.sets.filter((s) => s.exercise_id === t.exercise_id)
              const done = sets.filter((s) => !s.is_warmup).length
              const form = getForm(t.exercise_id)
              const complete = !!t.target_sets && done >= t.target_sets
              const prevSets = previousByEx[t.exercise_id]
              return (
                <Card key={t.exercise_id} className="wk-ex">
                  <CardHeader
                    title={t.name}
                    action={
                      t.target_reps ? (
                        <span className="wk-scheme">
                          {t.target_sets}×{t.target_reps} · RPE {t.target_rpe}
                        </span>
                      ) : null
                    }
                  />
                  <div className="wk-ex__sub">
                    {t.target_sets ? (
                      <span className={`wk-count${complete ? ' wk-count--done' : ''}`}>
                        {complete ? <Check size={13} aria-hidden="true" /> : null}
                        {done}/{t.target_sets} sets
                      </span>
                    ) : done > 0 ? (
                      <span className="wk-count">{done} logged</span>
                    ) : null}
                    {t.suggested_weight ? (
                      <span className="wk-suggest">
                        Target <span className="wk-suggest__val num">{t.suggested_weight}</span> kg
                      </span>
                    ) : null}
                  </div>

                  {sets.length > 0 && (
                    <div className="wk-sets">
                      <div className="wk-set wk-set-head" aria-hidden="true">
                        <span>Set</span>
                        <span>Prev</span>
                        <span>Weight</span>
                        <span>Reps</span>
                        <span>RPE</span>
                        <span />
                      </div>
                      {sets.map((s, i) => {
                        const workingIdx = sets.slice(0, i).filter((x) => !x.is_warmup).length
                        const prev = s.is_warmup ? undefined : prevSets?.[workingIdx]
                        const prevLabel = prev ? `${prev.weight}×${prev.reps}` : '—'
                        return editingSet === s.id ? (
                          <div className="wk-set wk-set--editing" key={s.id}>
                            <span className="wk-set__badge">{i + 1}</span>
                            <span className="wk-set__prev num">{prevLabel}</span>
                            <Input
                              type="number"
                              value={editForm.weight}
                              onChange={(e) => setEditForm((f) => ({ ...f, weight: e.target.value }))}
                              aria-label="Weight (kg)"
                            />
                            <Input
                              type="number"
                              value={editForm.reps}
                              onChange={(e) => setEditForm((f) => ({ ...f, reps: e.target.value }))}
                              aria-label="Reps"
                            />
                            <Input
                              type="number"
                              value={editForm.rpe}
                              onChange={(e) => setEditForm((f) => ({ ...f, rpe: e.target.value }))}
                              aria-label="RPE"
                            />
                            <span className="wk-set__actions">
                              <IconButton label="Save set" variant="primary" size="sm" onClick={() => saveEdit(s)}>
                                <Check size={16} />
                              </IconButton>
                              <IconButton label="Cancel edit" size="sm" onClick={() => setEditingSet(null)}>
                                <X size={16} />
                              </IconButton>
                            </span>
                          </div>
                        ) : (
                          <div className={`wk-set${s.is_warmup ? ' wk-set--warmup' : ''}`} key={s.id}>
                            <span
                              className={`wk-set__badge${s.is_warmup ? ' wk-set__badge--warmup' : ''}`}
                              title={s.is_warmup ? 'Warm-up set' : 'Completed set'}
                            >
                              {s.is_warmup ? <Flame size={13} aria-hidden="true" /> : <Check size={14} aria-hidden="true" />}
                            </span>
                            <span className="wk-set__prev num">{prevLabel}</span>
                            <span className="wk-set__val num">{s.weight}</span>
                            <span className="wk-set__val num">{s.reps}</span>
                            <span className="wk-set__val wk-set__val--muted num">{s.rpe ?? '—'}</span>
                            <span className="wk-set__actions">
                              <IconButton label="Edit set" size="sm" onClick={() => beginEdit(s)}>
                                <Pencil size={15} />
                              </IconButton>
                              <IconButton label="Delete set" size="sm" onClick={() => removeSet(s.id)}>
                                <Trash2 size={15} />
                              </IconButton>
                            </span>
                          </div>
                        )
                      })}
                    </div>
                  )}

                  <div className="wk-addset">
                    <div className="wk-addset__fields">
                      <Input
                        type="number"
                        placeholder={t.suggested_weight ? String(t.suggested_weight) : 'kg'}
                        value={form.weight}
                        onChange={(e) => setForm(t.exercise_id, { weight: e.target.value })}
                        aria-label="Weight (kg)"
                      />
                      <Input
                        type="number"
                        placeholder="reps"
                        value={form.reps}
                        onChange={(e) => setForm(t.exercise_id, { reps: e.target.value })}
                        aria-label="Reps"
                      />
                      <Input
                        type="number"
                        placeholder="RPE"
                        value={form.rpe}
                        onChange={(e) => setForm(t.exercise_id, { rpe: e.target.value })}
                        aria-label="RPE"
                      />
                      <Button
                        variant="secondary"
                        className="wk-addset__btn"
                        leftIcon={<Plus size={18} aria-hidden="true" />}
                        onClick={() => addSet(t)}
                      >
                        Add set
                      </Button>
                    </div>
                    <Checkbox
                      checked={form.warmup}
                      onChange={(e) => setForm(t.exercise_id, { warmup: e.target.checked })}
                      label="Warm-up set"
                    />
                  </div>
                </Card>
              )
            })}

            <Button
              variant="secondary"
              block
              leftIcon={<Plus size={18} aria-hidden="true" />}
              onClick={() => setPickerOpen(true)}
            >
              Add exercise
            </Button>
          </div>
        )}

        {rest !== null && (
          <div className="wk-restbar" role="region" aria-label="Rest timer">
            <div className="wk-restbar__inner">
              <RestTimer key={rest + '-' + session.sets.length} duration={rest} onClose={() => setRest(null)} />
            </div>
          </div>
        )}

        <ExercisePicker open={pickerOpen} onClose={() => setPickerOpen(false)} onPick={addExercise} />
      </div>
    )
  }

  // -------- Start view --------
  const { today, recent, adaptive } = data
  const adaptByEx = new Map<number, AdaptiveExerciseRec>((adaptive?.exercises ?? []).map((e) => [e.exercise_id, e]))
  const showDeload = !!adaptive && (adaptive.deload || adaptive.exercises.some((e) => e.deload || e.action === 'deload'))
  const resumeEx = adaptive?.exercises.find((e) => e.action === 'hold' && /resuming/i.test(e.reason))
  const showBanner = !today.rest_day && (showDeload || !!resumeEx)

  return (
    <div className="page stagger">
      <PageHeader
        eyebrow={friendlyDate(todayISO())}
        title="Workout"
        subtitle="Log your training and track every set."
      />

      {showBanner ? (
        <div className={`wk-banner wk-banner--${showDeload ? 'deload' : 'resume'}`} role="status">
          <span className="wk-banner__icon" aria-hidden="true">
            {showDeload ? <ShieldCheck size={20} /> : <RotateCcw size={20} />}
          </span>
          <div className="wk-banner__body">
            <strong className="wk-banner__title">{showDeload ? 'Deload session' : 'Easing back in'}</strong>
            <p className="wk-banner__text">{showDeload ? adaptive!.reason : resumeEx!.reason}</p>
          </div>
        </div>
      ) : null}

      <Card variant="feature" className="wk-today">
        <CardHeader
          title="Today's session"
          action={
            today.rest_day ? (
              <StatusChip status="not-started">Rest day</StatusChip>
            ) : (
              <Badge variant="primary">{today.exercises?.length ?? 0} exercises</Badge>
            )
          }
        />
        {today.rest_day ? (
          <div className="wk-restday">
            <span className="wk-restday__icon" aria-hidden="true">
              <Moon size={26} />
            </span>
            <div>
              <strong>Rest day</strong>
              <p className="muted" style={{ margin: 0 }}>
                No session scheduled today. You can still start an empty workout.
              </p>
            </div>
          </div>
        ) : (
          <>
            <p className="wk-today__name">
              <strong>{today.name}</strong>
              {adaptive ? <span className="wk-today__note"> · targets adapted from your logs</span> : null}
            </p>
            <div className="wk-plan">
              {(today.exercises ?? []).map((ex, i) => {
                const a = adaptByEx.get(ex.exercise_id)
                const key = a ? exActionKey(a) : null
                const meta = key ? EX_ACTION_META[key] : null
                const delta = a && key ? actionDelta(key, a) : null
                const sets = a?.target_sets ?? ex.target_sets
                const reps = a?.target_reps ?? ex.target_reps
                const rpe = a?.target_rpe ?? ex.target_rpe
                const targetWeight = a?.suggested_weight ?? ex.suggested_weight
                return (
                  <div key={ex.exercise_id} className="wk-plan__row">
                    <span className="wk-num" aria-hidden="true">{i + 1}</span>
                    <div className="wk-plan__main">
                      <div className="wk-plan__top">
                        <span className="wk-plan__name">{ex.name}</span>
                        {meta ? (
                          <span className={`wk-act wk-act--${key}`}>
                            <meta.Icon size={13} aria-hidden="true" />
                            {meta.label}
                            {delta ? <span className="wk-act__delta num">{delta}</span> : null}
                          </span>
                        ) : null}
                      </div>
                      <div className="wk-plan__scheme">
                        <span className="wk-scheme">{sets}×{reps} · RPE {rpe}</span>
                        {targetWeight != null ? <span className="wk-plan__weight num">{targetWeight} kg</span> : null}
                      </div>
                      {a ? (
                        <details className="wk-why">
                          <summary className="wk-why__summary">Why this target</summary>
                          <p className="wk-why__text">{a.reason}</p>
                          <p className="wk-why__basis">{a.history_basis}</p>
                        </details>
                      ) : null}
                    </div>
                  </div>
                )
              })}
            </div>
          </>
        )}
        <div className="wk-actions">
          {!today.rest_day && (
            <Button
              loading={busy}
              leftIcon={<Dumbbell size={18} aria-hidden="true" />}
              rightIcon={<ArrowRight size={18} aria-hidden="true" />}
              onClick={() => startSession(today)}
            >
              Start today's workout
            </Button>
          )}
          <Button
            variant="secondary"
            loading={busy}
            leftIcon={<Plus size={18} aria-hidden="true" />}
            onClick={() => startSession(today, true)}
          >
            Start empty session
          </Button>
        </div>
      </Card>

      <Card>
        <CardHeader title="Recent sessions" />
        {recent.length === 0 ? (
          <EmptyState
            icon={<Dumbbell size={28} aria-hidden="true" />}
            title="No sessions yet"
            text="Start your first workout and it'll show up here."
          />
        ) : (
          <List>
            {recent.map((w: WorkoutSummary) => (
              <ListRow
                key={w.id}
                leading={
                  <span className="wk-rec-ico" aria-hidden="true">
                    <CalendarDays size={16} />
                  </span>
                }
                title={w.name ?? 'Workout'}
                sub={`${formatDateLabel(w.date)} · ${w.set_count} sets`}
                trailing={<span className="wk-weight-val num">{round(w.total_volume).toLocaleString()} kg</span>}
              />
            ))}
          </List>
        )}
      </Card>
    </div>
  )
}
