import type { ReactNode } from 'react'

export interface TooltipProps {
  content: ReactNode
  children: ReactNode
}

export function Tooltip({ content, children }: TooltipProps) {
  return (
    <span className="tooltip" tabIndex={0}>
      {children}
      <span className="tooltip__bubble" role="tooltip">
        {content}
      </span>
    </span>
  )
}
