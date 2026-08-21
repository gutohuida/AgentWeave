/** Whether the OS/browser asks for reduced motion right now (task-dependencies task 8.16, D12).
 *  Read fresh on each call rather than cached or subscribed to — the cards that use this re-render
 *  often enough (task list refetches) that a stale value would not survive long, and the
 *  accessibility floor here is "never animate when asked not to", not "react instantly to a
 *  mid-session OS setting change". */
export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}
