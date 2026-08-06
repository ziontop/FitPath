import type { HTMLAttributes, ReactNode } from 'react'

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'feature' | 'hero' | 'stat' | 'glass'
  interactive?: boolean
  flush?: boolean
  children: ReactNode
}

const VARIANT_CLASS: Record<NonNullable<CardProps['variant']>, string> = {
  default: '',
  feature: 'card--feature',
  hero: 'card--hero',
  stat: 'card--stat',
  glass: 'card--glass',
}

export function Card({
  variant = 'default',
  interactive = false,
  flush = false,
  className = '',
  children,
  ...rest
}: CardProps) {
  const cls = [
    'card',
    VARIANT_CLASS[variant],
    interactive ? 'card--interactive' : '',
    flush ? 'card--flush' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')
  return (
    <div className={cls} {...rest}>
      {children}
    </div>
  )
}

export interface CardHeaderProps {
  title: ReactNode
  action?: ReactNode
}

export function CardHeader({ title, action }: CardHeaderProps) {
  return (
    <div className="card__head">
      <h3 className="card__title">{title}</h3>
      {action}
    </div>
  )
}

export interface StatCardProps {
  label: ReactNode
  value: ReactNode
  sub?: ReactNode
  icon?: ReactNode
  center?: boolean
}

export function StatCard({ label, value, sub, icon, center = false }: StatCardProps) {
  return (
    <Card>
      <div className={center ? 'stat stat--center' : 'stat'}>
        {icon ? <span className="stat__icon">{icon}</span> : null}
        <span className="stat__label">{label}</span>
        <span className="stat__value">{value}</span>
        {sub ? <span className="stat__sub">{sub}</span> : null}
      </div>
    </Card>
  )
}
