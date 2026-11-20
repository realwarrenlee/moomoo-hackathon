# MooTrade Dashboard

Read-only Next.js dashboard for MooTrade, the **Moomoo × Qoder AI Trading Agent Challenge** paper-trading agent.

This dashboard visualises the exact competition **paper** account and the deterministic controls around it. It has no order-capable route, no credential entry, and no control that can enable writes or bypass the RiskGate.

## Pages

| Route | Purpose |
| --- | --- |
| `/dashboard` | Overview: account, quotes, AI evidence and execution locks |
| `/agents` | Historical Qoder agent sessions, summaries and candidates |
| `/portfolio` | Broker positions, open orders, today's orders and order history |
| `/risk` | Policy limits, live gate inputs, recorded real preflight and controls |
| `/analytics` | Historical backtest/catalyst evidence, explicitly not paper performance |
| `/audit` | Append-only SQLite ledger events |

Every source is labelled: `LIVE_BROKER_READ`, `HISTORICAL_BACKTEST`, `HISTORICAL_QODER_RUN`, `RECORDED_REAL_PREFLIGHT`, `LOCAL_LEDGER` or `LOCAL_CONTROLS`.

## Run locally

Backend (from the repository root):

```bash
cd backend
../.venv/Scripts/python.exe -m uvicorn app.dashboard.api:app --host 127.0.0.1 --port 8000
```

Frontend (from `frontend/`):

```bash
npx --yes pnpm@10 install --frozen-lockfile
npx pnpm@10 run dev
```

The template's existing `pnpm-lock.yaml` is authoritative. `npm install` does not resolve one unused 3D peer dependency in the template; pnpm's lockfile does.

Open <http://localhost:3000>. The Next server proxies `/api/mootrade/*` to the FastAPI backend, so the browser never receives OAuth data.

### Environment

The frontend server route reads these optional variables:

| Variable | Default | Use |
| --- | --- | --- |
| `MOOTRADE_API_URL` | `http://127.0.0.1:8000` | Backend origin |
| `MOOTRADE_DASHBOARD_TOKEN` | unset | Bearer token attached server-side |

The backend is loopback-only when no dashboard token is configured. Set the same token in the backend environment for non-loopback access. Never expose it through `NEXT_PUBLIC_*`.

## Checks

```bash
npx pnpm@10 run typecheck
npx pnpm@10 run lint
npx pnpm@10 run build
```

## Data boundary

- Paper account only. This project never implements live-money routing.
- No API here submits, cancels or modifies orders.
- Historical research and backtests are never displayed as realised paper performance.
- Full account IDs, OAuth tokens, fingerprints and raw agent logs are not sent to the browser.
- A broker acknowledgement is not treated as a fill.
