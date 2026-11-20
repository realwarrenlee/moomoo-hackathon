# Operations guide

**Purpose:** a runbook another developer can follow to install, verify and operate MooTrade safely. Read [`docs/integrations.md`](integrations.md) first for what has been verified against the real providers, and [`docs/strategy-and-risk.md`](strategy-and-risk.md) for the policy rules referenced below.

**Safety posture:** every command below is read-only unless explicitly stated. Under the current mandate, the only authorised order workflow is `moomoo-supervised-execute`, requiring two explicit flags, a durable owner approval for the **exact proposal/key of EVERY BUY and SELL**, and every preflight check. `TRADING_MODE=SUPERVISED_PAPER` and `ORDER_WRITES_ENABLED=false` remain unchanged; writes may be scoped only to a separately approved supervised invocation, not a scheduled autonomous run. Execution scope is SPY/SH only (risk-v3, 20 November 2026); UPRO/SPXU were removed from the universe and are rejected by default-deny symbol validation, with their historical records preserved. This is not new activation, permission or an order. SPY/SH MARKET capacity was verified read-only on 19 November (112/2,476 cash-buy shares), without establishing guaranteed order acceptance. The operator control command `moomoo-kill-switch` changes persistent kill-switch state only (never submits or cancels orders) and requires explicit confirmation. Do not paste credentials into terminals, chat messages, commits or screenshots.

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
| `TRADING_MODE` | `READ_ONLY` default; `.env` stays `SUPERVISED_PAPER`. `AUTO_PAPER` is authorised only for the time-limited activation recorded on 20 November 2026 (expires 2026-11-27T18:00Z) and only via the scheduler wrapper; legacy `paper_only` fails closed |
| `ORDER_WRITES_ENABLED` | stays `false` in `.env`; only a separately approved supervised invocation may enable its own transport |
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

## Trading modes and historical activation records

- `READ_ONLY` is the default when unset; execution refuses. Unknown values (including legacy `paper_only`) fail closed.
- **Current runtime:** `SUPERVISED_PAPER` in `.env`, with `ORDER_WRITES_ENABLED=false`. Every supervised BUY and SELL requires a durable exact-proposal/key approval, `--enable-order-writes`, exact `--confirm-client-order-key` and a fresh passing RiskGate decision. Separately, a time-limited `AUTO_PAPER` activation (recorded 20 November 2026, expiring 2026-11-27T18:00Z) authorises the scheduled autonomous executor for the pinned risk-v3 policy only; it never applies to supervised invocations.
- **Active policy:** risk-v3 only: tiered research targets of `0%` or `10%`/`25–40%`/`40%` signed-exposure magnitude, 40% signed-effective ceiling, ±5 percentage-point target tolerance, one-position RiskGate maximum (matching the strategy), 2% daily drawdown, US$5 cash buffer, quotes ≤300s and account snapshots ≤60s, 1x leverage maximum, plus the competition 40% single-security concentration cap (`R019`). Only the supervised path skips the 10% floor; it does not waive the other rules. Risk-v1 and the pre-simplification risk-v2 (20 November 2026 cutover) are retired and cannot be selected or reactivated.

**HISTORICAL pins:** the append-only 18 November risk-v1 pin (16:03Z: SPY/SH, 10% single / 30% gross / 2% drawdown, 5% position fraction, no leverage) and pre-simplification risk-v2 pin (23:58Z: SPY/UPRO/SH/SPXU, 20% minimum / 150% maximum signed-effective exposure, 3x, 2% drawdown; `order_submitted=false`) remain audit evidence. They are not current unattended authority. A risk-v3 activation pin binds only SPY/SH, 10%/40% limits and the 2% drawdown; `latest_trading_activation` returns nothing for non-risk-v3 rows. R014 is mode-aware: an exact-order approval authorises supervised orders, while only a valid, unexpired risk-v3 activation authorises autonomous orders — and it never applies on the supervised gate.

**Superseding a stale approval:** `moomoo-supersede-approval` marks an approval row superseded (append-only; the row remains as historical evidence) and records an `APPROVAL_SUPERSEDED` event. It never submits an order and requires `--confirm-supersede`:

```bash
.venv/Scripts/python -m app.cli moomoo-supersede-approval \
  --proposal-id <proposal-id> --strategy-version spy-directional \
  --reason "<why the approval is superseded>" --confirm-supersede
```

The 576-SH BUY approval (`spy-directional-2026-11-19-SH-BUY`, old 20% weak tier) was superseded on 20 November 2026 under the risk-v3 cutover; new orders need a fresh policy-bound approval for a new proposal id and client order key.

Inspecting state is read-only:

```bash
.venv/Scripts/python -m app.cli moomoo-auto-paper-status
```

Do not reactivate old pins or restore `AUTO_PAPER` after acceptance orders. Future autonomy requires separate explicit owner authorisation; this runbook does not grant it.

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

**Historical-data dry run** (pinned decision time; uses committed bar fixtures with the current v2-only rules, never reactivates retired risk-v1). Frozen old artifacts retain their original policy/results:

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
../.venv/Scripts/python -m scripts.refresh_daily_bars
../.venv/Scripts/python -m scripts.current_market_run \
  --bars ../evidence/current-market/<completed-session>/daily-bars.json \
  --window session --strategy spy-directional
```

**Historical diagnostic preflight:** `scripts.readonly_preflight.py` produced sanitised QQQ diagnostic previews without contacting an order endpoint. Those artifacts remain evidence only, not a current strategy proposal or a reason to repeat diagnostics. Use the exact research proposal in the supervised preview below.

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

## Morning AUTO_PAPER schedule — Mode A supervised decision, Mode B autonomous (time-limited)

The read-only evening decision task remains separate from execution: at 16:20 ET it refreshes completed bars to `evidence/current-market/<session>/daily-bars.json` and records the three-agent workflow in `evidence/qoder/<run-id>.json`. A completed artifact is research evidence, not owner approval.

**Mode A (supervised):** with `TRADING_MODE=SUPERVISED_PAPER`, `MooTrade Auto Paper Scheduler` invokes `backend/scripts/schedule_auto_paper.py` at 13:35Z/14:35Z inside a 09:35–10:30 ET window. The morning phase validates the pinned prior-session artifact, recomputes the deterministic risk-v3 decision on fresh broker reads and records an `AUTO_PAPER_DECISION` event. **It never submits an order**; a BUY/SELL outcome reports the exact proposal and client order key and awaits `moomoo-supervised-execute` after explicit owner approval. Writes are scoped to the executor subprocess only in `AUTO_PAPER` mode, never in this mode.

**Mode B (autonomous, active until 2026-11-27T18:00Z):** the wrapper `backend/scripts/run_auto_paper_schedule.cmd` sets `TRADING_MODE=AUTO_PAPER` with `ORDER_WRITES_ENABLED=false`; `schedule_auto_paper` scopes `ORDER_WRITES_ENABLED=true` to the in-process executor only. The durable risk-v3 activation pin (recorded 2026-11-20T02:25:30Z by explicit owner authorisation, expiring 2026-11-27T18:00:00Z — the exact close of the final shortened 27 November session, verified against the provider trading calendar) binds the account fingerprint, strategy version, SPY/SH allowlist, 10%/40% exposure limits and 2% daily drawdown. Every submission still passes the full RiskGate (R001–R019, mode-aware R014 satisfied only by the valid activation) plus per-run checks: fresh bars and account snapshot, pinned artifact verification, kill switch, no UNKNOWN submissions, fresh regular-session quote and a fresh version-bound client order key. A failed or ambiguous submission is never blindly retried; the activation cannot authorise supervised orders and expires automatically. The scheduler passes the provider-calendar-resolved prior session (`--expected-session`) so post-holiday mornings (e.g. the Friday after Thanksgiving) validate correctly. State: `data/auto_paper_schedule.json`, `data/auto-scheduler-events.jsonl`, `data/auto_paper_schedule.lock`. The design does not retry an abstained/completed session or backfill a missed execution window.

## Daily risk monitor

The read-only monitor (`backend/scripts/risk_monitor.py`) runs inside three ET windows from one Task Scheduler task with six dual-DST triggers (13:45Z/14:45Z, 16:00Z/17:00Z, 19:45Z/20:45Z): reconcile `09:45-10:30`, midday `12:00-13:00`, pre-close `15:45-16:00`. Register or re-register:

```powershell
powershell -ExecutionPolicy Bypass -File backend/scripts/register_risk_monitor_task.ps1
```

- The task runs `backend/scripts/run_risk_monitor.cmd`, which invokes `scripts.risk_monitor --scheduled` and logs to `data/risk-monitor-task.log`.
- Durable state: `data/risk_monitor_schedule.json`, `data/risk-monitor-events.jsonl` (append-only), `data/risk_monitor_schedule.lock`. Evidence reports: `evidence/risk-monitor/<session>/<window>-<utc>.json`.
- The monitor is strictly read-only: it builds its stack with `order_writes_enabled=False` and refuses to run if the environment has `ORDER_WRITES_ENABLED=true` or a trade-write token.
- Breaches are appended as `RISK_BREACH` events. The persistent kill switch engages on daily drawdown or unresolved ambiguity at pre-close; exposure, holding-duration and open-order breaches are reported only. Any resulting reduction or exit requires its own exact-proposal/key owner approval; the monitor never places it.
- For a one-time timer validation add `-ValidationDelayMinutes 2`, then remove the validation trigger afterwards.

## Running tests

```bash
.venv/Scripts/python -m pytest                     # compare observed results with docs/evidence.md
cd frontend && npx --yes pnpm@10 run test          # formatting regression tests
cd frontend && npx --yes pnpm@10 run typecheck && npx --yes pnpm@10 run lint && npx --yes pnpm@10 run build
```

Negative-path tests (oversized orders, stale quotes, kill switch, ambiguous timeouts) use the mock broker; they are not broker evidence. The authenticated REST reads are the only tests that touch the real provider.

## Inspecting decisions and audit logs

- Dashboard: `/dashboard` (overview), `/agents` (latest Qoder run), `/risk` (policy state), `/audit` (ledger timeline), `/portfolio` (broker state), `/analytics` (competition period only: paper-account day-start equity vs SPY/cash, 17 Nov to 30 Nov 2026).
- Ledger: SQLite at `data/mootrade.db`. The `events` table is append-only (SQL triggers forbid UPDATE/DELETE). Useful tables: `events`, `submissions` (idempotency), `order_approvals`, `controls` (kill switch), `equity_days` (drawdown baseline).
- Qoder run artifacts: `evidence/qoder/qoder-<run-id>.md` and `.json` (sanitised; raw session event logs are never exported).
- Preflight artifacts: `evidence/preflight/preflight-<UTC>.json`.

## Executing supervised paper trades

The provider-observed lifecycle is the historical QQQ diagnostic round trip only, not SPY/SH acceptance or strategy performance. Do not repeat diagnostics or substitute a new key to bypass idempotency. Read `docs/integrations.md` before considering an order. The prepared CLI adds `--proposal-file` to the existing preview/execute arguments; all required flags remain required and must match the file. Use the exact research `TradeProposal`, preserving its timestamps, evidence IDs and declared target rather than reconstructing a proposal from flags. Current verification results and the genuine SH preview are recorded in `docs/evidence.md`.

1. **Preview** — use values from that exact proposal, not the placeholder text below. Evaluates with writes hypothetically enabled, reports per-rule states and current/post-order signed-effective exposure, and never submits:

   ```bash
   .venv/Scripts/python -m app.cli moomoo-supervised-preview \
     --proposal-file <research-proposal.json> \
     --symbol <symbol> --action <BUY-or-SELL> --quantity <quantity> --proposal-id <proposal-id> \
     --strategy-version spy-directional \
     --thesis "<exact thesis from proposal>" \
     --invalidation "<exact invalidation from proposal>"
   ```

2. **Owner approval for EVERY BUY and SELL** — only after explicit approval of the exact proposal and key. The historical command name remains `approve-first-order`, but it is used for each supervised order, not just the first. Recording approval never submits:

   ```bash
   .venv/Scripts/python -m app.cli approve-first-order \
     --proposal-id <proposal-id> --strategy-version spy-directional
   ```

3. **Execute** — only for that approved proposal/key, with runtime still `SUPERVISED_PAPER`. Requires `--enable-order-writes`, exact `--confirm-client-order-key`, durable approval, fresh quote (≤300s), account (≤60s), provider `AFTERNOON` (09:30–16:00 ET per official Q&A), reconciliation, clean kill switch, no `UNKNOWN` submissions and every applicable risk-v3 rule. The 10% floor is skipped only in the supervised path (including its preview); the 40% signed-effective ceiling, ±5pp target tolerance and 40% competition concentration cap (`R019`) are unchanged. The key is derived from the existing strategy/proposal identity by `build_client_order_key`; do not invent a replacement key. Submits at most once, with no ambiguous-outcome retry:

   ```bash
   .venv/Scripts/python -m app.cli moomoo-supervised-execute \
     --proposal-file <research-proposal.json> \
     --symbol <symbol> --action <BUY-or-SELL> --quantity <quantity> --proposal-id <proposal-id> \
     --strategy-version spy-directional \
     --thesis "<exact thesis from proposal>" \
     --invalidation "<exact invalidation from proposal>" \
     --enable-order-writes --confirm-client-order-key <client-order-key>
   ```

   Exit codes: `2` risk did not approve; `3` outcome `UNKNOWN`.

4. **Resolve an `UNKNOWN` submission** — after an ambiguous outcome the broker must first be re-verified read-only (no matching correlation tag in Today's Orders or history); only then may the local row be resolved. Refuses without that live re-verification, without `--confirm-resolve`, or when the local status is not `UNKNOWN`; appends an `UNKNOWN_RESOLVED` audit event:

   ```bash
   .venv/Scripts/python -m app.cli moomoo-supervised-resolve-unknown \
     --client-order-key <client-order-key> --confirm-resolve
   ```

   Exit codes: `2` refused (a broker order matched, local status not `UNKNOWN`, or confirmation missing). Resolving clears the `R009` block on new submissions. Re-submitting the same proposal is blocked by `R011`; a retry requires a new proposal id with its own recorded owner approval for the identical order.

5. **Reconcile** — read-only; reports the local order and latest reconciliation event:

   ```bash
   .venv/Scripts/python -m app.cli moomoo-supervised-reconcile --client-order-key <client-order-key>
   ```

**Approval boundaries:** owner approval is durable and bound to one exact proposal/key; **the 30-second TTL belongs to the risk decision, not the owner approval**. Re-evaluate expired risk decisions or changed account snapshots before submission. A previous fill, approval or activation never approves the next BUY/SELL. The dashboard, agents and scheduler cannot grant owner approval. There is no current unattended-trading scope; future autonomy requires separate explicit authorisation.

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
- **A second `mootrade.db` appears under `backend/data/`:** a pre-19-Nov run resolved the relative `DATABASE_URL` against the working directory. Since 19 Nov `ledger_path_from_env` anchors relative paths at the project root, so all commands and scheduled tasks use `data/mootrade.db` regardless of cwd. The 18 Nov stray file is preserved as `backend/data/mootrade.db.split-backup-20261119` with its rows merged into the canonical ledger (see the `LEDGER_REPAIR` audit event).
