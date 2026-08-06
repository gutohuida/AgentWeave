import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ProviderMark } from '@/components/common/Icon'

describe('ProviderMark — brand mark with a text fallback (composer/chrome refinement §4)', () => {
  it('renders a known provider as an inline SVG mark, not text', () => {
    const { container } = render(<ProviderMark provider="claude" label="Claude Code" />)
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  it('renders an unknown provider as text initials, and no mark', () => {
    const { container } = render(<ProviderMark provider="some-future-provider" label="Some Future Provider" />)
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    // No SVG for an unknown provider — only the initials fallback renders.
    expect(container.querySelector('svg')).not.toBeInTheDocument()
    expect(screen.getByText('SF')).toBeInTheDocument()
  })

  it('a provider with no mark is still fully described by its label, not a broken icon', () => {
    render(<ProviderMark provider="unmapped" label="Unmapped Provider" />)
    // title carries the accessible label even without a mark to attach it to.
    expect(screen.getByTitle('Unmapped Provider')).toBeInTheDocument()
  })
})
