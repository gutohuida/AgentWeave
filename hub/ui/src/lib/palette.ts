/** Opens the command palette from a control rather than its Ctrl K shortcut (the TopBar's Search
 *  button). An event, not shared state: the palette owns whether it is open, and a click is one
 *  more way of asking, exactly as the key is. Focus returns to the control that asked. */
export const OPEN_PALETTE_EVENT = 'aw:open-palette'

export function openCommandPalette(): void {
  document.dispatchEvent(new CustomEvent(OPEN_PALETTE_EVENT))
}
