import type { ReactNode } from 'react'

export interface SectionTitleProps {
  children: ReactNode
  /** Optional right-aligned action (link, button, badge). */
  action?: ReactNode
  className?: string
}

/** Section heading with an optional trailing action, for grouping content on a page. */
export function SectionTitle({ children, action, className = '' }: SectionTitleProps) {
  return (
    <div className={['section-head', className].filter(Boolean).join(' ')}>
      <h2 className="section-head__title">{children}</h2>
      {action}
    </div>
  )
}
