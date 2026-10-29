import { useConfigStore, type ModeId } from '@/store/configStore'

/** Switch between light and dark. A flip repaints every surface at once, so transitions are
 *  suspended for that frame: it is one change rather than a hundred staggered fades. */
export function applyColorMode(next: ModeId): void {
  const root = document.documentElement
  root.classList.add('no-transitions')
  useConfigStore.getState().setMode(next)
  root.dataset.mode = next
  requestAnimationFrame(() => requestAnimationFrame(() => root.classList.remove('no-transitions')))
}
