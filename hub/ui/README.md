# AgentWeave Hub — Dashboard UI

React + Vite + Tailwind dashboard for monitoring and interacting with the AgentWeave Hub.

## Prerequisites

- Node.js 20+ (`node --version`)
- A running Hub instance (see `hub/` root for Docker setup)

## Dev setup (one time)

```bash
cd hub/ui
npm install
```

## Start dev server

```bash
npm run dev
# → http://localhost:5173
# Proxies /api and /health to http://localhost:8000
```

On first load, a **Setup modal** asks for:
- **Hub URL** — default `http://localhost:8000`
- **API key** — `aw_live_...` (printed by Hub on first start)
- **Project ID** — default `proj-default`

Config is saved in `localStorage`, so you only need to enter it once.

## Production build

```bash
npm run build
# Outputs to dist/
```

The Docker multi-stage build runs this automatically — you never need to build manually for deployment.

## Stack

| | |
|---|---|
| Framework | React 18 + TypeScript |
| Build | Vite 5 |
| Styling | Tailwind CSS v3 |
| Icons | Lucide React |
| Data fetching | TanStack Query v5 |
| Real-time | Native EventSource (SSE) |
| State | Zustand (localStorage persistence) |
| Dates | date-fns |
