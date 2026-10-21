import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
// The base stylesheets load first, before any component's own (which arrive with `App`): a
// screen's stylesheet refines index.css's rules at equal specificity, so it has to come after
// them. The mock loads them in this same order.
import './index.css'
import './styles/story.css'
import './styles/primitives.css'
import './styles/shell.css'
import App from './App.tsx'
import { ErrorBoundary } from './components/common/ErrorBoundary'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>,
)
