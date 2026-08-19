import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { FilePreview } from '@/components/spec/FilePreview'

describe('FilePreview — a file shown the way its type deserves', () => {
  it('renders Markdown as a document, not as source', () => {
    render(<FilePreview path="docs/guide.md" content={'# Title\n\nSome **bold** prose.'} />)

    // A heading element, not the literal "# Title" a <pre> would show.
    expect(screen.getByRole('heading', { level: 1, name: 'Title' })).toBeInTheDocument()
    expect(screen.getByText('bold').tagName).toBe('STRONG')
    expect(screen.queryByTestId('file-tab-content')).not.toBeInTheDocument()
  })

  it('renders GitHub-flavoured tables, which plain CommonMark would not', () => {
    const content = ['| Flag | Meaning |', '| --- | --- |', '| `-v` | verbose |'].join('\n')
    render(<FilePreview path="README.md" content={content} />)

    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Flag' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: 'verbose' })).toBeInTheDocument()
  })

  it('syntax-highlights a source file into spans rather than flat text', () => {
    const { container } = render(
      <FilePreview path="src/app.ts" content={'const answer = 42\n'} />,
    )

    const pre = screen.getByTestId('file-tab-content')
    expect(pre).toHaveAttribute('data-language', 'typescript')
    // The point of the feature: tokens are real elements that CSS can colour.
    expect(container.querySelectorAll('.hljs-keyword').length).toBeGreaterThan(0)
    expect(container.querySelectorAll('.hljs-number').length).toBeGreaterThan(0)
    // and the text is still intact, not mangled by the highlighter
    expect(pre.textContent).toContain('const answer = 42')
  })

  it('highlights a Dockerfile, which has no extension to go on', () => {
    const { container } = render(
      <FilePreview path="Dockerfile" content={'FROM python:3.11\nRUN pip install .\n'} />,
    )

    expect(screen.getByTestId('file-tab-content')).toHaveAttribute('data-language', 'dockerfile')
    expect(container.querySelectorAll('.hljs-keyword').length).toBeGreaterThan(0)
  })

  it('falls back to plain text for a type it has no grammar for, without blanking', () => {
    render(<FilePreview path="notes.unknownext" content={'just some text'} />)

    const pre = screen.getByTestId('file-tab-content')
    expect(pre).not.toHaveAttribute('data-language')
    expect(pre.textContent).toBe('just some text')
  })

  it('escapes content rather than letting a file inject markup', () => {
    // The one dangerouslySetInnerHTML in this component is highlight.js output, which escapes
    // every character of its input. A file containing a script tag must appear as text.
    const { container } = render(
      <FilePreview path="evil.ts" content={'const x = "<img src=x onerror=alert(1)>"'} />,
    )

    expect(container.querySelector('img')).toBeNull()
    expect(screen.getByTestId('file-tab-content').textContent).toContain('<img src=x')
  })
})
