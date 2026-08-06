import type { HTMLAttributes, ReactNode } from 'react'

export function List({ className = '', children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={['list', className].filter(Boolean).join(' ')} {...rest}>
      {children}
    </div>
  )
}

export interface ListRowProps extends Omit<HTMLAttributes<HTMLDivElement>, 'title'> {
  active?: boolean
  leading?: ReactNode
  title?: ReactNode
  sub?: ReactNode
  trailing?: ReactNode
}

export function ListRow({
  active = false,
  leading,
  title,
  sub,
  trailing,
  className = '',
  children,
  ...rest
}: ListRowProps) {
  const cls = ['list-row', active ? 'is-active' : '', className].filter(Boolean).join(' ')
  // Structured mode when title/leading/trailing are supplied; otherwise render children as-is.
  if (title || leading || trailing || sub) {
    return (
      <div className={cls} {...rest}>
        {leading}
        <div className="list-row__main">
          {title ? <div className="list-row__title">{title}</div> : null}
          {sub ? <div className="list-row__sub">{sub}</div> : null}
        </div>
        {trailing}
      </div>
    )
  }
  return (
    <div className={cls} {...rest}>
      {children}
    </div>
  )
}
