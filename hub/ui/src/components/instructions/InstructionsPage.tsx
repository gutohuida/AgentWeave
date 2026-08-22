import { useState, useEffect } from 'react'
import { useInstructions, useSaveInstructions } from '@/api/instructions'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/input'
import { Icon } from '@/components/common/Icon'
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
          {saved && <span role="status" className="flex items-center gap-1 text-xs" style={{ color: 'var(--green)' }}><Icon name="check" size={13} />Saved</span>}
          <Button variant="primary" size="sm" onClick={handleSave} disabled={saveMutation.isPending}>
            {saveMutation.isPending ? 'Saving...' : 'Save'}
          </Button>
        </div>
      )}
    >
      {isLoading ? (
        <div aria-label="Loading instructions" className="space-y-3 py-4">
          <div className="skeleton h-[400px] w-full" />
          <div className="skeleton h-12 w-full" />
        </div>
      ) : (
        <div className="py-4">
          <Textarea
            aria-label="Project instructions"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="Enter project-wide instructions here..."
            className="min-h-[400px] w-full resize-y p-4 font-mono text-sm leading-relaxed"
            style={{
              background: 'var(--surface)',
            }}
            spellCheck={false}
          />
          <div
            className="mt-4 flex items-start gap-2 rounded-md px-4 py-3"
            style={{
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
              color: 'var(--text-3)',
              fontSize: 12,
            }}
          >
            <Icon name="info" size={15} className="mt-0.5 shrink-0" />
            <span><strong style={{ color: 'var(--text-2)' }}>Session boundary.</strong> Changes take effect when agents start a new session. Running sessions are not affected.</span>
          </div>
        </div>
      )}
    </SettingsSection>
  )
}
