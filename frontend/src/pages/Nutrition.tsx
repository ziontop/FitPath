import './Nutrition.css'
import { useEffect, useState } from 'react'
import { Check, Coffee, Cookie, Flame, Pencil, Plus, Sparkles, Star, Sun, Sunset, Trash2, Utensils } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { ai, meals as mealsApi, nutrition as nutritionApi, recommendations } from '../api'
import type { AdaptiveMealSuggestion, Meal, MealCategory, MealInput, MealQuickItem } from '../api'
import { useAsync } from '../lib/useAsync'
import { capitalize, formatTime, friendlyDate, pct, round, todayISO } from '../lib/format'
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  FilterChip,
  IconButton,
  Input,
  List,
  ListRow,
  Modal,
  PageHeader,
  ProgressRing,
  Segmented,
  Skeleton,
  useToast,
} from '../components/ui'

const emptyMeal: MealInput = { name: '', kcal: 0, category: 'lunch' }

const CATEGORY_META: Record<MealCategory, { label: string; Icon: LucideIcon }> = {
  breakfast: { label: 'Breakfast', Icon: Coffee },
  lunch: { label: 'Lunch', Icon: Sun },
  dinner: { label: 'Dinner', Icon: Sunset },
  snack: { label: 'Snack', Icon: Cookie },
}
const CATEGORY_ORDER: MealCategory[] = ['breakfast', 'lunch', 'dinner', 'snack']

type MacroKind = 'protein' | 'carbs' | 'fat'

function MacroBar({ label, consumed, target, macro }: { label: string; consumed: number; target: number; macro: MacroKind }) {
  const [mounted, setMounted] = useState(false)
  useEffect(() => {
    const id = requestAnimationFrame(() => setMounted(true))
    return () => cancelAnimationFrame(id)
  }, [])
  const p = pct(consumed, target)
  return (
    <div className="nut-macro">
      <div className="nut-macro__meta">
        <span className="nut-macro__name">{label}</span>
        <span className="nut-macro__val">
          {round(consumed)} / {round(target)} g<span className="nut-macro__pct">{p}%</span>
        </span>
      </div>
      <div
        className="nut-macro__track"
        role="progressbar"
        aria-valuenow={round(consumed)}
        aria-valuemin={0}
        aria-valuemax={Math.max(round(target), 1)}
        aria-label={`${label}: ${round(consumed)} of ${round(target)} grams`}
      >
        <div className={`nut-macro__fill nut-macro__fill--${macro}`} style={{ width: `${mounted ? p : 0}%` }} />
      </div>
    </div>
  )
}

function NutritionSkeleton() {
  return (
    <div className="page" aria-busy="true" aria-label="Loading nutrition">
      <div className="stack-sm">
        <Skeleton variant="text" width={120} />
        <Skeleton variant="title" width={180} />
      </div>
      <Card variant="hero">
        <div className="nut-hero__main">
          <Skeleton variant="circle" width={190} height={190} />
          <div className="nut-macros">
            {[0, 1, 2].map((i) => (
              <div key={i} className="nut-skel-macro">
                <Skeleton variant="text" width="40%" />
                <Skeleton variant="block" height={12} radius="var(--radius-pill)" />
              </div>
            ))}
          </div>
        </div>
      </Card>
      <Card>
        <Skeleton variant="title" width={120} />
        <div style={{ marginTop: 'var(--sp-3)' }}>
          <Skeleton variant="block" height={46} radius="var(--radius-md)" />
        </div>
      </Card>
      <Card>
        <Skeleton variant="title" width={150} />
        <div className="nut-skel-list">
          {[0, 1, 2].map((i) => (
            <div key={i} className="nut-skel-row">
              <Skeleton variant="text" width="55%" />
              <Skeleton variant="text" width="18%" />
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}

export function Nutrition() {
  const toast = useToast()
  const { data, loading, error, reload } = useAsync(async () => {
    const [today, list, quick, adaptive] = await Promise.all([
      nutritionApi.today(),
      mealsApi.list(),
      mealsApi.recent(),
      // Adaptive picks are additive: a failure must not break the nutrition log.
      recommendations.meals().catch(() => null),
    ])
    return { today, meals: list.items, quick, adaptive }
  }, [])

  const [nl, setNl] = useState('')
  const [parsing, setParsing] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<Meal | null>(null)
  const [form, setForm] = useState<MealInput>(emptyMeal)
  const [saving, setSaving] = useState(false)
  const [logging, setLogging] = useState<string | null>(null)

  function openAdd(prefill?: MealInput) {
    setEditing(null)
    setForm(prefill ?? emptyMeal)
    setModalOpen(true)
  }
  function openEdit(m: Meal) {
    setEditing(m)
    setForm({ name: m.name, kcal: m.kcal, category: m.category, protein_g: m.protein_g, carbs_g: m.carbs_g, fat_g: m.fat_g })
    setModalOpen(true)
  }

  async function parseNl() {
    if (!nl.trim()) return
    setParsing(true)
    try {
      const parsed = await ai.parseLog(nl)
      openAdd({ name: parsed.name, kcal: parsed.kcal, category: parsed.category, protein_g: parsed.protein_g, carbs_g: parsed.carbs_g, fat_g: parsed.fat_g })
      setNl('')
    } catch {
      toast.error('Could not parse that. Try adding it manually.')
    } finally {
      setParsing(false)
    }
  }

  async function saveMeal() {
    setSaving(true)
    try {
      if (editing) {
        await mealsApi.update(editing.id, form)
        toast.success('Meal updated.')
      } else {
        await mealsApi.create(form)
        toast.success('Meal logged!')
      }
      setModalOpen(false)
      reload()
    } catch {
      toast.error('Could not save meal.')
    } finally {
      setSaving(false)
    }
  }

  async function relog(m: MealQuickItem) {
    try {
      await mealsApi.create({ name: m.name, kcal: m.kcal, category: m.category, protein_g: m.protein_g, carbs_g: m.carbs_g, fat_g: m.fat_g })
      toast.success(`Logged ${m.name}`)
      reload()
    } catch {
      toast.error('Could not log meal.')
    }
  }

  // One-tap log of an adaptive pick. Logging it feeds the next round of picks
  // (history-based), closing the loop — the exact meal_payload is sent as-is.
  async function logSuggestion(s: AdaptiveMealSuggestion) {
    setLogging(s.name)
    try {
      await mealsApi.create(s.meal_payload)
      toast.success(`Logged ${s.name}`)
      reload()
    } catch {
      toast.error('Could not log meal.')
    } finally {
      setLogging(null)
    }
  }

  async function del(m: Meal) {
    try {
      await mealsApi.remove(m.id)
      reload()
    } catch {
      toast.error('Could not delete meal.')
    }
  }

  if (loading) return <NutritionSkeleton />
  if (error || !data) {
    return (
      <div className="page">
        <Card>
          <EmptyState
            icon={<Utensils size={28} aria-hidden="true" />}
            title="Couldn't load nutrition"
            text={error ?? 'Something went wrong. Please try again.'}
            action={<Button onClick={reload}>Retry</Button>}
          />
        </Card>
      </div>
    )
  }

  const { today, meals, quick, adaptive } = data
  const chips = [...quick.favorites, ...quick.recent].slice(0, 8)
  const seen = new Set<string>()
  const uniqueChips = chips.filter((m) => (seen.has(m.name) ? false : (seen.add(m.name), true)))

  const adaptivePicks = adaptive?.suggestions.slice(0, 3) ?? []
  const allStarters = adaptivePicks.length > 0 && adaptivePicks.every((s) => s.logged_count === 0)

  const kcalPct = pct(today.consumed.kcal, today.targets.kcal)
  const overBudget = today.targets.kcal > 0 && today.consumed.kcal > today.targets.kcal
  const onTarget = !overBudget && today.targets.kcal > 0 && today.consumed.kcal >= today.targets.kcal * 0.9
  const state: 'under' | 'on' | 'over' = overBudget ? 'over' : onTarget ? 'on' : 'under'
  // Adherence-neutral: over target reads as a calm amber note, on-target earns a
  // volt goal-hit — never a punitive red.
  const ringColor = overBudget ? 'var(--color-warning)' : onTarget ? 'var(--color-accent-strong)' : 'var(--color-primary)'
  const leftKcal = Math.max(0, round(today.remaining.kcal))
  const overKcal = Math.max(0, round(today.consumed.kcal - today.targets.kcal))

  const grouped = CATEGORY_ORDER.map((cat) => ({ cat, items: meals.filter((m) => m.category === cat) })).filter(
    (g) => g.items.length > 0,
  )

  return (
    <div className="page stagger">
      <PageHeader
        eyebrow={friendlyDate(todayISO())}
        title="Nutrition"
        subtitle="Log meals and hit your macro targets."
        actions={
          <Button leftIcon={<Plus size={18} aria-hidden="true" />} onClick={() => openAdd()}>
            Add meal
          </Button>
        }
      />

      {/* Calorie hero + macro breakdown + folded day summary */}
      <Card variant="hero" className={`nut-hero${state === 'on' ? ' nut-hero--celebrate' : ''}`}>
        <div className="nut-hero__main">
          <div className="nut-ring">
            <ProgressRing value={kcalPct} size={196} stroke={15} color={ringColor} label={`${kcalPct}% of calorie target`}>
              <div className="nut-ring__center">
                <span className="nut-ring__value num">{round(today.consumed.kcal).toLocaleString()}</span>
                <span className="nut-ring__target num">of {round(today.targets.kcal).toLocaleString()} kcal</span>
                <span className={`nut-chip nut-chip--${state}`}>
                  {state === 'on' ? <Check size={13} aria-hidden="true" /> : state === 'over' ? null : <Flame size={13} aria-hidden="true" />}
                  {state === 'over'
                    ? `${overKcal.toLocaleString()} kcal over`
                    : state === 'on'
                      ? 'Target hit'
                      : `${leftKcal.toLocaleString()} kcal left`}
                </span>
              </div>
            </ProgressRing>
          </div>
          <div className="nut-macros">
            <MacroBar label="Protein" consumed={today.consumed.protein_g} target={today.targets.protein_g} macro="protein" />
            <MacroBar label="Carbs" consumed={today.consumed.carbs_g} target={today.targets.carbs_g} macro="carbs" />
            <MacroBar label="Fat" consumed={today.consumed.fat_g} target={today.targets.fat_g} macro="fat" />
          </div>
        </div>
        <div className="nut-hero__stats">
          <div className="nut-stat">
            <span className="nut-stat__label">Eaten</span>
            <span className="nut-stat__value num">
              {round(today.consumed.kcal).toLocaleString()} <i>kcal</i>
            </span>
          </div>
          <div className="nut-stat">
            <span className="nut-stat__label">{overBudget ? 'Over target' : 'Remaining'}</span>
            <span className="nut-stat__value num">
              {(overBudget ? overKcal : leftKcal).toLocaleString()} <i>kcal</i>
            </span>
          </div>
          <div className="nut-stat">
            <span className="nut-stat__label">Meals</span>
            <span className="nut-stat__value num">{meals.length}</span>
          </div>
        </div>
      </Card>

      {/* Natural-language quick add (secondary tool; header owns the primary CTA) */}
      <Card className="nut-quick">
        <CardHeader title="Quick add" action={<Badge variant="ai"><Sparkles size={12} aria-hidden="true" /> AI</Badge>} />
        <p className="nut-quick__hint">Describe a meal in plain English and we'll estimate the macros.</p>
        <div className="nut-quick__row">
          <Input
            className="nut-quick__input"
            placeholder="e.g. chicken burrito bowl ~650 kcal"
            value={nl}
            onChange={(e) => setNl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && parseNl()}
            aria-label="Describe your meal"
          />
          <Button variant="secondary" onClick={parseNl} loading={parsing} leftIcon={<Sparkles size={18} aria-hidden="true" />}>
            Parse
          </Button>
        </div>
      </Card>

      {/* Recents / favorites */}
      {uniqueChips.length > 0 && (
        <Card>
          <CardHeader title="Log again" />
          <div className="nut-chips">
            {uniqueChips.map((m) => (
              <FilterChip key={m.name} className="nut-relog" onClick={() => relog(m)} title={`${m.kcal} kcal`}>
                {m.favorite ? (
                  <span className="nut-star" aria-hidden="true">
                    <Star size={12} fill="currentColor" />
                  </span>
                ) : null}
                {m.name}
                <span className="nut-relog__kcal">{m.kcal} kcal</span>
              </FilterChip>
            ))}
          </div>
        </Card>
      )}

      {/* Adaptive picks — history-ranked, portion-scaled to fit the rest of today */}
      {adaptivePicks.length > 0 && (
        <Card className="nut-adapt">
          <CardHeader
            title="Based on your eating history"
            action={<Badge>{capitalize(adaptive!.confidence)} confidence</Badge>}
          />
          <p className="nut-adapt__hint">
            {allStarters
              ? 'Starter picks to get you going — log a few meals and these adapt to what you actually eat.'
              : 'Ranked from what you actually log and scaled to fit the rest of today. Logging one updates what we suggest next from your history.'}
          </p>
          <div className="nut-adapt__list">
            {adaptivePicks.map((s) => {
              const starter = s.logged_count === 0
              return (
                <div key={s.name} className="nut-adapt__item">
                  <div className="nut-adapt__head">
                    <div className="nut-adapt__title">
                      <span className="nut-adapt__name">{s.name}</span>
                      <span className="nut-adapt__cat">{CATEGORY_META[s.category].label}</span>
                    </div>
                    <Button
                      size="sm"
                      variant="secondary"
                      leftIcon={<Plus size={16} aria-hidden="true" />}
                      loading={logging === s.name}
                      onClick={() => logSuggestion(s)}
                    >
                      Log this
                    </Button>
                  </div>
                  <div className="nut-adapt__macros num">
                    {s.portion !== 1 ? <span className="nut-adapt__serving">{s.portion}× serving</span> : null}
                    <span>{round(s.kcal).toLocaleString()} kcal</span>
                    <span>P{round(s.protein_g)}</span>
                    <span>C{round(s.carbs_g)}</span>
                    <span>F{round(s.fat_g)}</span>
                  </div>
                  <p className="nut-adapt__reason">{s.reason}</p>
                  <span className="nut-adapt__meta">
                    {starter ? 'Starter suggestion' : `From your logs · eaten ${s.logged_count}× · ${capitalize(s.confidence)} confidence`}
                  </span>
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* Today's meals */}
      <Card>
        <CardHeader
          title="Today's meals"
          action={meals.length > 0 ? <Badge>{meals.length} · {round(today.consumed.kcal).toLocaleString()} kcal</Badge> : null}
        />
        {meals.length === 0 ? (
          <EmptyState
            icon={<Utensils size={28} aria-hidden="true" />}
            title="Nothing logged yet"
            text="Add your first meal to start tracking today's macros."
            action={
              <Button leftIcon={<Plus size={18} aria-hidden="true" />} onClick={() => openAdd()}>
                Add meal
              </Button>
            }
          />
        ) : (
          <div className="nut-groups">
            {grouped.map((g) => {
              const meta = CATEGORY_META[g.cat]
              const kcal = g.items.reduce((s, m) => s + m.kcal, 0)
              return (
                <div key={g.cat} className="nut-group">
                  <div className="nut-group__head">
                    <span className={`nut-group__ico nut-group__ico--${g.cat}`} aria-hidden="true">
                      <meta.Icon size={15} />
                    </span>
                    <span className="nut-group__name">{meta.label}</span>
                    <span className="nut-group__kcal">{round(kcal).toLocaleString()} kcal</span>
                  </div>
                  <List>
                    {g.items.map((m) => (
                      <ListRow
                        key={m.id}
                        title={
                          <span className="nut-meal__title">
                            {m.name}
                            {m.favorite ? (
                              <span className="nut-star" title="Favorite">
                                <Star size={13} fill="currentColor" aria-hidden="true" />
                              </span>
                            ) : null}
                          </span>
                        }
                        sub={`${m.kcal} kcal · P${round(m.protein_g ?? 0)} C${round(m.carbs_g ?? 0)} F${round(m.fat_g ?? 0)}${m.eaten_at ? ` · ${formatTime(m.eaten_at)}` : ''}`}
                        trailing={
                          <span className="nut-row__actions">
                            <IconButton label="Edit meal" size="sm" onClick={() => openEdit(m)}>
                              <Pencil size={15} />
                            </IconButton>
                            <IconButton label="Delete meal" size="sm" onClick={() => del(m)}>
                              <Trash2 size={15} />
                            </IconButton>
                          </span>
                        }
                      />
                    ))}
                  </List>
                </div>
              )
            })}
          </div>
        )}
      </Card>

      {/* Add / edit modal */}
      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editing ? 'Edit meal' : 'Add meal'}
        footer={
          <div className="row" style={{ justifyContent: 'flex-end' }}>
            <Button variant="ghost" onClick={() => setModalOpen(false)}>Cancel</Button>
            <Button onClick={saveMeal} loading={saving} disabled={!form.name || !form.kcal}>Save</Button>
          </div>
        }
      >
        <div className="stack">
          <Input label="Name" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} required />
          <Input label="Calories" type="number" min={0} value={String(form.kcal || '')} onChange={(e) => setForm((f) => ({ ...f, kcal: Number(e.target.value) }))} required />
          <div>
            <span className="field__label">Category</span>
            <div style={{ marginTop: 6 }}>
              <Segmented<MealCategory>
                ariaLabel="Category"
                value={form.category}
                onChange={(v) => setForm((f) => ({ ...f, category: v }))}
                block
                options={[
                  { value: 'breakfast', label: 'Breakfast' },
                  { value: 'lunch', label: 'Lunch' },
                  { value: 'dinner', label: 'Dinner' },
                  { value: 'snack', label: 'Snack' },
                ]}
              />
            </div>
          </div>
          <div className="nut-form-macros">
            <Input label="Protein (g)" type="number" min={0} value={String(form.protein_g ?? '')} onChange={(e) => setForm((f) => ({ ...f, protein_g: e.target.value ? Number(e.target.value) : undefined }))} />
            <Input label="Carbs (g)" type="number" min={0} value={String(form.carbs_g ?? '')} onChange={(e) => setForm((f) => ({ ...f, carbs_g: e.target.value ? Number(e.target.value) : undefined }))} />
            <Input label="Fat (g)" type="number" min={0} value={String(form.fat_g ?? '')} onChange={(e) => setForm((f) => ({ ...f, fat_g: e.target.value ? Number(e.target.value) : undefined }))} />
          </div>
        </div>
      </Modal>
    </div>
  )
}
