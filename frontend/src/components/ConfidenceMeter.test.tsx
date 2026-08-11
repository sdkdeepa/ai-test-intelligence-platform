import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'

import { ConfidenceMeter } from './ConfidenceMeter'

describe('ConfidenceMeter', () => {
  it('renders the value as a rounded percentage', () => {
    render(<ConfidenceMeter value={0.756} />)
    expect(screen.getByText('76%')).toBeInTheDocument()
  })

  it('clamps values above 1', () => {
    render(<ConfidenceMeter value={1.5} />)
    expect(screen.getByText('100%')).toBeInTheDocument()
  })

  it('clamps values below 0', () => {
    render(<ConfidenceMeter value={-0.2} />)
    expect(screen.getByText('0%')).toBeInTheDocument()
  })

  it('sets an accessible label including the percentage', () => {
    render(<ConfidenceMeter value={0.5} label="confidence" />)
    expect(screen.getByRole('img', { name: 'confidence: 50%' })).toBeInTheDocument()
  })
})
