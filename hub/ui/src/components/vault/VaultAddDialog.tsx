import * as React from 'react'
import { vaultFileMediaType, type VaultVisibility } from '@/api/vault'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { Dialog, DialogClose, DialogContent } from '@/components/ui/dialog'
import { DropZone } from '@/components/ui/dropzone'
import { Input, Textarea } from '@/components/ui/input'
import { MenuSelect } from '@/components/ui/menu'
import { Segmented } from '@/components/ui/segmented'
import { Field } from '@/components/ui/settings'
import { VAULT_KINDS } from './vaultKinds'

/** Adding to the vault: files (dropped or browsed) or pasted text, in one dialog.
 *
 *  Replaces an inline form that took over the reader, with a 16px-tall name field, the browser's
 *  "Choose File · No file chosen" button and its mm/dd/yyyy date picker. "When it was said" is a
 *  plain field that reads YYYY-MM-DD and says what is wrong on its own line; Add explains why it
 *  is disabled instead of just being grey. */

export type VaultAddInput =
  | {
      kind: 'files'
      files: File[]
      /** The kind shown; `typeChosen` false means it was the default, which each file may refine
       *  (a PDF or image is a document unless the operator says otherwise). */
      type: string
      typeChosen: boolean
      visibility: VaultVisibility
      dated?: string
    }
  | { kind: 'text'; name: string; type: string; content: string; visibility: VaultVisibility; dated?: string }

/** What the container answers when the Hub refused some or all of an add: the reason, and the
 *  files still to add (the ones that went in are dropped from the list). */
export interface VaultAddResult {
  error: string
  keep?: File[]
}

/** Hidden files and folders (a name or a folder starting with a dot) are not offered. */
function visibleFiles(files: File[]): File[] {
  return files.filter((file) => {
    const path = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name
    return !path.split('/').some((part) => part.startsWith('.'))
  })
}

const DATE = /^\d{4}-\d{2}-\d{2}$/

export function VaultAddDialog({
  open,
  onOpenChange,
  defaultVisibility,
  initialFiles,
  initialMode = 'files',
  onAdd,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  defaultVisibility: VaultVisibility
  /** Files dropped on the page before the dialog opened. */
  initialFiles?: File[]
  /** Which way the dialog opens: "Or paste text" opens it on the text form. */
  initialMode?: 'files' | 'text'
  onAdd: (input: VaultAddInput) => Promise<VaultAddResult | void> | void
}) {
  const [mode, setMode] = React.useState<'files' | 'text'>('files')
  const [files, setFiles] = React.useState<File[]>([])
  const [name, setName] = React.useState('')
  const [chosenType, setChosenType] = React.useState<string | null>(null)
  const [content, setContent] = React.useState('')
  const [dated, setDated] = React.useState('')
  const [visibility, setVisibility] = React.useState<VaultVisibility>(defaultVisibility)
  const [pending, setPending] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (!open) return
    setFiles(visibleFiles(initialFiles ?? []))
    setMode(initialFiles?.length ? 'files' : initialMode)
    setVisibility(defaultVisibility)
    setError(null)
  }, [open, initialFiles, initialMode, defaultVisibility])

  // Until the operator picks a kind: files that are all PDFs or images are documents, the rest
  // transcripts, as the form always defaulted.
  const binary = mode === 'files' && files.length > 0 && files.every((file) => vaultFileMediaType(file))
  const type = chosenType ?? (binary ? 'document' : 'transcript')

  const dateError = dated && !DATE.test(dated.trim()) ? 'Write it as YYYY-MM-DD, e.g. 2026-10-12.' : undefined
  const blocker =
    mode === 'files'
      ? !files.length
        ? 'Choose or drop at least one file.'
        : dateError
          ? 'Fix the date first.'
          : null
      : !name.trim()
        ? 'Give it a name.'
        : !content.trim()
          ? 'Paste the text to add.'
          : dateError
            ? 'Fix the date first.'
            : null

  const submit = async () => {
    if (blocker || pending) return
    const day = dated.trim() || undefined
    setPending(true)
    setError(null)
    const result =
      mode === 'files'
        ? await onAdd({ kind: 'files', files, type, typeChosen: chosenType !== null, visibility, dated: day })
        : await onAdd({ kind: 'text', name: name.trim(), type, content, visibility, dated: day })
    setPending(false)
    if (result?.error) {
      // Keep what the operator typed, and only the files that did not go in.
      setError(result.error)
      if (result.keep) setFiles(result.keep)
      return
    }
    setFiles([])
    setName('')
    setContent('')
    setDated('')
    setChosenType(null)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title="Add to the vault"
        description="Agents see the vault listed in every turn and read an entry when their work needs it."
        width={560}
        footer={
          <div className="flex w-full items-center gap-3">
            {error ? (
              <span className="vault-add-blocker" data-tone="error" role="alert">
                {error}
              </span>
            ) : (
              <span className="vault-add-blocker" role="status">
                {blocker ?? ''}
              </span>
            )}
            <DialogClose asChild>
              <Button variant="ghost" size="sm">
                Cancel
              </Button>
            </DialogClose>
            <Button variant="primary" size="sm" data-testid="vault-upload-submit" disabled={Boolean(blocker) || pending} onClick={() => void submit()}>
              {pending ? 'Adding…' : mode === 'files' && files.length > 1 ? `Add ${files.length} files` : 'Add'}
            </Button>
          </div>
        }
      >
        <div className="flex flex-col gap-4">
          <Segmented
            label="What to add"
            className="self-start"
            value={mode}
            onChange={setMode}
            options={[
              { value: 'files', label: 'Files or folders' },
              { value: 'text', label: 'Paste text' },
            ]}
          />

          {mode === 'files' ? (
            <div className="flex flex-col gap-2">
              <DropZone
                title="Drop files or a folder"
                hint="Text, Markdown, PDF and images. Hidden files are skipped."
                inputTestId="vault-upload-file"
                onFiles={(picked) => setFiles((current) => [...current, ...visibleFiles(picked)])}
              />
              {files.length ? (
                <ul className="vault-add-files">
                  {files.map((file, i) => (
                    <li key={`${file.name}-${i}`}>
                      <Icon name="description" size={13} />
                      <span className="min-w-0 flex-1 truncate">{file.name}</span>
                      <span className="vault-add-size">{Math.max(1, Math.round(file.size / 1024))} KB</span>
                      <button
                        data-slot="icon-button"
                        type="button"
                        className="aw-icon-button"
                        aria-label={`Remove ${file.name}`}
                        onClick={() => setFiles((current) => current.filter((_, j) => j !== i))}
                      >
                        <Icon name="close" size={12} />
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : (
            <>
              <Field label="Name" htmlFor="vault-add-name">
                <Input
                  id="vault-add-name"
                  data-testid="vault-upload-name"
                  value={name}
                  placeholder="Kickoff call with the operator"
                  onChange={(e) => setName(e.target.value)}
                  autoFocus
                />
              </Field>
              <Field label="Text" htmlFor="vault-add-text" hint="Markdown is kept as written.">
                <Textarea
                  id="vault-add-text"
                  data-testid="vault-upload-content"
                  rows={7}
                  value={content}
                  placeholder={'Operator: The export should keep the original file names.\nArchitect: Even when two files share one?'}
                  onChange={(e) => setContent(e.target.value)}
                />
              </Field>
            </>
          )}

          <div className="vault-add-grid">
            <Field label="Kind">
              <MenuSelect
                label="Kind"
                testId="vault-upload-type"
                value={type}
                onChange={setChosenType}
                maxWidth={520}
                options={VAULT_KINDS.map((k) => ({ value: k.type, label: k.label, detail: k.detail, icon: k.icon }))}
              />
            </Field>
            <Field label="Storage">
              <MenuSelect
                label="Storage"
                testId="vault-upload-visibility"
                value={visibility}
                onChange={setVisibility}
                maxWidth={520}
                options={[
                  { value: 'tracked', label: 'In the repository', detail: 'Committed with the project, so teammates and their agents see it.', icon: 'call_split' },
                  { value: 'private', label: 'Private, this machine', detail: 'Kept outside the repository. Only agents on this machine read it.', icon: 'lock' },
                ]}
              />
            </Field>
            {/* For files too: if two sources disagree, the later-dated one is presumed to hold. */}
            <Field label="When it was said" htmlFor="vault-add-dated" hint="Optional. e.g. 2026-10-12" error={dateError}>
              <Input
                id="vault-add-dated"
                data-testid="vault-upload-dated"
                value={dated}
                inputMode="numeric"
                placeholder="YYYY-MM-DD"
                aria-invalid={Boolean(dateError)}
                onChange={(e) => setDated(e.target.value)}
              />
            </Field>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
