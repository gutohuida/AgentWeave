import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { readableApiError } from '@/api/client'
import { useWorkspaceFile } from '@/api/workspace'
import { fileColourFor, fileIconFor } from './fileIcons'
import { FilePreview } from './FilePreview'

interface FileTabProps {
  path: string
  /** Appends this file's `@path` mention to the composer — omitted where there is no composer to
   *  insert into (there always is one today; kept optional so a future host without one degrades
   *  by hiding the button rather than crashing). */
  onInsertIntoComposer?: (path: string) => void
  onClose: () => void
}

/**
 * A workspace file, open beside a conversation — the files tab's detail kind (task 5.3,
 * `2026-08-18-one-shell-three-panels`). Reads through `GET /workspace/file`
 * (`useWorkspaceFile`), which already states binary and oversized refusals as the request's own
 * failure; this component's job is only to show whichever one comes back.
 */
export function FileTab({ path, onInsertIntoComposer, onClose }: FileTabProps) {
  const { data, isLoading, error } = useWorkspaceFile(path)
  const filename = path.slice(path.lastIndexOf('/') + 1)

  return (
    <div
      className="flex h-full min-w-0 flex-col overflow-hidden"
      data-testid="file-tab"
      style={{ background: 'var(--bg)' }}
    >
      <div className="flex shrink-0 items-center gap-2 px-3 py-2">
        <div className="flex min-w-0 items-center gap-1.5 px-2 py-1" title={path}>
          <Icon name={fileIconFor(path)} size={14} style={{ color: fileColourFor(path) }} />
          <span className="truncate" style={{ fontSize: 12, color: 'var(--text-2)' }}>
            {filename}
          </span>
        </div>
        <div className="flex-1" />
        {onInsertIntoComposer && (
          <Button
            variant="ghost"
            size="sm"
            data-testid="file-tab-insert"
            onClick={() => onInsertIntoComposer(path)}
            aria-label="Insert into composer"
            title="Insert into composer"
          >
            <Icon name="add" size={14} />
            Insert into composer
          </Button>
        )}
        <Button
          variant="ghost"
          size="icon-sm"
          data-testid="file-tab-close"
          onClick={onClose}
          aria-label="Close file"
          title="Close file"
        >
          <Icon name="close" size={16} />
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {isLoading ? (
          <div className="p-6" style={{ color: 'var(--text-3)', fontSize: 14 }}>Loading…</div>
        ) : error ? (
          <div className="p-6" data-testid="file-tab-error" style={{ color: 'var(--text-3)', fontSize: 13 }}>
            {readableApiError(error, 'This file could not be read.')}
          </div>
        ) : data?.binary ? (
          <div className="p-6" data-testid="file-tab-binary" style={{ color: 'var(--text-3)', fontSize: 13 }}>
            This file is binary ({data.size.toLocaleString()} bytes) and cannot be previewed.
          </div>
        ) : (
          <FilePreview path={path} content={data?.content ?? ''} />
        )}
      </div>
    </div>
  )
}
