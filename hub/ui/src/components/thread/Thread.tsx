import * as React from 'react'
import { Button } from '@/components/ui/button'
import { SURFACE, type KnotLink, type ThreadLevelData } from '@/api/thread'
import { Knot } from './Knot'
import { Scrubber } from './Scrubber'
import '@/styles/thread.css'

export interface ThreadProps {
  /** Every level loaded so far, by the address of the knot it lies under (`SURFACE` for the top). */
  levels: Record<string, ThreadLevelData | undefined>
  /** Addresses of the knots that are open. */
  open: ReadonlySet<string>
  /** The knot to bring into view and focus; `reveal` changes whenever it should be brought again. */
  current: string | null
  reveal: number
  now: Date
  atBeginning: boolean
  atPresent: boolean
  onToggle: (key: string) => void
  onMore: (under: string, direction: 'before' | 'after') => void
  onJumpToBeginning: () => void
  onBackToPresent: () => void
  onOpenLink: (link: KnotLink) => void
}

type LevelProps = Omit<ThreadProps, 'atBeginning' | 'atPresent' | 'onJumpToBeginning' | 'onBackToPresent' | 'reveal'> & {
  under: string
}

function Level({ under, levels, open, current, now, onToggle, onMore, onOpenLink }: LevelProps) {
  const level = levels[under]
  if (!level) {
    return (
      <p className="aw-thread-note aw-delayed" role="status">
        Unspooling…
      </p>
    )
  }
  return (
    <>
      {level.hasBefore ? (
        <div className="aw-thread-more">
          <Button variant="ghost" data-slot="thread-more" onClick={() => onMore(under, 'before')}>
            Earlier
          </Button>
        </div>
      ) : null}
      <ol className="aw-thread-level" data-surface={under === SURFACE ? 'true' : undefined}>
        {level.knots.map((knot) => {
          const isOpen = open.has(knot.key)
          return (
            <Knot
              key={knot.key}
              knot={knot}
              open={isOpen}
              now={now}
              current={current === knot.key}
              onToggle={() => onToggle(knot.key)}
              onOpenLink={onOpenLink}
            >
              {isOpen ? (
                <Level
                  under={knot.key}
                  levels={levels}
                  open={open}
                  current={current}
                  now={now}
                  onToggle={onToggle}
                  onMore={onMore}
                  onOpenLink={onOpenLink}
                />
              ) : null}
            </Knot>
          )
        })}
      </ol>
      {level.hasAfter ? (
        <div className="aw-thread-more">
          <Button variant="ghost" data-slot="thread-more" onClick={() => onMore(under, 'after')}>
            Later
          </Button>
        </div>
      ) : null}
    </>
  )
}

/** The head of the knot a key press should move to, among the heads currently drawn. */
function move(root: HTMLElement, from: HTMLElement, step: 1 | -1): HTMLElement | undefined {
  const heads = Array.from(root.querySelectorAll<HTMLElement>('[data-knot-head]'))
  return heads[heads.indexOf(from) + step]
}

/** The project's thread: one red line, oldest at the top, newest at the bottom. Knots open in place
 *  into their own thread. Presentational: the container owns what is loaded and what is open. */
export function Thread(props: ThreadProps) {
  const { current, reveal, atBeginning, atPresent, onJumpToBeginning, onBackToPresent, ...level } = props
  const root = React.useRef<HTMLDivElement>(null)

  // Bring the current knot into view and focus it. The browser scrolls; nothing here animates it.
  React.useEffect(() => {
    if (!current) return
    const li = Array.from(root.current?.querySelectorAll<HTMLElement>('[data-knot-key]') ?? []).find(
      (el) => el.dataset.knotKey === current,
    )
    const head = li?.querySelector<HTMLElement>(':scope > [data-knot-head]')
    head?.focus({ preventScroll: true })
    li?.scrollIntoView({ block: 'center' })
  }, [current, reveal])

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement
    if (!target.matches('[data-knot-head]') || !root.current) return
    const expanded = target.getAttribute('aria-expanded')
    switch (event.key) {
      case 'ArrowDown':
      case 'ArrowUp': {
        const next = move(root.current, target, event.key === 'ArrowDown' ? 1 : -1)
        if (next) {
          event.preventDefault()
          next.focus()
        }
        break
      }
      case 'ArrowRight':
        if (expanded === 'false') {
          event.preventDefault()
          target.click()
        }
        break
      case 'ArrowLeft':
        if (expanded === 'true') {
          event.preventDefault()
          target.click()
        } else {
          const parent = target.closest('li')?.parentElement?.closest('li')
          const head = parent?.querySelector<HTMLElement>(':scope > [data-knot-head]')
          if (head) {
            event.preventDefault()
            head.focus()
          }
        }
        break
    }
  }

  return (
    <div className="aw-thread" ref={root} onKeyDown={onKeyDown}>
      <Scrubber
        atBeginning={atBeginning}
        atPresent={atPresent}
        onJumpToBeginning={onJumpToBeginning}
        onBackToPresent={onBackToPresent}
      />
      <Level under={SURFACE} current={current} {...level} />
    </div>
  )
}
