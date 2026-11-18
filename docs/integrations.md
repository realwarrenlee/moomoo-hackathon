# Integrations and owner setup

**Purpose:** prevent development from assuming that an ordinary Moomoo paper account or public MCP is equivalent to the **competition-issued account**.

## Verified competition facts (17 November 2026)

- Masked account identity: `****0101` (full id intentionally withheld).
- Starting equity: `100,000 USD`.
- Starting positions: none.
- Verification source: owner confirmation plus direct read-only Moomoo MCP responses locally and from a vault-attached Qoder Cloud Agent v4 session (`sess_00vr5lar7i5mo93aq1j5`).
- Moomoo MCP account list returned eight simulated accounts. Exactly one is titled `Moomoo x Qoder AI Paper Trading Agent Challenge`: masked id `****0101`, `market_id=100`, `account_type=2`. The other seven are US/HK/SG/JP/futures/KR paper accounts.
- `sim_trade_cash_info` for `****0101`: `balance=100000`, `hold=0`, `total_asset=100000`, `mv=0`, `long_mv=0`, `short_mv=0`, `max_power_long=200000`. The 200,000 figure is margin buying power and is deliberately ignored.
- `sim_trade_position_list` with `market=100`: empty.
- `sim_trade_history_order_list` with `market=100`: `orders=[]`, `pagination.has_more=false`, `pagination.next_key="0"`.
- `quote_stock_quote` for `US.QQQ`: `last_price=661.75`, `data_time=1794862800312` (`2026-11-16T21:00:00.312Z`), `data_date=2026-11-16`. `quote_market_state` returned `AFTER_HOURS_END`, so the quote was stale and outside the regular session at observation time.
- The fingerprint and masked id are configured locally in `.env`; full ids are not written to this repository or the adapter snapshots.
- The non-empty order-history field shape is not yet observed. The adapter validates the documented order fields and fails closed on an unrecognized status.

## Direct REST OAuth and read-only status (17 November 2026)

Moomoo's documented OpenAPI exposes OAuth 2.1 + PKCE and simulated-trade read endpoints. A separate local client was registered with requested scope `quote:read trade:read`. The token record is stored only in a DPAPI-encrypted file outside the repository: `%LOCALAPPDATA%\MooTrade\moomoo-oauth.bin` by default, or the path in `MOOTRADE_OAUTH_STORE`. Token values are never printed or committed.

Observed authorization behaviour:

- Sim-account consent returned `quote:read` plus an account binding `accid:<redacted>`, not a literal `trade:read` grant. The login validator accepts `quote:read` plus either `trade:read` or an `accid:` binding, and rejects any `trade:write` grant.
- Despite the missing literal `trade:read`, the same token successfully called `GET /api/v1.0/sim-trade/accounts`, cash, positions, open orders and paginated history. This provider/sim-account quirk is recorded; the REST client remains read-only, using GET for account data and two allowlisted POSTs for quotes/market state.
- Access-token lifetime is 7,200 seconds. Refresh is unit-tested; a real provider refresh has not yet been observed.

Authenticated read result from the product CLI (`moomoo-read`):

- `account_type=2`, `market_id=100`, title `Moomoo x Qoder AI Paper Trading Agent Challenge`, masked id `****0101`; the configured account fingerprint matched.
- Equity, cash and buying power all `100000`; no positions; no open orders; empty order history; `reconciled=true`, `unknown_orders=0`.
- Observation time `2026-11-17T12:44:21Z`. For all observable fields this is the same account as the earlier cloud MCP verification.
- No order endpoint was contacted. `ORDER_WRITES_ENABLED` remained false.

## What the owner provides

- [ ] Sign up to Qoder using the email from the approved Luma event registration.
- [ ] Confirm competition Pro plan/credits and access to the required Cloud Agent features.
- [ ] Sign into Moomoo and complete any required onboarding.
- [x] Confirm the **dedicated competition paper account** exists and holds the stated starting balance (owner-verified `****0101`, 100,000 USD, no positions).
- [ ] Obtain organisers' actual Moomoo MCP instructions, available tools/scopes and allowed order types.
- [x] Authorise **read-only** Moomoo access. Local MCP calls and cloud MCP reads were verified 17 November; the separate local REST OAuth client was verified against the same competition account with read-only consent. No order scope was added.
- [ ] Create private GitHub repository `mootrade` (or another chosen name).
- [ ] Keep Qoder access tokens, OAuth credentials and account identifiers in your own secure environment; never paste them into agent prompts, chats, commits or screenshots.
- [ ] Review the organisers' rules on OSS reuse, trade restrictions and submission evidence.

## What to verify technically (do not assume)

| Question | How to verify | Safe fallback |
|---|---|---|
| Can Qoder cloud runs access the approved MCP connector? | Real read-only tool call from cloud run, with logged tool name/response shape | **Verified 17 Nov:** vault-attached v4 session registered the read tools and returned account/cash/positions/orders. Without the vault, MCP initialization returned HTTP 401. |
| Is the MCP connection to the competition account? | Compare non-secret account metadata and balance with official competition portal | Do not enable order writes |
| What are the exact tool names, parameters and response types? | Discover from the authorised MCP tool registry/docs | Implement adapter interface with mock provider |
| Does the provider support client order IDs? | Inspect official tool spec and sandbox call behavior | Local durable de-duplication + reconciliation before retries |
| What orders and instruments are eligible? | Check handbook and official competition tools | Use read-only SPY/QQQ/IWM analysis pending eligibility check |
| Are scheduling and reusable skills available in this Qoder account? | Confirm in account and one actual cloud run | Use only documented accessible features; explain restrictions |
| Can orders be cancelled through the paper MCP? | Check documented tool and run a controlled test if permitted | Kill switch blocks new orders; document that cancellations are unavailable |
| Are quotes delayed and which timestamps are available? | Inspect metadata on returned quotes | Mark data stale/unknown and abstain |

## Integration sequence

### Phase A — read-only smoke tests

1. Connect with the organisers' approved Qoder/Moomoo flow.
2. Retrieve one timestamped quote.
3. Retrieve cash, buying power, current positions and open orders for the competition paper account.
4. Record a redacted JSON shape and the tool's actual name/version in an integration notes file.
5. Deliberately test missing permission/token expiry with mock responses.

**Exit (met):** the earlier vault-attached MCP read was verified, and the local Python REST client now independently reads the same competition account with DPAPI-stored OAuth, account fingerprint, timestamp and reconciliation checks. Keep writes disabled; the REST adapter exposes GET account paths plus two POST quote reads and explicitly rejects order submission.

### Phase B — supervised paper order

1. Owner explicitly approves enabling paper writes for a verified account.
2. Run local tests of position, drawdown, stale-data and kill-switch checks.
3. Record strategy version and an order's unique idempotency key.
4. Submit a small, permissible paper order with valid market/session checks.
5. Capture acknowledgement, then query status until terminal or unknown; reconcile broker positions/fills.

**Exit:** traceable *actual* order and account-state evidence, or a documented blocker; simulated results must remain labelled `MOCK`.

### Phase C — scheduled autonomy

The read-only local schedule is implemented; it has no order authority and never approves an order. Any order-capable autonomy remains gated on stable reconciliation, repeatable preflight checks, a persisted kill switch and a bounded retry policy. No automatic retry of unknown submission outcomes.

## Environment variables (internal names, not official Qoder/Moomoo schemas)

Use `.env.example` as a starting guide, not a claim that the providers expect those exact fields. Configure provider-issued credentials using the supported secret manager or OAuth connection.

- `APP_ENV` = `development` / `demo`.
- `TRADING_MODE` is now enforced: `READ_ONLY` (default), `SUPERVISED_PAPER` or `AUTO_PAPER`. The earlier `paper_only` value was a documented convention only; it now fails closed and must be replaced in `.env`. `ORDER_WRITES_ENABLED` remains the write guard (the dashboard API and read-only scripts refuse to start when it is `true`).
- `ORDER_WRITES_ENABLED` = `false` initially.
- `DATABASE_URL` = durable local/test SQLite path.
- `MOOTRADE_OAUTH_STORE` = optional path override for the DPAPI-encrypted local OAuth record; defaults to `%LOCALAPPDATA%\MooTrade\moomoo-oauth.bin` on Windows. Never commit its contents.
- `COMPETITION_ACCOUNT_MASKED_ID` = non-secret masked identity, e.g. `****0101`.
- `COMPETITION_ACCOUNT_FINGERPRINT` = lowercase SHA-256 of the full Moomoo `acc_id`; generate it without echoing the id:
  `python -m app.cli fingerprint-account`.
- `COMPETITION_ACCOUNT_MARKET_ID` = expected market id (US margin account is `100`); this is a consistency check only, never the selector.
- `QODER_ACCESS_TOKEN` = *only if Qoder's supported API integration requires it*.
- `MOOMOO_MCP_URL` = *set only to organiser-verified endpoint*; do not infer it from a public example.

The account lock requires both the masked id and the fingerprint. If either is missing, it fails closed instead of falling back to a market-only or single-account match.

### Local read-only Moomoo REST setup

```bash
.venv/Scripts/python -m app.cli moomoo-login
.venv/Scripts/python -m app.cli moomoo-auth-status
.venv/Scripts/python -m app.cli moomoo-read
```

Complete browser consent with read permissions only; do not grant `trade:write`. `moomoo-read` prints sanitized `PAPER` JSON and never prints tokens or full account ids. The token record is DPAPI-encrypted outside the repository.

### Read-only history and trading calendar (17 November 2026)

Two documented GET endpoints were verified against the competition token and added to the REST allowlist:

- `GET /api/v1.0/quote/{symbol}/history-kline` with `end=YYYY-MM-DD`, `ktype=2` (daily), `autype=1`, `num<=370`, `extended_time=0`. Response `data.kline_list[]` carries `date` (`YYYYMMDD`), OHLC, volume and `time_key`. The final daily bar is the named session's completed bar.
- `GET /api/v1.0/quote/trading-days` with `market=US`, `start`, `end`. Response `data.trading_days[].time` is the provider calendar.

`backend/app/broker/moomoo_history.py` parses both strictly: integer dates, positive and internally consistent OHLC, non-negative integer volume, positive `time_key`, chronological ordering and no bar after the requested end. `snapshot(..., require_end_session=True)` requires the last bar to equal the requested session. Snapshots record provider, endpoint, args, fetch time and last completed session only; they contain no account identifiers.

`backend/scripts/refresh_daily_bars.py` refreshes the four `spy-directional` candidates (SPY, UPRO, SH, SPXU) atomically into `evidence/current-market/<session>/daily-bars.json`. It refuses `ORDER_WRITES_ENABLED=true` and any stored `trade:write`. Verified real refresh on 17 November 2026: 370 bars per symbol, last completed session `20261116`, fetched `2026-11-17T14:17:20Z`.

`backend/scripts/current_market_run.py` performs the read-only current-market collection and three-agent Qoder review. Session mode requires `MoomooQuoteFeed.get_quote` to return the regular-session state for every symbol; post-close mode records quote observations and requires bars from the last completed session. Both modes validate the competition paper account, freshness, completeness and zero order writes before any Qoder session starts.

`backend/scripts/schedule_readonly.py` is the local recurring workflow (`backend/config/readonly_schedule.json`, default `16:20` `America/New_York`, `post-close`). It is invoked by Windows Task Scheduler through `backend/scripts/run_readonly_schedule.cmd` and registered by `backend/scripts/register_readonly_task.ps1`. It checks the provider trading calendar, refreshes completed bars and account state, runs deterministic screening and the three-agent review, and records a durable idempotent run history in `data/readonly_schedule.json` plus append-only events in `data/scheduler-events.jsonl`. A process lock prevents overlapping runs; a prior `RUNNING` record is marked `ABANDONED` only after the lock is reacquired, and interrupted processes persist `INTERRUPTED`. The schedule imports no order adapter and reports `order_writes_enabled=false` in every state record. Qoder Cloud cron cannot access the local DPAPI token, repository or ledger, so scheduling stays local.

`backend/scripts/run_readonly_schedule.cmd` is the Task Scheduler action wrapper. Register or re-register the task with:

```powershell
powershell -ExecutionPolicy Bypass -File backend/scripts/register_readonly_task.ps1
```

`backend/scripts/schedule_auto_paper.py` is the AUTO_PAPER execution-phase scheduler (`backend/config/auto_paper_schedule.json`, execution window `09:35`-`10:30` `America/New_York`). It is invoked by the Task Scheduler task `MooTrade Auto Paper Scheduler` through `backend/scripts/run_auto_paper_schedule.cmd`, registered by `backend/scripts/register_auto_paper_task.ps1` with two daily UTC triggers at `13:35Z` and `14:35Z` (covering 09:35 ET in both DST offsets). It consumes the read-only scheduler's evening decision artifacts (`evidence/qoder/`) and daily bars (`evidence/current-market/<session>/`), scopes `ORDER_WRITES_ENABLED=true` to the executor invocation only, and records a durable per-session history in `data/auto_paper_schedule.json` plus append-only events in `data/auto-scheduler-events.jsonl`. Outside the window, on non-trading days, after an already-attempted session or without an AUTO_PAPER activation pin it skips or abstains; no session is ever retried later the same day and no window is backfilled. Timer mechanics (WakeToRun, interactive DPAPI user session, Modern Standby limits) match the read-only task and were verified there on 18 November 2026.

For a one-time timer validation, add `-ValidationDelayMinutes 2`; remove the validation trigger afterward with `Set-ScheduledTask` filtered to the daily triggers. Do not use a manual `--once` run as timer evidence.

`backend/scripts/readonly_preflight.py` is the sanitised read-only preflight collector. It refuses `ORDER_WRITES_ENABLED=true` or a stored `trade:write`, validates the competition account and token scopes, observes SPY/QQQ/IWM, evaluates a diagnostic QQQ BUY 1 proposal through the deterministic `RiskGate`, and writes `evidence/preflight/preflight-<UTC>.json`. It never contacts an order endpoint.

### Verified read-only evidence (17 November 2026)

- Preflight `preflight-2026-11-17T155320Z.json`: quotes and account fresh (0s age), `AFTERNOON` session, risk decision `REJECT` with only `R010` (writes disabled) and `R014` (owner first-order approval missing). The earlier contradictory "future-dated / 58,150s old" display came from a recorded artifact captured before market open, not from current policy; stale and future messages are now distinct.
- Current-market run `qoder-bc9eb9e3-8f3b-46f8-9f20-8f2eb94f541a`: regular-session quotes IWM 268.16, QQQ 647.65, SPY 727.71; competition account fresh and reconciled; completed daily bars through `2026-11-16`; three genuine sessions (coordinator, researcher, auditor); outcome `NO_TRADE` because SPY 739.95 closed below its 20-session SMA 757.695. No order was submitted.
- Scheduled one-shot `data/readonly_schedule_session_verify.json`: the scheduler runner executed end-to-end (`run_key 2026-11-17`, status `COMPLETED`, `order_writes_enabled=false`, run `qoder-08ac0d92-8f55-475a-a348-6b5e50d72e66`, outcome `NO_TRADE`).
- **Timer repair and verification (18 November 2026):** the 17 November `16:20 America/New_York` timer was missed because the host was in Modern Standby. Windows Kernel-Power events in `evidence/scheduler/power-events-2026-11-18.json` show standby from `2026-11-18 00:23:59 SGT`, a brief exit/re-entry at `03:27:29 SGT`, and a full exit at `08:39:40 SGT`. The due time was `05:20 SGT` on 18 November, entirely inside that interval. The Python sleep-loop could neither wake the host nor recover a missed deadline, so it was replaced.
- The replacement is the Task Scheduler task `MooTrade Read-Only Scheduler`: two daily UTC triggers at `20:20Z` and `21:20Z` cover both US Eastern DST offsets; the Python entry point validates the due session against the Moomoo US trading calendar and the `America/New_York` clock. Settings are `WakeToRun=true`, `StartWhenAvailable=true`, `MultipleInstances=IgnoreNew`, `StopOnIdleEnd=false`, a two-hour limit and two 15-minute restart attempts. The task runs as the interactive user at limited privilege; it cannot run while the user is signed out because the local DPAPI token and network identity are required.
- **Failed validation attempt:** the first timer trigger at `09:06:59 SGT` started but was terminated with `0xC000013A` (Ctrl+C) after about 13 seconds. The task XML still had the PowerShell default `StopOnIdleEnd=true`; the run left a durable `RUNNING` record. The registration now sets `-DontStopOnIdleEnd`, and the scheduler persists `INTERRUPTED` before re-raising, so the next run can recover.
- **Genuine timer execution:** the fresh validation trigger fired at `09:10:52 SGT` with `LastTaskResult=0`. It selected the missed `2026-11-17` session (`catch_up=true`, `minutes_late=230.894`), completed the read-only refresh and three-agent Qoder run `qoder-83bc0a47-e238-4672-a5cc-42e8080180ce` with outcome `NO_TRADE`, and persisted `order_writes_enabled=false`. This was a Task Scheduler timer, not a manual `--once` run. The host was awake for this validation; `WakeToRun` is configured for future standby, but a physical Modern Standby wake was not induced for this test. Evidence: `evidence/scheduler/validation-2026-11-18.json`, `evidence/scheduler/task-2026-11-18.xml`, `evidence/scheduler/final-state-2026-11-18.json`, `evidence/scheduler/task-final-2026-11-18.xml`, `data/scheduler-events.jsonl`, `data/readonly_schedule.json` and `evidence/qoder/qoder-83bc0a47-e238-4672-a5cc-42e8080180ce.md`.
- The one-time validation trigger was removed after capture; the task retains only the two daily triggers. `NextRunTime` is `2026-11-19 04:20 SGT`, which is `15:20 ET` on 18 November and therefore resolves to the prior session: it normally returns `SKIPPED_ALREADY_RUN`, but remains available as a catch-up slot if that prior session was missed. The `05:20 SGT` trigger is `16:20 ET` on 18 November and is the due run. The two-trigger design keeps this correct through the DST change without editing the task.

### Technical-analysis capability audit (18 November 2026)

Read-only probes used the existing `quote:read` authorization (`trade:read` and `trade:write` absent). Raw responses and the frozen research protocol are in `evidence/research/moomoo-tech-audit-2026-11-18/`.

| Capability | Endpoint | Verified result |
|---|---|---|
| Candlestick patterns | `GET /api/v1.0/quote/{symbol}/kline-shape` | HTTP 200. `ktype=2` and `9` return `shape_name`, `direction`, `points`, `forecast`, `backtest_statistic`; `ktype=1` is rejected (`ret_code=-3`). No as-of parameter. On the 2026-11-17 close, 12/12 symbols returned `NONE`/code 0. |
| Indicator polarity | `GET /api/v1.0/quote/{symbol}/indicator-polarity` | HTTP 200. Returns `overall_score`, `update_time` and 15 named indicators (`RSI_6`, `RSI_12`, `MACD_12_26_9`, `KDJ_9_3_3`, etc.) with `SEVERELY_OVER_BOUGHT` … `SEVERELY_OVER_SOLD` labels. Update time 16:00 ET on the named session. No as-of parameter. |
| Indicator backtest | `GET /api/v1.0/quote/{symbol}/indicator-backtest` | HTTP 200 with `indicator_id` 1–15. Returns `occurs_total/up/down`, `probability_up/down`, `avg_change_pct`, `max_up/down_pct`. The provider does not disclose the window, horizon or methodology; AAPL samples ranged 4–55 occurrences. |
| Technical unusual movements | `POST /api/v1.0/quote/{symbol}/unusual/technical` | **HTTP 403, code -12006.** Not accessible with the current authorization; no workaround was attempted. |
| Capital flow history | `GET /api/v1.0/quote/{symbol}/capital-flow/history` | HTTP 200 and genuinely historical: 500 daily rows from 2024-11-19 to 2026-11-17 for stocks and ETFs, with `main_in_flow`, `in_flow`, size buckets, `main_deal_ratio` and a `next_time` cursor. |

`MoomooRestClient` allows the two snapshot reads (`kline-shape`, `indicator-polarity`) alongside `history-kline`; order paths remain refused. The study's observer script was removed in the 18 November 2026 cleanup; its recorded, frozen-protocol observations remain in [`evidence/research/moomoo-signal-observation/`](../evidence/research/moomoo-signal-observation/) and the candidate is not deployed.
- Provider quote and account timestamps may lead the local clock by fractions of a second. A 5-second `CLOCK_SKEW_TOLERANCE_SECONDS` is accepted; larger skew still fails closed as future-dated. Quote age is clamped to zero for skew, and stale messages no longer share wording with the future-date check.

## MCP restriction and cloud read status (17 November 2026)

The existing Qoder Cloud Agent `moomoo-mcp-readonly-test` was updated in place; no duplicate agent was created. Agent version 4 uses the documented platform policy schema:

- `mcp_toolset` for `moomoo` with `permission_policy.type="always_deny"` on all ten order-writing tools: `trading_order_place`, `trading_order_replace`, `trading_order_cancel`, `trading_order_confirm`, `sim_trade_input_order`, `sim_trade_cancel_order`, `sim_trade_modify_order`, `crypto_account_create_order`, `crypto_account_cancel_order`, `crypto_account_modify_order`.
- `agent_toolset_20260401` with `enabled_tools=["Read"]` only, so `Bash`, `WebFetch`, `WebSearch`, `Write`, `Edit`, `Glob` and `Grep` are not exposed.

**Cloud read verification.** The earlier 401 came from starting v4 sessions without a vault. Attaching `vault_00vqvi7wl0xs2mgffyo8` (`moomoo-mcp`) to a fresh v4 session made tool discovery succeed. In `sess_00vr5lar7i5mo93aq1j5` the agent:

- called `sim_trade_account_list` (allowed) and found exactly one account titled `Moomoo x Qoder AI Paper Trading Agent Challenge`, masked `****0101`, `market_id=100`, `account_type=2`;
- called `sim_trade_cash_info`, `sim_trade_position_list` and `sim_trade_history_order_list` for that account (all allowed): `balance=100000`, `hold=0`, `total_asset=100000`, `max_power_long=200000`, zero positions, zero orders, `pagination.has_more=false`;
- called `quote_stock_quote` for `US.QQQ`: `last_price=661.75`, `data_time=1794862800312`, `data_date=2026-11-16` (the quote remains stale/outside the regular session);
- reported no `Bash`, `WebFetch`, `WebSearch`, `Write`, `Edit`, `Glob` or `Grep` tools.

No repository, files or environment variables were mounted in that session, so the `Read` tool had nothing credential-bearing to open and no CLI/HTTP path could reuse the vault token.

The deny probe result: `sim_trade_input_order` was **not registered** in the session, so the agent could not form a call. There was no `agent.mcp_tool_use` event for any order tool and no order endpoint contact. Tool registration excluded the write tools before any permission evaluation; the paired platform `always_deny` config remains a second layer. The system prompt was not the control. No order was placed, modified, cancelled or confirmed.

**Residual redaction risk:** raw Moomoo tool results include full account ids inside their JSON payload. Qoder session event logs therefore contain identifiers even when the agent's final message masks them. Do not export raw session events into the repository, submission deck or screenshots. The Python adapters store only the SHA-256 fingerprint and masked identity.

**Remaining bypass surface:** the local interactive Qoder session still exposes the full Moomoo tool set, including the ten order tools. That session is not the automated executor. The Python read-only paths are the MCP adapter (four-name allowlist) and the REST adapter (GET account paths plus two POST quote-read paths); neither has a working order-submission implementation. Keep `ORDER_WRITES_ENABLED=false`.

**Required remediation before any write path is considered:**

1. Keep order submission outside every LLM agent. The Python executor must use a separately scoped tool/credential path, not an interactive or cloud agent session.
2. Use the verified local REST OAuth path for Python reads. Qoder Vault tokens are injection-only and must not be extracted or reused; do not route orders through an LLM or cloud session.
3. Observe a non-empty order-history response before relying on open-order reconciliation. The adapter validates the documented fields and fails closed on unknown statuses, but that shape remains unobserved.

## Qoder custom client-side tools (verified 17 November 2026)

Source: Qoder Cloud Agents documentation for [Agent Tools](https://docs.qoder.com/cloud-agents/tools), [Send events](https://docs.qoder.com/cloud-agents/api/sessions/events/send) and the [Python SDK](https://docs.qoder.com/cloud-agents/sdk/python).

- A custom tool is declared on the Agent's `tools` array as `{"type":"custom","name":...,"description":...,"input_schema":{...}}`. The schema must be a JSON Schema object with `"type": "object"`; names must be unique within the Agent, must not collide with built-in tool names, and the `mcp__` prefix is reserved.
- When the Agent calls a custom tool, the session pauses with stop reason `requires_action`. The client reads the `agent.custom_tool_use` event and replies on `POST /api/v1/cloud/sessions/{session_id}/events` with `{"type":"user.custom_tool_result","custom_tool_use_id":"<call event id>","content":[...],"is_error":false}`. Authentication is `Authorization: Bearer $QODER_ACCESS_TOKEN`.
- The Python SDK (`qca-sdk`, Python 3.10+) provides `Managed`/`AsyncManaged`, `sessions.events.send(...)`, and `events.stream(...)` / `events.resumable_stream(...)` for this loop. Credentials come from a PAT or a service-account key, not from the browser.
- **`permission_policy` is not supported on custom tools** because the client executes them. The handler is therefore the security boundary: it must enforce a fixed allowlist and must never accept arbitrary commands, file paths or credentials.
- Fit for MooTrade: a local session runner can expose read-only custom tools that call the deterministic Python research pipeline in-process and return sanitized evidence. This keeps the decision engine local; no inbound network path is required because the client polls the session.
- This does **not** bridge Python to the Vault-injected Moomoo MCP connection, and it does not authorise orders. Custom tools remain read-only; order submission stays outside every LLM session, behind the deterministic gate and a separately scoped executor.

### MooTrade read-only implementation (17 November 2026)

- `backend/app/qoder_tools.py` implements exactly two handlers: `research_market` and `evaluate_proposal`. Both reject extra fields, malformed or oversized inputs, unknown tool names, unpinned run IDs and proposals that differ from the pinned research artifact. `evaluate_proposal` invokes the real deterministic `RiskGate` with a synthetic historical account, never a broker.
- `backend/scripts/qoder_readonly_run.py` owns a runner-generated run ID, creates coordinator/researcher/auditor sessions with `resources=[]` and `vault_ids=[]`, deduplicates event IDs, sends each expected tool result once, and records ambiguous delivery as non-retryable. A timeout is marked `AGENT_ERROR`; the runner never resubmits a turn.
- Genuine run `qoder-5abed69d-8fbc-4342-a51f-e46814f3941c` completed as `HISTORICAL_DRY_RUN` / `NO_TRADE`. Sessions: coordinator `sess_00vrjkuvor0n5z2xowpc`, researcher `sess_00vrjkz4rxkaolrwifgl`, auditor `sess_00vrjl9k6r08wt8i5u0z`. All were idle with no MCP servers, no skills, no Vault bindings and no order tools.
- The deterministic snapshot showed SPY 739.95 below its 20-session SMA 757.695 and no eligible candidate. The auditor independently confirmed `NO_TRADE`. Sanitized evidence is in `evidence/qoder/`; the Coordinator's final message was recovered read-only after fixing a multi-turn cursor defect, not by rerunning paid turns.
- On 18 November 2026 the researcher agent was updated to version 3: its `research_market` schema enumerated only `directional-event-v2`. That version, the event archive and the synthetic-event demo are now retired historical evidence. The run `qoder-62b08de4-d64f-43ab-b044-fe781eae393e` placed no order.
- The same researcher agent was updated to **version 4** for `spy-directional`: the schema now enumerates only `spy-directional`, and the prompt covers SPY 10-session return, SMA50 trend, 20-session volatility, the four candidates and CASH. A genuine current-market run `qoder-328aefff-7dde-4a98-ac76-99b3e0e33728` completed with coordinator `sess_00vuffkjlafwgresy62p`, researcher `sess_00vuffpgw47pdzx2s53d` and auditor `sess_00vufg56d34sgybrbybv`. It recorded SPY `732.44`, 10-session return `-2.90%`, SMA50 `762.89`, volatility `23.06%`, BEARISH target SH and a 147-share proposal. The real `RiskGate` rejected it for `R002`, stale post-close quote, non-regular session, `R010` and `R014`. No order was created, approved or filled.
- A historical dry run is not current account data, owner approval or an order. `ORDER_WRITES_ENABLED=false` remains in force.

## Execution preflight and disabled order adapter (17 November 2026)

The local REST route provides authenticated reads without extracting Qoder Vault credentials:

- Direct REST uses a separately registered local public client, DPAPI-protected token storage, GET-only account reads and two documented POST-for-read quote endpoints.
- Qoder Vault credentials remain unavailable to local Python; that limitation no longer blocks competition-account reads.
- Qoder agents and custom tools remain read-only. Routing an order through an LLM session would violate the required authority boundary.

### Verified quote and session contract

The official OpenAPI documents these read-only POSTs, now allowlisted explicitly; every order path is refused by `post_read`:

- `POST /api/v1.0/quote/stock-quote` with `{"code_list":["US.QQQ"]}` returns `data.quote_list` with one row: `code`, integer `data_time` (Unix milliseconds), numeric `last_price`, `sec_status`, `suspension`.
- `POST /api/v1.0/quote/market-state` with `code_list`, `is_contain_ba`, `is_contain_overnight` returns `data.market_state_list` with `code` and `market_state`.
- Only `AFTERNOON` is documented as regular US trading hours (09:30–16:00 ET). Any other state, including extended-hours states, is treated as a closed regular session. A refused preflight is not an error; it produces no order.

`MoomooQuoteFeed` rejects a symbol that is not a US ticker shape, a missing/duplicate/wrong-code row, a missing or non-integer timestamp, a future timestamp, a quote older than 300 seconds, a non-positive or non-numeric price, `sec_status != "NORMAL"`, and `suspension != False`. Quote and market-state data must both succeed before execution can continue.

### Documented simulated-order contract

- `POST /api/v1.0/sim-trade/{acc_id}/orders` requires `trade:write`; the separate execution consent now grants it, but no order endpoint has been contacted.
- Request fields used by the prototype: `market` (the account's `market_id`, 100 for this US paper account), `symbol` (`US.QQQ`), `order_type` 3 (market), `order_side` 1 buy/2 sell, string `qty`, optional `price` (omitted for market orders), `text` ≤100 bytes, `order_trade_time_type` 1 (regular session only).
- The request has no client order ID or idempotency key. The documentation states: "Orders are not idempotent: on timeout or an unknown result, check today's orders before retrying."
- Success returns only `order_id`. Today's Orders and order history return `order_id`, status, side, symbol, quantities, prices, fill quantity, microsecond timestamps and the caller's `text` remark.
- Documented status codes map to internal states as follows: 1/2 → acknowledged; 3 → partially filled; 4 → filled; 5/7 → cancelled; 6 → rejected. Unlisted codes fail closed. Acknowledgement is never reported as a fill.
- Cancel is `POST /api/v1.0/sim-trade/{acc_id}/orders/{order_id}/cancel` and accepts only status 2 (`SUBMITTED`).

**Implemented adaptation, not provider-tested:** `MoomooSimulatedOrderAdapter` encodes the durable `client_order_key` in the documented `text` field as `MTP1-<64 hex>` (69 bytes). The local ledger remains the sole idempotency authority: reserve before any broker call; on timeout or malformed response mark `UNKNOWN` and never retry; query Today's Orders, history and the account snapshot; accept only one exact tag match whose symbol, side and quantity match the local request. No match or more than one match remains `UNKNOWN` for operator reconciliation. `text` is a correlation aid, not broker-enforced uniqueness.

**Disabled transport implemented, not provider-tested:** `MoomooOrderTransport` is the only order-call implementation. It validates the exact `/api/v1.0/sim-trade/{acc_id}/orders` path, refuses unless `ORDER_WRITES_ENABLED` is true, never retries, and raises an ambiguous-outcome error for any non-200, malformed response or transport failure. `MoomooPaperBroker` composes the read-only REST adapter, account lock, payload adapter and transport; `TradingService` accepts either that facade or `MockPaperBroker` through a protocol. The documented success response contains only an order id, so submission records `ACKNOWLEDGED` with no fills; fills require read-only reconciliation. Only `moomoo-supervised-execute`, after both CLI flags, an exact durable approval and every preflight check, constructs a transport with writes enabled; no real order endpoint has been contacted. `MoomooRestClient` still has no order path, and `moomoo-preview-order` still evaluates and prints only (`submission_performed` is always false). `TradingService` strict broker-response validation converts unexpected objects, key/proposal/fingerprint/request mismatches and illegal statuses into persisted `UNKNOWN`.

### OAuth scope conclusion

Sources reviewed on 17 November 2026:

- [OpenAPI overview](https://open.moomoo.com/api/overview/getting-started) and [API authority](https://open.moomoo.com/api/overview/api-authority)
- [Trading overview](https://open.moomoo.com/api/trading/overview), [get accounts](https://open.moomoo.com/api/trading/account/get-accounts) and [simulated order input](https://open.moomoo.com/api/sim-trade/input-order)

**Documented facts.** The documented scopes are `quote:read`, `quote:write` (watchlist writes), `trade:read` (assets, positions and order history) and `trade:write` (place, modify, cancel and confirm orders). The registration example includes `quote:read quote:write trade:read trade:write accid:*`; the token example includes `quote:read trade:read accid:123456`. The docs also state that `trade:write` "means the API layer may accept trading write requests. It does not replace whether the account is eligible to trade a given market — check `enable_market`". The trading overview says "Calling the securities trading APIs places real trades." `POST /api/v1.0/sim-trade/{acc_id}/orders` is the documented simulated-order endpoint and checks that the account matches the market.

**What the documentation does not establish.** No official page states that `accid:<id>` narrows `trade:write` to that account, or that a `trade:write` consent cannot reach the user's personal/live accounts. The OAuth flow documents scope selection and account binding, not account-level exclusion from a write scope. `GET /api/v1.0/accounts/authorized_trd_accs` returns authorized trading accounts, but that is account discovery, not proof of a write-scope restriction.

**Conclusion.** Account-exclusive `trade:write` is **not confirmed**. A future `trade:write` consent must be treated as potentially account-wide. The existing read-only token has no `trade:write`, and `MoomooOAuth` rejects any `trade:write` grant.

**Execution client authorized (18 November 2026), no order sent.** `MoomooExecutionOAuth` is a separate client with its own DPAPI-protected token file (`MOOTRADE_EXECUTION_OAUTH_STORE`, default `moomoo-execution-oauth.bin`). The owner completed browser consent for `quote:read trade:read trade:write` plus an account binding, and the access and refresh tokens are stored only in that separate file. `moomoo-execution-login` printed the account-exclusive-scope warning before consent; `moomoo-execution-status` reports the granted scopes without printing tokens; `moomoo-execution-check` used read-only calls only and verified the exact competition account with `order_endpoint_contacted: false` and `account_exclusive_write_scope_verified: false`. Account-exclusive write scope remains unverified and the consent is treated as potentially account-wide. The read-only client remains unchanged and still rejects `trade:write`.

**Supervised runtime boundary implemented (18 November 2026); first paper orders submitted and filled.** `backend/app/supervised.py` composes the existing execution OAuth, read-only REST broker, quote feed, paper-broker facade, `RiskGate`, ledger and `TradingService` without changing any policy. Three operator-only commands use it:

- `moomoo-supervised-preview` requires the execution token, reads a fresh execution quote and reconciled account, evaluates the gate with writes hypothetically enabled and prints the exact documented payload. It always reports `submission_performed: false` and never constructs an enabled transport.
- `moomoo-supervised-execute` requires both `--enable-order-writes` and the exact `--confirm-client-order-key`, plus a durable approval bound to that key and proposal. It submits at most once, never retries, marks ambiguous outcomes `UNKNOWN`, and performs one read-only reconciliation. Writes exist only in that process invocation.
- `moomoo-supervised-reconcile` is read-only and reports the local order plus the latest `RECONCILIATION_OK`/`MISMATCH` event.

The CLI never accepts a token or full account id, and reports `account_exclusive_write_scope_verified: false`. Writes remain disabled by default and no Qoder/MCP agent session can invoke these commands.

**Live provider contract findings (18 November 2026).** The first supervised diagnostic QQQ BUY 1 and SELL 1 were submitted and filled (broker order ids `3115842` at 661.72 and `3115920` at 654.73; see `docs/evidence.md`). Three provider-behaviour deviations were observed against the live paper account and fixed in the REST parsers, each with regression tests:

- Position-list rows return `market: 100` (the account market id) although the documented field is the market enum (`1=HK 2=US 3=US options 4=HK Connect`); order rows return `2` as documented. `_parse_positions` now accepts `100` as the US account market id in addition to the enum.
- The cash-info `mv` and the position-row `mv` are read in separate calls and drift between them (observed ≤ 0.5 USD on a ~658 USD position); the position-total check now tolerates `max(0.01, 0.1% of cash mv)`.
- `_snapshot_id` now hashes state fields only (fingerprint, cash, position symbol/quantity, open-order symbol/side/remaining quantity), so the `R009` double-read guard rejects real account changes without failing on tick-level mark drift.
- Immediately after an acknowledgement, today's-orders rows can be transient and raise `MoomooResponseError`; the read-only reconcile command is re-run once the order state settles. No write is ever retried.

**Prepared support question (not sent; the standalone file was removed in the 18 November cleanup):**

> Can a Moomoo OAuth client be authorized with `trade:write` that is technically restricted to one simulated competition account (`account_type=2`) and guaranteed not to permit orders on the user's personal or live accounts? Does an `accid:<id>` binding limit write scope to that account, or is `trade:write` account-wide? Is `POST /api/v1.0/sim-trade/{acc_id}/orders` explicitly permitted for the Moomoo × Qoder AI Trading Agent Challenge, and what competition-specific execution restrictions or order types apply?

### First paper trade completed (18 November 2026)

The first supervised competition paper trade completed end to end: diagnostic QQQ BUY 1 filled at 661.72 (broker order `3115842`, 14:33:36Z) and the closing QQQ SELL 1 filled at 654.73 (broker order `3115920`, 14:45:27Z), each behind a separate exact-proposal owner approval, each reconciled to `RECONCILIATION_OK` from broker rows. The account ended flat with 99,991.02 USD cash. The diagnostic is not counted as strategy performance.

Remaining unverified items:

1. **Account-exclusive write scope remains unverified.** The separate execution client has `quote:read`, `trade:read`, `trade:write` and an account binding, but the documentation does not establish that an `accid:` binding restricts `trade:write` to the competition paper account, so the consent is treated as potentially account-wide.
2. **Order lifecycle partially observed.** Market-order acknowledgement, fill and position reconciliation are now observed against the real provider; modify/cancel and partial-fill lifecycles remain unobserved. The correlation tag is a local aid, not broker-enforced idempotency.

The first order failed closed with `R014` until a durable exact-proposal approval existed, and the execute command still requires `--enable-order-writes` plus the exact key confirmation.

**Acceptance tests:** fresh quote and session checks pass with strict success/partial/filled/cancelled/rejected/unknown mapping; stale, future, suspended, wrong-symbol and malformed quote responses fail closed; POST-read allowlisting refuses order paths and refresh failure is fatal; the correlation tag is bounded and ambiguous matches are refused; the disabled transport sends nothing; a documented success response records acknowledgement without inventing a fill; partial fill and rejection arrive only through read-only reconciliation; transport timeout or malformed acknowledgement persists `UNKNOWN`, blocks new submissions and never retries; duplicate proposals send at most one request; an oversized order returns `R004` without a broker call; reconciliation queries all three broker sources and rejects account mismatch. The full backend suite passes (**313 tests**, 18 November 2026, including execution OAuth registration-only status rejection, scheduler catch-up, lock exclusion, abandoned-run recovery, interruption persistence, clock-skew acceptance, execution-transport mocks, supervised CLI guard tests, dashboard API tests and the three live-contract regression tests).

## Vibe-Trading research audit (18 November 2026)

Vibe-Trading `0.1.19` (MIT, pinned commit `a8d815d17ec054a34dbdfc7ce8d1d9972566b709`, now archived outside the repository) was assessed as a possible quantitative research engine. It was **not** imported into the MooTrade backend and did not touch the risk gate, broker adapter, OAuth scopes, scheduler, dashboard or order transport. `ORDER_WRITES_ENABLED=false` remained in force.

- **Phase 2:** the Vibe `GlobalEquityEngine` consumed 370 Moomoo daily bars and reproduced the existing momentum-v1 shares and equity curve exactly (equity difference below `$1e-10`). The comparison exposed a production metric-base defect in [`backend/app/research/evaluate.py`](../backend/app/research/evaluate.py): total return and CAGR divided by the first post-entry equity and the curve omitted the initial value. This is corrected; both engines now report `0.0895%` and `$100,089.46`, with regression tests covering the initial-equity base and drawdown peak.
- **Phase 3:** 210 read-only `history-kline` requests returned all 2,516 provider US sessions for the frozen 20-stock universe plus SPY over 2015-2024. Data checks, independent weekly-selection recomputation, target constraints, a truncation/future-perturbation look-ahead test and fill-to-equity reconciliation all passed.
- **Result:** one pre-registered run of `volume-confirmed-relative-strength-v1` returned 36.82% versus 20.47% for exposure-matched SPY, but 107.48% for the equal-weight 30%-gross comparator; Sharpe was 0.735 versus 0.867 for exposure-matched SPY. The frozen rejection rule triggered. No 2025-2026 data was used for the stock protocol and no tuning or deployment followed.
- **Integration blockers:** the full Vibe runner requires `fastmcp` and a `yfinance` import; this environment lacks both. The engine was invoked in-process with a benchmark-resolver stub, a custom loader, a whole-share `round_size` override and an explicit weekly rebalance mask. Vibe requires `pandas<3.0`; the local environment has `pandas 3.1.1`, so the successful run used an unsupported combination.
- **Verdict:** use Vibe-Trading as a separate, pinned research tool (Option B), not as a production dependency. Evidence and precise module references are in [`evidence/research/vibe-trading-poc-2026-11-18/`](../evidence/research/vibe-trading-poc-2026-11-18/), with the protocol report in `protocol-report.md` and the integration verdict in `integration-verdict.md`.

## Security cautions

- An OAuth login with trade permission must not silently grant access to a personal live account. Verify exact account routing **before** writes.
- Read-only permissions are the default. Grant order-write access only to the narrow execution component where the platform allows it.
- GitHub contains configuration *examples*, never active tokens or raw authenticated HTTP dumps.
- Do not assume a Qoder desktop connector automatically propagates into Qoder Cloud Agent runs.
- Use no additional paid LLM or market-data API until an actual missing capability requires one.
