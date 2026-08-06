import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'

const clampPct = (n: number) => Math.max(0, Math.min(100, n))

/** Flips to true on the frame after mount so CSS transitions animate from empty → value. */
function useMountAnimate(enabled: boolean) {
  const [ready, setReady] = useState(!enabled)
  useEffect(() => {
    if (!enabled) return
    const id = requestAnimationFrame(() => setReady(true))
    return () => cancelAnimationFrame(id)
  }, [enabled])
  return ready
}

export interface ProgressBarProps {
  value: number
  max?: number
  variant?: 'primary' | 'success' | 'secondary' | 'warning'
  /** Use the brand gradient fill instead of a flat color. */
  gradient?: boolean
  label?: string
}

export function ProgressBar({ value, max = 100, variant = 'primary', gradient = false, label }: ProgressBarProps) {
  const pct = clampPct(max > 0 ? (value / max) * 100 : 0)
  const fillCls = [
    'progress__fill',
    variant !== 'primary' ? `progress__fill--${variant}` : '',
    gradient ? 'progress__fill--gradient' : '',
  ]
    .filter(Boolean)
    .join(' ')
  return (
    <div
      className="progress"
      role="progressbar"
      aria-valuenow={Math.round(value)}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-label={label}
    >
      <div className={fillCls} style={{ width: `${pct}%` }} />
    </div>
  )
}

export interface ProgressRingProps {
  value: number // 0..100
  size?: number
  stroke?: number
  color?: string
  trackColor?: string
  children?: ReactNode
  label?: string
  /** Animate the fill from empty on first render. */
  animate?: boolean
}

export function ProgressRing({
  value,
  size = 120,
  stroke = 12,
  color = 'var(--color-primary)',
  trackColor = 'var(--ring-track)',
  children,
  label,
  animate = true,
}: ProgressRingProps) {
  const ready = useMountAnimate(animate)
  const pct = clampPct(value)
  const r = (size - stroke) / 2
  const circ = 2 * Math.PI * r
  const offset = ready ? circ - (pct / 100) * circ : circ
  return (
    <div style={{ position: 'relative', width: size, height: size }}>
      <svg width={size} height={size} className="ring-svg" role="img" aria-label={label ?? `${Math.round(pct)}%`}>
        <circle className="ring-svg__track" cx={size / 2} cy={size / 2} r={r} fill="none" stroke={trackColor} strokeWidth={stroke} />
        <circle
          className="ring-svg__value"
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeDasharray={circ}
          strokeDashoffset={offset}
        />
      </svg>
      {children ? (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'grid',
            placeItems: 'center',
            textAlign: 'center',
          }}
        >
          {children}
        </div>
      ) : null}
    </div>
  )
}

export interface ActivityRing {
  key: 'move' | 'exercise' | 'hydrate'
  value: number
  goal: number
}

export interface ActivityRingsProps {
  rings: ActivityRing[]
  size?: number
  /** Animate each ring filling from empty on first render. */
  animate?: boolean
}

const RING_GEO = {
  move: { rIndex: 0 },
  exercise: { rIndex: 1 },
  hydrate: { rIndex: 2 },
}

/** Three concentric Apple-Health-style rings: Move / Exercise / Hydrate. */
export function ActivityRings({ rings, size = 200, animate = true }: ActivityRingsProps) {
  const ready = useMountAnimate(animate)
  const stroke = size * 0.09
  const gap = stroke * 0.35
  const center = size / 2

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="ring-svg" role="img" aria-label="Daily activity rings">
      <defs>
        <linearGradient id="grad-move" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="var(--ring-move-from)" />
          <stop offset="100%" stopColor="var(--ring-move-to)" />
        </linearGradient>
        <linearGradient id="grad-exercise" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="var(--ring-exercise-from)" />
          <stop offset="100%" stopColor="var(--ring-exercise-to)" />
        </linearGradient>
        <linearGradient id="grad-hydrate" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="var(--ring-hydrate-from)" />
          <stop offset="100%" stopColor="var(--ring-hydrate-to)" />
        </linearGradient>
      </defs>
      {rings.map((ring) => {
        const idx = RING_GEO[ring.key].rIndex
        const r = center - stroke / 2 - idx * (stroke + gap)
        const circ = 2 * Math.PI * r
        const pct = ring.goal > 0 ? Math.min(1, ring.value / ring.goal) : 0
        const offset = ready ? circ - pct * circ : circ
        return (
          <g key={ring.key}>
            <circle cx={center} cy={center} r={r} fill="none" stroke="var(--ring-track)" strokeWidth={stroke} />
            <circle
              className="ring-svg__value"
              cx={center}
              cy={center}
              r={r}
              fill="none"
              stroke={`url(#grad-${ring.key})`}
              strokeWidth={stroke}
              strokeLinecap="round"
              strokeDasharray={circ}
              strokeDashoffset={offset}
            />
          </g>
        )
      })}
    </svg>
  )
}
