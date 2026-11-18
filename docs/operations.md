# Operations guide

**Purpose:** a runbook another developer can follow to install, verify and operate MooTrade safely. Read [`docs/integrations.md`](integrations.md) first for what has been verified against the real providers, and [`docs/strategy-and-risk.md`](strategy-and-risk.md) for the policy rules referenced below.

**Safety posture:** every command below is read-only unless explicitly stated. The only write-capable command is `moomoo-supervised-execute`, which additionally requires two explicit flags, a durable owner approval and every preflight check. `ORDER_WRITES_ENABLED` must remain `false` except inside that single supervised invocation. Do not paste credentials into terminals, chat messages, commits or screenshots.

## Prerequisites

- Windows 10/11 (the OAuth token stores use DPAPI; non-Windows hosts cannot decrypt them).
- Python 3.11+ on PATH (`python -m venv`).
- Node.js 20+ for the dashboard; pnpm is used via `npx --yes pnpm@10`.
- A Moomoo account eligible for the competition, and a Qoder workspace with Cloud Agent access. The owner must perform the OAuth browser consents personally.
- The competition account lock variables in `.env` (see below).

## Installation

From the repository root on Windows:

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
```

On macOS/Linux use `.venv/bin/python`. The frontend installs separately:

```bash
cd frontend
npx --yes pnpm@10 install --frozen-lockfile
```

## Environment configuration

Copy `.env.example` to `.env` and set:

| Variable | Purpose |
|---|---|
| `APP_ENV` | `development` or `demo` |
| `TRADING_MODE` | documented convention, keep `paper_only`; not itself enforced — the enforced guard is `ORDER_WRITES_ENABLED` |
| `ORDER_WRITES_ENABLED` | must stay `false` |
| `DATABASE_URL` | SQLite path, default `sqlite:///./data/mootrade.db` |
| `COMPETITION_ACCOUNT_MASKED_ID` | masked identity, e.g. `****0101` |
| `COMPETITION_ACCOUNT_FINGERPRINT` | SHA-256 fingerprint from `fingerprint-account` |
| `COMPETITION_ACCOUNT_MARKET_ID` | `100` for the US paper account |
| `MOOTRADE_DASHBOARD_TOKEN` | optional bearer token for the dashboard API; leave empty for loopback-only |
| `MOOTRADE_API_URL` | backend URL for the Next.js proxy, default `http://127.0.0.1:8000` |
| `MOOTRADE_OAUTH_STORE` / `MOOTRADE_EXECUTION_OAUTH_STORE` | optional overrides for the two DPAPI token files |

The account lock fails closed if the masked id or fingerprint is missing; the market id is a consistency check, never the selector. `.env` is git-ignored.

## Credential handling

- Browser consents are completed only by the owner. `moomoo-login` requests read permissions; do not grant `trade:write` there. `moomoo-execution-login` is a separate client that does request `trade:write`, prints a warning first, and stores its own token file.
- Tokens live in DPAPI-encrypted files outside the repository: `%LOCALAPPDATA%\MooTrade\moomoo-oauth.bin` (read) and `moomoo-execution-oauth.bin` (execution). Plaintext token files are rejected on Windows.
- The browser dashboard never receives tokens, the full account id or the fingerprint.
- Treat the execution `trade:write` consent as potentially account-wide; account-exclusive write scope is unverified. See `docs/integrations.md`.

## Read-only account verification

All from the repository root. Replace the fingerprint step's hidden prompt input with the full Moomoo acc_id.

```bash
.venv/Scripts/python -m app.cli fingerprint-account      # prints SHA-256 only; never echoes the id
.venv/Scripts/python -m app.cli moomoo-login             # owner browser consent, read scopes only
.venv/Scripts/python -m app.cli moomoo-auth-status       # token presence and granted scopes
.venv/Scripts/python -m app.cli moomoo-read              # sanitized PAPER account/cash/positions/orders
```

`moomoo-read` must report the exact competition account (`****0101`, `account_type=2`, `market_id=100`), `reconciled=true` and `order_endpoint_contacted=false`. If the identity does not match, stop; the account lock rejects it at `R001`.

The separate execution client (still no order submission):

```bash
.venv/Scripts/python -m app.cli moomoo-execution-login   # owner consent; prints exclusivity warning
.venv/Scripts/python -m app.cli moomoo-execution-status
.venv/Scripts/python -m app.cli moomoo-execution-check   # read-only identity check, no order endpoint
```

## Local startup

Terminal 1 — read-only API (refuses to start if `ORDER_WRITES_ENABLED=true`):

```bash
cd backend && ../.venv/Scripts/python -m uvicorn app.dashboard.api:app --host 127.0.0.1 --port 8000
```

Terminal 2 — dashboard:

```bash
cd frontend && npx --yes pnpm@10 run dev
```

Open `http://localhost:3000`. API docs at `http://127.0.0.1:8000/api/docs`. The API accepts only GET/HEAD/OPTIONS on `/api/`; everything else returns 405.

## Running the agent pipeline

The pipeline is read-only and has no order path. Commands run from `backend/`.

**Historical dry run** (pinned decision time, reproducible; uses committed bar fixtures):

```bash
../.venv/Scripts/python -m scripts.qoder_readonly_run \
  --workspace-id "$QODER_WORKSPACE_ID" \
  --environment-id "$QODER_ENVIRONMENT_ID" \
  --coordinator-agent-id "$QODER_COORDINATOR_AGENT_ID" \
  --researcher-agent-id "$QODER_RESEARCHER_AGENT_ID" \
  --auditor-agent-id "$QODER_AUDITOR_AGENT_ID" \
  --decision-time 2026-10-13T21:00:00Z
```

**Current-market run** (fresh read-only Moomoo bars, quotes and account state, then the same three-agent review):

```bash
../.venv/Scripts/python -m scripts.refresh_daily_bars.py   # refreshes evidence/current-market/<session>/daily-bars.json
../.venv/Scripts/python -m scripts.current_market_run.py
```

**Read-only preflight** (records a sanitised preflight artifact with a diagnostic QQQ preview; never contacts an order endpoint):

```bash
../.venv/Scripts/python -m scripts.readonly_preflight.py
```

Agent ids for the current-market config live in `backend/config/current_market.json`; never commit Qoder access tokens there.

## Local scheduler

The recurring read-only workflow is Windows Task Scheduler task `MooTrade Read-Only Scheduler`, with two daily UTC triggers (20:20Z and 21:20Z) covering both US Eastern DST offsets. Register or re-register:

```powershell
powershell -ExecutionPolicy Bypass -File backend/scripts/register_readonly_task.ps1
```

- The task runs `backend/scripts/run_readonly_schedule.cmd`, which invokes `scripts.schedule_readonly --scheduled` and logs to `data/scheduler-task.log`.
- Durable state: `data/readonly_schedule.json` (run history), `data/scheduler-events.jsonl` (append-only events), `data/readonly_schedule.lock` (process lock).
- Every state record reports `order_writes_enabled=false`; the scheduler imports no order adapter.
- The task requires the interactive user session (DPAPI) and cannot wake a machine in Modern Standby; `WakeToRun=true` is set for ordinary standby.

For one-time timer validation add `-ValidationDelayMinutes 2`, then remove the validation trigger afterwards (see `docs/integrations.md`).

## Running tests

```bash
.venv/Scripts/python -m pytest                     # backend: 310 tests, 18 November 2026
cd frontend && npx --yes pnpm@10 run test          # formatting regression tests
cd frontend && npx --yes pnpm@10 run typecheck && npx --yes pnpm@10 run lint && npx --yes pnpm@10 run build
```

Negative-path tests (oversized orders, stale quotes, kill switch, ambiguous timeouts) use the mock broker; they are not broker evidence. The authenticated REST reads are the only tests that touch the real provider.

## Inspecting decisions and audit logs

- Dashboard: `/dashboard` (overview), `/agents` (latest Qoder run), `/risk` (policy state), `/audit` (ledger timeline), `/portfolio` (broker state), `/analytics` (historical curves only).
- Ledger: SQLite at `data/mootrade.db`. The `events` table is append-only (SQL triggers forbid UPDATE/DELETE). Useful tables: `events`, `submissions` (idempotency), `order_approvals`, `controls` (kill switch), `equity_days` (drawdown baseline).
- Qoder run artifacts: `evidence/qoder/qoder-<run-id>.md` and `.json` (sanitised; raw session event logs are never exported).
- Preflight artifacts: `evidence/preflight/preflight-<UTC>.json`.

## Executing supervised paper trades

The order path is a prototype and remains provider-unproven. Read `docs/integrations.md` (execution section) before considering it. Sequence:

1. **Preview** — evaluates the real gate with writes hypothetically enabled; prints the payload and risk result; never submits:

   ```bash
   .venv/Scripts/python -m app.cli moomoo-supervised-preview \
     --symbol QQQ --action BUY --quantity 1 --proposal-id <proposal-id> \
     --strategy-version spy-directional \
     --thesis "Diagnostic supervised-preview thesis" \
     --invalidation "Diagnostic invalidation"
   ```

2. **Owner approval** — records a durable approval bound to the proposal and its client order key; never submits:

   ```bash
   .venv/Scripts/python -m app.cli approve-first-order \
     --proposal-id <proposal-id> --strategy-version spy-directional
   ```

3. **Execute** — the only write-capable command. Requires both `--enable-order-writes` and the exact `--confirm-client-order-key`, plus a durable approval, a fresh regular-session quote (≤300 s, `AFTERNOON`), a reconciled competition account, a clean kill switch, no `UNKNOWN` submissions and every `RiskGate` rule. Submits at most once and never retries an ambiguous outcome. The client order key is `mootrade-` plus the SHA-256 of `<strategy-version>:<proposal-id>` (`build_client_order_key` in `backend/app/service.py`); compute it with:

   ```bash
   .venv/Scripts/python -c "import hashlib; print('mootrade-' + hashlib.sha256('spy-directional:<proposal-id>'.encode()).hexdigest())"
   ```

   ```bash
   .venv/Scripts/python -m app.cli moomoo-supervised-execute \
     --symbol QQQ --action BUY --quantity 1 --proposal-id <proposal-id> \
     --strategy-version spy-directional \
     --thesis "Diagnostic supervised-order thesis" \
     --invalidation "Diagnostic invalidation" \
     --enable-order-writes --confirm-client-order-key <client-order-key>
   ```

   Exit codes: `2` risk did not approve; `3` outcome `UNKNOWN`.

4. **Reconcile** — read-only; reports the local order plus the latest reconciliation event:

   ```bash
   .venv/Scripts/python -m app.cli moomoo-supervised-reconcile --client-order-key <client-order-key>
   ```

**Approval boundaries:** approval is durable, bound to one proposal and key, and expires with the risk decision (30-second policy TTL; a changed account snapshot requires re-evaluation). Nothing in the dashboard, the agents or the scheduler can approve or submit. There is no unattended-trading scope; a later autonomous mode requires separate explicit owner authorisation.

## Stopping operations safely

- The default state is already the safe state: `ORDER_WRITES_ENABLED=false`, and the dashboard API refuses to start if it is ever `true`.
- The kill switch is persisted in the ledger `controls` table and is checked on every submission (`R010`). It is exercised through the ledger API in tests (`set_kill_switch(True)`); there is currently no operator CLI command to toggle it. If a stop is needed, keep `ORDER_WRITES_ENABLED=false` (which also rejects at `R010`) and do not run the supervised execute command.
- Stopping the scheduler does not affect account safety: it is read-only. To stop it, disable the `MooTrade Read-Only Scheduler` task in Task Scheduler.
- A kill switch blocks new orders; it does not liquidate holdings. Cancelling open orders would require a separate, explicitly logged and authorised action, which is not implemented.

## Failure handling

| Situation | Required behaviour | Where enforced |
|---|---|---|
| Failed API request / broker disconnect | Fail closed; no order, no retry of a write; read path can be retried manually | REST allowlist, transport, `R007`/`R009` |
| Stale quote (>300 s or outside regular session) | Reject `R007`/`R012`; dashboard shows age honestly | `MoomooQuoteFeed`, `RiskGate` |
| `UNKNOWN` order (timeout/ambiguous response) | Persist `UNKNOWN`; block new submissions (`R009`); reconcile read-only from today's orders, history and positions; never blind-retry | `TradingService`, `moomoo_orders.py` |
| Partial fill | Ledger records `PARTIALLY_FILLED`; remainder stays pending; fills accepted only from broker evidence | state machine, reconciler |
| Reconciliation mismatch | Halt new submissions; append `RECONCILIATION_MISMATCH`; investigate manually | `TradingService.reconcile` |
| Missed scheduler run | Next trigger catches up the missed session (`catch_up=true`); a stale `RUNNING` record becomes `ABANDONED` only after the lock is reacquired | `schedule_readonly.py` |
| Interrupted scheduler process | Persists `INTERRUPTED` before exit; next run recovers | `schedule_readonly.py` |
| Clock skew >5 s | Fails closed as future-dated | `RiskGate`, quote feed |

## Common troubleshooting

- **Dashboard shows no account data:** check the backend log; the dashboard shows an explicit `UNAVAILABLE` state rather than invented values. Run `moomoo-read` to confirm the REST token still works (access tokens live 7,200 s; refresh is unit-tested, a real provider refresh has not yet been observed).
- **`moomoo-read` reports a different account:** stop. Re-check `.env` lock variables; do not relax them.
- **Agent run fails:** the runner persists `AGENT_ERROR` and never resubmits a turn; rerun the script manually and inspect the artifact in `evidence/qoder/`.
- **Order preview rejected:** expected outside the regular session or without approval. `moomoo-preview-order` / `moomoo-supervised-preview` print the exact rule ids (`R0xx`) and reasons; `submission_performed` is always `false`.
- **`ORDER_WRITES_ENABLED=true` in the environment:** the dashboard API and every read-only script refuse to start. Set it back to `false`.
