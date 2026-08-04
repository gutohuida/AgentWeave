import { useStatus } from '@/api/status'

export function DiagnosticsPanel() {
  const { data } = useStatus()
  return (
    <section className="p-4" aria-labelledby="diagnostics-heading">
      <h2 id="diagnostics-heading" className="text-sm font-semibold">Diagnostics</h2>
      <pre className="mt-3 overflow-auto rounded p-3 text-xs" style={{ background: 'var(--surface-2)' }}>
        {JSON.stringify(data ?? {}, null, 2)}
      </pre>
    </section>
  )
}
