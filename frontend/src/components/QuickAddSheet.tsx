import { useState } from 'react'
import type { FormEvent } from 'react'
import { Utensils, Activity, Droplet, Moon, Footprints, Scale, ChevronLeft } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { BottomSheet, Button, Input, Segmented } from './ui'
import { useToast } from './ui'
import { activities, meals, sleep, stepsApi, water, weight } from '../api'
import type { Intensity, MealCategory } from '../api'

export type QuickAddKind = 'meal' | 'activity' | 'water' | 'sleep' | 'steps' | 'weight'

const TILES: { kind: QuickAddKind; Icon: LucideIcon; label: string; color: string }[] = [
  { kind: 'meal', Icon: Utensils, label: 'Meal', color: 'var(--color-primary)' },
  { kind: 'activity', Icon: Activity, label: 'Activity', color: 'var(--color-success)' },
  { kind: 'water', Icon: Droplet, label: 'Water', color: 'var(--color-secondary)' },
  { kind: 'sleep', Icon: Moon, label: 'Sleep', color: '#8b5cf6' },
  { kind: 'steps', Icon: Footprints, label: 'Steps', color: '#14b8a6' },
  { kind: 'weight', Icon: Scale, label: 'Weight', color: '#ec4899' },
]

interface Props {
  open: boolean
  onClose: () => void
  onLogged?: () => void
  initialKind?: QuickAddKind | null
}

export function QuickAddSheet({ open, onClose, onLogged, initialKind = null }: Props) {
  const toast = useToast()
  const [kind, setKind] = useState<QuickAddKind | null>(initialKind)
  const [saving, setSaving] = useState(false)

  // form fields
  const [name, setName] = useState('')
  const [kcal, setKcal] = useState('')
  const [category, setCategory] = useState<MealCategory>('lunch')
  const [protein, setProtein] = useState('')
  const [carbs, setCarbs] = useState('')
  const [fat, setFat] = useState('')
  const [minutes, setMinutes] = useState('')
  const [intensity, setIntensity] = useState<Intensity>('moderate')
  const [ml, setMl] = useState('')
  const [hours, setHours] = useState('')
  const [wake, setWake] = useState('07:00')
  const [stepCount, setStepCount] = useState('')
  const [weightKg, setWeightKg] = useState('')

  function reset() {
    setKind(null)
    setName(''); setKcal(''); setProtein(''); setCarbs(''); setFat('')
    setMinutes(''); setMl(''); setHours(''); setStepCount(''); setWeightKg('')
  }

  function close() {
    reset()
    onClose()
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!kind) return
    setSaving(true)
    try {
      switch (kind) {
        case 'meal':
          await meals.create({
            name,
            kcal: Number(kcal),
            category,
            protein_g: protein ? Number(protein) : undefined,
            carbs_g: carbs ? Number(carbs) : undefined,
            fat_g: fat ? Number(fat) : undefined,
          })
          break
        case 'activity':
          await activities.create({ activity: name, minutes: Number(minutes), intensity })
          break
        case 'water':
          await water.create({ ml: Number(ml) })
          break
        case 'sleep':
          await sleep.create({ hours: Number(hours), wake_time: wake })
          break
        case 'steps':
          await stepsApi.upsert({ steps: Number(stepCount) })
          break
        case 'weight':
          await weight.upsert({ weight_kg: Number(weightKg) })
          break
      }
      toast.success('Logged!')
      onLogged?.()
      close()
    } catch {
      toast.error('Could not save. Try again.')
    } finally {
      setSaving(false)
    }
  }

  const title = kind ? `Log ${kind}` : 'Quick add'

  return (
    <BottomSheet open={open} onClose={close} title={title}>
      {!kind ? (
        <div className="add-grid">
          {TILES.map((t) => (
            <button key={t.kind} className="add-tile" onClick={() => setKind(t.kind)}>
              <span
                className="add-tile__ico"
                style={{ color: t.color, background: `color-mix(in srgb, ${t.color} 14%, transparent)` }}
                aria-hidden="true"
              >
                <t.Icon size={24} />
              </span>
              {t.label}
            </button>
          ))}
        </div>
      ) : (
        <form className="stack" onSubmit={submit}>
          {kind === 'meal' && (
            <>
              <Input label="What did you eat?" value={name} onChange={(e) => setName(e.target.value)} required />
              <div className="row">
                <Input label="Calories" type="number" min={0} value={kcal} onChange={(e) => setKcal(e.target.value)} required wrapperClassName="grow" />
              </div>
              <div>
                <span className="field__label">Category</span>
                <div style={{ marginTop: 6 }}>
                  <Segmented<MealCategory>
                    ariaLabel="Meal category"
                    value={category}
                    onChange={setCategory}
                    options={[
                      { value: 'breakfast', label: 'Breakfast' },
                      { value: 'lunch', label: 'Lunch' },
                      { value: 'dinner', label: 'Dinner' },
                      { value: 'snack', label: 'Snack' },
                    ]}
                  />
                </div>
              </div>
              <div className="row">
                <Input label="Protein (g)" type="number" min={0} value={protein} onChange={(e) => setProtein(e.target.value)} wrapperClassName="grow" />
                <Input label="Carbs (g)" type="number" min={0} value={carbs} onChange={(e) => setCarbs(e.target.value)} wrapperClassName="grow" />
                <Input label="Fat (g)" type="number" min={0} value={fat} onChange={(e) => setFat(e.target.value)} wrapperClassName="grow" />
              </div>
            </>
          )}
          {kind === 'activity' && (
            <>
              <Input label="Activity" value={name} onChange={(e) => setName(e.target.value)} required />
              <Input label="Minutes" type="number" min={0} value={minutes} onChange={(e) => setMinutes(e.target.value)} required />
              <div>
                <span className="field__label">Intensity</span>
                <div style={{ marginTop: 6 }}>
                  <Segmented<Intensity>
                    ariaLabel="Intensity"
                    value={intensity}
                    onChange={setIntensity}
                    options={[
                      { value: 'light', label: 'Light' },
                      { value: 'moderate', label: 'Moderate' },
                      { value: 'vigorous', label: 'Vigorous' },
                    ]}
                  />
                </div>
              </div>
            </>
          )}
          {kind === 'water' && (
            <>
              <div className="row wrap">
                {[250, 500, 750].map((v) => (
                  <Button key={v} type="button" variant={ml === String(v) ? 'primary' : 'secondary'} onClick={() => setMl(String(v))}>
                    {v} ml
                  </Button>
                ))}
              </div>
              <Input label="Amount (ml)" type="number" min={0} value={ml} onChange={(e) => setMl(e.target.value)} required />
            </>
          )}
          {kind === 'sleep' && (
            <>
              <Input label="Hours slept" type="number" step="0.1" min={0} value={hours} onChange={(e) => setHours(e.target.value)} required />
              <Input label="Wake time" type="time" value={wake} onChange={(e) => setWake(e.target.value)} required />
            </>
          )}
          {kind === 'steps' && (
            <Input label="Steps today" type="number" min={0} value={stepCount} onChange={(e) => setStepCount(e.target.value)} required />
          )}
          {kind === 'weight' && (
            <Input label="Weight (kg)" type="number" step="0.1" min={0} value={weightKg} onChange={(e) => setWeightKg(e.target.value)} required />
          )}

          <div className="wizard__nav">
            <Button type="button" variant="ghost" onClick={() => setKind(null)} leftIcon={<ChevronLeft size={16} aria-hidden="true" />}>
              Back
            </Button>
            <Button type="submit" loading={saving}>
              Save
            </Button>
          </div>
        </form>
      )}
    </BottomSheet>
  )
}
