import * as React from 'react'

/** Whole-region drop: spread `bind` on the region; `dragging` is true while files hover it. */
export function usePageDrop(onFiles: (files: File[]) => void) {
  const [dragging, setDragging] = React.useState(false)
  const depth = React.useRef(0)
  const bind = {
    onDragEnter: (e: React.DragEvent) => {
      if (!Array.from(e.dataTransfer.types).includes('Files')) return
      depth.current += 1
      setDragging(true)
    },
    onDragOver: (e: React.DragEvent) => {
      if (Array.from(e.dataTransfer.types).includes('Files')) e.preventDefault()
    },
    onDragLeave: () => {
      depth.current = Math.max(0, depth.current - 1)
      if (depth.current === 0) setDragging(false)
    },
    onDrop: (e: React.DragEvent) => {
      e.preventDefault()
      depth.current = 0
      setDragging(false)
      const files = Array.from(e.dataTransfer.files)
      if (files.length) onFiles(files)
    },
  }
  return { dragging, bind }
}
