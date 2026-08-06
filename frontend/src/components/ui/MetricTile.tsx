import type { ReactNode } from 'react'
import { Card } from './Card'

export type MetricDelta = 'up' | 'down' | 'flat'

export interface MetricTileProps {
  label: ReactNode
  value: ReactNode
  /** Small trailing unit shown next to the big value (e.g. "kg", "min"). */
  unit?: ReactNode
  /** Flat icon shown in a soft tinted badge, top-right. */
  icon?: ReactNode
  /** Trend indicator, e.g. { direction: 'up', label: '+12%' }. */
  delta?: { direction: MetricDelta; label: ReactNode }
  /** Muted sub-label shown when no delta is provided. */
  sub?: ReactNode
  /** Render the icon in a soft indigo accent badge (use at most one per card). */
  accentIcon?: boolean
  className?: string
}

/**
 * Glanceable metric tile: big bold value + label + optional icon and trend delta.
 * Renders inside a compact stat Card so it drops straight into a grid.
 */
export function MetricTile({ label, value, unit, icon, delta, sub, accentIcon = false, className = '' }: MetricTileProps) {
  return (
    <Card variant="stat" className={className}>
      <div className="metric">
        <div className="metric__top">
          <span className="metric__label">{label}</span>
          {icon ? (
            <span className={`metric__icon${accentIcon ? ' metric__icon--accent' : ''}`} aria-hidden="true">
              {icon}
            </span>
          ) : null}
        </div>
        <div className="metric__value">
          <span>{value}</span>
          {unit ? <span className="metric__unit">{unit}</span> : null}
        </div>
        {delta ? (
          <span className={`metric__delta metric__delta--${delta.direction}`}>{delta.label}</span>
        ) : sub ? (
          <span className="stat__sub">{sub}</span>
        ) : null}
      </div>
    </Card>
  )
}

/** Alias — `Stat` reads well in dashboards; identical to MetricTile. */
export const Stat = MetricTile
