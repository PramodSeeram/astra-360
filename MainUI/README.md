# Astra 360 — Web UI

React single-page app for Astra 360: onboarding, dashboards, chat with the financial assistant, and related flows. Built with **Vite**, **TypeScript**, **Tailwind CSS**, **shadcn/ui**-style primitives, and **TanStack Query**.

## Requirements

- **Node.js** 18+ and npm (or pnpm/yarn if you prefer — examples use npm)

The UI talks to the FastAPI backend. For full functionality, run the [backend](../backend/README.md) (default `http://127.0.0.1:8000`).

## Install

```bash
cd MainUI
npm install
```

## Development

Start the **backend** first, then:

```bash
npm run dev
```

- Dev server listens on **port 8080** by default (`vite.config.ts`).
- API routes such as `/api`, `/chat`, `/rag`, `/data`, `/insurance`, and `/dev` are **proxied** to the backend (`http://127.0.0.1:8000` by default).

If the API runs elsewhere, set when starting Vite:

```bash
BACKEND_PROXY_TARGET=http://127.0.0.1:8000 npm run dev
```

Open the URL shown in the terminal (typically `http://localhost:8080` or your LAN IP on port 8080).

## Production build

```bash
npm run build
```

Preview the static build locally:

```bash
npm run preview
```

When the built assets are served **separately** from the API (not using the dev proxy), set the API origin:

```bash
VITE_API_BASE=https://your-api.example.com npm run build
```

If `VITE_API_BASE` is unset in production, the client falls back to `http://127.0.0.1:8000` (see `src/lib/api.ts`).

## Other scripts

| Command | Purpose |
|---------|---------|
| `npm run lint` | ESLint |
| `npm test` | Vitest (single run) |
| `npm run test:watch` | Vitest watch mode |

## Tech stack

- **Framework**: React 18, React Router
- **Build**: Vite 5
- **Styling**: Tailwind CSS, `tailwindcss-animate`, `class-variance-authority`, `tailwind-merge`
- **UI primitives**: Radix UI packages
- **Data**: TanStack Query
- **Forms**: react-hook-form, Zod
- **Charts**: Recharts
- **Markdown**: react-markdown
