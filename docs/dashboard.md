# Dashboard — implemented read-only surface

**Status:** implemented 17 November 2026. The UI is adapted from the MIT-licensed [Shadcn Fintech](https://github.com/abderrahimghazali/shadcn-fintech) template (commit `a905058`). Banking routes, components, mock data and decorative 3D assets were removed. Attribution is preserved in `frontend/LICENSE` and `frontend/ATTRIBUTION.md`.

**Safety boundary:** the dashboard has no order-capable route. It cannot enable writes, approve an order, cancel an order, liquidate a position, change a risk limit or edit Qoder evidence. `ORDER_WRITES_ENABLED=true` causes the API to refuse startup. On 18 November 2026 the owner removed the header `PAPER` badge and “Competition account · read-only” caption; the persistent sidebar `Writes DISABLED` status remains the in-shell paper-mode indicator.

## Pages

| Route | Purpose | Sources |
|---|---|---|
| `/dashboard` | Overview: account, market tape, latest Qoder run, controls, recent ledger events | Broker read, Qoder artifact, local controls, ledger |
| `/agents` | Qoder sessions, role summaries, decision record, current-market evidence timestamps and candidates | Sanitised Qoder evidence only |
| `/portfolio` | Positions, open orders, today's orders, history and reconciliation | Broker read only |
| `/risk` | Locked state, limits, current inputs, rule catalogue, recorded real preflight | Local controls, broker read, recorded preflight |
| `/analytics` | Historical normalised curves, metrics and limitations | Historical research evidence only |
| `/audit` | Append-only ledger timeline with filters | SQLite ledger |

## Backend API

FastAPI application: `backend/app/dashboard/api.py`.

| Endpoint | Read model |
|---|---|
| `GET /api/v1/health` | Auth presence, masked-scope state, writes disabled, ledger availability |
| `GET /api/v1/overview` | Account, quote observations, safety, latest Qoder run, warnings |
| `GET /api/v1/portfolio` | Account snapshot, positions, open orders, today/history orders |
| `GET /api/v1/risk` | Limits, lock reasons, current inputs, recorded real preflight |
| `GET /api/v1/agents` | Latest sanitised Qoder dry-run artifact |
| `GET /api/v1/analytics` | Historical datasets, server-normalised base-100 curves, metrics |
| `GET /api/v1/audit` | Reverse-chronological ledger summaries |

Only `GET`, `HEAD` and `OPTIONS` reach the API. Other methods return `405` before a route is resolved. Non-loopback binding requires `MOOTRADE_DASHBOARD_TOKEN`; otherwise the middleware only accepts loopback clients. The Next.js server route (`frontend/src/app/api/mootrade/[...path]/route.ts`) has its own six-path allowlist and attaches the optional token server-side, so no token reaches browser code.

## Provenance labels

Every displayed section carries one of:

- `LIVE_BROKER_READ` — a current read-only Moomoo REST response, displayed as “Broker-verified PAPER”.
- `HISTORICAL_BACKTEST` — frozen research evidence, never paper-account performance.
- `HISTORICAL_QODER_RUN` — a completed Qoder dry run, not current market data.
- `CURRENT_MARKET_READ_ONLY` — a completed Qoder run over independently validated current read-only broker/session evidence. Still not an order, fill or owner approval.
- `RECORDED_REAL_PREFLIGHT` — a real execution-time preflight that submitted nothing.
- `LOCAL_LEDGER` — append-only SQLite events.
- `LOCAL_CONTROLS` — local knobs and persistent safety state.

There is no `MOCK` data in the dashboard. The deliberate absence is visible as an empty state rather than invented values.

## Time and number formatting

- Candidate 5-day returns arrive as fractions (`-0.0338749`) and render as percentage points (`-3.39%`). Values already scaled by the backend use a separate formatter so they are not multiplied twice.
- API timestamps are UTC and render with an explicit `UTC` suffix. US market times render in `America/New_York`; provider session states such as `AFTERNOON` display as “Regular session”.
- “Page fetched” shows when the browser last called the API and is explicitly not the broker data time. Quote rows show the broker observation time and its age.
- Quote age is computed from the broker timestamp; sub-5-second provider clock skew displays as `0s`, and stale quotes show their age separately from future-date errors.

## Required states

| State | Behaviour |
|---|---|
| Loading | Route skeletons / in-page skeleton blocks |
| Broker unavailable | `UNAVAILABLE` state and safe reason; no substituted account values |
| Quote stale | Amber tile, explicit age and “outside 300s execution window” |
| Session closed | Shown as a gate input; never treated as executable |
| Empty positions/orders | Explicit observed-empty panel sourced from broker response |
| API disconnected | Error panel with retry; last successful data retained on background failure |
| Reconciliation attention | Amber status; backend still reports execution locked |
| Historical analytics | Persistent `HISTORICAL · NOT LIVE` label and limitation list |
| No Qoder evidence | Empty state; no synthetic agent summary |

## Display quote separation

`MoomooQuoteFeed.observe_quote()` returns a `QuoteObservation` for display. It allows stale observations so the UI can show age honestly, but it never returns an executable `Quote`. The RiskGate still receives only strict `get_quote()` results: ≤300 seconds, positive price, `NORMAL`, not suspended and regular session only.

For `CURRENT_MARKET_READ_ONLY` runs, `/agents` shows the sanitized collection time, account snapshot time and each quote's broker timestamp and market state. The dashboard refresh time (`UI refreshed`) is separate from these broker timestamps. The backend exposes only the sanitized collection summary; raw account identifiers and the account fingerprint are excluded.

## Account and secret handling

- Browser receives only the masked account id (`****0101` style), never the full id or fingerprint.
- OAuth tokens remain in DPAPI storage outside the repository and are never passed to Next.js.
- Agent text is truncated to 2,500 characters per role and clearly marked untrusted.
- Raw Qoder logs, prompts and raw broker payloads are not exposed.

## Visual system reused from the template

Sidebar shell, inset content surface, breadcrumb, command palette, theme toggle, cards, badges, table styling, typography and Tailwind/shadcn configuration. MooTrade added its own provenance primitives, six pages, typed API client, polling hook and read-only proxy. Historical curves use Recharts.

## Run

See `frontend/README.md`. The backend API is started with:

```bash
cd backend
../.venv/Scripts/python.exe -m uvicorn app.dashboard.api:app --host 127.0.0.1 --port 8000
```

No order endpoint is started, and `ORDER_WRITES_ENABLED` must remain `false`.
