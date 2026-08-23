import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Badge, StatusBadge } from '@/components/common/Badge'
import { Input, Select, Textarea } from '@/components/ui/input'
import { taskStatusTone } from '@/lib/taskStatusColors'

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
    // `--blue` on `in_progress` is the one status use IDENTITY.md clause 2 permits, and only here.
    expect(screen.getByText('in progress')).toHaveStyle({ color: 'var(--blue)' })
    expect(screen.getByText('under review')).toHaveStyle({ color: 'var(--amber)' })
  })

  it('draws every task status colour from the one shared map', () => {
    // The board, the Overview and StatusBadge each used to carry their own copy of this mapping,
    // and they had drifted: `in_progress` was blue on the board and amber on the Overview, where
    // it also collided with `under_review`. Any new copy should fail this test by diverging.
    expect(taskStatusTone('in_progress')).toBe('var(--blue)')
    expect(taskStatusTone('under_review')).toBe('var(--amber)')
    expect(taskStatusTone('approved')).toBe('var(--green)')
    expect(taskStatusTone('rejected')).toBe('var(--red)')
    expect(taskStatusTone('revision_needed')).toBe('var(--red)')
    // Deliberately neutral — these three are not asking the operator for anything.
    expect(taskStatusTone('pending')).toBeNull()
    expect(taskStatusTone('assigned')).toBeNull()
    expect(taskStatusTone('completed')).toBeNull()
    // An unknown status must not fall through to a hue.
    expect(taskStatusTone('nonsense')).toBeNull()
  })
})
