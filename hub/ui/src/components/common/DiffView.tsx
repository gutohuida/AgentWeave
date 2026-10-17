import { useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { Expander } from '@/components/common/Expander'
import { classifyDiffLine as classify, diffStat } from '@/lib/diffLines'

export interface DiffFile {
  path: string
  /** git's name-status letter: A added, M modified, D deleted. */
  status: string
  /** The file's unified diff, header included. */
  patch: string
}

const FOLD_AFTER = 8

const STATUS_WORD: Record<string, string> = { A: 'added', M: 'modified', D: 'deleted' }

function FileDiff({ file, initiallyOpen }: { file: DiffFile; initiallyOpen: boolean }) {
  const [open, setOpen] = useState(initiallyOpen)
  const [added, removed] = diffStat(file.patch)
  const lines = file.patch.split('\n').filter((line) => classify(line) !== 'meta')
  return (
    <div className="aw-diff-file" data-testid={`diff-file-${file.path}`}>
      <button
        type="button"
        className="aw-diff-head"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <Icon name="chevron_right" size={12} aria-hidden="true" />
        <span style={{ overflowWrap: 'anywhere' }}>{file.path}</span>
        <span className="aw-tl-meta">{STATUS_WORD[file.status] ?? file.status}</span>
        <span className="aw-diff-stat">
          <span className="add">+{added}</span>
          <span className="del">-{removed}</span>
        </span>
      </button>
      <Expander open={open}>
        <div className="aw-diff-body">
          <pre>
            {lines.map((line, index) => (
              <span key={index} className="aw-diff-line" data-kind={classify(line)}>
                {line || ' '}
              </span>
            ))}
          </pre>
        </div>
      </Expander>
    </div>
  )
}

/**
 * Files changed, each collapsible, with added and removed lines in the state tones. The first
 * file opens by itself when there are few, so the change is on screen without a click.
 */
export function DiffView({ files, testId }: { files: DiffFile[]; testId?: string }) {
  // A long line of work lists its first files and folds the rest behind one control.
  const [showAll, setShowAll] = useState(false)
  const visible = showAll ? files : files.slice(0, FOLD_AFTER)
  const hidden = files.length - visible.length
  return (
    <div className="aw-diff" data-testid={testId}>
      {visible.map((file, index) => (
        <FileDiff key={file.path} file={file} initiallyOpen={index === 0 && files.length <= 3} />
      ))}
      {hidden > 0 ? (
        <button type="button" className="aw-diff-more" onClick={() => setShowAll(true)}>
          Show {hidden} more {hidden === 1 ? 'file' : 'files'}
        </button>
      ) : null}
    </div>
  )
}
