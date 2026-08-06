import './Onboarding.css'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  Building2,
  Check,
  Dumbbell,
  Flame,
  Footprints,
  Hand,
  Home,
  Minus,
  PartyPopper,
  PersonStanding,
  Ruler,
  Scale,
  Target,
  TrendingDown,
  TrendingUp,
  Trophy,
} from 'lucide-react'
import { profile as profileApi } from '../api'
import type {
  ActivityLevel,
  Equipment,
  ExperienceLevel,
  NutritionGoal,
  Profile,
  Sex,
  TrainingGoal,
  Units,
} from '../api'
import { useAsync } from '../lib/useAsync'
import { Button, Card, Input, ProgressBar, Segmented, SpinnerCenter, useToast } from '../components/ui'
import { Logo } from '../components/Logo'

const DEFAULTS: Profile = {
  name: '',
  sex: 'female',
  age: 25,
  height_cm: 168,
  weight_kg: 65,
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

const STEPS = [
  { key: 'you', label: 'You' },
  { key: 'body', label: 'Body' },
  { key: 'training', label: 'Training' },
  { key: 'goals', label: 'Goals' },
] as const

type Choice<T extends string> = { value: T; label: string; desc: string; icon: ReactNode }

const NUTRITION_GOALS: Choice<NutritionGoal>[] = [
  { value: 'lose', label: 'Lose', desc: 'Shed fat in a calorie deficit', icon: <TrendingDown size={20} aria-hidden="true" /> },
  { value: 'maintain', label: 'Maintain', desc: 'Hold your current weight', icon: <Minus size={20} aria-hidden="true" /> },
  { value: 'gain', label: 'Gain', desc: 'Build size in a calorie surplus', icon: <TrendingUp size={20} aria-hidden="true" /> },
]

const TRAINING_GOALS: Choice<TrainingGoal>[] = [
  { value: 'powerlifting', label: 'Powerlifting', desc: 'Max strength on the big lifts', icon: <Trophy size={20} aria-hidden="true" /> },
  { value: 'hypertrophy', label: 'Hypertrophy', desc: 'Build muscle size and volume', icon: <Dumbbell size={20} aria-hidden="true" /> },
  { value: 'maingain', label: 'Maingain', desc: 'Lean gains near maintenance', icon: <Scale size={20} aria-hidden="true" /> },
]

const EXPERIENCE_LEVELS: Choice<ExperienceLevel>[] = [
  { value: 'beginner', label: 'Beginner', desc: 'New to structured training', icon: <Footprints size={20} aria-hidden="true" /> },
  { value: 'intermediate', label: 'Intermediate', desc: 'Comfortable with the basics', icon: <Activity size={20} aria-hidden="true" /> },
  { value: 'advanced', label: 'Advanced', desc: 'Years of dedicated lifting', icon: <Flame size={20} aria-hidden="true" /> },
]

const EQUIPMENT_OPTIONS: Choice<Equipment>[] = [
  { value: 'full_gym', label: 'Full gym', desc: 'Barbells, machines, cables', icon: <Building2 size={20} aria-hidden="true" /> },
  { value: 'home_basic', label: 'Home basic', desc: 'Dumbbells and bands', icon: <Home size={20} aria-hidden="true" /> },
  { value: 'bodyweight', label: 'Bodyweight', desc: 'No equipment needed', icon: <PersonStanding size={20} aria-hidden="true" /> },
]

function OptionGrid<T extends string>({
  label,
  ariaLabel,
  value,
  onChange,
  options,
}: {
  label: string
  ariaLabel: string
  value: T
  onChange: (value: T) => void
  options: Choice<T>[]
}) {
  return (
    <div className="onb-group">
      <span className="onb-fieldlabel">{label}</span>
      <div className="onb-options" role="radiogroup" aria-label={ariaLabel}>
        {options.map((o) => {
          const selected = o.value === value
          return (
            <button
              key={o.value}
              type="button"
              role="radio"
              aria-checked={selected}
              className={`onb-option${selected ? ' is-selected' : ''}`}
              onClick={() => onChange(o.value)}
            >
              <span className="onb-option__ic">{o.icon}</span>
              <span className="onb-option__title">{o.label}</span>
              <span className="onb-option__desc">{o.desc}</span>
              <Check className="onb-option__check" size={18} aria-hidden="true" />
            </button>
          )
        })}
      </div>
    </div>
  )
}

export function Onboarding() {
  const navigate = useNavigate()
  const toast = useToast()
  const [step, setStep] = useState(0)
  const [saving, setSaving] = useState(false)
  const [celebrating, setCelebrating] = useState(false)
  const [triedNext, setTriedNext] = useState(false)
  const [form, setForm] = useState<Profile>(DEFAULTS)

  // Prefill from an existing profile (edit mode) if present.
  const { loading } = useAsync(async () => {
    const existing = await profileApi.get().catch(() => null)
    if (existing) setForm({ ...DEFAULTS, ...existing })
    return existing
  }, [])

  function set<K extends keyof Profile>(key: K, value: Profile[K]) {
    setForm((f) => ({ ...f, [key]: value }))
  }
  const num = (v: string) => (v === '' ? 0 : Number(v))

  const last = STEPS.length - 1
  const ageValid = form.age >= 10 && form.age <= 120
  const heightValid = form.height_cm > 0
  const weightValid = form.weight_kg > 0
  const stepValid = step !== 1 || (ageValid && heightValid && weightValid)

  function goNext() {
    if (!stepValid) {
      setTriedNext(true)
      return
    }
    setTriedNext(false)
    setStep((s) => Math.min(last, s + 1))
  }
  function goBack() {
    setTriedNext(false)
    setStep((s) => Math.max(0, s - 1))
  }

  async function finish() {
    setSaving(true)
    try {
      await profileApi.upsert(form)
      toast.success('Profile saved!')
      setCelebrating(true)
      window.setTimeout(() => navigate('/', { replace: true }), 1100)
    } catch {
      toast.error('Could not save your profile.')
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="onb-page">
        <div className="onb-shell">
          <div className="onb-brand">
            <Logo />
          </div>
          <Card variant="feature" className="onb-card">
            <SpinnerCenter label="Loading your profile" />
          </Card>
        </div>
      </div>
    )
  }

  return (
    <div className="onb-page">
      <div className="onb-shell">
        <div className="onb-brand">
          <Logo />
        </div>

        <Card variant="feature" className="onb-card">
          <ol className="onb-steps">
            {STEPS.map((s, i) => {
              const state = i < step ? 'is-done' : i === step ? 'is-active' : 'is-todo'
              return (
                <li key={s.key} className={`onb-step ${state}`} aria-current={i === step ? 'step' : undefined}>
                  <span className="onb-step__dot">{i < step ? <Check size={16} aria-hidden="true" /> : i + 1}</span>
                  <span className="onb-step__label">{s.label}</span>
                </li>
              )
            })}
          </ol>

          <div className="onb-progress">
            <div className="onb-progress__row">
              <span>
                Step {step + 1} of {STEPS.length}
              </span>
            </div>
            <ProgressBar value={step + 1} max={STEPS.length} label="Onboarding progress" />
          </div>

          <div className="onb-panel" key={step}>
            {step === 0 && (
              <section>
                <div className="onb-hero">
                  <span className="onb-hero__badge">
                    <Hand size={26} aria-hidden="true" />
                  </span>
                  <h2 className="onb-hero__title">Welcome to FitPath</h2>
                  <p className="onb-hero__sub">Let's personalise your training &amp; nutrition targets.</p>
                </div>
                <div className="onb-stack">
                  <Input
                    label="What should we call you?"
                    value={form.name ?? ''}
                    onChange={(e) => set('name', e.target.value)}
                    placeholder="Optional"
                  />
                  <div className="onb-group">
                    <span className="onb-fieldlabel">Biological sex</span>
                    <Segmented<Sex>
                      block
                      ariaLabel="Sex"
                      value={form.sex}
                      onChange={(v) => set('sex', v)}
                      options={[
                        { value: 'female', label: 'Female' },
                        { value: 'male', label: 'Male' },
                      ]}
                    />
                  </div>
                </div>
              </section>
            )}

            {step === 1 && (
              <section>
                <div className="onb-hero">
                  <span className="onb-hero__badge">
                    <Ruler size={26} aria-hidden="true" />
                  </span>
                  <h2 className="onb-hero__title">Your body</h2>
                  <p className="onb-hero__sub">Used to compute your calorie &amp; macro targets.</p>
                </div>
                <div className="onb-stack">
                  <div className="onb-grid">
                    <Input
                      label="Age"
                      type="number"
                      min={10}
                      max={120}
                      value={String(form.age)}
                      onChange={(e) => set('age', num(e.target.value))}
                      error={triedNext && !ageValid ? 'Enter an age between 10 and 120.' : undefined}
                    />
                    <div className="onb-group">
                      <span className="onb-fieldlabel">Units</span>
                      <Segmented<Units>
                        block
                        ariaLabel="Units"
                        value={form.units}
                        onChange={(v) => set('units', v)}
                        options={[
                          { value: 'metric', label: 'Metric' },
                          { value: 'imperial', label: 'Imperial' },
                        ]}
                      />
                    </div>
                    <Input
                      label="Height (cm)"
                      type="number"
                      step="0.1"
                      value={String(form.height_cm)}
                      onChange={(e) => set('height_cm', num(e.target.value))}
                      error={triedNext && !heightValid ? 'Enter your height.' : undefined}
                    />
                    <Input
                      label="Weight (kg)"
                      type="number"
                      step="0.1"
                      value={String(form.weight_kg)}
                      onChange={(e) => set('weight_kg', num(e.target.value))}
                      error={triedNext && !weightValid ? 'Enter your weight.' : undefined}
                    />
                  </div>
                  <div className="onb-group">
                    <span className="onb-fieldlabel">Activity level</span>
                    <Segmented<ActivityLevel>
                      block
                      ariaLabel="Activity level"
                      value={form.activity_level}
                      onChange={(v) => set('activity_level', v)}
                      options={[
                        { value: 'sedentary', label: 'Sedentary' },
                        { value: 'light', label: 'Light' },
                        { value: 'moderate', label: 'Moderate' },
                        { value: 'active', label: 'Active' },
                        { value: 'very_active', label: 'Very' },
                      ]}
                    />
                  </div>
                </div>
              </section>
            )}

            {step === 2 && (
              <section>
                <div className="onb-hero">
                  <span className="onb-hero__badge">
                    <Dumbbell size={26} aria-hidden="true" />
                  </span>
                  <h2 className="onb-hero__title">Training</h2>
                  <p className="onb-hero__sub">We'll build a program that fits your goal.</p>
                </div>
                <div className="onb-stack">
                  <OptionGrid<TrainingGoal>
                    label="Training goal"
                    ariaLabel="Training goal"
                    value={form.training_goal}
                    onChange={(v) => set('training_goal', v)}
                    options={TRAINING_GOALS}
                  />
                  <OptionGrid<ExperienceLevel>
                    label="Experience"
                    ariaLabel="Experience"
                    value={form.experience_level}
                    onChange={(v) => set('experience_level', v)}
                    options={EXPERIENCE_LEVELS}
                  />
                  <OptionGrid<Equipment>
                    label="Equipment"
                    ariaLabel="Equipment"
                    value={form.equipment}
                    onChange={(v) => set('equipment', v)}
                    options={EQUIPMENT_OPTIONS}
                  />
                  <div className="onb-group">
                    <span className="onb-fieldlabel">Training days per week</span>
                    <div className="onb-days" role="radiogroup" aria-label="Training days per week">
                      {[1, 2, 3, 4, 5, 6, 7].map((d) => (
                        <button
                          key={d}
                          type="button"
                          role="radio"
                          aria-checked={form.days_per_week === d}
                          className={`onb-day${form.days_per_week === d ? ' is-selected' : ''}`}
                          onClick={() => set('days_per_week', d)}
                        >
                          {d}
                        </button>
                      ))}
                    </div>
                    <p className="onb-days__cap">
                      <strong>{form.days_per_week}</strong> {form.days_per_week === 1 ? 'day' : 'days'} / week
                    </p>
                  </div>
                </div>
              </section>
            )}

            {step === 3 && (
              <section>
                <div className="onb-hero">
                  <span className="onb-hero__badge">
                    <Target size={26} aria-hidden="true" />
                  </span>
                  <h2 className="onb-hero__title">Your goals</h2>
                  <p className="onb-hero__sub">Daily targets we'll track on your rings.</p>
                </div>
                <div className="onb-stack">
                  <OptionGrid<NutritionGoal>
                    label="Nutrition goal"
                    ariaLabel="Nutrition goal"
                    value={form.goal}
                    onChange={(v) => set('goal', v)}
                    options={NUTRITION_GOALS}
                  />
                  <div className="onb-grid">
                    <Input label="Wake time" type="time" value={form.wake_time} onChange={(e) => set('wake_time', e.target.value)} />
                    <Input label="Step goal" type="number" value={String(form.step_goal)} onChange={(e) => set('step_goal', num(e.target.value))} />
                    <Input label="Water goal (ml)" type="number" value={String(form.water_goal_ml)} onChange={(e) => set('water_goal_ml', num(e.target.value))} />
                    <Input label="Exercise goal (min)" type="number" value={String(form.exercise_goal_min)} onChange={(e) => set('exercise_goal_min', num(e.target.value))} />
                  </div>
                </div>
              </section>
            )}
          </div>

          <div className="onb-nav">
            <Button variant="ghost" leftIcon={<ArrowLeft size={18} aria-hidden="true" />} onClick={goBack} disabled={step === 0}>
              Back
            </Button>
            {step < last ? (
              <Button rightIcon={<ArrowRight size={18} aria-hidden="true" />} onClick={goNext}>
                Continue
              </Button>
            ) : (
              <Button gradient size="lg" loading={saving} rightIcon={<Check size={18} aria-hidden="true" />} onClick={finish}>
                Finish setup
              </Button>
            )}
          </div>

          {celebrating && (
            <div className="onb-celebrate" role="status" aria-live="polite">
              <span className="onb-celebrate__ic">
                <PartyPopper size={34} aria-hidden="true" />
              </span>
              <h2 className="onb-celebrate__title">You're all set!</h2>
              <p className="onb-celebrate__sub">Taking you to your dashboard…</p>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
