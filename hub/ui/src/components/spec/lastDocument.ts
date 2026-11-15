/** The spec document the operator last opened, kept per project in this browser so the Spec tab
 *  reopens it, after the app is closed and reopened too (spec
 *  `spec-page-remembers-readable-task-threads-retrospective-after-landing`, FR-1..FR-4).
 *
 *  A stored empty string is "the list": the remembered document no longer exists, so a bare Spec tab
 *  shows the list until a document is opened again, rather than falling back to some other one. */
const keyOf = (projectId: string) => `aw.spec.last.${projectId}`

/** `undefined`: nothing remembered. `''`: remembered that the list is what to show. */
export function readLastDocument(projectId: string): string | undefined {
  try {
    return window.localStorage.getItem(keyOf(projectId)) ?? undefined
  } catch {
    return undefined
  }
}

export function rememberDocument(projectId: string, path: string): void {
  try {
    window.localStorage.setItem(keyOf(projectId), path)
  } catch {
    // Storage refused (private window): the document is remembered for this visit only.
  }
}

/** The remembered document is gone: forget it, and show the list on the next bare open. */
export function forgetDocument(projectId: string): void {
  rememberDocument(projectId, '')
}
