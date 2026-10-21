import React from 'react'
import ReactDOM from 'react-dom/client'
import '@/index.css'
import '@/styles/story.css'
import '@/styles/primitives.css'
import '@/styles/shell.css'
import './mock.css'
import { QueryClientProvider } from '@tanstack/react-query'
import { MockApp } from './MockApp'
import { mockQueryClient } from './queryClient'

// Each screen's own stylesheet lives beside its components in src/styles and is imported by the
// screen module, so the mock and the app load exactly the same CSS.

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={mockQueryClient()}>
      <MockApp />
    </QueryClientProvider>
  </React.StrictMode>,
)
