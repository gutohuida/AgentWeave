import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SidebarItem } from '@/components/layout/SidebarItem'

// Stub the Icon component so we can assert it was rendered with the right name
// without depending on the real lucide-react material-symbol mapping.
vi.mock('@/components/common/Icon', () => ({
  Icon: ({ name, size }: { name: string; size: number }) => (
    <span data-testid="icon" data-name={name} data-size={size} />
  ),
}))

describe('Q14 — <SidebarItem />', () => {
  it('renders the label as text content', () => {
    render(<SidebarItem label="Agents" icon="smart_toy" active={false} onClick={() => {}} />)
    expect(screen.getByText('Agents')).toBeInTheDocument()
  })

  it('renders an <Icon> with the provided icon name and default size 18', () => {
    render(<SidebarItem label="Tasks" icon="task_alt" active={false} onClick={() => {}} />)
    const icon = screen.getByTestId('icon')
    expect(icon.getAttribute('data-name')).toBe('task_alt')
    expect(icon.getAttribute('data-size')).toBe('18')
  })

  it('fires onClick when the button is clicked', () => {
    const onClick = vi.fn()
    render(<SidebarItem label="Logs" icon="terminal" active={false} onClick={onClick} />)
    fireEvent.click(screen.getByRole('button'))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('applies the active background when active=true', () => {
    render(<SidebarItem label="Overview" icon="home" active={true} onClick={() => {}} />)
    const btn = screen.getByRole('button')
    // jsdom normalizes rgba spacing — match the digits with a regex.
    expect(btn.style.background).toMatch(/rgba\(\s*255\s*,\s*255\s*,\s*255\s*,\s*0\.06\s*\)/)
  })

  it('applies a transparent background when inactive and not hovered', () => {
    render(<SidebarItem label="Overview" icon="home" active={false} onClick={() => {}} />)
    const btn = screen.getByRole('button')
    expect(btn.style.background).toBe('transparent')
  })

  it('switches to the hover background on mouse enter', () => {
    render(<SidebarItem label="Overview" icon="home" active={false} onClick={() => {}} />)
    const btn = screen.getByRole('button')
    fireEvent.mouseEnter(btn)
    expect(btn.style.background).toMatch(/rgba\(\s*255\s*,\s*255\s*,\s*255\s*,\s*0\.04\s*\)/)
    fireEvent.mouseLeave(btn)
    expect(btn.style.background).toBe('transparent')
  })

  it('active item keeps the active background even while hovered', () => {
    render(<SidebarItem label="Overview" icon="home" active={true} onClick={() => {}} />)
    const btn = screen.getByRole('button')
    fireEvent.mouseEnter(btn)
    expect(btn.style.background).toMatch(/rgba\(\s*255\s*,\s*255\s*,\s*255\s*,\s*0\.06\s*\)/)
  })

  it('does not render a badge when badge is omitted or null', () => {
    const { rerender } = render(<SidebarItem label="X" icon="x" active={false} onClick={() => {}} />)
    expect(screen.queryByText(/^\d+$/)).not.toBeInTheDocument()
    rerender(<SidebarItem label="X" icon="x" active={false} onClick={() => {}} badge={null} />)
    expect(screen.queryByText(/^\d+$/)).not.toBeInTheDocument()
  })

  it('renders the badge count when provided', () => {
    render(
      <SidebarItem
        label="Messages"
        icon="chat"
        active={false}
        onClick={() => {}}
        badge={{ count: 5, danger: false }}
      />
    )
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  it('applies the danger background to the badge when danger=true', () => {
    render(
      <SidebarItem
        label="Questions"
        icon="help"
        active={false}
        onClick={() => {}}
        badge={{ count: 3, danger: true }}
      />
    )
    const badge = screen.getByText('3')
    expect(badge.style.background).toBe('var(--red)')
  })

  it('applies the neutral background to the badge when danger=false', () => {
    render(
      <SidebarItem
        label="Messages"
        icon="chat"
        active={false}
        onClick={() => {}}
        badge={{ count: 7, danger: false }}
      />
    )
    const badge = screen.getByText('7')
    expect(badge.style.background).toBe('var(--surface-3)')
  })

  it('uses the testId prop on the underlying button when provided', () => {
    render(
      <SidebarItem
        label="Agents"
        icon="smart_toy"
        active={false}
        onClick={() => {}}
        testId="nav-agents"
      />
    )
    expect(screen.getByTestId('nav-agents')).toBeInTheDocument()
  })
})
