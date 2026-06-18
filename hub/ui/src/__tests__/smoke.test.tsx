import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

describe('vitest infrastructure', () => {
  it('renders a trivial component', () => {
    render(<div data-testid="smoke">hello vitest</div>)
    expect(screen.getByTestId('smoke')).toHaveTextContent('hello vitest')
  })

  it('provides a working jsdom environment', () => {
    expect(typeof window).toBe('object')
    expect(typeof document).toBe('object')
    expect(typeof localStorage).toBe('object')
    expect(typeof sessionStorage).toBe('object')
  })
})
