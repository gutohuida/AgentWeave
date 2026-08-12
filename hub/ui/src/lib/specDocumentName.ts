/**
 * Turning what the operator typed into a document path.
 *
 * The server's path contract is narrow — lowercase, POSIX separators, beneath
 * `spec/`, ending `.html`, no dot or hidden segments — and it is the authority.
 * This exists so the operator can type "Budget app" and get a document, rather
 * than being asked to compose a path that satisfies a contract they cannot see.
 *
 * Unlike a project name, a title that cannot be slugified is not refused: there
 * is no destructive surprise in `spec/changes/budget-app/spec.html`, and the
 * title itself is preserved separately. What *is* refused is a title that
 * slugifies to nothing, because then there is no document to name.
 */

/** The directory new explorations start in. Archived ones move elsewhere later. */
export const EXPLORATION_ROOT = 'spec/changes'

export function slugify(title: string): string {
  return title
    .normalize('NFKD')
    // Drop accents rather than transliterating them: the slug is an identifier,
    // and the readable form lives in the title.
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64)
    .replace(/-+$/g, '')
}

/** `null` when the title carries nothing a path can be built from. */
export function documentPathFor(title: string): string | null {
  const slug = slugify(title)
  if (!slug) return null
  return `${EXPLORATION_ROOT}/${slug}/spec.html`
}
