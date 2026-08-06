import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from 'react'

export type ChipStatus = 'completed' | 'in-progress' | 'not-started' | 'locked'

export interface FilterChipProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  selected?: boolean
  children: ReactNode
}

/** Interactive filter chip (toggle). */
export function FilterChip({
  selected = false,
  className = '',
  children,
  ...rest
}: FilterChipProps) {
  const cls = ['chip', 'chip--filter', selected ? 'is-selected' : '', className]
    .filter(Boolean)
    .join(' ')
  return (
    <button type="button" className={cls} aria-pressed={selected} {...rest}>
      {children}
    </button>
  )
}

export interface StatusChipProps extends HTMLAttributes<HTMLSpanElement> {
  status: ChipStatus
  children?: ReactNode
}

const STATUS_LABEL: Record<ChipStatus, string> = {
  completed: 'Completed',
  'in-progress': 'In progress',
  'not-started': 'Not started',
  locked: 'Locked',
}

/** Non-interactive status chip. Uses neutral tones for incomplete (never red). */
export function StatusChip({ status, className = '', children, ...rest }: StatusChipProps) {
  const cls = ['chip', `chip--${status}`, className].filter(Boolean).join(' ')
  return (
    <span className={cls} {...rest}>
      {children ?? STATUS_LABEL[status]}
    </span>
  )
}
