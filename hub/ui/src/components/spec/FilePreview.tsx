import { useMemo } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import hljs from 'highlight.js/lib/core'
import bash from 'highlight.js/lib/languages/bash'
import c from 'highlight.js/lib/languages/c'
import cpp from 'highlight.js/lib/languages/cpp'
import csharp from 'highlight.js/lib/languages/csharp'
import css from 'highlight.js/lib/languages/css'
import dockerfile from 'highlight.js/lib/languages/dockerfile'
import dos from 'highlight.js/lib/languages/dos'
import go from 'highlight.js/lib/languages/go'
import ini from 'highlight.js/lib/languages/ini'
import java from 'highlight.js/lib/languages/java'
import javascript from 'highlight.js/lib/languages/javascript'
import json from 'highlight.js/lib/languages/json'
import kotlin from 'highlight.js/lib/languages/kotlin'
import lua from 'highlight.js/lib/languages/lua'
import makefile from 'highlight.js/lib/languages/makefile'
import markdown from 'highlight.js/lib/languages/markdown'
import php from 'highlight.js/lib/languages/php'
import powershell from 'highlight.js/lib/languages/powershell'
import python from 'highlight.js/lib/languages/python'
import ruby from 'highlight.js/lib/languages/ruby'
import rust from 'highlight.js/lib/languages/rust'
import sql from 'highlight.js/lib/languages/sql'
import swift from 'highlight.js/lib/languages/swift'
import typescript from 'highlight.js/lib/languages/typescript'
import xml from 'highlight.js/lib/languages/xml'
import yaml from 'highlight.js/lib/languages/yaml'

import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { useCopy } from '@/hooks/useCopy'
import { fileLanguageFor, isMarkdownPath } from './fileIcons'

/* Registered explicitly, from `highlight.js/lib/core` rather than the default bundle: the full
 * bundle carries nearly 200 grammars and the app's chunk is already over Vite's 500 kB advisory.
 * Adding a language here is one import and one line. */
const LANGUAGES: Record<string, Parameters<typeof hljs.registerLanguage>[1]> = {
  bash, c, cpp, csharp, css, dockerfile, dos, go, ini, java, javascript, json, kotlin, lua,
  makefile, markdown, php, powershell, python, ruby, rust, sql, swift, typescript, xml, yaml,
}
for (const [name, language] of Object.entries(LANGUAGES)) {
  hljs.registerLanguage(name, language)
}

/** Fenced code inside rendered Markdown, highlighted with the same engine as a whole code file so
 *  the two never disagree about what TypeScript looks like. */
const markdownComponents: Components = {
  a: ({ href, children, ...props }) => (
    <a {...props} href={href} target="_blank" rel="noreferrer" className="md-link">
      {children}
    </a>
  ),
  code: ({ className, children, ...props }) => {
    const language = /language-(\w+)/.exec(className ?? '')?.[1]
    const text = String(children ?? '')
    if (!language || !hljs.getLanguage(language)) {
      return (
        <code {...props} className="md-code">
          {children}
        </code>
      )
    }
    return (
      <code
        {...props}
        className="md-code hljs"
        dangerouslySetInnerHTML={{ __html: hljs.highlight(text, { language }).value }}
      />
    )
  },
}

interface FilePreviewProps {
  path: string
  content: string
  /** The owning tab's actions, rendered into this header. `FileTab` used to draw a second header
   *  strip of its own for them, which repeated the filename and cost a row of a panel the
   *  research describes as "always on screen while working". */
  headerActions?: React.ReactNode
}

/**
 * A workspace file's content, shown the way its type deserves (operator request, 2026-08-19):
 * Markdown rendered rather than shown as source, everything else syntax-highlighted like an IDE.
 *
 * **Why not `MarkdownMessage`.** That component carries an explicit, load-bearing rule — *"No
 * rehypePlugins, ever"* — because it renders agent output and peer-agent traffic, which the
 * operator did not author. A workspace file is different: the operator opened it from their own
 * checkout on purpose. Rather than weaken that boundary by adding highlighting to the shared
 * component, this is a separate renderer for a separate trust context. Raw HTML is still never
 * parsed here either; `react-markdown`'s default pipeline drops it, and no `rehype-raw` is added.
 *
 * The one `dangerouslySetInnerHTML` is highlight.js's output, which HTML-escapes every character
 * of its input before wrapping tokens in spans — the documented way to use it, and it never sees
 * anything but the file's own text.
 */
export function FilePreview({ path, content, headerActions }: FilePreviewProps) {
  const { copied, copy } = useCopy()
  const lastSlash = path.lastIndexOf('/')
  const directories = lastSlash > 0 ? path.slice(0, lastSlash) : ''
  const filename = lastSlash >= 0 ? path.slice(lastSlash + 1) : path
  const language = fileLanguageFor(path)
  const asMarkdown = isMarkdownPath(path)

  const highlighted = useMemo(() => {
    if (asMarkdown || !language || !hljs.getLanguage(language)) return null
    try {
      return hljs.highlight(content, { language }).value
    } catch {
      // A grammar that throws on odd input must degrade to plain text, never to a blank pane.
      return null
    }
  }, [asMarkdown, language, content])

  const preview = asMarkdown ? (
      <div className="markdown-message file-preview-markdown p-4" data-testid="file-preview-markdown">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
          {content}
        </ReactMarkdown>
      </div>
    ) : (() => {
      const preStyle: React.CSSProperties = {
        margin: 0,
        fontSize: 12,
        lineHeight: 1.6,
        fontFamily: "'JetBrains Mono', monospace",
        whiteSpace: 'pre',
        color: 'var(--text)',
      }

      if (highlighted === null) {
        return (
          <pre data-testid="file-tab-content" className="p-3" style={preStyle}>
            {content}
          </pre>
        )
      }

      return (
        <pre
          data-testid="file-tab-content"
          data-language={language}
          className="hljs p-3"
          style={preStyle}
        >
          <code dangerouslySetInnerHTML={{ __html: highlighted }} />
        </pre>
      )
    })()

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="file-preview">
      <div className="file-preview-header flex shrink-0 items-center gap-2 px-3 py-2">
        <Icon name="article" size={14} style={{ color: 'var(--text-3)' }} />
        {/* The directories truncate; the filename never does. A single `truncate` across the whole
            path clips the *end*, which hides the one segment the reader actually needs —
            `hub/ui/src/components/…` tells you nothing about which file you are looking at. */}
        <span className="flex min-w-0 flex-1 items-baseline font-mono text-[11px]" title={path}>
          {directories && (
            <span className="truncate" style={{ color: 'var(--text-3)' }}>{directories}/</span>
          )}
          <span className="shrink-0" style={{ color: 'var(--text-2)' }}>{filename}</span>
        </span>
        <span className="aw-chip" data-pill="true">{asMarkdown ? 'Markdown' : language ?? 'Plain text'}</span>
        <Button
          variant="ghost"
          size="icon-xs"
          aria-label="Copy file path"
          title={copied ? 'Copied file path' : 'Copy file path'}
          onClick={() => { void copy(path) }}
        >
          <Icon name={copied ? 'check' : 'content_copy'} size={13} />
        </Button>
        {/* The tab's own actions render here rather than in a second header strip of their own —
            two stacked strips both naming the same file cost two rows of an always-on-screen
            panel and said the filename twice. */}
        {headerActions}
      </div>
      <div className="min-h-0 flex-1 overflow-auto">{preview}</div>
    </div>
  )
}
