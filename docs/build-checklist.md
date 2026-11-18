# Build checklist and acceptance gates

**Deadline:** 30 November 2026, 23:59 SGT. **Trading window:** 17–28 November. One milestone should be fully accepted before starting nonessential work on the next.

## Stage 0 — 16 November: account and rule verification

- [x] Owner confirms Qoder credits, Cloud Agent entitlements and competition account (`****0101`, 100,000 USD).
- [ ] Discover actual competition MCP tool registry, permissions, account fingerprint and rate limits.
- [ ] Confirm OSS reuse and submission requirements with organisers/handbook.
- [ ] Record unknowns in `docs/integrations.md`; do not guess endpoint paths.

**Gate:** documented verified integration facts and an explicit list of unresolved blockers.

## Stage 1 — 17–18 November: read-only vertical slice

- [x] Minimal Python project, Pydantic contracts and mock broker fixture.
- [x] Read-only MCP quote, account, positions and order-history queries through actual Qoder cloud context. Verified 17 November in vault-attached v4 session `sess_00vr5lar7i5mo93aq1j5`; sessions without the vault returned HTTP 401.
- [ ] Python adapter to cloud MCP runtime transport; vault secrets are injection-only and cannot be read by Python. Read access is instead provided by the separate local REST OAuth client.
- [x] Local REST OAuth 2.1 + PKCE client with DPAPI token storage, read-only allowlist (GET account data plus two POST quote reads) and exact competition-account verification; real cash, positions, open orders and paginated history read 17 Nov.
- [x] Save redacted provider response shapes and timestamps in `docs/integrations.md` (account list, cash, positions, empty order history, QQQ quote, market state).
- [x] SQLite event ledger; mock broker snapshots are verified in tests. Real broker-snapshot persistence was exercised through the local REST read transport.
- [x] Account identity and paper-only routing checks (account lock plus `MoomooReadOnlyBroker` tests; cloud read returned the exact competition account).
- [x] Read-only adapter with a four-tool allowlist, strict parsing, fail-closed validation, cash-only buying power and no order-submission method.
- [x] Prove no order-capable MCP tool is reachable from the restricted cloud agent session: v4 exposes only `Read`; all ten order tools are `always_deny` and none registered; no shell/web tools; no order endpoint contacted.
- [x] Verify Qoder custom client-side tool protocol as a possible read-only bridge (agent pauses with `requires_action`; client returns `user.custom_tool_result`). Protocol only; not implemented, because order submission must stay outside every agent session.

**Gate:** read-only cloud and local REST verification met. Keep order writes disabled. The Python-to-MCP runtime bridge remains missing, but the separate REST client provides live Python read access; no order path exists.

## Stage 2 — 19–20 November: safe order pipeline

- [x] Freeze `momentum-v1` signals/exit rules (documented in `docs/strategy-and-risk.md`; no parameter search).
- [x] Deterministic research pipeline for `momentum-v1` and `news-catalyst-v1` with evidence IDs, signal strength and explicit buy/skip reasons.
- [x] Historical evaluation against matched SPY/QQQ/IWM and cash baselines with no look-ahead; results and limitations in `evidence/sample-reports/decision-report-2026-11-17.md`.
- [x] Dry-run proposal → `RiskGate.evaluate` demonstration covering approved hypothetical proposals and `R004`/`R007`/`R010`/`R014` rejections. No broker call and no order submitted.
- [x] Deterministic risk gate, account refresh, kill switch, idempotency, first-order approval and broker state machine (local/mock).
- [x] Complete mandatory mock failure tests listed in strategy-and-risk document.
- [x] Strategy review against a catalyst alternative and exposure-matched SPY (18 November 2026); no defensible alpha found, rules unchanged and `NO_TRADE` retained (`docs/strategy-and-risk.md`).
- [x] Moomoo technical-signal capability audit and forward observation (18 November 2026): pattern/polarity are snapshot-only, unusual-technical POST is refused, capital flow adds no positive forward information, and the candidate is rejected (`docs/strategy-and-risk.md`).
- [x] Deployable-limit `momentum-v1` re-evaluation (18 November 2026): 10% per position, 30% gross, whole shares, same 370-bar fixture. Return `+0.09%`, max drawdown `1.22%`, average exposure `6.62%`; it lost to same-schedule SPY (`+0.43%`). No rule or parameter change.
- [x] Pre-registered one fixed stock-selection hypothesis using reconstructable OHLCV only (18 November 2026). Not evaluated, not deployed, no Moomoo snapshot labels as gates (`docs/strategy-and-risk.md`).
- [x] Execution-time quote freshness, symbol and regular-session preflight; strict parsing and fail-closed tests.
- [x] Documented simulated-order payload, bounded `text` correlation tag, strict provider-status mapping and `UNKNOWN` reconciliation across today/history/positions; adapter refuses submission in both flag states and the operator preview never submits.
- [x] Real read-only preflight against the competition paper account for SPY/QQQ/IWM: fresh quote/session/account checks, diagnostic QQQ BUY 1 preview, RiskGate evaluation and sanitized recorded evidence. Failed closed on stale premarket quotes and closed regular session; `submission_performed=false`, `order_endpoint_contacted=false`.
- [ ] Obtain owner approval for a controlled small paper order.
- [ ] Submit, query, reconcile and store one genuine broker response, or document why unavailable.

**Gate:** traceable proposal → policy → verified broker outcome, with no opportunity to bypass limits.

## Stage 3 — 21–23 November: agents and interface

- [ ] Four bounded Qoder agent roles with structured output validation.
- [ ] Real Qoder run IDs, tool calls and handoffs in ledger.
- [x] Scheduled read/research workflows with bounded retries. *(Task Scheduler repaired and verified 18 November 2026: wake/start-when-available, two UTC triggers for both ET DST offsets, catch-up, OS lock and durable idempotent state. A genuine timer-triggered catch-up run completed `NO_TRADE`; the one-time validation trigger was removed.)*
- [x] Next.js dashboard: Overview, AI Agent Activity, Portfolio & Orders, Risk Centre, Performance Analytics and Audit Log. Adapted from the cloned Shadcn Fintech template with MIT attribution.
- [x] Typed GET-only FastAPI dashboard API with bearer/loopback auth, 405 on writes, stale/empty/disconnected/error states and PAPER/HISTORICAL/LOCAL provenance labels; paper-account performance shown as unavailable rather than fabricated.

**Gate:** judge can inspect the end-to-end process without viewing a terminal.

## Stage 4 — 24–28 November: paper evaluation and risk demonstrations

- [ ] Execute schedule only under verified safe settings and permitted hours.
- [ ] Reconcile account after submissions and restarts.
- [ ] Track actual decisions, fills, abstentions, errors and equity.
- [ ] Compare performance against matched benchmark and cash baseline.
- [ ] Run negative-case mock tests and capture evidence of pre-broker rejection.
- [ ] Record incidents/limitations and version any legitimate strategy changes.

**Gate:** all presented performance and order claims are traceable to evidence.

## Stage 5 — 29–30 November: final submission

- [ ] Pin dependencies and verify repository licence/attribution.
- [ ] Run fresh checkout/install smoke test and all unit tests.
- [ ] Check no active credentials in Git history, screenshots, logs or slides.
- [ ] Save redacted evidence and recorded replay for market-closed presentations.
- [ ] Create **Qoder-generated** deck; explain success, failure and limitations.
- [ ] Submit runnable package and deck; record confirmation before 23:59 SGT.

**Gate:** a reviewer can install, run mocks, inspect authentic paper evidence and reproduce at least one safe demonstration.

## No-go conditions

Do not enable order writes when the competition account is unverified, a risk test fails, reconciliation is broken, quote age is unknown, active exposure is unknown, kill switch cannot persist, order-capable MCP tools remain reachable from an agent session, or MCP permissions might reach live capital.

## How to report progress after each stage

`Done` / `Evidence` / `Tests passed` / `Still blocked` / `Next milestone`. A checkmark is earned only by demonstrated evidence, not by generated code alone.
