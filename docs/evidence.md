# Competition evidence

**Purpose:** separate demonstrated achievements from unverified claims, so a judge can audit every statement in this project. Every entry names a durable artifact, its timestamp and its verification level. Nothing in this document is invented; where evidence is missing, that is stated explicitly.

## Verification levels

1. **Implemented** — code exists and is covered by the repository's own tests, but has not been observed against an external system.
2. **Automated-test verified** — unit/fixture/mock tests executed locally with observed results.
3. **Genuine Qoder run** — a completed Qoder Cloud Agent session set, with recorded session ids and artifacts.
4. **Real Moomoo account read** — an authenticated read-only call against the competition paper account.
5. **Broker-confirmed paper order** — an order submitted to and confirmed by the broker, with fills reconciled. **None exists yet.**
6. **Blocked / unverified** — claimed capability without supporting observation.

Historical backtests are **not** performance levels; they are signal-quality studies on historical data and are always labelled `HISTORICAL`.

## Evidence matrix

| Claim | Evidence | Verification | Status |
|---|---|---|---|
| Competition account identified and locked (`****0101`, US paper, 100,000 USD) | `backend/app/broker/account_lock.py`; `docs/integrations.md` | Real MCP reads (17 Nov) and real REST reads (17–18 Nov); masked id + SHA-256 fingerprint match | Verified |
| Deterministic risk gate `risk-v1` enforces R001–R015 | `backend/app/risk/policy.py`; `backend/tests/test_risk.py` | 310-test suite, 18 Nov 2026 | Test-verified |
| Oversized order rejected before the broker adapter is called | `backend/tests/test_trading_flow.py`, `test_risk.py` | Mock broker observes zero calls | Test-verified |
| Ledger is append-only; kill switch persists across restarts | `backend/app/ledger/store.py` (SQL triggers); `backend/tests/test_ledger.py` | 28 events, 0 submissions, 0 approvals in `data/mootrade.db` (18 Nov) | Test-verified |
| Order state machine and `UNKNOWN` handling | `backend/app/models/contracts.py`; `backend/tests/test_contracts.py`, `test_moomoo_execution.py` | 310-test suite | Test-verified |
| Genuine three-agent Qoder workflow | `backend/scripts/qoder_readonly_run.py`; `evidence/qoder/*` | 8 cloud runs with session ids (table below) | Genuine Qoder runs |
| `spy-directional` signal, sizing and HOLD/SELL/CASH/reversal rules | `backend/app/research/strategy.py`; `backend/tests/test_research.py` | 310-test suite | Test-verified |
| Real Moomoo daily bars for all four ETFs (370 sessions through 17 Nov 2026) | `evidence/current-market/2026-11-17/daily-bars.json` | Read-only `history-kline` REST calls | Real provider read |
| Real current-market agent run rejected a real SH proposal (`R002/R007/R012/R010/R014`) | `evidence/qoder/qoder-328aefff-…md/.json` | Genuine cloud run, 18 Nov 2026 | Genuine Qoder run + real account read |
| Read-only preflights contacted no order endpoint | `evidence/preflight/preflight-*.json` | 4 real preflights; `submission_performed=false`, `order_endpoint_contacted=false` | Real provider read |
| Execution OAuth consent exists; write scope treated as potentially account-wide | `evidence/execution/*.json`; `docs/integrations.md` | Real consent 18 Nov; `account_exclusive_write_scope_verified=false` | Verified with caveat |
| Local Task Scheduler runs the read-only workflow unattended | `evidence/scheduler/*`; `data/scheduler-events.jsonl` | Genuine timer-triggered catch-up run `qoder-83bc0a47-…`, 18 Nov | Verified |
| AUTO_PAPER execution phase fails closed without the mode/pin | `backend/scripts/auto_paper_run.py`; `evidence/auto/2026-11-17/auto-paper-20261118T155123Z.json` | Real run against the genuine decision artifact: `TRADING_MODE=READ_ONLY`, `submission_performed=false` | Verified |
| AUTO_PAPER scheduler task fires via Windows Task Scheduler | `evidence/scheduler/auto-task-2026-11-18.xml`, `auto-events-2026-11-18.jsonl` | Genuine 2-minute validation trigger: `LastTaskResult=0`, `SKIPPED_NOT_IN_WINDOW` at 10:53 ET; validation trigger removed afterwards | Verified |
| AUTO_PAPER activated by explicit owner authorization | ledger `activations` record; `moomoo-auto-paper-status` output | 18 Nov 2026 16:03Z: pin binds account fingerprint, `spy-directional`, `SPY`/`SH`, `risk-v1`, 5%/10%/30%/2%; `order_submitted=false` | Verified |
| Historical sanity check of `spy-directional` (`-0.40%` vs SPY `+15.47%`) | `docs/strategy-and-risk.md`; `evidence/current-market/2026-11-17/daily-bars.json` | Fixed-rule replay, 12 Aug 2025 – 17 Nov 2026 | Historical only |
| **First broker-confirmed paper order and fill** | none | none | **Blocked / not yet performed** |

## Genuine Qoder Cloud Agent runs

Artifacts: `evidence/qoder/qoder-<run-id>.md` and `.json` (sanitised; raw session event logs are intentionally not exported because provider payloads contain full account ids).

| Run id | Mode | Strategy | Outcome | Completed (UTC) |
|---|---|---|---|---|
| `qoder-5abed69d-8fbc-4342-a51f-e46814f3941c` | HISTORICAL_DRY_RUN | momentum-v1 | NO_TRADE | 2026-11-17 11:32 |
| `qoder-bc9eb9e3-8b3f-46f8-9f20-8f2eb94f541a` | CURRENT_MARKET_READ_ONLY | momentum-v1 | NO_TRADE | 2026-11-17 15:54 |
| `qoder-08ac0d92-8f55-475a-a348-6b5e50d72e66` | CURRENT_MARKET_READ_ONLY | momentum-v1 | NO_TRADE (scheduler one-shot) | 2026-11-17 15:54 |
| `qoder-b5802072-58a5-42b1-b935-5c7942ed8946` | HISTORICAL_DRY_RUN | directional-event-v2 | AGENT_ERROR → NO_TRADE (recorded failure) | 2026-11-18 05:56 |
| `qoder-05d6227e-7069-47d3-97b9-d56032d87614` | HISTORICAL_DRY_RUN | directional-event-v2 | HISTORICAL_POLICY_APPROVAL (dry-run only) | 2026-11-18 05:58 |
| `qoder-62b08de4-d64f-43ab-b044-fe781eae393e` | HISTORICAL_DRY_RUN | directional-event-v2 | HISTORICAL_POLICY_APPROVAL (dry-run only) | 2026-11-18 05:59 |
| `qoder-83bc0a47-e238-4672-a5cc-42e8080180ce` | CURRENT_MARKET_READ_ONLY | momentum-v1 | NO_TRADE (timer-triggered catch-up) | 2026-11-18 01:11 |
| `qoder-328aefff-7dde-4a98-ac76-99b3e0e33728` | CURRENT_MARKET_READ_ONLY | spy-directional | POLICY_REJECTED (SH blocked at R002) | 2026-11-18 06:56 |
| `qoder-12bd7001-ee8a-4d65-b94e-7c3075140b32` | CURRENT_MARKET_READ_ONLY | spy-directional | POLICY_REJECTED (SH BUY 147 rejected only by `R010`, writes disabled) | 2026-11-18 15:51 |

Runs marked `directional-event-v2` and `momentum-v1` predate the 18 November pivot and are retained as historical execution evidence. The current `spy-directional` run recorded sessions: coordinator `sess_00vuffkjlafwgresy62p`, researcher `sess_00vuffpgw47pdzx2s53d`, auditor `sess_00vufg56d34sgybrbybv`. No run placed, modified or cancelled an order.

## Moomoo competition paper account

- Identity: masked `****0101`, `account_type=2`, `market_id=100`, title `Moomoo x Qoder AI Paper Trading Agent Challenge`. Verified through a vault-attached Qoder Cloud Agent v4 session (17 Nov) and the local OAuth 2.1 + PKCE REST client (17–18 Nov).
- State: 100,000 USD cash/equity at session start; after the 18 Nov diagnostic round trip the account is flat with 99,991.02 USD cash. Margin buying power (200,000 USD) is deliberately ignored for sizing.
- Reads use a token with no `trade:write`; the separate execution token (18 Nov) has `trade:write` and submitted exactly two diagnostic orders, each behind a separate owner approval.

## Preflight and execution evidence

- `evidence/preflight/preflight-*.json` — four real read-only preflights (17–18 Nov), each recording quotes, account identity, a diagnostic QQQ BUY 1 risk evaluation and `submission_performed=false`, `order_endpoint_contacted=false`, `oauth_scope_trade_write=false`.
- `evidence/execution/execution-preflight-2026-11-18T025133Z.json` — supervised preview against the execution client; decision `DEFERRED_TO_NEXT_REGULAR_SESSION` (stale post-close quote); no submission.
- `evidence/execution/diagnostic-buy-candidate-2026-11-18T024420Z.json` — diagnostic candidate record; `submission_performed=false`, `durable_approval=false`.
- `evidence/execution/diagnostic-roundtrip-2026-11-18.json` — the completed supervised diagnostic: broker order `3115842` QQQ BUY 1 filled at 661.72 (14:33:36Z), broker order `3115920` QQQ SELL 1 filled at 654.73 (14:45:27Z); both reconciled `RECONCILIATION_OK` from broker rows and recorded `FILLED` in the ledger `submissions` table.

## Scheduler evidence

`evidence/scheduler/` holds the task registration XML, a Kernel-Power standby log explaining a missed 17 Nov timer, and validation exports. `data/scheduler-events.jsonl` records the run lifecycle (`ABANDONED` → `RUNNING` → `COMPLETED`, outcome `NO_TRADE`, `order_writes_enabled=false`). The timer-triggered catch-up run is genuine Task Scheduler evidence, not a manual invocation.

The AUTO_PAPER execution task `MooTrade Auto Paper Scheduler` (two daily triggers at 13:35Z/14:35Z; execution window 09:35–10:30 ET) was registered 18 Nov and validated with a two-minute one-shot trigger: it fired at 15:53:38Z via Task Scheduler, logged `SKIPPED_NOT_IN_WINDOW` (10:53 ET, outside the window) with `order_writes_enabled=false` and exited 0. The validation trigger was then removed; `evidence/scheduler/auto-task-2026-11-18.xml` and `auto-events-2026-11-18.jsonl` capture the final task and event record. The in-window path is covered by `tests/test_schedule_auto_paper.py` and `tests/test_auto_paper_run.py` (mock-driven). AUTO_PAPER was activated by explicit owner authorization on 18 November 2026 (16:03Z), so the first real in-window firing (19 Nov 2026, 09:35 ET / 14:35Z) will run the full execution phase: revalidate the pinned 18 Nov decision artifact, recompute the signal against a fresh broker snapshot, and submit only if the gate approves. The 13:35Z trigger on 19 Nov (08:35 ET in EST) remains outside the window and will be skipped.

## Historical research (never paper performance)

All under `evidence/research/`, all `HISTORICAL`:

| Study | Key result | Limitation |
|---|---|---|
| `momentum-v1` / `news-catalyst-v1` first evaluation | both below SPY buy-and-hold in dev and holdout windows | retired 18 Nov; small samples |
| `momentum-v1` deployable-limit re-evaluation | +0.09% vs +0.43% same-schedule SPY | sizing effect, not alpha |
| `etf-trend-baseline-2026-11-17` | +0.26% vs +1.31% matched SPY (7 monthly decisions) | one entry; no alpha claim |
| `volume-confirmed-relative-strength-v1` (pre-registered, Vibe-Trading engine) | 36.82% vs 20.47% exposure-matched SPY, but 107.48% equal-weight comparator | frozen rejection rule triggered; not deployed |
| `moomoo-tech-audit-2026-11-18` | provider pattern/indicator signals not auditable or not positive; candidate rejected | snapshot-only capabilities |
| `spy-directional` sanity check | -0.40% total, 0.59% max drawdown, 35 trades vs SPY +15.47% (12 Aug 2025 – 17 Nov 2026) | fixed rules, unoptimised; **not alpha evidence** |

Details and exact figures are in `docs/strategy-and-risk.md` (appendix) and each study's own artifacts.

## Automated test results

- Backend: **368 tests passed**, Python 3.14.5, 18 November 2026 (`pytest`). Covers contracts, account lock, risk policy, ledger append-only/kill-switch persistence, trading flow and mock broker failure injection, Moomoo REST/history/quote/order adapters (including the three live-contract regression tests from the first paper trade), supervised CLI guards, Qoder runner and tools, `spy-directional` signal/HOLD/CASH/reversal, leverage gate, ETF baseline, scheduler recovery, dashboard API, and the AUTO_PAPER execution phase (`test_auto_paper_run.py`: abstention, CASH/HOLD/BUY/SELL, duplicate and `UNKNOWN` paths) and its scheduler (`test_schedule_auto_paper.py`: window/DST gating, skip rules, `RUNNING` recovery, env scoping).
- Frontend: formatting regression tests via `node --test`, TypeScript `tsc --noEmit`, ESLint, `next build` — all passing on 18 November 2026.
- Reproduce: `python -m pytest` from the root; frontend commands in `frontend/README.md`.

## Currently blocked or unverified

1. **Broker-confirmed order and fill lifecycle partially observed:** market-order acknowledgement, full fill and post-trade reconciliation are now real broker evidence (18 Nov diagnostic); modify/cancel and partial-fill lifecycles remain unobserved.
2. **Account-exclusive `trade:write` scope is unverified**; the execution consent is treated as potentially account-wide.
3. **No demonstrated forward edge:** `spy-directional` has no filled forward paper sample; the historical sanity check underperformed SPY buy-and-hold. The 18 Nov diagnostic fills are connectivity evidence, not strategy performance.
4. **Python cannot reach the cloud Moomoo MCP** (vault credentials are injection-only); reads use the local REST client instead.
5. **Kill-switch operator command:** the kill switch is persisted and tested through the ledger API; no CLI command toggles it yet.
6. **AUTO_PAPER activated, first autonomous trade pending:** the owner authorized activation on 18 November 2026 (16:03Z); the durable pin binds the competition-account fingerprint, `spy-directional`, `SPY`/`SH`, `risk-v1` and the 5%/10%/30%/2% limits (`moomoo-auto-paper-status` verified). The activation command submitted no order; the first autonomous trade can only occur in the 19 Nov 09:35 ET execution window if the pipeline and gate approve. UPRO/SPXU remain disabled pending separate explicit approval.

## Regenerating the evidence summary

`backend/scripts/evidence_report.py` derives a sanitised summary from the ledger, Qoder artifacts, preflights, scheduler state and research results. It is read-only, refuses to run if `ORDER_WRITES_ENABLED=true`, and never contacts a broker. See `docs/reusability.md`.
