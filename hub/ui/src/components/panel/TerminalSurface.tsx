import * as React from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { openAttachSocket } from '@/api/terminal'

/** What the container needs from a mounted terminal to send it to the composer (FR-11). */
export interface TerminalHandle {
  /** The selection, or the visible screen when nothing is selected. */
  textToSend: () => string
}

interface Props {
  projectId: string
  conversationId: string
  shellId: string
  onHandle: (shellId: string, handle: TerminalHandle | null) => void
  onExit: (shellId: string, code: number | null) => void
}

/** The visible screen of an xterm, without the blank rows below the cursor. */
function visibleScreen(term: Terminal): string {
  const buffer = term.buffer.active
  const lines: string[] = []
  for (let row = 0; row < term.rows; row += 1) {
    lines.push(buffer.getLine(buffer.viewportY + row)?.translateToString(true) ?? '')
  }
  while (lines.length > 0 && lines[lines.length - 1] === '') lines.pop()
  return lines.join('\n')
}

/** One shell's emulator, attached over the Hub socket. The Hub keeps the shell and its last lines,
 *  so mounting again (returning to the conversation) replays what was produced meanwhile (FR-8). */
export function TerminalSurface({ projectId, conversationId, shellId, onHandle, onExit }: Props) {
  const host = React.useRef<HTMLDivElement>(null)
  const callbacks = React.useRef({ onHandle, onExit })
  callbacks.current = { onHandle, onExit }

  React.useEffect(() => {
    const element = host.current
    if (!element) return undefined
    let disposed = false
    let socket: WebSocket | null = null
    const term = new Terminal({ scrollback: 5000, cursorBlink: true, fontSize: 13 })
    const fit = new FitAddon()
    term.loadAddon(fit)
    term.open(element)
    const send = (message: unknown) => {
      if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message))
    }
    const refit = () => {
      try {
        fit.fit()
      } catch {
        return // not laid out yet
      }
      send({ type: 'resize', cols: term.cols, rows: term.rows })
    }
    term.onData((data) => send({ type: 'input', data }))
    callbacks.current.onHandle(shellId, {
      textToSend: () => (term.hasSelection() ? term.getSelection() : visibleScreen(term)),
    })
    const observer = new ResizeObserver(refit)
    observer.observe(element)
    refit()

    openAttachSocket(projectId, conversationId, shellId)
      .then((ws) => {
        if (disposed) {
          ws.close()
          return
        }
        socket = ws
        ws.onopen = refit
        ws.onmessage = (event) => {
          let message: { type?: string; data?: string; code?: number | null }
          try {
            message = JSON.parse(String(event.data))
          } catch {
            return
          }
          if (message.type === 'output' && typeof message.data === 'string') term.write(message.data)
          else if (message.type === 'exit') callbacks.current.onExit(shellId, message.code ?? null)
        }
      })
      .catch(() => term.write('\r\n[could not attach to this shell]\r\n'))

    return () => {
      disposed = true
      observer.disconnect()
      callbacks.current.onHandle(shellId, null)
      socket?.close()
      term.dispose()
    }
  }, [projectId, conversationId, shellId])

  return <div ref={host} className="aw-term-xterm" data-testid={`terminal-surface-${shellId}`} style={{ height: '100%', width: '100%' }} />
}
