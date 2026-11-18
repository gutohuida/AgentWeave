// The composer's field is a contenteditable element, not a textarea
// (`reference-a-spec-in-a-sentence-from-the-composer`, D5): these stand in for `fireEvent.change`,
// `toHaveValue` and `getByPlaceholderText`, reading and writing the field's value the way the
// composer itself does, with each box as its reference's text form.
import { fireEvent, screen } from '@testing-library/react'
import { readEditor, renderEditor } from '@/lib/composerEditor'

/** Replace the field's content with `value`, as an edit by the operator would, caret at the end. */
export function setComposerText(field: HTMLElement, value: string): void {
  renderEditor(field, value)
  const selection = window.getSelection()
  if (selection) {
    const range = document.createRange()
    range.selectNodeContents(field)
    range.collapse(false)
    selection.removeAllRanges()
    selection.addRange(range)
  }
  fireEvent.input(field)
}

/** The field's value: its text, with each box as its reference's text form. */
export function composerText(field: HTMLElement): string {
  return readEditor(field).text
}

/** The composer field whose placeholder matches, like `getByPlaceholderText`. */
export function queryComposerByPlaceholder(placeholder: string | RegExp): HTMLElement | null {
  const matches = (value: string | null) =>
    value !== null && (typeof placeholder === 'string' ? value === placeholder : placeholder.test(value))
  return screen.queryAllByRole('textbox').find((el) => matches(el.getAttribute('aria-placeholder'))) ?? null
}

export function getComposerByPlaceholder(placeholder: string | RegExp): HTMLElement {
  const found = queryComposerByPlaceholder(placeholder)
  if (!found) throw new Error(`no composer field with the placeholder ${String(placeholder)}`)
  return found
}
