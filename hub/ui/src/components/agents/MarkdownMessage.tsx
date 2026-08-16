import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkBreaks from 'remark-breaks'

// No rehypePlugins, ever — react-markdown's default pipeline never parses embedded raw HTML,
// which is the security boundary this component is built around: conversation content includes
// agent output and peer-agent traffic, neither of which the operator authored.
const components: Components = {
  a: ({ href, children, ...props }) => (
    <a {...props} href={href} target="_blank" rel="noreferrer" className="md-link">
      {children}
    </a>
  ),
  pre: ({ children, ...props }) => (
    <pre {...props} className="md-pre">
      {children}
    </pre>
  ),
  code: ({ children, ...props }) => (
    <code {...props} className="md-code">
      {children}
    </code>
  ),
}

/** Renders message-level prose (operator input, agent text output, peer traffic) as Markdown.
 * Scoped to prose only — tool-call payloads stay on literal text rendering (WorkRow). */
export function MarkdownMessage({ content }: { content: string }) {
  return (
    <div className="markdown-message">
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  )
}
