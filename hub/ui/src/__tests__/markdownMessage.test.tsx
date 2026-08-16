import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MarkdownMessage } from '@/components/agents/MarkdownMessage'

describe('MarkdownMessage', () => {
  it('renders bold text, a fenced code block, and a bulleted list as real elements, not literal syntax', () => {
    const content = [
      'This is **bold** text.',
      '',
      '```',
      'const x = 1',
      '```',
      '',
      '- one',
      '- two',
    ].join('\n')
    const { container } = render(<MarkdownMessage content={content} />)

    const strong = container.querySelector('strong')
    expect(strong).not.toBeNull()
    expect(strong?.textContent).toBe('bold')
    expect(container.textContent).not.toContain('**bold**')

    const code = container.querySelector('pre code')
    expect(code).not.toBeNull()
    expect(code?.textContent).toContain('const x = 1')
    expect(container.textContent).not.toContain('```')

    const list = container.querySelector('ul')
    expect(list).not.toBeNull()
    expect(list?.querySelectorAll('li')).toHaveLength(2)
    expect(container.textContent).not.toMatch(/^- one/m)
  })

  it('treats a single newline as a line break, not collapsing two lines into one (remark-breaks)', () => {
    const { container } = render(<MarkdownMessage content={'line one\nline two'} />)
    // Standard Markdown would join these into "line one line two" in a single
    // text node with no break — remark-breaks is what this test guards.
    expect(container.querySelector('br')).not.toBeNull()
    expect(container.textContent).toContain('line one')
    expect(container.textContent).toContain('line two')
  })

  it('renders a literal <script> tag or an img onerror string as inert visible text, never as a DOM element', () => {
    const malicious = 'before <script>window.__pwned = true</script> after, and <img src=x onerror="window.__pwned2 = true">'
    const { container } = render(<MarkdownMessage content={malicious} />)

    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('img')).toBeNull()
    expect((window as unknown as { __pwned?: boolean }).__pwned).toBeUndefined()
    expect((window as unknown as { __pwned2?: boolean }).__pwned2).toBeUndefined()
    // The raw markup is still visible to the operator as text, not silently dropped.
    expect(container.textContent).toContain('script')
    expect(container.textContent).toContain('img')
  })

  it('renders plain text with no Markdown syntax exactly as before — no regression for ordinary messages', () => {
    render(<MarkdownMessage content="just a normal sentence" />)
    expect(screen.getByText('just a normal sentence')).toBeInTheDocument()
  })
})
