/**
 * Composing the target directory for a new project, from a parent the operator browsed to
 * and a name they typed.
 *
 * Creating a project needs a path that does **not** exist yet, and every browse affordance
 * returns one that does. Rather than making the operator splice a segment onto a path
 * string, create mode takes the two parts separately and joins them here.
 */

/**
 * Which separator to build the path with.
 *
 * This is cosmetic, not semantic — the Hub normalises either form. It exists so a Windows
 * operator who browsed to `C:\Users\me\projects` is shown a path they recognise instead of
 * a mixed-separator hybrid.
 */
export function pathSeparator(parent: string): '\\' | '/' {
  const trimmed = parent.trim()
  if (/^[a-zA-Z]:/.test(trimmed)) return '\\'
  if (trimmed.includes('\\') && !trimmed.includes('/')) return '\\'
  return '/'
}

/** Join a parent directory and a project name into the absolute target to be created. */
export function joinProjectPath(parent: string, name: string): string {
  const separator = pathSeparator(parent)
  const trimmedParent = parent.trim().replace(/[\\/]+$/, '')
  const trimmedName = name.trim()
  if (!trimmedParent || !trimmedName) return ''
  return `${trimmedParent}${separator}${trimmedName}`
}

/**
 * Why a project name is unusable as a directory name, or `null` if it is fine.
 *
 * Deliberately refuses rather than sanitising: rewriting `my/project` into `my-project`
 * would create a directory the operator never asked for, at a path they never saw, which is
 * the same class of surprise this whole change exists to remove.
 *
 * Only the unambiguous, portable cases are checked here. Platform-specific rules — Windows
 * reserved device names, trailing dots, `<>:"|?*` — stay the server's to enforce, and it
 * already surfaces them as `project_create_failed`. A client-side list pretending to be
 * complete would be a fourth place for those rules to drift.
 */
export function projectNameProblem(name: string): string | null {
  const trimmed = name.trim()
  if (!trimmed) return 'Enter a name for the project.'
  if (trimmed.includes('/') || trimmed.includes('\\')) {
    return 'A project name is a single folder name, not a path — remove the slashes.'
  }
  if (trimmed === '.' || trimmed === '..') {
    return 'That name refers to a directory that already exists.'
  }
  return null
}
