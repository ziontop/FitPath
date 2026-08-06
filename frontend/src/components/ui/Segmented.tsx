import type { ReactNode } from 'react'

export interface SegmentedOption<T extends string> {
  value: T
  label: ReactNode
}

export interface SegmentedProps<T extends string> {
  options: SegmentedOption<T>[]
  value: T | undefined
  onChange: (value: T) => void
  block?: boolean
  ariaLabel?: string
}

/** Accessible single-select segmented control (radio-group semantics). */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  block = false,
  ariaLabel,
}: SegmentedProps<T>) {
  return (
    <div
      className={['segmented', block ? 'segmented--block' : ''].filter(Boolean).join(' ')}
      role="radiogroup"
      aria-label={ariaLabel}
    >
      {options.map((opt) => {
        const selected = opt.value === value
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={selected}
            className={['segmented__opt', selected ? 'is-selected' : ''].filter(Boolean).join(' ')}
            onClick={() => onChange(opt.value)}
          >
            {opt.label}
          </button>
        )
      })}
    </div>
  )
}
