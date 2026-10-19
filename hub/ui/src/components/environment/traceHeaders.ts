/**
 * `Name=value` per line (a `Name: value` line is read the same way). Returns the parsed headers,
 * or the first line it could not read, so nothing half-parsed is ever saved. Header values are
 * write-only on the Hub, so this text is the only place the operator ever sees them.
 */
export function parseHeaderLines(
  textValue: string,
): { headers: Record<string, string> } | { error: string } {
  const headers: Record<string, string> = {}
  for (const raw of textValue.split(/\r?\n/)) {
    const line = raw.trim()
    if (!line) continue
    const match = /^([^=:\s]+)\s*[=:]\s*(.*)$/.exec(line)
    if (!match || !match[2]) return { error: `“${line}” is not a Name=value header.` }
    headers[match[1]] = match[2]
  }
  return { headers }
}
