import type { InputHTMLAttributes, ReactNode } from 'react'

export interface RadioProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label?: ReactNode
}

export function Radio({ label, className = '', ...rest }: RadioProps) {
  return (
    <label className={['radio', className].filter(Boolean).join(' ')}>
      <input type="radio" {...rest} />
      <span className="radio__dot" aria-hidden="true" />
      {label ? <span>{label}</span> : null}
    </label>
  )
}
