import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'

import { StatusBadge } from './StatusBadge'

describe('StatusBadge', () => {
  it('renders the given value as text', () => {
    render(<StatusBadge value="completed" />)
    expect(screen.getByText('completed')).toBeInTheDocument()
  })

  it('applies a positive tone for completed', () => {
    render(<StatusBadge value="completed" />)
    expect(screen.getByText('completed')).toHaveClass('status-badge--positive')
  })

  it('applies a negative tone for failed', () => {
    render(<StatusBadge value="failed" />)
    expect(screen.getByText('failed')).toHaveClass('status-badge--negative')
  })

  it('applies a negative tone for block', () => {
    render(<StatusBadge value="block" />)
    expect(screen.getByText('block')).toHaveClass('status-badge--negative')
  })

  it('falls back to a neutral tone for an unrecognized value', () => {
    render(<StatusBadge value="something-new" />)
    expect(screen.getByText('something-new')).toHaveClass('status-badge--neutral')
  })
})
