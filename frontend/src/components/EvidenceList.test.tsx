import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'

import { EvidenceList } from './EvidenceList'

describe('EvidenceList', () => {
  it('renders each item as a list entry', () => {
    render(<EvidenceList items={['first fact', 'second fact']} />)
    expect(screen.getByText('first fact')).toBeInTheDocument()
    expect(screen.getByText('second fact')).toBeInTheDocument()
  })

  it('shows the default empty message when there are no items', () => {
    render(<EvidenceList items={[]} />)
    expect(screen.getByText('None recorded.')).toBeInTheDocument()
  })

  it('shows a custom empty message when provided', () => {
    render(<EvidenceList items={[]} emptyText="No hypotheses generated." />)
    expect(screen.getByText('No hypotheses generated.')).toBeInTheDocument()
  })
})
