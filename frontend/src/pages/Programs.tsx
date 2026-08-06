import './Programs.css'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowRight,
  CalendarDays,
  ClipboardList,
  Dumbbell,
  Layers,
  Pencil,
  Sparkles,
  Target,
  Trash2,
} from 'lucide-react'
import { programs as programsApi } from '../api'
import type { Program, ProgramSummary, ProgressionScheme } from '../api'
import { useAsync } from '../lib/useAsync'
import { cx, humanize } from '../lib/format'
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  IconButton,
  Input,
  List,
  ListRow,
  Modal,
  PageHeader,
  Skeleton,
  StatusChip,
  useToast,
} from '../components/ui'

const PROGRESSION_LABEL: Record<string, string> = {
  linear: 'Linear',
  double: 'Double',
  rpe_autoreg: 'RPE auto',
  block: 'Block',
}
const progressionLabel = (p: ProgressionScheme) => PROGRESSION_LABEL[p] ?? humanize(p)

function ProgramsSkeleton() {
  return (
    <div className="page" aria-busy="true" aria-label="Loading programs">
      <div className="row-between wrap">
        <div className="stack-sm">
          <Skeleton variant="text" width={120} />
          <Skeleton variant="title" width={200} />
        </div>
        <Skeleton variant="block" width={190} height={44} radius="var(--radius-md)" />
      </div>
      <Card variant="hero">
        <div className="prog-skel-hero">
          <Skeleton variant="title" width={220} />
          <div className="prog-skel-row">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} variant="block" width={128} height={40} radius="var(--radius-pill)" />
            ))}
          </div>
        </div>
      </Card>
      <Card>
        <Skeleton variant="title" width={160} />
        <div className="prog-skel-row" style={{ marginTop: 'var(--sp-4)' }}>
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} variant="block" width={92} height={40} radius="var(--radius-md)" />
          ))}
        </div>
        <div className="prog-skel-exlist">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} variant="block" height={64} radius="var(--radius-md)" />
          ))}
        </div>
      </Card>
    </div>
  )
}

export function Programs() {
  const toast = useToast()
  const navigate = useNavigate()
  const { data, loading, error, reload } = useAsync(async () => {
    const [active, list] = await Promise.all([
      programsApi.active().catch(() => null),
      programsApi.list(),
    ])
    return { active, list: list.items }
  }, [])

  const [busy, setBusy] = useState(false)
  const [renaming, setRenaming] = useState<Program | ProgramSummary | null>(null)
  const [name, setName] = useState('')
  const [dayId, setDayId] = useState<number | null>(null)

  async function generate() {
    setBusy(true)
    try {
      await programsApi.generate({})
      toast.success('New program generated!')
      reload()
    } catch {
      toast.error('Could not generate a program.')
    } finally {
      setBusy(false)
    }
  }

  async function activate(id: number) {
    try {
      await programsApi.update(id, { active: true })
      toast.success('Program activated.')
      reload()
    } catch {
      toast.error('Could not activate.')
    }
  }

  async function del(id: number) {
    try {
      await programsApi.remove(id)
      toast.success('Program deleted.')
      reload()
    } catch {
      toast.error('Could not delete.')
    }
  }

  async function saveName() {
    if (!renaming) return
    try {
      await programsApi.update(renaming.id, { name })
      setRenaming(null)
      reload()
    } catch {
      toast.error('Could not rename.')
    }
  }

  if (loading) return <ProgramsSkeleton />
  if (error || !data) {
    return (
      <div className="page">
        <Card>
          <EmptyState
            icon={<ClipboardList size={28} aria-hidden="true" />}
            title="Couldn't load your programs"
            text={error ?? 'Something went wrong. Please try again.'}
            action={<Button onClick={reload}>Retry</Button>}
          />
        </Card>
      </div>
    )
  }
  const { active, list } = data
  const others = list.filter((p) => !active || p.id !== active.id)

  const days = active?.days ?? []
  const currentDay = days.find((d) => d.id === dayId) ?? days[0] ?? null

  return (
    <div className="page stagger">
      <PageHeader
        eyebrow="Training plan"
        title="Programs"
        subtitle="Your training plan, tailored to your goal."
        actions={
          <Button
            variant="secondary"
            leftIcon={<Sparkles size={18} aria-hidden="true" />}
            onClick={generate}
            loading={busy}
          >
            Generate program
          </Button>
        }
      />

      {active ? (
        <>
          <Card variant="hero" className="prog-hero">
            <div className="prog-hero__top">
              <div className="prog-hero__id">
                <span className="prog-hero__icon" aria-hidden="true">
                  <ClipboardList size={24} />
                </span>
                <div style={{ minWidth: 0 }}>
                  <div className="prog-hero__eyebrow">Active program</div>
                  <h2 className="prog-hero__name">{active.name}</h2>
                </div>
              </div>
              <div className="prog-hero__actions">
                <StatusChip status="in-progress">Active</StatusChip>
                <IconButton
                  label="Rename program"
                  onClick={() => {
                    setRenaming(active)
                    setName(active.name)
                  }}
                >
                  <Pencil size={18} aria-hidden="true" />
                </IconButton>
              </div>
            </div>

            <div className="prog-facts">
              <span className="prog-fact">
                <span className="prog-fact__icon" aria-hidden="true">
                  <Target size={18} />
                </span>
                <span className="prog-fact__body">
                  <span className="prog-fact__label">Goal</span>
                  <span className="prog-fact__value">{humanize(active.training_goal)}</span>
                </span>
              </span>
              <span className="prog-fact">
                <span className="prog-fact__icon" aria-hidden="true">
                  <Layers size={18} />
                </span>
                <span className="prog-fact__body">
                  <span className="prog-fact__label">Split</span>
                  <span className="prog-fact__value">{humanize(active.split_type)}</span>
                </span>
              </span>
              <span className="prog-fact">
                <span className="prog-fact__icon" aria-hidden="true">
                  <CalendarDays size={18} />
                </span>
                <span className="prog-fact__body">
                  <span className="prog-fact__label">Frequency</span>
                  <span className="prog-fact__value">{active.days_per_week} days/week</span>
                </span>
              </span>
            </div>
          </Card>

          {currentDay && (
            <Card>
              <CardHeader
                title="Training days"
                action={<Badge variant="primary">{humanize(active.split_type)}</Badge>}
              />
              <div className="prog-daytabs" role="tablist" aria-label="Program days">
                {days.map((d) => (
                  <button
                    key={d.id}
                    type="button"
                    role="tab"
                    aria-selected={d.id === currentDay.id}
                    className={cx('prog-daytab', d.id === currentDay.id && 'is-active')}
                    onClick={() => setDayId(d.id)}
                  >
                    <span>{d.name}</span>
                    <span className="prog-daytab__count">{d.exercises.length}</span>
                  </button>
                ))}
              </div>

              <div className="prog-day">
                <div className="prog-day__title">
                  <span className="prog-day__name">{currentDay.name}</span>
                  <span className="prog-day__count num">{currentDay.exercises.length} exercises</span>
                </div>
                <List>
                  {currentDay.exercises.map((ex, i) => (
                    <ListRow
                      key={`${currentDay.id}-${ex.exercise_id}`}
                      leading={<span className="prog-ex__idx num" aria-hidden="true">{i + 1}</span>}
                      title={ex.name}
                      sub={
                        <span className="prog-ex__meta num">
                          {ex.target_sets}×{ex.target_reps} · RPE {ex.target_rpe} · {ex.rest_seconds}s rest
                        </span>
                      }
                      trailing={<Badge>{progressionLabel(ex.progression)}</Badge>}
                    />
                  ))}
                </List>
                <Button
                  block
                  className="prog-start"
                  leftIcon={<Dumbbell size={18} aria-hidden="true" />}
                  rightIcon={<ArrowRight size={18} aria-hidden="true" />}
                  onClick={() => navigate('/workout')}
                >
                  Start workout
                </Button>
              </div>
            </Card>
          )}
        </>
      ) : (
        <Card>
          <EmptyState
            icon={<ClipboardList size={28} aria-hidden="true" />}
            title="No active program yet"
            text="Generate a personalised training plan built around your goal, experience, and weekly schedule."
            action={
              <Button
                gradient
                leftIcon={<Sparkles size={18} aria-hidden="true" />}
                onClick={generate}
                loading={busy}
              >
                Generate your first program
              </Button>
            }
          />
        </Card>
      )}

      {others.length > 0 && (
        <Card>
          <CardHeader title="All programs" action={<Badge>{others.length}</Badge>} />
          <List>
            {others.map((p) => (
              <ListRow
                key={p.id}
                leading={
                  <span className="prog-others__icon" aria-hidden="true">
                    <ClipboardList size={18} />
                  </span>
                }
                title={p.name}
                sub={`${humanize(p.training_goal)} · ${humanize(p.split_type)} · ${p.days_per_week} days/week`}
                trailing={
                  <span className="prog-others__actions">
                    <Button size="sm" variant="secondary" onClick={() => activate(p.id)}>
                      Activate
                    </Button>
                    <IconButton
                      label={`Rename ${p.name}`}
                      size="sm"
                      onClick={() => {
                        setRenaming(p)
                        setName(p.name)
                      }}
                    >
                      <Pencil size={16} aria-hidden="true" />
                    </IconButton>
                    <IconButton label={`Delete ${p.name}`} size="sm" onClick={() => del(p.id)}>
                      <Trash2 size={16} aria-hidden="true" />
                    </IconButton>
                  </span>
                }
              />
            ))}
          </List>
        </Card>
      )}

      <Modal
        open={renaming !== null}
        onClose={() => setRenaming(null)}
        title="Rename program"
        footer={
          <div className="row" style={{ justifyContent: 'flex-end' }}>
            <Button variant="ghost" onClick={() => setRenaming(null)}>
              Cancel
            </Button>
            <Button onClick={saveName} disabled={!name.trim()}>
              Save
            </Button>
          </div>
        }
      >
        <Input label="Program name" value={name} onChange={(e) => setName(e.target.value)} />
      </Modal>
    </div>
  )
}
