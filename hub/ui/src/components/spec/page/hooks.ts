import * as React from 'react'
import { DEFAULT_LIST_PREFERENCES, type ListPreferences } from './model'

/** The document list's filters and order, kept per project in this browser: reopening the tab (or
 *  the app) shows the list the way the operator left it. The search text is not kept. */
export function useListPreferences(projectId: string): [ListPreferences, (next: ListPreferences) => void] {
  const key = `aw.spec.list.${projectId}`
  const [prefs, setPrefs] = React.useState<ListPreferences>(() => {
    try {
      const stored = JSON.parse(window.localStorage.getItem(key) ?? 'null') as Partial<ListPreferences> | null
      return { ...DEFAULT_LIST_PREFERENCES, ...(stored ?? {}), query: '' }
    } catch {
      return DEFAULT_LIST_PREFERENCES
    }
  })
  const update = React.useCallback(
    (next: ListPreferences) => {
      setPrefs(next)
      try {
        window.localStorage.setItem(key, JSON.stringify({ ...next, query: '' }))
      } catch {
        // Storage refused (private window): the choice holds for this visit only.
      }
    },
    [key],
  )
  return [prefs, update]
}

/** Back and forward through the positions the operator jumped to within a document (an outline
 *  pick, a link, a task or requirement chip), and the jump itself: the scroller moves the position
 *  under the sticky filter bar and it flashes once. Scrolling by hand is not a position. */
export function useDocumentNavigation(scroller: React.RefObject<HTMLElement | null>, initial: string | null) {
  const [state, setState] = React.useState<{ stack: Array<string | null>; index: number; tick: number }>({ stack: [initial], index: 0, tick: 1 })
  const [flash, setFlash] = React.useState<string | null>(null)
  const current = state.stack[state.index] ?? null

  React.useEffect(() => {
    if (!current) {
      // Back to where the document opened: its top.
      if (state.tick > 1) scroller.current?.scrollTo({ top: 0, behavior: prefersReducedMotion() ? 'auto' : 'smooth' })
      return
    }
    let timer = 0
    const frame = requestAnimationFrame(() => {
      const root = scroller.current
      const el = root?.querySelector<HTMLElement>(`[data-anchor="${CSS.escape(current)}"]`)
      if (!root || !el) return
      const top = el.getBoundingClientRect().top - root.getBoundingClientRect().top + root.scrollTop - 56
      root.scrollTo({ top: Math.max(0, top), behavior: prefersReducedMotion() ? 'auto' : 'smooth' })
      setFlash(current)
      timer = window.setTimeout(() => setFlash(null), 1600)
    })
    return () => {
      cancelAnimationFrame(frame)
      window.clearTimeout(timer)
    }
    // `tick` re-runs a jump to the position already current (the same outline entry picked twice).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current, state.tick])

  const jump = React.useCallback((anchor: string) => {
    setState((s) => {
      if (s.stack[s.index] === anchor) return { ...s, tick: s.tick + 1 }
      const stack = [...s.stack.slice(0, s.index + 1), anchor]
      return { stack, index: stack.length - 1, tick: s.tick + 1 }
    })
  }, [])
  const back = React.useCallback(() => setState((s) => (s.index > 0 ? { ...s, index: s.index - 1, tick: s.tick + 1 } : s)), [])
  const forward = React.useCallback(() => setState((s) => (s.index < s.stack.length - 1 ? { ...s, index: s.index + 1, tick: s.tick + 1 } : s)), [])
  return { current, flash, canBack: state.index > 0, canForward: state.index < state.stack.length - 1, jump, back, forward }
}

/** True while the operator asks for reduced motion; scroll jumps are then instant. */
export function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true
}

/** The anchor of the section, requirement or task nearest the top of a scrolling container,
 *  for the outline's highlight. */
export function useActiveAnchor(container: React.RefObject<HTMLElement | null>, deps: unknown[]): string | null {
  const [active, setActive] = React.useState<string | null>(null)
  React.useEffect(() => {
    const root = container.current
    if (!root) return
    const read = () => {
      const top = root.getBoundingClientRect().top + 72
      let best: string | null = null
      for (const el of Array.from(root.querySelectorAll<HTMLElement>('[data-anchor]'))) {
        if (el.getBoundingClientRect().top <= top) best = el.dataset.anchor ?? best
        else break
      }
      setActive(best)
    }
    read()
    root.addEventListener('scroll', read, { passive: true })
    return () => root.removeEventListener('scroll', read)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return active
}

const ENTER = {
  rise: [{ opacity: 0, transform: 'translateY(6px)' }, { opacity: 1, transform: 'none' }],
  pop: [{ opacity: 0, transform: 'scale(.96)' }, { opacity: 1, transform: 'none' }],
} as const

/** Plays an element's entrance once, when it mounts (or `key` changes). Through the Web Animations
 *  API rather than a CSS animation, because the app turns animations off for a frame around a theme
 *  switch, and a CSS entrance would replay on every switch. Nothing plays under reduced motion. */
export function useEnter<T extends HTMLElement>(kind: keyof typeof ENTER, delay = 0, key?: unknown) {
  const ref = React.useRef<T>(null)
  React.useLayoutEffect(() => {
    const el = ref.current
    if (!el || prefersReducedMotion() || typeof el.animate !== 'function') return
    const animation = el.animate(ENTER[kind] as unknown as Keyframe[], { duration: 200, delay, easing: 'cubic-bezier(0.23, 1, 0.32, 1)', fill: 'backwards' })
    return () => animation.cancel()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  return ref
}

/** The same entrance for every `[data-enter]` element inside a container, staggered: a document's
 *  sections and cards when it opens. */
export function useEnterChildren(container: React.RefObject<HTMLElement | null>, key: unknown) {
  React.useLayoutEffect(() => {
    const root = container.current
    if (!root || prefersReducedMotion() || typeof root.animate !== 'function') return
    const animations = Array.from(root.querySelectorAll<HTMLElement>('[data-enter]'))
      .slice(0, 24)
      .map((el, i) => el.animate(ENTER.rise as unknown as Keyframe[], { duration: 220, delay: Math.min(i, 14) * 18, easing: 'cubic-bezier(0.23, 1, 0.32, 1)', fill: 'backwards' }))
    return () => animations.forEach((a) => a.cancel())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
}
