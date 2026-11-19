# Operations guide

**Purpose:** a runbook another developer can follow to install, verify and operate MooTrade safely. Read [`docs/integrations.md`](integrations.md) first for what has been verified against the real providers, and [`docs/strategy-and-risk.md`](strategy-and-risk.md) for the policy rules referenced below.

**Safety posture:** every command below is read-only unless explicitly stated. The only write-capable order command is `moomoo-supervised-execute`, which additionally requires two explicit flags, a durable owner approval and every preflight check. The operator control command `moomoo-kill-switch` changes the persistent kill-switch state only (never submits or cancels orders) and requires explicit confirmation flags. `ORDER_WRITES_ENABLED` must remain `false` except inside a single supervised or scheduled execution invocation. Do not paste credentials into terminals, chat messages, commits or screenshots.

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
| `TRADING_MODE` | `READ_ONLY` (default), `SUPERVISED_PAPER` or `AUTO_PAPER`; enforced by the supervised executor and the autonomous pipeline. The legacy `paper_only` value fails closed and must be replaced |
| `ORDER_WRITES_ENABLED` | stays `false` in `.env` in every mode; the auto-paper scheduler scopes it `true` in-process for the executor only (see below) |
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

## Trading modes and AUTO_PAPER activation

`TRADING_MODE` is read from the environment by every relevant command:

- `READ_ONLY` (default when unset): all read paths work; `moomoo-supervised-execute` refuses with exit 2. Any unknown value (including the legacy `paper_only` convention) also fails closed.
- `SUPERVISED_PAPER`: the operator-supervised execution workflow behaves as before — per-proposal durable approval, `--enable-order-writes` and exact `--confirm-client-order-key`.
- `AUTO_PAPER`: additionally requires a durable activation pin recorded by `moomoo-activate-auto-paper`. The pin binds the exact competition-account SHA-256 fingerprint, strategy `spy-directional`, the allowed symbols and a versioned risk policy. The **recorded pin is `risk-v2`** (18 November 2026 23:58Z: SPY/UPRO/SH/SPXU, 20% minimum / 150% maximum signed effective exposure, 3x leverage, 2% drawdown), owner-approved at the cutover. The earlier `risk-v1` pin (SPY/SH, 10% single / 30% gross / 2% drawdown, 5% position fraction, no leverage; 18 November 2026 16:03Z) is retained append-only. The record is append-only in the ledger.

```bash
.venv/Scripts/python -m app.cli moomoo-auto-paper-status   # mode, write flag, kill switch, activation pin
.venv/Scripts/python -m app.cli moomoo-activate-auto-paper --confirm-auto-paper
```

Activation records a pin only; it never submits an order. It refuses unless `TRADING_MODE=AUTO_PAPER` and `ORDER_WRITES_ENABLED=true` are already set (a temporary one-time condition), and it stores the pin for the configured competition-account fingerprint. The pin is the durable write-authority record. Autonomous submission additionally requires, at every run: `TRADING_MODE=AUTO_PAPER` from `.env`, `ORDER_WRITES_ENABLED=true` **scoped in-process by the auto-paper scheduler for the executor only** (`.env` itself keeps it `false` so the read-only scheduler, risk monitor and dashboard API keep working), a matching activation pin, an unengaged kill switch and a fresh RiskGate decision. To stop autonomous trading: set `TRADING_MODE=READ_ONLY` in `.env`, or engage the persistent kill switch for an immediate stop of new submissions.

**Current state:** the owner approved the risk-v2 cutover on 18 November 2026 and the risk-v2 activation pin was recorded at 23:58Z (`order_submitted=false`). During the acceptance phase `.env` holds `TRADING_MODE=SUPERVISED_PAPER` and `ORDER_WRITES_ENABLED=false`, so no autonomous submission can occur. The remaining cutover steps are: (1) one supervised UPRO acceptance order and one supervised SPXU acceptance order during the next regular session, each behind the owner's explicit go-ahead and broker reconciliation; (2) restore `TRADING_MODE=AUTO_PAPER` in `.env`, leaving `ORDER_WRITES_ENABLED=false` (the scheduler scopes writes true in-process for the executor). From then on autonomous risk-v2 trading continues without individual order approvals.

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

## Autonomous AUTO_PAPER schedule

The autonomous trading loop reuses the read-only scheduler for its evening decision phase and adds a separate execution-phase task. AUTO_PAPER was activated on 18 November 2026 (16:03Z); before that every execution attempt recorded an abstention.

**Decision phase (read-only, existing task `MooTrade Read-Only Scheduler`):** at 16:20 ET it refreshes completed daily bars to `evidence/current-market/<session>/daily-bars.json` and runs the three-agent Qoder workflow into `evidence/qoder/<run-id>.json`. This is the pinned decision artifact the execution phase consumes.

**Execution phase (new task `MooTrade Auto Paper Scheduler`):** triggers at 13:35Z and 14:35Z (09:35 ET in either US DST offset); `backend/scripts/schedule_auto_paper.py` runs `scripts.auto_paper_run` only while the wall clock is inside 09:35-10:30 ET. It re-reads the prior session's bars and decision artifact, recomputes the deterministic signal and holdings comparison, and auto-submits only when `TRADING_MODE=AUTO_PAPER`, the activation pin matches, the kill switch is clean, no `UNKNOWN` submission exists and a fresh execution-time RiskGate approves. `ORDER_WRITES_ENABLED` is set to `true` only inside that scheduled invocation and restored afterwards; the dashboard and all read paths never see it enabled.

Register the task:

```powershell
powershell -ExecutionPolicy Bypass -File backend/scripts/register_auto_paper_task.ps1
```

- Durable state: `data/auto_paper_schedule.json` (per-session history), `data/auto-scheduler-events.jsonl` (append-only events), `data/auto_paper_schedule.lock`.
- A session is attempted once: an abstained or completed run is never retried later the same day, and missed windows are not backfilled (fail closed; the next session re-evaluates).
- After a mid-week market holiday the prior weekday may not be the last bar session; the executor then abstains for that morning instead of trading on stale data.
- Disabling the read-only scheduler (or its failure) also stops autonomous trading: the execution phase abstains when the pinned decision artifact is missing.
- The task runs in the interactive user session (DPAPI) and cannot wake a machine in Modern Standby; `WakeToRun=true` is set for ordinary standby. If the machine sleeps through 09:35-10:30 ET, no trade occurs that day.
- Stop autonomous trading: set `TRADING_MODE=READ_ONLY` and `ORDER_WRITES_ENABLED=false` in `.env`, engage the kill switch, or disable the `MooTrade Auto Paper Scheduler` task.

## Daily risk monitor

The read-only monitor (`backend/scripts/risk_monitor.py`) runs inside three ET windows from one Task Scheduler task with six dual-DST triggers (13:45Z/14:45Z, 16:00Z/17:00Z, 19:45Z/20:45Z): reconcile `09:45-10:30`, midday `12:00-13:00`, pre-close `15:45-16:00`. Register or re-register:

```powershell
powershell -ExecutionPolicy Bypass -File backend/scripts/register_risk_monitor_task.ps1
```

- The task runs `backend/scripts/run_risk_monitor.cmd`, which invokes `scripts.risk_monitor --scheduled` and logs to `data/risk-monitor-task.log`.
- Durable state: `data/risk_monitor_schedule.json`, `data/risk-monitor-events.jsonl` (append-only), `data/risk_monitor_schedule.lock`. Evidence reports: `evidence/risk-monitor/<session>/<window>-<utc>.json`.
- The monitor is strictly read-only: it builds its stack with `order_writes_enabled=False` and refuses to run if the environment has `ORDER_WRITES_ENABLED=true` or a trade-write token.
- Breaches are appended as `RISK_BREACH` events. The persistent kill switch engages only on a daily-drawdown breach or ambiguous submissions still unresolved at pre-close; exposure, holding-duration and open-order breaches are reported only so the deterministic reduction rules can exit positions at the next execution window.
- For a one-time timer validation add `-ValidationDelayMinutes 2`, then remove the validation trigger afterwards.

## Running tests

```bash
.venv/Scripts/python -m pytest                     # backend: 400 tests, 19 November 2026
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
- The kill switch is persisted in the ledger `controls` table and is checked on every submission (`R010`). The operator toggles it with `moomoo-kill-switch`, which requires explicit confirmation flags and records audit events:

  ```bash
  .venv/Scripts/python -m app.cli moomoo-kill-switch                     # report current state
  .venv/Scripts/python -m app.cli moomoo-kill-switch --engage --confirm-engage
  .venv/Scripts/python -m app.cli moomoo-kill-switch --release --confirm-release
  ```

  Without the matching confirmation flag the command refuses with exit 2 and changes nothing. The scheduled risk monitor also engages the switch automatically on a daily-drawdown breach or pre-close-unresolved ambiguous submissions.
- Stopping the schedulers does not affect account safety: the read-only scheduler and the risk monitor are read-only. To stop them, disable the `MooTrade Read-Only Scheduler` and `MooTrade Risk Monitor` tasks in Task Scheduler; to stop autonomous trading, disable `MooTrade Auto Paper Scheduler` as well.
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
