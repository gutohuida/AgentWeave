import type { CSSProperties, ReactNode } from 'react'
import { Icon } from '@/components/common/Icon'
import type { Tone } from '@/components/common/StatePill'

/**
 * A vertical story: a rail that draws itself down, a dot per event in its state tone, and events
 * that stagger in (`styles/story.css`). Reduced motion turns every animation off.
 */
export function Timeline({ children, testId }: { children: ReactNode; testId?: string }) {
  return (
    <ol className="aw-timeline" data-testid={testId}>
      {children}
    </ol>
  )
}

/**
 * One event. `index` sets its place in the entry stagger; `fresh` marks one that arrived while the
 * story was open, which glows once. `aside` sits on the right of the head line (a cost, a time).
 */
export function TimelineItem({
  tone,
  icon,
  head,
  meta,
  aside,
  index = 0,
  fresh = false,
  live = false,
  testId,
  children,
}: {
  tone: Tone
  icon: string
  head: ReactNode
  meta?: ReactNode
  aside?: ReactNode
  index?: number
  fresh?: boolean
  live?: boolean
  testId?: string
  children?: ReactNode
}) {
  return (
    <li
      className={`aw-tl-item tone-${tone}`}
      style={{ '--i': index } as CSSProperties}
      data-fresh={fresh ? 'true' : undefined}
      data-testid={testId}
    >
      <span className="aw-tl-dot" data-live={live ? 'true' : undefined} aria-hidden="true">
        <Icon name={icon} size={12} />
      </span>
      <div className="aw-tl-body">
        <div className="aw-tl-head">
          {head}
          {aside ? <span className="aw-tl-aside">{aside}</span> : null}
        </div>
        {meta ? <div className="aw-tl-meta">{meta}</div> : null}
        {children ? <div className="aw-tl-content">{children}</div> : null}
      </div>
    </li>
  )
}
