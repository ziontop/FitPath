import './Insights.css'
import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import {
  Sparkles,
  Send,
  Flame,
  Dumbbell,
  Utensils,
  Award,
  Trophy,
  Droplet,
  Sunrise,
  Moon,
  Clock,
  MessageSquare,
  BarChart3,
} from 'lucide-react'
import { ai, insights as insightsApi, recommendations } from '../api'
import type { AiInsights, Consistency } from '../api'
import { useAsync } from '../lib/useAsync'
import { capitalize } from '../lib/format'
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  FilterChip,
  IconButton,
  Input,
  MetricTile,
  PageHeader,
  ProgressBar,
  Segmented,
  Skeleton,
  Spinner,
  StatusChip,
} from '../components/ui'

interface Message {
  role: 'user' | 'coach'
  text: string
}

const WELCOME: Message = {
  role: 'coach',
  text: "Hi! I'm your FitPath coach. I read your real logs — ask me about training, nutrition, or what to do next.",
}

interface PatternRow {
  title: string
  detail: string
  kind: string
}

const MEAL_ORDER = ['breakfast', 'lunch', 'dinner', 'snack']

const CONSISTENCY_LABEL: Record<Consistency, string> = {
  on_track: 'On track',
  inconsistent: 'Inconsistent',
  returning: 'Returning',
}

/** Turn the backend's meal-pattern analysis into human-readable insight rows. */
function buildPatternInsights(p: AiInsights): PatternRow[] {
  if (!p || p.total_meals === 0) {
    return [{ title: 'No patterns yet', detail: 'Log a few meals and your coach will surface trends here.', kind: 'general' }]
  }
  const rows: PatternRow[] = [
    { title: 'Logging cadence', detail: `~${p.meals_per_day} meals/day across ${p.days_observed} days (${p.total_meals} logged).`, kind: 'general' },
  ]
  for (const cat of MEAL_ORDER) {
    const time = p.typical_times[cat]
    if (time) {
      const kcal = p.avg_kcal[cat]
      rows.push({ title: `Typical ${cat}`, detail: `Usually around ${time}${kcal ? ` · ~${kcal} kcal` : ''}.`, kind: 'eating' })
    }
  }
  for (const cat of MEAL_ORDER) {
    const top = p.top_foods[cat]?.[0]
    if (top) {
      rows.push({ title: `Go-to ${cat}`, detail: `${top.name} — logged ${top.count}× (~${top.avg_kcal} kcal).`, kind: 'eating' })
    }
  }
  return rows.slice(0, 8)
}

/** Flat lucide icon per achievement id (keeps the design emoji-free). */
function badgeIcon(id: string): ReactNode {
  switch (id) {
    case 'first_meal':
      return <Utensils size={22} aria-hidden="true" />
    case 'ten_workouts':
      return <Dumbbell size={22} aria-hidden="true" />
    case 'week_streak':
      return <Flame size={22} aria-hidden="true" />
    case 'consistent_lifter':
      return <Trophy size={22} aria-hidden="true" />
    case 'hydration_master':
      return <Droplet size={22} aria-hidden="true" />
    default:
      return <Award size={22} aria-hidden="true" />
  }
}

function InsightsSkeleton() {
  return (
    <div className="page" aria-busy="true" aria-label="Loading your coach">
      <div className="stack-sm">
        <Skeleton variant="text" width={120} />
        <Skeleton variant="title" width={240} />
      </div>
      <Skeleton variant="block" height={44} radius="var(--radius-md)" width={280} />
      <Card>
        <div className="ins-skel-chat">
          <Skeleton variant="text" width="70%" />
          <Skeleton variant="text" width="52%" />
          <div className="ins-skel-chat__me">
            <Skeleton variant="block" height={40} width="46%" radius="var(--radius-lg)" />
          </div>
          <Skeleton variant="text" width="64%" />
          <div className="ins-skel-chat__foot">
            <Skeleton variant="block" height={44} radius="var(--radius-md)" />
          </div>
        </div>
      </Card>
    </div>
  )
}

export function Insights() {
  const { data, loading, error, reload } = useAsync(async () => {
    const [aiInsights, streaks, achievements, circadian, adaptive] = await Promise.all([
      ai.insights(),
      insightsApi.streaks(),
      insightsApi.achievements(),
      insightsApi.circadian(),
      // Adaptive envelope powers the "what your history is changing" summary.
      recommendations.adaptive().catch(() => null),
    ])
    return { aiInsights, streaks, achievements, circadian, adaptive }
  }, [])

  const [view, setView] = useState<'coach' | 'insights'>('coach')
  const [messages, setMessages] = useState<Message[]>([WELCOME])
  const [chips, setChips] = useState<string[]>([
    'What should I eat next?',
    'How is my bench progressing?',
    'Am I hitting protein?',
  ])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  async function send(text: string) {
    const msg = text.trim()
    if (!msg || sending) return
    setMessages((m) => [...m, { role: 'user', text: msg }])
    setInput('')
    setSending(true)
    try {
      const res = await ai.chat(msg)
      setMessages((m) => [...m, { role: 'coach', text: res.reply }])
      if (res.chips?.length) setChips(res.chips)
    } catch {
      setMessages((m) => [...m, { role: 'coach', text: 'Sorry, I had trouble answering just now.' }])
    } finally {
      setSending(false)
    }
  }

  if (loading) return <InsightsSkeleton />
  if (error || !data) {
    return (
      <div className="page">
        <Card>
          <EmptyState
            icon={<Sparkles size={28} aria-hidden="true" />}
            title="Couldn't load your coach"
            text={error ?? 'Something went wrong. Please try again.'}
            action={<Button onClick={reload}>Retry</Button>}
          />
        </Card>
      </div>
    )
  }

  const { aiInsights, streaks, achievements, circadian, adaptive } = data
  const patternInsights = buildPatternInsights(aiInsights)
  const earnedBadges = achievements.badges.filter((b) => b.earned).length
  const hasPatterns = aiInsights.total_meals > 0

  const streakTiles = [
    { label: 'Logging streak', value: streaks.any_streak, sub: 'days', icon: <Flame size={18} aria-hidden="true" /> },
    { label: 'Workout streak', value: streaks.workout_streak, sub: 'sessions', icon: <Dumbbell size={18} aria-hidden="true" /> },
    { label: 'Meal streak', value: streaks.meal_streak, sub: 'days', icon: <Utensils size={18} aria-hidden="true" /> },
    { label: 'Badges', value: earnedBadges, sub: `of ${achievements.badges.length}`, icon: <Award size={18} aria-hidden="true" /> },
  ]

  const rhythm = [
    { label: 'Wake', value: circadian.wake_time, icon: <Sunrise size={18} aria-hidden="true" /> },
    { label: 'First meal', value: circadian.first_meal, icon: <Utensils size={18} aria-hidden="true" /> },
    { label: 'Last meal', value: circadian.last_meal, icon: <Utensils size={18} aria-hidden="true" /> },
    { label: 'Sleep', value: circadian.sleep_target, icon: <Moon size={18} aria-hidden="true" /> },
    { label: 'Eating window', value: `${circadian.eating_window_hours}h`, icon: <Clock size={18} aria-hidden="true" /> },
  ]

  // Before the conversation grows, show a centered welcome + starters instead of
  // a tall empty void.
  const firstRun = messages.length <= 1 && !sending

  return (
    <div className="page stagger">
      <PageHeader
        eyebrow="AI coach"
        title="Coach & insights"
        subtitle="Patterns from your data, plus a coach that actually answers."
        actions={<Badge variant="ai">AI</Badge>}
      />

      <div className="ins-toolbar">
        <Segmented<'coach' | 'insights'>
          ariaLabel="Coach or insights"
          value={view}
          onChange={setView}
          options={[
            { value: 'coach', label: <span className="ins-seg"><MessageSquare size={16} aria-hidden="true" /> Coach</span> },
            { value: 'insights', label: <span className="ins-seg"><BarChart3 size={16} aria-hidden="true" /> Insights</span> },
          ]}
        />
      </div>

      {view === 'coach' ? (
        <Card className="ins-chat-card" flush>
          <div className={`ins-chat${firstRun ? ' ins-chat--empty' : ''}`}>
            <div className="ins-chat__messages" ref={scrollRef}>
              {firstRun ? (
                <div className="ins-welcome">
                  <span className="ins-welcome__icon" aria-hidden="true">
                    <Sparkles size={24} />
                  </span>
                  <h3 className="ins-welcome__title">Ask your coach anything</h3>
                  <p className="ins-welcome__text">{WELCOME.text}</p>
                  {chips.length > 0 ? (
                    <div className="ins-chips ins-welcome__chips">
                      {chips.map((c) => (
                        <FilterChip key={c} onClick={() => send(c)}>
                          {c}
                        </FilterChip>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : (
                <>
                  {messages.map((m, i) => (
                    <div key={i} className={`ins-msg ins-msg--${m.role}`}>
                      {m.role === 'coach' ? (
                        <span className="ins-msg__avatar" aria-hidden="true">
                          <Sparkles size={16} />
                        </span>
                      ) : null}
                      <div className="ins-msg__bubble">{m.text}</div>
                    </div>
                  ))}
                  {sending ? (
                    <div className="ins-msg ins-msg--coach">
                      <span className="ins-msg__avatar" aria-hidden="true">
                        <Sparkles size={16} />
                      </span>
                      <div className="ins-msg__bubble ins-msg__bubble--typing" aria-label="Coach is thinking">
                        <span className="ins-typing">
                          <i />
                          <i />
                          <i />
                        </span>
                      </div>
                    </div>
                  ) : null}
                </>
              )}
            </div>

            <div className="ins-chat__foot">
              {!firstRun && chips.length > 0 ? (
                <div className="ins-starters">
                  <span className="ins-starters__label">
                    <Sparkles size={13} aria-hidden="true" /> Try asking
                  </span>
                  <div className="ins-chips">
                    {chips.map((c) => (
                      <FilterChip key={c} onClick={() => send(c)}>
                        {c}
                      </FilterChip>
                    ))}
                  </div>
                </div>
              ) : null}
              <form
                className="ins-form"
                onSubmit={(e) => {
                  e.preventDefault()
                  send(input)
                }}
              >
                <Input
                  className="ins-form__input"
                  placeholder="Ask your coach anything…"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  aria-label="Message the coach"
                />
                <IconButton
                  type="submit"
                  label="Send message"
                  variant="primary"
                  disabled={!input.trim() || sending}
                >
                  {sending ? <Spinner size="sm" /> : <Send size={18} aria-hidden="true" />}
                </IconButton>
              </form>
            </div>
          </div>
        </Card>
      ) : (
        <>
          {adaptive ? (
            <Card className="ins-adapt">
              <CardHeader title="What your history is changing" action={<Badge>From your logs</Badge>} />
              <p className="ins-adapt__tip">{adaptive.tip}</p>
              <div className="ins-adapt__facts">
                {adaptive.workout.adherence ? (
                  <span className="ins-adapt__fact">
                    <Dumbbell size={14} aria-hidden="true" />
                    {CONSISTENCY_LABEL[adaptive.workout.adherence.consistency]} · {adaptive.workout.adherence.sessions_last_14d} sessions in 14 days
                  </span>
                ) : null}
                <span className="ins-adapt__fact">
                  <BarChart3 size={14} aria-hidden="true" />
                  {capitalize(adaptive.workout.confidence)} training · {capitalize(adaptive.meals.confidence)} nutrition confidence
                </span>
              </div>
            </Card>
          ) : null}

          <div className="ins-metrics">
            {streakTiles.map((s) => (
              <MetricTile key={s.label} label={s.label} value={s.value} sub={s.sub} icon={s.icon} />
            ))}
          </div>

          <Card>
            <CardHeader title="Patterns we noticed" action={<Badge>From your logs</Badge>} />
            {hasPatterns ? (
              <div className="ins-patterns">
                {patternInsights.map((ins, i) => (
                  <div key={i} className="ins-pattern">
                    <div className="ins-pattern__main">
                      <div className="ins-pattern__title">{ins.title}</div>
                      <div className="ins-pattern__detail">{ins.detail}</div>
                    </div>
                    {ins.kind ? <Badge>{capitalize(ins.kind)}</Badge> : null}
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState
                icon={<Utensils size={28} aria-hidden="true" />}
                title="No patterns yet"
                text="Log a few meals and your coach will start surfacing trends here."
              />
            )}
          </Card>

          <Card>
            <CardHeader title="Daily rhythm" action={<Badge variant="info">Circadian</Badge>} />
            <div className="ins-rhythm">
              {rhythm.map((r) => (
                <div key={r.label} className="ins-rhythm__item">
                  <span className="ins-rhythm__icon" aria-hidden="true">
                    {r.icon}
                  </span>
                  <div className="ins-rhythm__meta">
                    <span className="ins-rhythm__label">{r.label}</span>
                    <span className="ins-rhythm__value">{r.value}</span>
                  </div>
                </div>
              ))}
            </div>
            {circadian.tips.length > 0 ? (
              <ul className="ins-tips">
                {circadian.tips.map((t, i) => (
                  <li key={i} className="ins-tips__item">
                    <span className="ins-tips__dot" aria-hidden="true">
                      <Sparkles size={13} />
                    </span>
                    <span>{t}</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </Card>

          <Card>
            <CardHeader title="Achievements" action={<Badge variant="primary">{earnedBadges}/{achievements.badges.length}</Badge>} />
            <div className="ins-badges">
              {achievements.badges.map((b) => (
                <div key={b.id} className={`ins-badge ${b.earned ? 'is-earned' : 'is-locked'}`}>
                  <span
                    className="ins-badge__icon"
                    style={b.earned ? { background: `color-mix(in srgb, ${b.color} 18%, transparent)`, color: b.color } : undefined}
                    aria-hidden="true"
                  >
                    {badgeIcon(b.id)}
                  </span>
                  <span className="ins-badge__label">{b.label}</span>
                  {b.earned ? (
                    <StatusChip status="completed">Earned</StatusChip>
                  ) : (
                    <div className="ins-badge__progress">
                      <ProgressBar value={b.current} max={b.target} label={`${b.label} progress`} />
                      <span className="ins-badge__count">
                        {b.current}/{b.target}
                      </span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </Card>
        </>
      )}
    </div>
  )
}
