import './Performance.css'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Activity, BarChart3, Dumbbell, Plus, Scale, TrendingUp, Trophy } from 'lucide-react'
import { insights as insightsApi, performance as perfApi } from '../api'
import type { ExercisePerformance, PrRecord } from '../api'
import { useAsync } from '../lib/useAsync'
import { round } from '../lib/format'
import { useTheme } from '../theme/useTheme'
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  MetricTile,
  PageHeader,
  SectionTitle,
  Select,
  Skeleton,
} from '../components/ui'

/* Recharts renders SVG with explicit color attributes, so CSS variables
   don't resolve there — mirror the Ridgeline chart tokens per theme so charts
   stay legible in both. Primary = indigo, secondary = cyan, accent = volt (PR
   marker), bodyweight = amber. No orange. */
const CHART_LIGHT = {
  axis: '#8a93a3',
  grid: '#e6e9ef',
  primary: '#5b57e0',
  secondary: '#0e8aa3',
  accent: '#7cb518',
  bodyweight: '#d97706',
}
const CHART_DARK = {
  axis: '#6b7686',
  grid: '#232c38',
  primary: '#8b87ff',
  secondary: '#38bdf8',
  accent: '#cbff47',
  bodyweight: '#fbbf24',
}

const shortDate = (iso: string) => {
  const d = new Date(iso.length <= 10 ? `${iso}T00:00:00` : iso)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

/* Compact axis label for large volume numbers (5,000 -> "5k") so they don't clip. */
const kFmt = (v: number) => (Math.abs(v) >= 1000 ? `${Math.round(v / 100) / 10}k` : String(v))

interface TipItem {
  name?: string
  value?: number | string
  color?: string
  stroke?: string
  fill?: string
}
interface PerfTooltipProps {
  active?: boolean
  payload?: TipItem[]
  label?: string | number
  labelFormatter?: (value: string | number) => string
  unit?: string
  /** Explicit solid dot color — set per chart so bar gradients (url(...)) don't leak in. */
  color?: string
}

function PerfTooltip({ active, payload, label, labelFormatter, unit, color }: PerfTooltipProps) {
  if (!active || !payload || payload.length === 0) return null
  return (
    <div className="perf-tip">
      <div className="perf-tip__label">
        {labelFormatter && label !== undefined ? labelFormatter(label) : label}
      </div>
      {payload.map((p, i) => (
        <div key={i} className="perf-tip__row">
          <span
            className="perf-tip__dot"
            style={{ background: color ?? p.stroke ?? p.color ?? 'currentColor' }}
          />
          <span className="perf-tip__name">{p.name}</span>
          <span className="perf-tip__val">
            {p.value}
            {unit ? ` ${unit}` : ''}
          </span>
        </div>
      ))}
    </div>
  )
}

function PerformanceSkeleton() {
  return (
    <div className="page" aria-busy="true" aria-label="Crunching your numbers">
      <div className="stack-sm">
        <Skeleton variant="text" width={110} />
        <Skeleton variant="title" width={180} />
      </div>
      <div className="perf-tiles">
        {[0, 1, 2, 3].map((i) => (
          <Card key={i} variant="stat">
            <Skeleton variant="text" lines={3} />
          </Card>
        ))}
      </div>
      {[0, 1].map((i) => (
        <Card key={i}>
          <Skeleton variant="title" width={200} />
          <div style={{ marginTop: 'var(--sp-4)' }}>
            <Skeleton variant="block" height={208} radius="var(--radius-md)" />
          </div>
        </Card>
      ))}
    </div>
  )
}

export function Performance() {
  const navigate = useNavigate()
  const { theme } = useTheme()
  const palette = theme === 'dark' ? CHART_DARK : CHART_LIGHT

  const { data, loading, error, reload } = useAsync(async () => {
    const [summary, prs, volume, trends] = await Promise.all([
      perfApi.summary(),
      perfApi.prs(),
      perfApi.volume(),
      insightsApi.trends(30),
    ])
    return { summary, prs: prs.items, volume, trends }
  }, [])

  const [selected, setSelected] = useState<number | null>(null)
  const [detail, setDetail] = useState<ExercisePerformance | null>(null)
  const [showAllPrs, setShowAllPrs] = useState(false)

  useEffect(() => {
    if (data && selected === null && data.prs.length) setSelected(data.prs[0].exercise_id)
  }, [data, selected])

  useEffect(() => {
    if (selected === null) return
    let alive = true
    perfApi.exercise(selected).then((d) => alive && setDetail(d)).catch(() => alive && setDetail(null))
    return () => {
      alive = false
    }
  }, [selected])

  if (loading) return <PerformanceSkeleton />
  if (error || !data) {
    return (
      <div className="page">
        <Card>
          <EmptyState
            icon={<TrendingUp size={28} aria-hidden="true" />}
            title="Couldn't load your progress"
            text={error ?? 'Something went wrong. Please try again.'}
            action={<Button onClick={reload}>Retry</Button>}
          />
        </Card>
      </div>
    )
  }
  const { summary, prs, volume, trends } = data

  const weightSeries = trends.days
    .filter((d) => typeof d.weight_kg === 'number')
    .map((d) => ({ date: d.date, weight: d.weight_kg }))
  const volumeSeries = volume.weeks.map((w) => ({ week: w.week_start, volume: w.total_volume }))

  const topLift = summary.e1rm_highlights[0]
  const hasData =
    summary.sessions_count > 0 ||
    summary.total_volume > 0 ||
    prs.length > 0 ||
    volumeSeries.length > 0

  const axisTick = { fill: palette.axis, fontSize: 12 }

  // PRs are capped to a glanceable set by default; charts lead the page.
  const visiblePrs = showAllPrs ? prs : prs.slice(0, 6)
  const e1Trend = detail?.e1rm_trend ?? []
  const e1Delta = e1Trend.length >= 2 ? Math.round(e1Trend[e1Trend.length - 1].value - e1Trend[0].value) : 0
  const prPoint = e1Trend.length ? e1Trend.reduce((mx, p) => (p.value >= mx.value ? p : mx), e1Trend[0]) : null

  if (!hasData) {
    return (
      <div className="page stagger">
        <PageHeader eyebrow="Progress" title="Progress" subtitle="Strength, volume, and bodyweight trends." />
        <Card>
          <EmptyState
            icon={<Dumbbell size={28} aria-hidden="true" />}
            title="No training data yet"
            text="Log your first workout to unlock strength, volume, and bodyweight insights."
            action={
              <Button gradient leftIcon={<Plus size={18} aria-hidden="true" />} onClick={() => navigate('/workout')}>
                Log a workout
              </Button>
            }
          />
        </Card>
      </div>
    )
  }

  return (
    <div className="page stagger">
      <PageHeader eyebrow="Progress" title="Progress" subtitle="Strength, volume, and bodyweight trends." />

      {/* Per-exercise drill-down — e1RM + volume history (charts lead the page) */}
      {prs.length > 0 && (
        <Card>
          <CardHeader
            title="Exercise deep-dive"
            action={
              <div className="perf-select">
                <Select
                  value={selected ?? ''}
                  onChange={(e) => setSelected(Number(e.target.value))}
                  aria-label="Choose exercise"
                >
                  {prs.map((p: PrRecord) => (
                    <option key={p.exercise_id} value={p.exercise_id}>
                      {p.exercise_name}
                    </option>
                  ))}
                </Select>
              </div>
            }
          />
          {detail && (detail.e1rm_trend.length > 0 || detail.volume_trend.length > 0) ? (
            <>
              <div className="perf-charts2">
                <div className="perf-subchart">
                  <div className="perf-subchart__title">
                    <span className="perf-subchart__name"><TrendingUp size={15} aria-hidden="true" /> Estimated 1RM</span>
                    {e1Delta !== 0 ? (
                      <span className={`perf-delta num${e1Delta > 0 ? ' perf-delta--up' : ' perf-delta--down'}`}>
                        {e1Delta > 0 ? '+' : ''}{e1Delta} kg
                      </span>
                    ) : null}
                  </div>
                  <div className="perf-chart perf-chart--sm">
                    {detail.e1rm_trend.length > 0 ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={detail.e1rm_trend} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                          <defs>
                            <linearGradient id="perfE1rm" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="0%" stopColor={palette.primary} stopOpacity={0.14} />
                              <stop offset="100%" stopColor={palette.primary} stopOpacity={0.02} />
                            </linearGradient>
                          </defs>
                          <CartesianGrid stroke={palette.grid} strokeDasharray="3 3" vertical={false} />
                          <XAxis dataKey="date" tickFormatter={shortDate} tick={axisTick} stroke={palette.grid} tickLine={false} axisLine={false} />
                          <YAxis tick={axisTick} stroke={palette.grid} width={44} tickLine={false} axisLine={false} />
                          <Tooltip content={<PerfTooltip labelFormatter={(v) => shortDate(String(v))} unit="kg" color={palette.primary} />} cursor={{ stroke: palette.axis, strokeDasharray: '3 3' }} />
                          <Area type="monotone" dataKey="value" name="e1RM" stroke={palette.primary} strokeWidth={2} fill="url(#perfE1rm)" dot={false} activeDot={{ r: 4 }} />
                          {prPoint ? (
                            <ReferenceDot x={prPoint.date} y={prPoint.value} r={4} fill={palette.accent} stroke={palette.accent} />
                          ) : null}
                        </AreaChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="perf-chart-empty">Not enough data yet.</div>
                    )}
                  </div>
                </div>

                <div className="perf-subchart">
                  <div className="perf-subchart__title">
                    <BarChart3 size={15} aria-hidden="true" /> Volume per session
                  </div>
                  <div className="perf-chart perf-chart--sm">
                    {detail.volume_trend.length > 0 ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={detail.volume_trend} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                          <defs>
                            <linearGradient id="perfExVol" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="0%" stopColor={palette.secondary} stopOpacity={0.14} />
                              <stop offset="100%" stopColor={palette.secondary} stopOpacity={0.02} />
                            </linearGradient>
                          </defs>
                          <CartesianGrid stroke={palette.grid} strokeDasharray="3 3" vertical={false} />
                          <XAxis dataKey="date" tickFormatter={shortDate} tick={axisTick} stroke={palette.grid} tickLine={false} axisLine={false} />
                          <YAxis tickFormatter={kFmt} tick={axisTick} stroke={palette.grid} width={44} tickLine={false} axisLine={false} />
                          <Tooltip content={<PerfTooltip labelFormatter={(v) => shortDate(String(v))} unit="kg" color={palette.secondary} />} cursor={{ stroke: palette.axis, strokeDasharray: '3 3' }} />
                          <Area type="monotone" dataKey="value" name="Volume" stroke={palette.secondary} strokeWidth={2} fill="url(#perfExVol)" dot={false} activeDot={{ r: 4 }} />
                        </AreaChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="perf-chart-empty">Not enough data yet.</div>
                    )}
                  </div>
                </div>
              </div>
              {detail.best && (
                <div className="perf-best">
                  <Trophy size={15} aria-hidden="true" />
                  <span>
                    Best <strong>{detail.best.best_weight}kg × {detail.best.best_reps}</strong> · est. 1RM{' '}
                    <strong>{detail.best.best_e1rm}kg</strong>
                  </span>
                </div>
              )}
            </>
          ) : (
            <div className="perf-chart-empty">
              <Dumbbell className="perf-chart-empty__icon" size={26} aria-hidden="true" />
              Log sets for this lift to see its trend.
            </div>
          )}
        </Card>
      )}

      {/* Weekly training volume */}
      <Card>
        <CardHeader title="Weekly training volume" />
        {volumeSeries.length > 0 ? (
          <div className="perf-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={volumeSeries} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="perfWvol" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={palette.secondary} stopOpacity={0.95} />
                    <stop offset="100%" stopColor={palette.secondary} stopOpacity={0.5} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={palette.grid} strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="week" tickFormatter={shortDate} tick={axisTick} stroke={palette.grid} tickLine={false} axisLine={false} />
                <YAxis tickFormatter={kFmt} tick={axisTick} stroke={palette.grid} width={44} tickLine={false} axisLine={false} />
                <Tooltip content={<PerfTooltip labelFormatter={(v) => shortDate(String(v))} unit="kg" color={palette.secondary} />} cursor={{ fill: palette.grid }} />
                <Bar dataKey="volume" name="Volume" fill="url(#perfWvol)" radius={[6, 6, 0, 0]} maxBarSize={54} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="perf-chart-empty">
            <BarChart3 className="perf-chart-empty__icon" size={26} aria-hidden="true" />
            No volume data yet.
          </div>
        )}
      </Card>

      {/* Bodyweight */}
      <Card>
        <CardHeader title="Bodyweight" />
        {weightSeries.length > 0 ? (
          <div className="perf-chart">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={weightSeries} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="perfBw" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={palette.bodyweight} stopOpacity={0.14} />
                    <stop offset="100%" stopColor={palette.bodyweight} stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={palette.grid} strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tickFormatter={shortDate} tick={axisTick} stroke={palette.grid} tickLine={false} axisLine={false} />
                <YAxis domain={['dataMin - 1', 'dataMax + 1']} tick={axisTick} stroke={palette.grid} width={44} tickLine={false} axisLine={false} />
                <Tooltip content={<PerfTooltip labelFormatter={(v) => shortDate(String(v))} unit="kg" color={palette.bodyweight} />} cursor={{ stroke: palette.axis, strokeDasharray: '3 3' }} />
                <Area type="monotone" dataKey="weight" name="Weight" stroke={palette.bodyweight} strokeWidth={2} fill="url(#perfBw)" dot={false} activeDot={{ r: 4 }} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="perf-chart-empty">
            <Scale className="perf-chart-empty__icon" size={26} aria-hidden="true" />
            Log your bodyweight to see the trend.
          </div>
        )}
      </Card>

      {/* Summary + records follow the trends */}
      <div className="perf-tiles">
        <MetricTile
          label="Total volume"
          value={round(summary.total_volume).toLocaleString()}
          unit="kg"
          icon={<BarChart3 size={18} aria-hidden="true" />}
          sub="lifted all-time"
        />
        <MetricTile
          label="Sessions"
          value={summary.sessions_count}
          icon={<Activity size={18} aria-hidden="true" />}
          sub="logged"
        />
        <MetricTile
          label="Personal records"
          value={summary.prs_count}
          icon={<Trophy size={18} aria-hidden="true" />}
          sub="all-time"
        />
        <MetricTile
          label="Top e1RM"
          value={topLift?.e1rm ?? '—'}
          unit={topLift ? 'kg' : undefined}
          icon={<TrendingUp size={18} aria-hidden="true" />}
          sub={topLift?.exercise_name ?? 'no lifts yet'}
        />
      </div>

      {prs.length > 0 && (
        <div>
          <SectionTitle action={<Badge variant="success">{prs.length} total</Badge>}>
            Personal records
          </SectionTitle>
          <div className="perf-pr-grid">
            {visiblePrs.map((p: PrRecord) => (
              <Card key={p.exercise_id} variant="stat" className="perf-pr">
                <div className="perf-pr__top">
                  <span className="perf-pr__rank" aria-hidden="true">
                    <Trophy size={14} />
                  </span>
                  <span className="perf-pr__name">{p.exercise_name}</span>
                </div>
                <div className="perf-pr__e1rm num">
                  {p.best_e1rm}
                  <span className="perf-pr__unit">kg e1RM</span>
                </div>
                <div className="perf-pr__sub num">
                  Best {p.best_weight}kg × {p.best_reps}
                </div>
              </Card>
            ))}
          </div>
          {prs.length > 6 ? (
            <div className="perf-pr-more">
              <Button
                variant="ghost"
                size="sm"
                aria-expanded={showAllPrs}
                onClick={() => setShowAllPrs((v) => !v)}
              >
                {showAllPrs ? 'Show fewer' : `Show all ${prs.length}`}
              </Button>
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}
