/** Landing on a setting: scroll its row into view, highlight it, put keyboard focus on its control.
 *
 *  The row is found by the label it shows, because the label is what a destination names
 *  (`setting=` in the location) and what the search index lists. Sections load their data after
 *  they mount, so it keeps looking for a while; the highlight is an attribute set from here (rows
 *  never render it themselves) and is taken off again after `HIGHLIGHT_MS`. Returns a cleanup. */

export const HIGHLIGHT_MS = 4000
const GIVE_UP_MS = 10000
const POLL_MS = 100
/** While the section is still settling, keep the row where the operator can see it. */
const RESCROLL_MS = 600

const CONTROL = [
  'input:not([type="hidden"]):not(:disabled)',
  'select:not(:disabled)',
  'textarea:not(:disabled)',
  '[role="switch"]:not(:disabled)',
  '[role="combobox"]:not(:disabled)',
  'button:not([data-slot="icon-button"]):not(:disabled)',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

const normal = (text: string | null | undefined) => (text ?? '').replace(/\s+/g, ' ').trim().toLowerCase()

export function findSettingRow(root: ParentNode, label: string): HTMLElement | null {
  const want = normal(label)
  for (const row of Array.from(root.querySelectorAll<HTMLElement>('.aw-settings-row'))) {
    if (normal(row.querySelector('.aw-settings-row-label')?.textContent) === want) return row
  }
  return null
}

export function landOnSetting(root: ParentNode, label: string): () => void {
  const startedAt = Date.now()
  let landedAt = 0
  let lit: HTMLElement | null = null
  const unlight = () => {
    lit?.removeAttribute('data-highlighted')
    lit = null
  }
  const tick = () => {
    const now = Date.now()
    const row = findSettingRow(root, label)
    if (!row) {
      if (!landedAt && now - startedAt > GIVE_UP_MS) window.clearInterval(timer)
      return
    }
    if (!landedAt) landedAt = now
    if (now - landedAt >= HIGHLIGHT_MS) {
      unlight()
      window.clearInterval(timer)
      return
    }
    if (lit !== row) {
      unlight()
      row.setAttribute('data-highlighted', 'true')
      lit = row
    }
    if (now - landedAt <= RESCROLL_MS) row.scrollIntoView({ block: 'center' })
    const active = document.activeElement
    if ((!active || active === document.body) && now - landedAt <= RESCROLL_MS * 2) {
      const target = row.querySelector<HTMLElement>('.aw-settings-row-control')?.querySelector<HTMLElement>(CONTROL) ?? row.querySelector<HTMLElement>(CONTROL)
      target?.focus({ preventScroll: true })
    }
  }
  const timer = window.setInterval(tick, POLL_MS)
  tick()
  return () => {
    window.clearInterval(timer)
    unlight()
  }
}
