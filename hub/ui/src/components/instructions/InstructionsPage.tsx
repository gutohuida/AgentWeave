import { useState, useEffect } from 'react'
import { useInstructions, useSaveInstructions } from '@/api/instructions'

export function InstructionsPage() {
  const { data, isLoading } = useInstructions()
  const saveMutation = useSaveInstructions()
  const [content, setContent] = useState('')
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (data) {
      setContent(data.content)
    }
  }, [data])

  useEffect(() => {
    if (saveMutation.isSuccess) {
      setSaved(true)
      const timer = setTimeout(() => setSaved(false), 2000)
      return () => clearTimeout(timer)
    }
  }, [saveMutation.isSuccess])

  const handleSave = () => {
    saveMutation.mutate(content)
  }

  return (
    <div className="flex flex-col h-full" style={{ background: 'var(--bg)' }}>
      <div
        className="flex items-center justify-between px-6 py-4"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <div>
          <h1 style={{ fontSize: 18, fontWeight: 600, color: 'var(--text)' }}>
            Project Instructions
          </h1>
          <p style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>
            These rules are prepended to every agent's role guide at session start.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {saved && (
            <span style={{ fontSize: 12, color: 'var(--green)' }}>Saved</span>
          )}
          <button
            onClick={handleSave}
            disabled={saveMutation.isPending}
            className="px-4 py-2 rounded-md text-sm font-medium"
            style={{
              background: saveMutation.isPending ? 'var(--surface-3)' : 'var(--text)',
              color: saveMutation.isPending ? 'var(--text-3)' : 'var(--bg)',
              opacity: saveMutation.isPending ? 0.6 : 1,
              cursor: saveMutation.isPending ? 'not-allowed' : 'pointer',
            }}
          >
            {saveMutation.isPending ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>

      <div className="flex-1 p-6 overflow-auto">
        {isLoading ? (
          <div style={{ color: 'var(--text-3)', fontSize: 14 }}>Loading...</div>
        ) : (
          <>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="Enter project-wide instructions here..."
              className="w-full h-full resize-none rounded-md p-4 font-mono text-sm"
              style={{
                background: 'var(--surface)',
                color: 'var(--text)',
                border: '1px solid var(--border)',
                minHeight: 400,
                lineHeight: 1.6,
              }}
              spellCheck={false}
            />
            <div
              className="mt-4 px-4 py-3 rounded-md"
              style={{
                background: 'var(--surface-2)',
                border: '1px solid var(--border)',
                color: 'var(--text-3)',
                fontSize: 12,
              }}
            >
              <strong style={{ color: 'var(--text-2)' }}>Note:</strong> Changes take effect
              when agents start a new session. Running sessions are not affected.
            </div>
          </>
        )}
      </div>
    </div>
  )
}
