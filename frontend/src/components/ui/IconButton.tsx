import type { ButtonHTMLAttributes, ReactNode } from 'react'

export type IconButtonSize = 'sm' | 'md' | 'lg'
export type IconButtonVariant = 'ghost' | 'solid' | 'primary'

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Accessible label — required because icon-only buttons have no visible text. */
  label: string
  size?: IconButtonSize
  variant?: IconButtonVariant
  children: ReactNode
}

/** Icon-only button with consistent sizing, hover/press states, and a required a11y label. */
export function IconButton({
  label,
  size = 'md',
  variant = 'ghost',
  className = '',
  children,
  type = 'button',
  ...rest
}: IconButtonProps) {
  const cls = [
    'icon-btn',
    size !== 'md' ? `icon-btn--${size}` : '',
    variant !== 'ghost' ? `icon-btn--${variant}` : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')
  return (
    <button type={type} className={cls} aria-label={label} title={label} {...rest}>
      {children}
    </button>
  )
}
