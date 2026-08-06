import type { ReactNode } from 'react'

export interface PageHeaderProps {
  title: ReactNode
  subtitle?: ReactNode
  /** Small uppercase kicker shown above the title (e.g. the date, or a section). */
  eyebrow?: ReactNode
  /** Right-aligned actions slot (buttons, toggles). */
  actions?: ReactNode
  className?: string
}

/** Consistent page title block: eyebrow + title + subtitle, with an actions slot. */
export function PageHeader({ title, subtitle, eyebrow, actions, className = '' }: PageHeaderProps) {
  return (
    <header className={['page-header', className].filter(Boolean).join(' ')}>
      <div>
        {eyebrow ? <div className="page-header__eyebrow">{eyebrow}</div> : null}
        <h1 className="page-header__title">{title}</h1>
        {subtitle ? <p className="page-header__subtitle">{subtitle}</p> : null}
      </div>
      {actions ? <div className="page-header__actions">{actions}</div> : null}
    </header>
  )
}
