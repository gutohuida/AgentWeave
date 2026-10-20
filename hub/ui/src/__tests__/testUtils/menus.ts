import { fireEvent, screen } from '@testing-library/react'

/**
 * Opening a Radix menu from a test. Its trigger opens on pointer-down with the primary button, or
 * on Enter/Space; jsdom's synthetic pointer events carry no `button`, so the keyboard route is the
 * one a test can drive with `fireEvent`.
 */
export function openMenu(trigger: HTMLElement): void {
  fireEvent.keyDown(trigger, { key: 'Enter' })
}

/** Opens the document header's overflow menu ("More actions"). */
export function openMoreActions(): void {
  openMenu(screen.getByRole('button', { name: 'More actions' }))
}

/** Opens the overflow menu and chooses one of its items. */
export function chooseMoreAction(name: string | RegExp): void {
  openMoreActions()
  fireEvent.click(screen.getByRole('menuitem', { name }))
}

/** Picks a rigor from the document header's rigor chip (`data-testid="spec-rigor"`). */
export function chooseRigor(label: 'Sketch' | 'Contract' | 'Gate'): void {
  openMenu(screen.getByTestId('spec-rigor'))
  fireEvent.click(screen.getByRole('menuitemradio', { name: new RegExp(`^${label}`) }))
}

/** Picks an option of a `MenuSelect` by its trigger and the option's label. */
export function chooseMenuOption(trigger: HTMLElement, label: string | RegExp): void {
  openMenu(trigger)
  fireEvent.click(screen.getByRole('menuitemradio', { name: label }))
}
