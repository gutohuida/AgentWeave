/** Keyboard shortcuts named in more than one place: the matcher a listener uses and the label a
 *  tooltip shows come from here, so the two cannot drift apart. */

/** Whether this browser runs on macOS (or iOS), where Ctrl's role is played by Cmd and Alt is Option. */
export function isApplePlatform(nav: Pick<Navigator, 'platform' | 'userAgent'> | undefined = globalThis.navigator): boolean {
  if (!nav) return false
  const uaData = (nav as Navigator & { userAgentData?: { platform?: string } }).userAgentData
  const platform = uaData?.platform || nav.platform || nav.userAgent || ''
  return /mac|iphone|ipad|ipod/i.test(platform)
}

/** The side panel's toggle (leaner-navigation D5): Ctrl+Alt+B, Cmd+Option+B on macOS. Matched on
 *  `code`, not `key`, because Option+B on macOS types '∫'. */
export function isTogglePanelShortcut(event: Pick<KeyboardEvent, 'ctrlKey' | 'metaKey' | 'altKey' | 'shiftKey' | 'code'>): boolean {
  return (event.ctrlKey || event.metaKey) && event.altKey && !event.shiftKey && event.code === 'KeyB'
}

/** The side panel toggle's shortcut as this platform writes it. */
export function togglePanelShortcutLabel(apple: boolean = isApplePlatform()): string {
  return apple ? '⌘⌥B' : 'Ctrl+Alt+B'
}
