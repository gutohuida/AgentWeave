import { useEffect, useState } from 'react'
import { readableApiError } from '@/api/client'
import {
  VAULT_TYPES,
  isNoVault,
  useUpdateVaultSettings,
  useUploadVaultSource,
  useVaultEntry,
  useVaultMap,
  useVaultSettings,
  type VaultEntry,
  type VaultSettings,
  type VaultType,
  type VaultVisibility,
} from '@/api/vault'
import { Badge } from '@/components/common/Badge'
import { Button } from '@/components/ui/button'
import { Input, Select, Textarea } from '@/components/ui/input'
import { hubDate } from '@/lib/hubTime'

/**
 * The project's knowledge vault (`a-vault-the-operator-fills-with-text-and-agents-can-read`).
 *
 * The entries on the left, newest first; the chosen entry's text, or the upload form, on the
 * right; where entries go, below. Agents read the same entries through `vault_map` and
 * `vault_read`, and nothing they can call writes here.
 *
 * A Hub that predates the vault answers its routes 404. The bundle reaches the operator's app on
 * reload, possibly before their server restarts, so that reads as a state rather than an error.
 */
export function VaultPage() {
  const map = useVaultMap()
  const settings = useVaultSettings()
  const [selected, setSelected] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)

  if (isNoVault(map.error) || isNoVault(settings.error)) {
    return (
      <p data-testid="vault-none" className="p-6 text-sm" style={{ color: 'var(--text-3)' }}>
        This Hub has no vault yet. It arrives when the Hub is restarted on a version that has one.
      </p>
    )
  }

  const entries = map.data ?? []
  const current = entries.find((entry) => entry.id === selected) ?? null

  return (
    <div className="flex flex-col gap-6 p-6" data-testid="vault-page">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold">Vault</h2>
          <p className="mt-1 max-w-2xl text-xs" style={{ color: 'var(--text-3)' }}>
            What the business has told this project: meeting transcripts, rules, documents and
            examples. Agents see a short index of it in every turn and read entries by id.
          </p>
        </div>
        <Button
          size="sm"
          data-testid="vault-upload-open"
          onClick={() => {
            setAdding(true)
            setSelected(null)
          }}
        >
          Add a source
        </Button>
      </header>

      <div className="grid min-h-[320px] grid-cols-[minmax(220px,320px)_1fr] gap-6">
        <section aria-label="Vault entries" className="flex flex-col gap-1">
          {map.error ? (
            <p className="text-xs" style={{ color: 'var(--amber)' }} role="alert">
              {readableApiError(map.error, "Could not read this project's vault.")}
            </p>
          ) : !map.data ? (
            <div aria-label="Loading the vault" className="skeleton h-[120px] w-full" />
          ) : entries.length === 0 ? (
            <p className="text-xs" style={{ color: 'var(--text-3)' }}>
              Nothing yet. Add a transcript, a rule or a document, and agents can read it.
            </p>
          ) : (
            entries.map((entry) => (
              <EntryRow
                key={entry.id}
                entry={entry}
                active={entry.id === selected}
                onOpen={() => {
                  setSelected(entry.id)
                  setAdding(false)
                }}
              />
            ))
          )}
        </section>

        <section aria-label="Vault entry" className="min-w-0">
          {adding ? (
            <UploadForm
              settings={settings.data}
              onDone={(id) => {
                setAdding(false)
                setSelected(id)
              }}
              onCancel={() => setAdding(false)}
            />
          ) : current ? (
            <EntryView entry={current} />
          ) : (
            <p className="text-xs" style={{ color: 'var(--text-3)' }}>
              Choose an entry to read it.
            </p>
          )}
        </section>
      </div>

      <SettingsForm settings={settings.data} error={settings.error} />
    </div>
  )
}

function EntryRow({ entry, active, onOpen }: { entry: VaultEntry; active: boolean; onOpen: () => void }) {
  return (
    <button
      type="button"
      data-testid={`vault-entry-${entry.id}`}
      data-active={active ? 'true' : 'false'}
      onClick={onOpen}
      className="row-item flex w-full flex-col items-start gap-1 rounded-md px-3 py-2 text-left"
    >
      <span className="flex w-full items-center gap-2">
        <span className="truncate text-sm font-medium">{entry.name}</span>
        <Badge variant="default">{entry.type}</Badge>
        {entry.visibility === 'private' && <Badge variant="warning">private</Badge>}
      </span>
      <span className="line-clamp-2 text-xs" style={{ color: 'var(--text-3)' }}>
        {entry.available ? entry.opening : `Held on ${entry.holder ?? 'another machine'}`}
      </span>
    </button>
  )
}

function EntryView({ entry }: { entry: VaultEntry }) {
  const pages = useVaultEntry(entry.id)
  const loaded = pages.data?.pages ?? []
  const first = loaded[0]
  const text = loaded.map((page) => page.content ?? '').join('')

  return (
    <article className="flex flex-col gap-3">
      <header>
        <h3 className="text-sm font-semibold">{entry.name}</h3>
        <p className="mt-1 text-xs" style={{ color: 'var(--text-3)' }}>
          {entry.type} · {entry.visibility === 'private' ? `private, held on ${entry.holder ?? 'another machine'}` : 'tracked in the repository'}
          {' · '}
          {hubDate(entry.created_at).toLocaleString()} · <code>{entry.id}</code>
        </p>
      </header>
      {pages.error ? (
        <p className="text-xs" style={{ color: 'var(--amber)' }} role="alert">
          {readableApiError(pages.error, 'Could not read this entry.')}
        </p>
      ) : !first ? (
        <div aria-label="Loading the entry" className="skeleton h-[160px] w-full" />
      ) : first.content === null ? (
        <p className="text-xs" style={{ color: 'var(--text-3)' }}>{first.note}</p>
      ) : (
        <>
          <pre
            data-testid="vault-entry-text"
            className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-md p-4 text-sm"
            style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', fontFamily: 'inherit' }}
          >
            {text}
          </pre>
          {pages.hasNextPage && (
            <Button
              size="sm"
              variant="ghost"
              disabled={pages.isFetchingNextPage}
              onClick={() => void pages.fetchNextPage()}
            >
              Show more
            </Button>
          )}
        </>
      )}
    </article>
  )
}

function UploadForm({
  settings,
  onDone,
  onCancel,
}: {
  settings: VaultSettings | undefined
  onDone: (id: string) => void
  onCancel: () => void
}) {
  const upload = useUploadVaultSource()
  const [name, setName] = useState('')
  const [type, setType] = useState<VaultType>('transcript')
  const [visibility, setVisibility] = useState<VaultVisibility>(settings?.default_visibility ?? 'tracked')
  const [content, setContent] = useState('')
  const [fileError, setFileError] = useState<string | null>(null)

  const readFile = async (file: File | undefined) => {
    if (!file) return
    try {
      setContent(await file.text())
      setFileError(null)
      if (!name) setName(file.name.replace(/\.[^.]+$/, ''))
    } catch {
      setFileError(`Could not read ${file.name} as text.`)
    }
  }

  return (
    <form
      className="flex flex-col gap-3"
      aria-label="Add a source"
      onSubmit={(event) => {
        event.preventDefault()
        upload.mutate({ name, type, content, visibility }, { onSuccess: (entry) => onDone(entry.id) })
      }}
    >
      <h3 className="text-sm font-semibold">Add a source</h3>
      <label className="flex flex-col gap-1 text-xs">
        Name
        <Input data-testid="vault-upload-name" value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <div className="flex gap-3">
        <label className="flex flex-col gap-1 text-xs">
          Type
          <Select
            data-testid="vault-upload-type"
            value={type}
            onChange={(e) => setType(e.target.value as VaultType)}
            wrapperClassName="w-40"
            className="px-2 py-1.5 text-xs"
          >
            {VAULT_TYPES.map((item) => <option key={item} value={item}>{item}</option>)}
          </Select>
        </label>
        <label className="flex flex-col gap-1 text-xs">
          Where it goes
          <Select
            data-testid="vault-upload-visibility"
            value={visibility}
            onChange={(e) => setVisibility(e.target.value as VaultVisibility)}
            wrapperClassName="w-56"
            className="px-2 py-1.5 text-xs"
          >
            <option value="tracked">Tracked: in the repository</option>
            <option value="private">Private: this machine only</option>
          </Select>
        </label>
      </div>
      {visibility === 'private' && (
        <p className="text-xs" style={{ color: 'var(--text-3)' }}>
          The text stays on this machine. Its name, type and this machine's name are still listed
          in the repository, so colleagues know it exists.
        </p>
      )}
      <label className="flex flex-col gap-1 text-xs">
        Text
        <Textarea
          data-testid="vault-upload-content"
          rows={12}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Paste a transcript, a rule or a document, or choose a text file below."
        />
      </label>
      <input
        type="file"
        aria-label="Read the text from a file"
        data-testid="vault-upload-file"
        accept=".txt,.md,.markdown,.vtt,.srt,.csv,.json,text/*"
        className="text-xs"
        onChange={(e) => void readFile(e.target.files?.[0])}
      />
      {(fileError || upload.error) && (
        <p className="text-xs" style={{ color: 'var(--amber)' }} role="alert">
          {fileError ?? readableApiError(upload.error, 'Could not add that source.')}
        </p>
      )}
      <div className="flex gap-2">
        <Button
          type="submit"
          size="sm"
          data-testid="vault-upload-submit"
          disabled={upload.isPending || !name.trim() || !content}
        >
          Add
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  )
}

function SettingsForm({ settings, error }: { settings: VaultSettings | undefined; error: unknown }) {
  const update = useUpdateVaultSettings()
  const [location, setLocation] = useState('')
  useEffect(() => setLocation(settings?.private_location ?? ''), [settings?.private_location])

  return (
    <section aria-label="Where entries go" className="flex flex-col gap-3 border-t pt-4" style={{ borderColor: 'var(--border)' }}>
      <h3 className="settings-group-heading">Where entries go</h3>
      {error ? (
        <p className="text-xs" style={{ color: 'var(--amber)' }} role="alert">
          {readableApiError(error, "Could not read the vault's settings.")}
        </p>
      ) : !settings ? (
        <div aria-label="Loading the vault's settings" className="skeleton h-[60px] w-full" />
      ) : (
        <>
          <label className="flex items-center gap-3 text-xs">
            New sources are
            <Select
              data-testid="vault-settings-default"
              value={settings.default_visibility}
              onChange={(e) => update.mutate({ default_visibility: e.target.value as VaultVisibility })}
              wrapperClassName="w-56"
              className="px-2 py-1.5 text-xs"
            >
              <option value="tracked">tracked in the repository</option>
              <option value="private">private to this machine</option>
            </Select>
          </label>
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault()
              update.mutate({ private_location: location.trim() || null })
            }}
          >
            <label className="flex min-w-[320px] flex-1 flex-col gap-1 text-xs">
              Private entries are kept in (outside the repository)
              <Input
                data-testid="vault-settings-location"
                value={location}
                placeholder={settings.effective_private_location}
                onChange={(e) => setLocation(e.target.value)}
              />
            </label>
            <Button type="submit" size="sm" data-testid="vault-settings-save" disabled={update.isPending}>
              Save
            </Button>
          </form>
          {update.error && (
            <p className="text-xs" style={{ color: 'var(--amber)' }} role="alert">
              {readableApiError(update.error, 'Could not save that change.')}
            </p>
          )}
        </>
      )}
    </section>
  )
}
