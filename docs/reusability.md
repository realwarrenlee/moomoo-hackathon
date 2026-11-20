# Reusability and extension guide

**Purpose:** what another developer can reuse from MooTrade without weakening the safety controls. The current mandate is **risk-v3 only** (20 November 2026 cutover) and explicit durable owner approval for the exact proposal/key of **EVERY supervised BUY and SELL**. Risk-v1, the pre-simplification risk-v2 and historical AUTO_PAPER pins are audit evidence only; they cannot be selected or reactivated. Runtime remains `SUPERVISED_PAPER` with `ORDER_WRITES_ENABLED=false`. Execution scope is SPY/SH only; UPRO/SPXU were removed from the universe and are rejected by default-deny symbol validation, with their historical records preserved. Read-only capacity, current test results and the genuine SH preview are recorded in `docs/evidence.md`. Reuse instructions do not authorise account switching, new activation or unattended trading.

## Reusable Python modules

All under `backend/app/`. Install as an editable package (`pip install -e ".[dev]"`) and import as `app.<module>`.

| Module | Reusable capability | Interface |
|---|---|---|
| `models/contracts.py` | Typed trading contracts and the order state machine | Pydantic models (`TradeProposal`, `RiskDecision`, `OrderRequest`, `OrderRecord`, `Fill`, `AccountSnapshot`, `ControlState`), `can_transition()` |
| `risk/policy.py` | Deterministic risk-v3 gate only | `RiskGate.evaluate()` / `fail_closed()`; signed-effective exposure, target consistency, cash/freshness, account, approval and idempotency checks; retired policies are not an execution option |
| `ledger/store.py` | Append-only audit ledger, durable idempotency, kill switch, approvals | `SQLiteLedger` (event append with SQL triggers, `reserve_submission`, `set_kill_switch`, `approve_first_order`, equity baseline) |
| `broker/account_lock.py` | Exact-account identity resolution | `AccountLock.from_env()`; masked id + SHA-256 fingerprint, simulated-source only |
| `broker/mock.py` | Test-double broker | `MockPaperBroker` (idempotent, snapshot-bound, failure injection via `accept_then_timeout`) |
| `broker/moomoo_auth.py`, `moomoo_rest.py` | OAuth 2.1 + PKCE client, GET-only read transport with POST-for-read quotes | `MoomooOAuth`, `MoomooRestClient`, `MoomooExecutionOAuth` |
| `broker/moomoo_history.py`, `moomoo_quotes.py` | Strict daily-bar and quote/market-state parsing with staleness checks | `HistorySnapshot`, `MoomooQuoteFeed` |
| `broker/moomoo_orders.py` | Documented simulated-order payload, strict status mapping, `UNKNOWN` reconciliation | `MoomooSimulatedOrderAdapter`, `MoomooOrderTransport` (disabled by default), `MoomooPaperBroker` |
| `research/data.py` | Point-in-time market history (`MarketHistory`), fixtures and evidence loading | `history.bars_as_of(symbol, dt)` — no look-ahead |
| `research/strategy.py` | `spy-directional` risk-v3 tiered signal, selection, sizing, HOLD/SELL/CASH/reversal | `screen(history, decision_time)`, `decide(snapshot, history, account)`; two research ETFs (SPY/SH), one directional position |
| `research/dryrun.py`, `evaluate.py` | Replay harness and evaluation metrics | `decide_at()`, equity/drawdown/trade metrics with next-open execution |
| `research/etf_baseline.py` | HISTORICAL frozen 10% comparator, not executable risk-v1 | `backend/scripts/etf_baseline_study.py`; no proposal builder or order path |
| `qoder_tools.py` | Qoder custom-tool boundary (`research_market`, `evaluate_proposal`) | `QoderToolService` with pinned run state and strict schemas |
| `supervised.py` | Operator-only execution boundary | composes `TradingService` with the paper broker; writes only via explicit flags, exact-proposal/key approval for every order and passing preflight |
| `dashboard/api.py`, `dashboard/data.py` | Typed GET-only read models | seven `/api/v1/*` routes; refuses `ORDER_WRITES_ENABLED=true` |
| `service.py` | Supervised trade flow and reconciliation | `TradingService.execute()`, `reconcile()` |

## Qoder Cloud Agent configuration

The three agent roles are configured in the Qoder cloud workspace (not in this repository):

- **Coordinator** — no tools; validates the run boundary and closes the report.
- **Market Researcher** — one custom tool, `research_market`, declared with a strict JSON Schema enumerating `spy-directional`.
- **Independent Risk Auditor** — one custom tool, `evaluate_proposal`, which runs the real `RiskGate` locally; the proposal must match the pinned research artifact.

Agent ids used by the current-market runner are in `backend/config/current_market.json`. The `moomoo-mcp-readonly-test` connector applies `always_deny` to all ten order-writing MCP tools and exposes only `Read`; details in `docs/integrations.md`. MooTrade defines no custom Qoder skill; the `cloud-agents/` directory is an untracked reference clone of the official Qoder Cloud Agents skill/MCP documentation (`github.com/QoderAI/cloud-agents`), kept for API reference only.

## Scripts

| Script | Purpose | Write capability |
|---|---|---|
| `backend/scripts/qoder_readonly_run.py` | Historical three-agent Qoder run | none |
| `backend/scripts/current_market_run.py` | Current-market read-only collection + three-agent run | none |
| `backend/scripts/refresh_daily_bars.py` | Refresh completed daily bars for the two candidate ETFs (SPY/SH) | none (refuses writes) |
| `backend/scripts/readonly_preflight.py` | Sanitised preflight artifact | none |
| `backend/scripts/schedule_readonly.py` | Task Scheduler entry: refresh + screen + agent run, durable state | none |
| `backend/scripts/etf_baseline_study.py` | Benchmark study artifact generation | none |
| `backend/scripts/evidence_report.py` | Sanitised evidence summary from existing artifacts | none |
| `backend/scripts/register_readonly_task.ps1`, `run_readonly_schedule.cmd` | Task Scheduler registration and action | none |
| `backend/app/cli.py` | Operator commands (`moomoo-*`, `approve-first-order`, `fingerprint-account`) | only the supervised workflow is currently authorised; execute requires two flags + durable approval for every exact proposal/key |

## Key contracts

- **Broker protocol:** `TradingService` accepts any broker implementing submit/snapshot semantics (`MoomooPaperBroker` or `MockPaperBroker`). Only this adapter submits orders, and only after preflight.
- **RiskGate contract:** a typed `TradeProposal` in, a risk-v3 `RiskDecision` (`APPROVE`/`REJECT` + `reasons[]`) out, with a 30-second TTL bound to the proposal/account snapshot. This TTL does not expire durable owner approval, which is independently required for each exact supervised BUY/SELL proposal/key.
- **Active limits:** tiered research targets of 10%–40% or CASH, 40% signed-effective ceiling, ±5pp target tolerance, RiskGate maximum one position (matching the strategy), 2% drawdown, US$5 cash buffer, quote ≤300s and account ≤60s, 1x leverage maximum, plus the competition 40% single-security concentration cap (`R019`). Only the supervised path skips the 10% floor.
- **Prepared proposal handoff:** `--proposal-file` extends the existing supervised preview/execute arguments without removing required flags. All required values must match the exact research proposal; timestamps, evidence and target are preserved. Preview reports per-rule states and current/post-order signed-effective exposure; it never submits. The retained `approve-first-order` CLI name is used for EVERY supervised order.
- **Order state machine:** `PROPOSED → POLICY_APPROVED/REJECTED → SUBMITTING → ACKNOWLEDGED/PARTIALLY_FILLED/FILLED/CANCELLED/REJECTED/UNKNOWN`; terminal states cannot move backwards; `UNKNOWN` only resolves via read-only reconciliation.
- **Ledger events:** append-only rows with `event_type`, `source`, `payload_redacted_json`, `correlation_id`. Suggested event vocabulary is in `docs/architecture.md`.
- **Qoder artifact format:** `evidence/qoder/*.json` records run metadata, data collection, research snapshot/proposal, risk decision and sanitised agent summaries; the dashboard and the evidence report parse it.

## Configuration requirements

See `.env.example` and `docs/operations.md`. The account lock requires the masked id and fingerprint; the market id is a consistency check. Token files are DPAPI-encrypted and outside the repository. `ORDER_WRITES_ENABLED` must be `false` for every read-only component to start.

## Extension points

| Change | What to touch | Safety tests that must keep passing |
|---|---|---|
| New strategy version | `research/strategy.py` (version constant, signal rules), `qoder_tools.py` schema enum, agent prompt in Qoder console, `backend/config/current_market.json` | `test_research.py`, `test_qoder_tools*.py` |
| Allowlist expansion beyond SPY/SH | Separate explicit owner authorisation before changing gate construction; research eligibility is not execution permission | `test_risk.py`, `test_trading_flow.py` |
| Leverage execution (any leveraged fund) | Outside risk-v3: require an owner-approved policy version change; preserve the 40% ceiling, target tolerance and every-order approval | leverage tests in `test_risk.py` |
| Another broker/account in a separate adaptation | Out of scope for this competition runtime; never add fallback routing or implicit account switching | `test_account_lock.py`, `test_trading_flow.py` |
| New dashboard block | Read model in `dashboard/data.py` + view in `dashboard/api.py` + typed client in `frontend/src/lib/mootrade.ts`; GET-only | `test_dashboard_api.py` |
| New research study | `research/evaluate.py` metrics + a script like `etf_baseline_study.py`, artifacts under `evidence/research/` | `test_research.py`, `test_etf_baseline.py` |

## Adaptation checklist (another strategy or account)

1. Keep agent output untrusted: agents propose and challenge; deterministic code computes signal, selection, sizing and the gate outcome.
2. Verify the new account's identity through broker metadata and lock it by masked id + fingerprint before any write.
3. Keep the RiskGate as the only authoriser; reuse it unchanged rather than re-implementing limits.
4. Keep the ledger, idempotency keys, kill switch and `UNKNOWN`-never-retry semantics; they are transport-independent.
5. Keep order submission in the supervised CLI, behind explicit flags and durable exact-proposal/key approval for EVERY BUY/SELL. Approval of one order or a historical pin never approves another order or autonomy.
6. Pre-register any new strategy's rules before evaluation; do not tune thresholds on the evaluation window.
7. Label all historical studies `HISTORICAL` and all mock results `MOCK`; never present them as paper performance.

## Not yet reusable (future work)

- Modify/cancel and partial-fill lifecycles remain provider-unobserved. Acknowledgement, fill and non-empty history were observed for QQQ diagnostic BUY `3115842` and SELL `3115920`, both reconciled on 18 November; this is not SPY/SH acceptance.
- Order cancellation remains unimplemented. The confirmed, audited `moomoo-kill-switch` CLI already exists and blocks new orders without liquidating holdings.
- A reusable Qoder skill packaging the MooTrade workflow (no such skill exists today; only the platform's `qoder-cloud-agents` reference clone is present).
- Python access to the cloud Moomoo MCP (vault credentials are injection-only; reads use the local REST client).
