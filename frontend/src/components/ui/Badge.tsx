import type { HTMLAttributes, ReactNode } from 'react'

export type BadgeVariant = 'default' | 'primary' | 'success' | 'info' | 'ai'

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant
  children: ReactNode
}

export function Badge({ variant = 'default', className = '', children, ...rest }: BadgeProps) {
  const cls = ['badge', variant !== 'default' ? `badge--${variant}` : '', className]
    .filter(Boolean)
    .join(' ')
  return (
    <span className={cls} {...rest}>
      {children}
    </span>
  )
}
