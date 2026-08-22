import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Badge, StatusBadge } from '@/components/common/Badge'
import { Input, Select, Textarea } from '@/components/ui/input'

describe('considered shared controls', () => {
  it('gives every field the same stateful control recipe without replacing native semantics', () => {
    render(
      <>
        <Input aria-label="Name" className="h-8 px-2" />
        <Textarea aria-label="Instructions" />
        <Select aria-label="Runner"><option>Codex</option></Select>
      </>,
    )

    expect(screen.getByRole('textbox', { name: 'Name' })).toHaveClass('control-field', 'h-8')
    expect(screen.getByRole('textbox', { name: 'Instructions' }).tagName).toBe('TEXTAREA')
    expect(screen.getByRole('combobox', { name: 'Runner' })).toHaveClass('control-field')
    expect(screen.getByRole('option', { name: 'Codex' })).toBeInTheDocument()
  })

  it('uses shared chip geometry and separates active progress from review by colour', () => {
    render(<><Badge pill>category</Badge><StatusBadge status="in_progress" /><StatusBadge status="under_review" /></>)

    expect(screen.getByText('category')).toHaveClass('aw-chip')
    expect(screen.getByText('category')).toHaveAttribute('data-pill', 'true')
    expect(screen.getByText('in progress')).toHaveStyle({ color: 'var(--blue)' })
    expect(screen.getByText('under review')).toHaveStyle({ color: 'var(--amber)' })
  })
})
