import { useId } from 'react'
import type {
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react'

export interface FieldProps {
  label?: ReactNode
  hint?: ReactNode
  error?: ReactNode
  htmlFor?: string
  required?: boolean
  className?: string
  children: ReactNode
}

/** Wraps a control with an accessible label, hint, and error message. */
export function Field({ label, hint, error, htmlFor, required, className = '', children }: FieldProps) {
  return (
    <div className={['field', className].filter(Boolean).join(' ')}>
      {label ? (
        <label className="field__label" htmlFor={htmlFor}>
          {label}
          {required ? <span aria-hidden="true" className="text-error"> *</span> : null}
        </label>
      ) : null}
      {children}
      {error ? (
        <span className="field__error" role="alert">
          {error}
        </span>
      ) : hint ? (
        <span className="field__hint">{hint}</span>
      ) : null}
    </div>
  )
}

interface ControlExtras {
  label?: ReactNode
  hint?: ReactNode
  error?: ReactNode
  wrapperClassName?: string
}

export interface InputProps
  extends InputHTMLAttributes<HTMLInputElement>,
    ControlExtras {}

export function Input({
  label,
  hint,
  error,
  wrapperClassName,
  className = '',
  id,
  required,
  ...rest
}: InputProps) {
  const autoId = useId()
  const inputId = id ?? autoId
  const cls = ['input', error ? 'input--error' : '', className].filter(Boolean).join(' ')
  const control = (
    <input
      id={inputId}
      className={cls}
      aria-invalid={error ? true : undefined}
      required={required}
      {...rest}
    />
  )
  if (label || hint || error) {
    return (
      <Field label={label} hint={hint} error={error} htmlFor={inputId} required={required} className={wrapperClassName}>
        {control}
      </Field>
    )
  }
  return control
}

export interface TextareaProps
  extends TextareaHTMLAttributes<HTMLTextAreaElement>,
    ControlExtras {}

export function Textarea({
  label,
  hint,
  error,
  wrapperClassName,
  className = '',
  id,
  required,
  ...rest
}: TextareaProps) {
  const autoId = useId()
  const inputId = id ?? autoId
  const cls = ['textarea', error ? 'textarea--error' : '', className].filter(Boolean).join(' ')
  const control = (
    <textarea
      id={inputId}
      className={cls}
      aria-invalid={error ? true : undefined}
      required={required}
      {...rest}
    />
  )
  if (label || hint || error) {
    return (
      <Field label={label} hint={hint} error={error} htmlFor={inputId} required={required} className={wrapperClassName}>
        {control}
      </Field>
    )
  }
  return control
}

export interface SelectProps
  extends SelectHTMLAttributes<HTMLSelectElement>,
    ControlExtras {
  children: ReactNode
}

export function Select({
  label,
  hint,
  error,
  wrapperClassName,
  className = '',
  id,
  required,
  children,
  ...rest
}: SelectProps) {
  const autoId = useId()
  const inputId = id ?? autoId
  const cls = ['select', error ? 'select--error' : '', className].filter(Boolean).join(' ')
  const control = (
    <select
      id={inputId}
      className={cls}
      aria-invalid={error ? true : undefined}
      required={required}
      {...rest}
    >
      {children}
    </select>
  )
  if (label || hint || error) {
    return (
      <Field label={label} hint={hint} error={error} htmlFor={inputId} required={required} className={wrapperClassName}>
        {control}
      </Field>
    )
  }
  return control
}
