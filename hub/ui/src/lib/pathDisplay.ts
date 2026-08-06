/**
 * Middle-elides a filesystem path into breadcrumb segments: the root segment, an ellipsis if
 * segments were dropped, then the last `tailCount` segments — the tail is the identifying part
 * of a path, so eliding the middle (not the end) keeps what's worth reading on screen.
 */
export function elidePathSegments(path: string, headCount = 1, tailCount = 3): string[] {
  const isWindowsDrive = /^[a-zA-Z]:[\\/]/.test(path)
  const isUnixAbsolute = !isWindowsDrive && path.startsWith('/')

  const raw = path.split(/[\\/]+/).filter(Boolean)
  if (raw.length === 0) return []

  if (isWindowsDrive) raw[0] = `${raw[0]}\\`
  else if (isUnixAbsolute) raw[0] = `/${raw[0]}`

  if (raw.length <= headCount + tailCount) return raw
  return [...raw.slice(0, headCount), '…', ...raw.slice(raw.length - tailCount)]
}

export interface PathAncestor {
  label: string
  /** The cumulative absolute path up to and including this segment — what navigating
   * "back to here" means, unlike `elidePathSegments`'s display-only, non-navigable output. */
  path: string
}

/** Every segment of an absolute path with its own full path, for a breadcrumb that can
 * jump directly to any ancestor (composer/chrome refinement §9.2). Nothing is elided —
 * the directory picker's breadcrumb scrolls rather than drops segments. */
export function pathAncestors(path: string): PathAncestor[] {
  const isWindowsDrive = /^[a-zA-Z]:[\\/]/.test(path)
  const isUnixAbsolute = !isWindowsDrive && path.startsWith('/')
  const separator = isWindowsDrive ? '\\' : '/'

  const raw = path.split(/[\\/]+/).filter(Boolean)
  if (raw.length === 0) {
    return isUnixAbsolute || path === '/' ? [{ label: '/', path: '/' }] : []
  }

  if (isWindowsDrive) raw[0] = `${raw[0]}\\`
  else if (isUnixAbsolute) raw[0] = `/${raw[0]}`

  const ancestors: PathAncestor[] = []
  raw.forEach((segment, index) => {
    if (index === 0) {
      ancestors.push({ label: segment, path: segment })
      return
    }
    const previous = ancestors[index - 1]!.path
    const joined = previous.endsWith(separator) ? `${previous}${segment}` : `${previous}${separator}${segment}`
    ancestors.push({ label: segment, path: joined })
  })
  return ancestors
}
