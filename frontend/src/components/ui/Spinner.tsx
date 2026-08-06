export interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  label?: string
  className?: string
}

export function Spinner({ size = 'md', label = 'Loading', className = '' }: SpinnerProps) {
  const cls = ['spinner', size !== 'md' ? `spinner--${size}` : '', className]
    .filter(Boolean)
    .join(' ')
  return <span className={cls} role="status" aria-label={label} />
}

export function SpinnerCenter({ label }: { label?: string }) {
  return (
    <div className="spinner-center">
      <Spinner size="lg" label={label} />
    </div>
  )
}
