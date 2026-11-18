# MooTrade reuse, strategy and Qoder decision report

**Date:** 17 November 2026  
**Deadline:** 30 November 2026, 23:59 SGT  
**State:** PAPER / RESEARCH ONLY. `ORDER_WRITES_ENABLED=false`. No order, cancellation, modification or automatic execution was requested or performed.

## Decision

1. **Reject `sec-earnings-relative-momentum-v1`.** The single frozen experiment lost money in development and again in the chronological holdout, underperforming cash, SPY and QQQ. Its small drawdown resulted from approximately 4% average exposure, not demonstrated risk-adjusted alpha. No parameters will be tuned after seeing these results.
2. **Do not claim any current strategy has proven alpha.** Use `momentum-v1` only as the simplest frozen baseline for a supervised infrastructure validation order if it naturally produces a signal and every broker/risk gate passes. `news-catalyst-v1` remains a research comparator with sparse, asymmetric historical news coverage.
3. **Build one read-only Qoder vertical slice next:** Coordinator → Market Researcher → Independent Risk Auditor → deterministic Python gate → sanitized decision report. Use two custom client-side tools and the existing research/risk code. Do not expose any Moomoo order tool to an agent.
4. **Do not enable paper writes yet.** The shortest safe order route still requires a supported non-LLM Python-to-Moomoo transport, fresh trusted broker data, verified order-history handling, and explicit owner approval bound to one small order key.

## 1. Ranked reuse from the actual workspace

The installed source, tests, manifests and licences were inspected. Revisions were Vibe-Trading `a8d815d17ec054a34dbdfc7ce8d1d9972566b709`, AI Hedge Fund `5c553b5222044f6a5527bd377b4104c50ee0ad28` (`2.7.2`), and TradingAgents `9fa1196fffbcfd9de5146d2dd2869df84ab99838` (`0.7.1`). None was installed wholesale or merged into MooTrade.

| Rank | Reuse | Actual files | Decision and integration cost |
|---|---|---|---|
| 1 | **Vibe-Trading: evaluation and validation concepts** | `agent/backtest/metrics.py`, `validation.py`, `engines/base.py`, `loaders/sec_edgar_client.py`, `loaders/_http.py` | Reuse turnover metrics, point-in-time event alignment, bounded/throttled acquisition, bootstrap and path-diagnostic concepts. MIT. Medium cost if functions are extracted because of pandas/NumPy/SciPy coupling; no full engine adoption. |
| 2 | **AI Hedge Fund: typed signals, abstention and provenance** | `hedge_fund/models.py`, `signals/base.py`, `signals/llm_agent.py`, `data/protocol.py`, `pipeline/models.py` | Carry model/version, as-of time, horizon, rationale, components, content hashes and explicit abstention into sanitized tool/report schemas. Preserve the distinction between empty data and provider failure. MIT. Low conceptual cost; do not adopt its data provider or another risk authority. |
| 3 | **TradingAgents: structured rationale and safe report rendering** | `tradingagents/agents/schemas.py`, `reporting.py`, `report_html.py` | Reuse thesis/invalidation fields and restrictive HTML/CSP ideas if HTML reports are later needed. Apache-2.0. Low conceptual cost. Avoid its orchestration and branded reporting stack. |

### Explicitly avoid

- **Vibe full runner/engine:** `agent/backtest/runner.py`, `engines/global_equity.py`, `loaders/local_loader.py`, and `loaders/rsshub_events.py` bring a large dependency/config surface and do not solve MooTrade's missing broker transport. Generated-code AST checks are not a complete sandbox.
- **Vibe validation misinterpretation:** `monte_carlo_test` permutes observed trade order; it is not a random-entry/no-signal null. `walk_forward_analysis` is a consistency diagnostic, not genuine OOS training/testing. Neither was used as evidence here.
- **AI Hedge Fund portfolio/risk stack:** `backtesting/fund.py` uses different next-bar assumptions; `risk/limits.py` would duplicate MooTrade's final deterministic authority; `signals/pead.py` depends on an external Financial Datasets feed.
- **TradingAgents evaluation/debates:** `tradingagents/backtest.py` scores decision cells against later returns rather than simulating portfolio return, exposure, turnover and costs. LLM risk debaters are not deterministic controls.

No external source code was copied in this milestone, so no new notice was required. Any later copied or substantially adapted MIT/Apache-2.0 code must retain its licence and attribution. Market-data/provider terms remain separate from code licences.

## 2. Frozen catalyst-confirmed momentum evidence

### Data and protocol

- Fixed current-liquid universe: AAPL, MSFT, NVDA, AMZN, GOOGL, META, AVGO, TSLA, JPM, XOM, LLY, COST.
- 76 original SEC 8-K Item 2.02 events, exact `acceptanceDateTime`, no observed Item 2.02 amendments and no timestamp exclusions in the normalized window. JPM primary plus six linked supplemental submission files close its high-filing-volume gap back to 22 April 2025.
- Twelve Moomoo `quote_cur_kline` responses plus the existing SPY/QQQ/IWM fixture: 370 common sessions per symbol, 29 May 2025–16 November 2026, no duplicates/missing common sessions, valid OHLCV, `autype=1` forward ex-dividend adjustment.
- Original Item 2.02 eligible for five completed sessions; positive five-session return, SPY outperformance, stock and SPY above their 20-session SMAs; at most three 10%-of-equity positions; ten-session maximum hold; earlier trend/amendment exit.
- Signals use completed information and execute at the next common-session open with 2 bps adverse cost per side. One entry per accession per window; no pyramiding.
- Development: 30 June 2025–31 March 2026. Untouched chronological holdout: 1 April–16 November 2026. Both start with 100,000 USD cash and use the prior close for their first signal.
- Full rules and limitations were written to `evidence/research/catalyst-momentum-2026-11-17/protocol.json` before returns were calculated. Source hashes, normalized events/prices, daily equity and every trade are in the same directory.

### Results

Returns are net of modelled entry/exit costs. Exposure is average daily close gross market value/equity. Turnover is gross raw-open execution notional/average daily close equity. Trade count means entries; all catalyst trades were closed in each window.

| Window | Strategy/benchmark | Return | Avg exposure | Turnover | Costs USD | Max drawdown | Trades |
|---|---|---:|---:|---:|---:|---:|---:|
| Development | **SEC catalyst momentum** | **-2.41%** | 3.99% | 3.59x | 70.75 | 2.81% | 18 |
| Development | SPY buy/hold | +5.32% | 100% | 0.93x | 20.00 | 9.13% | 1 |
| Development | QQQ buy/hold | +4.68% | 100% | 0.92x | 20.00 | 12.19% | 1 |
| Development | Cash | 0.00% | 0% | 0.00x | 0.00 | 0.00% | 0 |
| Development | `momentum-v1` | -2.84% | 68.95% | 25.87x | 525.71 | 9.64% | 13 |
| Development | `news-catalyst-v1` | 0.00% | 0% | 0.00x | 0.00 | 0.00% | 0 |
| Holdout | **SEC catalyst momentum** | **-1.25%** | 4.49% | 2.59x | 51.82 | 2.57% | 13 |
| Holdout | SPY buy/hold | +13.14% | 100% | 0.88x | 20.00 | 5.92% | 1 |
| Holdout | QQQ buy/hold | +13.78% | 100% | 0.83x | 20.00 | 14.82% | 1 |
| Holdout | Cash | 0.00% | 0% | 0.00x | 0.00 | 0.00% | 0 |
| Holdout | `momentum-v1` | +2.50% | 62.26% | 19.92x | 439.01 | 11.68% | 10 |
| Holdout | `news-catalyst-v1` | +1.56% | 45.91% | 13.98x | 300.27 | 11.03% | 7 |

Catalyst win rates were 27.78% in development and 23.08% in holdout. Sharpe inference is withheld because each window has fewer than 30 closed catalyst trades and sparse exposure. The machine output contains descriptive daily Sharpe values (-1.20 and -0.94), but they are not statistically meaningful and support no alpha claim. Vibe bootstrap and Monte Carlo diagnostics were therefore not run.

The legacy comparisons reuse the existing `screen` rules and next-open execution but add an explicit initial-equity point, turnover and cost reporting. The existing full-window evaluator computes total return from its first post-entry close, omitting first-day P&L; the study does not. A cross-check produced identical legacy trade dates and final equity, so this is a metric-baseline distinction, not a different strategy.

### Interpretation and limitations

This is a **negative result**, not a mandate to search hundreds of variants. Item 2.02 is a deterministic earnings-filing proxy, not every material news event. The current-liquid universe creates survivorship/selection bias; 370 sessions and sparse earnings events cover limited regimes. Forward-adjusted OHLC is not a total-return series. Fractional shares, no spread/market-impact model beyond 2 bps, and retrospective provider corrections remain limitations. The previous news strategy's zero development trades illustrate inadequate historical news coverage, not proof that no catalysts occurred.

## 3. Minimum native Qoder architecture

Use three logical Cloud Agents coordinated by a local `qca-sdk` runner. The runner, not an LLM, controls session order and artifact persistence.

| Role | Tools and data | Output | Explicit prohibition |
|---|---|---|---|
| **Coordinator** | No Moomoo tools, no Vault, no shell/web/write tools. Receives only run ID, strategy allowlist and sanitized artifacts from the runner. | Validated run request and final human-readable summary. | Cannot create an approval, change limits, call a broker or convert prose into an order. |
| **Market Researcher** | One custom tool, `research_market(run_id, strategy_version)`. The local handler maps the server-issued run ID to pinned Moomoo evidence and calls existing `screen`/`build_proposal`. | Sanitized `ResearchSnapshot`, optional typed `TradeProposal`, evidence IDs, data timestamps and explicit abstention. | No arbitrary path/URL/command input, account data, credentials, Moomoo order tools or direct risk approval. |
| **Independent Risk Auditor** | One custom tool, `evaluate_proposal(run_id, proposal)`. The local handler validates the typed proposal and calls `RiskGate.evaluate` with locally constructed trusted dry-run quote/account/control inputs. | Immutable `RiskDecision`, rule IDs, approved quantity, policy/data timestamps and a separate critique. | Cannot modify the gate outcome, approve its own prose, select an account or access any order credential/tool. |

### Handoff and audit sequence

1. Runner creates a server-side run ID and binds it to an allowlisted evidence manifest and `DRY_RUN` mode.
2. Coordinator starts the run; the runner creates a genuine Researcher session and streams events.
3. `research_market` pauses the session with `requires_action`; the local handler executes only the fixed read-only function and returns `user.custom_tool_result`.
4. Runner validates Researcher output and starts a separate Risk Auditor session. The auditor calls `evaluate_proposal`; the Python gate remains the only decision authority.
5. Runner appends research/proposal/policy/agent events with actual Qoder session IDs to the existing ledger and writes a sanitized Markdown/JSON decision report. The Coordinator may explain it but cannot alter it.
6. Any validation, SDK, tool or data failure becomes `AGENT_ERROR`/abstention. No failure becomes a neutral market signal or an approval.

Custom tools do not support `permission_policy`; the handler is therefore the security boundary. Use `additionalProperties=false`, server-generated IDs, fixed strategy/file allowlists, input size/quantity limits, output redaction and no broker imports. Cloud sessions need no repository mount or Vault for the pinned historical milestone. Credentials for the local SDK remain in supported secret storage/environment and are never placed in prompts or artifacts.

This milestone uses **genuine timestamped Moomoo historical evidence**, not a claim of a current broker snapshot. A current tradable decision still requires independently refreshed trusted quote/account/order data; agent-relayed JSON is not trusted broker evidence.

## 4. Blockers and required fixes

| Priority | Blocker | Required fix and acceptance evidence |
|---|---|---|
| P0 | Python cannot use the Vault-injected cloud MCP credential. | Obtain an organiser/Qoder-supported non-LLM transport or separately scoped credential path. Demonstrate the existing read-only adapter resolving the exact account fingerprint and reading fresh quote/account/positions/orders. Never extract Vault secrets or route writes through an agent. |
| P0 | Custom-tool bridge is documented but not implemented. | Add the two fixed handlers and SDK runner; test malicious paths/commands, malformed proposals, stale data and SDK failure. Record actual sanitized Cloud session IDs and observed custom-tool round trips. |
| P0 | Nonempty Moomoo order-history response and eligible order contract remain unobserved. | Verify official permitted order types/instruments and parse a real or organiser-supplied nonempty response. Unknown fields/statuses must fail closed; reconcile broker status rather than inferring fills. |
| P0 | Owner has not approved a first paper order. | After all technical gates pass, request explicit approval for one specific small `client_order_key`, proposal and quantity. Approval does not bypass freshness, account lock, kill switch or exposure checks. |
| P0 | Historical fixtures cannot authorize a current order. | Require regular-session eligibility, fresh trusted quote/account data and current positions/open orders. If stale, ambiguous or no natural signal, record `NO TRADE`; never force a trade for evidence. |
| P1 | Raw cloud tool events can contain full account IDs. | Store only sanitized summaries/hashes in the repository, screenshots and deck. Do not export raw session event logs. |
| P1 | Dashboard and scheduling are incomplete. | Add only after the genuine read-only run and order safety gates. Show broker-backed state, staleness and PAPER labels; keep mock design data separate. |

## 5. Shortest safe route to one paper order

1. Keep all agent sessions read-only and complete the genuine Cloud decision run.
2. Establish the supported direct transport and pass exact account-lock, fresh-data, positions/orders and restart/reconciliation tests.
3. Freeze `momentum-v1` for this plumbing validation; do not substitute the rejected equity catalyst strategy.
4. At a permissible session, run the deterministic signal. If no signal, stop with a broker-backed no-trade report.
5. If a signal exists, persist the proposal, policy outcome and unique key before any write. Obtain explicit owner approval bound to that first small order.
6. Let only the separately scoped Python executor submit once. Record acknowledgement, query broker status, reconcile fills/positions/cash, and append all events. An acknowledgement is not a fill.
7. On timeout/ambiguity mark `UNKNOWN`, block further submissions and reconcile; never blindly retry. Kill switch blocks new orders and persists; it does not silently liquidate.

## 6. Prioritized schedule to 30 November

| Date | Milestone | Verification gate |
|---|---|---|
| **17 Nov** | Complete repository audit and frozen catalyst study; reject failed strategy. | 108 tests pass; reproducible metrics/trades/source hashes saved; writes disabled. |
| **18 Nov** | Implement two custom-tool handlers and local SDK runner; least-privilege three-agent configuration. | Handler/negative-path tests; mocked `requires_action` round trip; no order imports/tools. |
| **19 Nov** | Execute genuine read-only Cloud Coordinator → Researcher → Risk Auditor run. | Actual session IDs, observed tool events and sanitized decision report; fail-closed redaction review. |
| **20 Nov** | Establish supported direct Moomoo read transport and current preflight/reconciliation. | Exact account, fresh timestamps, nonempty order schema or documented external blocker; no writes. |
| **21 Nov** | Request/run one supervised small paper order only if all gates and a natural baseline signal pass. | Owner-bound approval, broker order ID/status, reconciled ledger; otherwise documented `NO TRADE`/blocker. |
| **22–23 Nov** | Persist Qoder provenance and build the minimal read-focused FastAPI/Next.js dashboard. | Broker-backed overview/decisions/orders/risk, PAPER/stale states, no exposed secrets. |
| **24–27 Nov** | Scheduled read-only research, risk drills and only explicitly authorised paper operation. | Restart, stale quote, duplicate, unknown order, kill-switch and reconciliation evidence; actual benchmark series. |
| **28 Nov** | Freeze code/strategy and package evidence. | Full tests and fresh-install smoke test; licence/secret scan; no raw cloud events. |
| **29 Nov** | Generate submission deck with Qoder and finish reproduction docs. | Deck distinguishes mock, historical research and actual paper evidence; limitations included. |
| **30 Nov** | Final verification and submission before 23:59 SGT. | Runnable package, complete checklist and recorded submission confirmation. |

Do not displace P0 transport, risk or reconciliation work with UI polish, debates, ML research or extra agents.

## 7. Exact files

### Reuse unchanged for the read-only Cloud milestone

- `backend/app/models/contracts.py` — typed proposals, quotes, account/control and risk decisions.
- `backend/app/research/data.py`, `strategy.py`, `dryrun.py` — point-in-time Moomoo evidence, frozen screening/proposal and gate invocation.
- `backend/app/risk/policy.py` — final deterministic policy authority.
- `backend/app/ledger/store.py` — append-only decisions, agent provenance and persistent controls.
- `backend/app/broker/account_lock.py`, `moomoo_readonly.py` — exact account resolution and four-tool read allowlist when direct transport becomes available.
- `backend/tests/fixtures/moomoo_daily_bars_2026-11-16.json`, `moomoo_news_2026-11-17.json` — pinned, genuine timestamped historical research inputs.
- `docs/integrations.md`, `docs/architecture.md`, `docs/strategy-and-risk.md` — verified boundaries and frozen policy.

### Add for the focused milestone

- `backend/app/qoder_tools.py` — only `research_market` and `evaluate_proposal`, typed fixed-allowlist handlers with sanitized outputs and no broker-write imports.
- `backend/scripts/qoder_readonly_run.py` — minimal `qca-sdk` session/event loop, three-session handoff, redacted artifact and ledger persistence.
- `backend/tests/test_qoder_tools.py` — schema/allowlist, no-trade, stale/oversized rejection, malformed input and redaction tests.
- `backend/tests/test_qoder_readonly_run.py` — fake-SDK `requires_action` continuation, session failure and no-order-call tests.
- `evidence/qoder/` — sanitized actual run summaries and decision reports, never raw authenticated event dumps.

Change `pyproject.toml` only to pin the verified Qoder SDK dependency needed by the runner. Update `docs/integrations.md` and `docs/architecture.md` only with observed run IDs, actual tool shapes and implemented status. Do not change `TradingService`, enable `ORDER_WRITES_ENABLED`, or add a broker-write adapter during this milestone.

### Research artifacts added in this milestone

- `backend/scripts/catalyst_study.py` — isolated normalizer/simulator; existing production ETF universe and strategy remain unchanged.
- `backend/tests/test_catalyst_study.py` — next-open timing, post-close filing, three-position/tie-break and amendment-exit tests.
- `evidence/research/catalyst-momentum-2026-11-17/` — frozen protocol, normalized provenance, results, equity curves, trades and run output.

## Verification record

- `.venv/Scripts/python -m pytest -q` — **108 passed** (104 pre-existing plus 4 focused research tests).
- `PYTHONIOENCODING=utf-8 .venv/Scripts/python backend/scripts/catalyst_study.py` — completed with 76 original events, 0 amendments, 0 excluded timestamps and 370 common sessions.
- Legacy cross-check — identical trade dates and final equity to the existing simulator; explicit initial-equity return baseline documented above.
- External framework test suites and full Vibe engine were **not run**; no wholesale dependencies were installed.
- No Moomoo order tool or automatic execution path was invoked.
