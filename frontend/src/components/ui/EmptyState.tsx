import type { ReactNode } from 'react'

export interface EmptyStateProps {
  /** Flat icon (e.g. a lucide-react icon), rendered inside a soft tinted badge. */
  icon?: ReactNode
  title: ReactNode
  text?: ReactNode
  /** Primary call-to-action (usually a Button). */
  action?: ReactNode
  className?: string
}

/** Friendly empty state: icon + title + supporting text + a clear CTA. */
export function EmptyState({ icon, title, text, action, className = '' }: EmptyStateProps) {
  return (
    <div className={['empty-state', className].filter(Boolean).join(' ')}>
      {icon ? (
        <div className="empty-state__icon" aria-hidden="true">
          {icon}
        </div>
      ) : null}
      <div className="empty-state__title">{title}</div>
      {text ? <p className="empty-state__text">{text}</p> : null}
      {action ? <div className="empty-state__action">{action}</div> : null}
    </div>
  )
}
