import { screen, within } from '@testing-library/react'
import type { UserEvent } from '@testing-library/user-event'

/** The `MenuSelect` trigger named `label` (its accessible name). It shows the chosen option's label
 *  as its text, so `toHaveTextContent` reads what is selected. */
export function menuSelect(label: string | RegExp): HTMLElement {
  return screen.getByRole('button', { name: label })
}

/** Opens the `MenuSelect` named `label` and returns its options (Radix `menuitemradio`s), each
 *  named by its label and its second line. */
export async function openMenuSelect(user: UserEvent, label: string | RegExp): Promise<HTMLElement[]> {
  await user.click(menuSelect(label))
  const menu = await screen.findByRole('menu')
  return within(menu).getAllByRole('menuitemradio')
}

/** Opens the `MenuSelect` named `label` and chooses the option whose name matches `option`. */
export async function chooseMenuOption(user: UserEvent, label: string | RegExp, option: string | RegExp): Promise<void> {
  await user.click(menuSelect(label))
  const menu = await screen.findByRole('menu')
  await user.click(within(menu).getByRole('menuitemradio', { name: option }))
}
