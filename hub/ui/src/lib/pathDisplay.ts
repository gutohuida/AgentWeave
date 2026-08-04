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
