import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Button } from './Button'

describe('Button (design system)', () => {
  it('renders its label with the correct variant and size classes', () => {
    render(
      <Button variant="secondary" size="lg">
        Save
      </Button>,
    )
    const btn = screen.getByRole('button', { name: 'Save' })
    expect(btn).toBeInTheDocument()
    expect(btn).toHaveClass('btn', 'btn--secondary', 'btn--lg')
  })

  it('defaults to a primary, medium, type=button element', () => {
    render(<Button>Go</Button>)
    const btn = screen.getByRole('button', { name: 'Go' })
    expect(btn).toHaveClass('btn--primary', 'btn--md')
    expect(btn).toHaveAttribute('type', 'button')
  })

  it('fires onClick when clicked', async () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Tap</Button>)
    await userEvent.click(screen.getByRole('button', { name: 'Tap' }))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('is disabled and does not fire onClick while loading', async () => {
    const onClick = vi.fn()
    render(
      <Button loading onClick={onClick}>
        Loading
      </Button>,
    )
    const btn = screen.getByRole('button')
    expect(btn).toBeDisabled()
    expect(btn).toHaveAttribute('aria-busy', 'true')
    await userEvent.click(btn)
    expect(onClick).not.toHaveBeenCalled()
  })
})
