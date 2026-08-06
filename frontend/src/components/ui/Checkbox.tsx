import type { InputHTMLAttributes, ReactNode } from 'react'

export interface CheckboxProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label?: ReactNode
}

export function Checkbox({ label, className = '', ...rest }: CheckboxProps) {
  return (
    <label className={['checkbox', className].filter(Boolean).join(' ')}>
      <input type="checkbox" {...rest} />
      <span className="checkbox__box" aria-hidden="true">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </span>
      {label ? <span>{label}</span> : null}
    </label>
  )
}
