import { useState, useEffect } from 'react'
import { useInstructions, useSaveInstructions } from '@/api/instructions'
import { Button } from '@/components/ui/button'
import { SettingsSection } from '@/components/environment/SettingsSection'

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
    <SettingsSection
      title="Instructions"
      description="These rules are prepended to every agent's role guide at session start."
      actions={(
        <div className="flex items-center gap-3">
          {saved && <span style={{ fontSize: 12, color: 'var(--green)' }}>Saved</span>}
          <Button variant="primary" size="sm" onClick={handleSave} disabled={saveMutation.isPending}>
            {saveMutation.isPending ? 'Saving...' : 'Save'}
          </Button>
        </div>
      )}
    >
      {isLoading ? (
        <div style={{ color: 'var(--text-3)', fontSize: 14 }}>Loading...</div>
      ) : (
        <div className="py-4">
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="Enter project-wide instructions here..."
            className="w-full resize-none rounded-md p-4 font-mono text-sm"
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
        </div>
      )}
    </SettingsSection>
  )
}
