import type { CSSProperties, HTMLAttributes } from 'react'

export type SkeletonVariant = 'text' | 'title' | 'circle' | 'block'

export interface SkeletonProps extends Omit<HTMLAttributes<HTMLDivElement>, 'children'> {
  variant?: SkeletonVariant
  width?: number | string
  height?: number | string
  radius?: number | string
  /** When >1 (text variant), renders that many stacked lines with a shorter last line. */
  lines?: number
}

/** Shimmering placeholder for loading states. Decorative (aria-hidden). */
export function Skeleton({
  variant = 'block',
  width,
  height,
  radius,
  lines,
  className = '',
  style,
  ...rest
}: SkeletonProps) {
  if (variant === 'text' && lines && lines > 1) {
    return (
      <div
        className={className}
        aria-hidden="true"
        style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)', ...style }}
        {...rest}
      >
        {Array.from({ length: lines }).map((_, i) => (
          <span
            key={i}
            className="skeleton skeleton--text"
            style={{ width: i === lines - 1 ? '68%' : '100%' }}
          />
        ))}
      </div>
    )
  }

  const cls = ['skeleton', `skeleton--${variant}`, className].filter(Boolean).join(' ')
  const s: CSSProperties = { width, height, borderRadius: radius, ...style }
  return <div className={cls} style={s} aria-hidden="true" {...rest} />
}
