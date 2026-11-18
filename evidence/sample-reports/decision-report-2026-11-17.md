# MooTrade decision report — PAPER / DRY RUN

> **No order was submitted. Order writes remain disabled.** This report is a deterministic research and risk-policy demonstration, not broker execution evidence and not a claim of actual investment returns.

Generated: `2026-11-18T02:08:38.098959Z`  
Decision input: last fully completed session `2026-11-16` at the conservative `21:00 UTC` close timestamp.  
Account identity: synthetic local dry-run fingerprint; the account-lock rule is a fixture check, not broker evidence.

## 1. Data provenance and safety state

- **Market bars:** `Moomoo MCP read-only session` via `quote_cur_kline`, 370 daily bars per symbol, 2025-05-29 to 2026-11-16, forward-adjusted (`autype=1`). Source fetch: `2026-11-17T06:30:00Z`.
- **News metadata:** `Moomoo MCP read-only session` via `news_search`; 152 relevant headlines with provider publish timestamps. Coverage: SPY 2026-04-27 to 2026-11-17, QQQ 2026-10-06 to 2026-11-16, IWM 2026-02-10 to 2026-11-16.
- **Account values used for dry-run:** `$100,000` cash/equity and zero positions/orders, consistent with the read-only Moomoo session verified on 17 November 2026. The dry-run `AccountSnapshot` is a flat hypothetical snapshot timestamped at the decision time; it is not a broker snapshot at that historical timestamp.
- **Actual execution controls:** `ORDER_WRITES_ENABLED=false`; no kill switch or circuit breaker was changed; no first-order approval was consumed. The approval examples use an ephemeral dry-run `ControlState` only so the deterministic gate can be exercised.
- **No broker call:** the research path calls `RiskGate.evaluate` directly. It does not call `TradingService.execute`, the mock broker or any Moomoo order tool.

## 2. Strategy rules evaluated

### `momentum-v1` (frozen from `docs/strategy-and-risk.md`)

- Broad-market regime: `SPY` completed close above its trailing 20-session SMA.
- Candidate: close above its own 20-session SMA and 5-session return positive.
- Selection: highest 5-session return; ticker alphabetical tie-break.
- Exit assumption for the research simulation: completed close below the held ETF's 20-session SMA.
- Warmup: 21 completed sessions; otherwise abstain.

### `news-catalyst-v1`

- Same regime, price-trend and selection rules as `momentum-v1`.
- Additional entry filter: at least one relevant headline published in the prior 72 hours and a positive recency-weighted headline sentiment score. The score is a transparent keyword lexicon over title and abstract, not an LLM judgement.
- Headlines are used only when `publish_time <= decision_time`.

## 3. Latest completed-session decision

### `momentum-v1` — NO TRADE

Regime: SPY close 739.95 below 20-session SMA 757.6950.  
Outcome reason: Broad-market regime filter is negative; abstain from new entries

| Symbol | Close | 20-session SMA | 5-session return | Regime | News (72h) | News score | Outcome | Reasons |
|---|---:|---:|---:|---|---:|---:|---|---|
| IWM | $272.94 | $278.46 | -3.39% | negative | 1 | 0.000 | SKIP | Broad-market regime negative (SPY below its 20-session SMA); Close 272.94 is not above its 20-session SMA 278.4590; 5-session return -3.3875% is not positive |
| QQQ | $661.75 | $692.62 | -2.59% | negative | 2 | 0.409 | SKIP | Broad-market regime negative (SPY below its 20-session SMA); Close 661.75 is not above its 20-session SMA 692.6180; 5-session return -2.5907% is not positive |
| SPY | $739.95 | $757.70 | -1.69% | negative | 13 | 1.082 | SKIP | Broad-market regime negative (SPY below its 20-session SMA); Close 739.95 is not above its 20-session SMA 757.6950; 5-session return -1.6926% is not positive |

### `news-catalyst-v1` — NO TRADE

Regime: SPY close 739.95 below 20-session SMA 757.6950.  
Outcome reason: Broad-market regime filter is negative; abstain from new entries

| Symbol | Close | 20-session SMA | 5-session return | Regime | News (72h) | News score | Outcome | Reasons |
|---|---:|---:|---:|---|---:|---:|---|---|
| IWM | $272.94 | $278.46 | -3.39% | negative | 1 | 0.000 | SKIP | Broad-market regime negative (SPY below its 20-session SMA); Close 272.94 is not above its 20-session SMA 278.4590; 5-session return -3.3875% is not positive; News catalyst is not positive (score 0.0000) |
| QQQ | $661.75 | $692.62 | -2.59% | negative | 2 | 0.409 | SKIP | Broad-market regime negative (SPY below its 20-session SMA); Close 661.75 is not above its 20-session SMA 692.6180; 5-session return -2.5907% is not positive |
| SPY | $739.95 | $757.70 | -1.69% | negative | 13 | 1.082 | SKIP | Broad-market regime negative (SPY below its 20-session SMA); Close 739.95 is not above its 20-session SMA 757.6950; 5-session return -1.6926% is not positive |

The latest session is a deliberate **abstention** for both strategies: the broad-market regime filter is negative, so no eligible candidate exists. The gate is not asked to approve a no-trade proposal; the absence of a proposal is recorded as a no-trade decision.

## 4. Accepted hypothetical proposals

These examples use a historical decision time and the same frozen rules. They show that a signal can pass the existing deterministic gate. **No order was placed.**

| Strategy | Decision time | Symbol | Qty | Quote | Notional | Risk | Approved qty | Rules |
|---|---|---|---:|---:|---:|---|---:|---|
| momentum-v1 | 2026-10-28T21:00:00+00:00 | IWM | 17 | $281.29 | $4,781.93 | APPROVE | 17 | none |
| news-catalyst-v1 | 2026-10-08T21:00:00+00:00 | QQQ | 6 | $747.58 | $4,485.48 | APPROVE | 6 | none |

**Thesis and invalidation for the accepted examples**

- `momentum-v1`: IWM closed at 281.29, above its 20-session SMA 277.2690, with a 1.7397% 5-session return. SPY close 772.31 above 20-session SMA 770.8955.
  Invalidation: Close below the 20-session SMA or a daily drawdown limit breach.
- `news-catalyst-v1`: QQQ closed at 747.58, above its 20-session SMA 735.7220, with a 0.7479% 5-session return. SPY close 773.93 above 20-session SMA 767.2630. 1 positive of 1 relevant headlines (sentiment score 0.2091).
  Invalidation: Close below the 20-session SMA or a daily drawdown limit breach.

## 5. Rejected or blocked proposals

| Scenario | Symbol | Qty | Risk | Rules |
|---|---|---:|---|---|
| stale quote (10-minute-old decision input) | IWM | 17 | REJECT | R007 |
| stale quote (10-minute-old decision input) | QQQ | 6 | REJECT | R007 |
| oversized quantity (20% of equity versus 10% limit) | IWM | 71 | REJECT | R004 |
| oversized quantity (20% of equity versus 10% limit) | QQQ | 26 | REJECT | R004 |
| production control: order writes disabled | IWM | 17 | REJECT | R010 |
| first paper order without owner approval | IWM | 17 | REJECT | R014 |

The stale-quote case fails `R007`; the 20%-of-equity case fails `R004`; disabled writes fail `R010`; a missing first-order approval fails `R014`. No rejection reaches a broker method.

## 6. Historical strategy evaluation

Research simulation only: 100% long/cash, fractional shares, 2 bps cost per side, no leverage or shorting, and no application of the 10%/30% live exposure caps. This is a signal-quality study, not the return of the risk-gated paper account.

| Strategy / baseline | Period | Signals | Closed trades | Total return | CAGR | Ann. vol | Sharpe | Max drawdown | Exposure | Win rate | Avg trade |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| momentum-v1 (full fixture) | 2025-06-27 to 2026-11-16 | 23 | 23 | -0.41% | -0.29% | 12.65% | 0.04 | 11.68% | 65.90% | 26.09% | +0.03% |
| momentum-v1 (news window) | 2026-02-10 to 2026-11-16 | 13 | 13 | -3.77% | -4.86% | 11.77% | -0.37 | 11.68% | 53.37% | 15.38% | -0.22% |
| news-catalyst-v1 (news window) | 2026-02-10 to 2026-11-16 | 7 | 7 | +1.56% | +2.03% | 10.45% | 0.25 | 11.03% | 37.82% | 28.57% | +0.32% |
| SPY buy-and-hold (full fixture) | 2025-06-27 to 2026-11-16 | 1 | 0 | +19.83% | +13.91% | 12.97% | 1.07 | 9.13% | 100.00% | n/a | n/a |
| SPY buy-and-hold (news window) | 2026-02-10 to 2026-11-16 | 1 | 0 | +6.23% | +8.17% | 14.46% | 0.62 | 9.27% | 100.00% | n/a | n/a |
| QQQ buy-and-hold (news window) | 2026-02-10 to 2026-11-16 | 1 | 0 | +7.34% | +9.64% | 23.08% | 0.52 | 14.82% | 100.00% | n/a | n/a |
| IWM buy-and-hold (news window) | 2026-02-10 to 2026-11-16 | 1 | 0 | +1.64% | +2.14% | 18.89% | 0.21 | 11.36% | 100.00% | n/a | n/a |
| cash (news window) | 2026-02-10 to 2026-11-16 | 0 | 0 | +0.00% | +0.00% | 0.00% | n/a | 0.00% | 0.00% | n/a | n/a |

**No-look-ahead convention:** a signal is computed only from bars whose conservative 21:00 UTC availability timestamp is at or before the decision time. Orders are assumed to execute at the next session's open; exits also occur at the next open after a close below the 20-session SMA. News is filtered by provider `publish_time <= decision_time`. Future bars are never used to construct a signal.

## 7. Limitations

- The sample is about 17 months of daily bars for three ETFs and one market regime. It cannot establish durable alpha or statistical significance.
- The news archive is sparse and asymmetric: QQQ headlines begin only on 2026-10-06, while SPY and IWM have earlier coverage. Headlines are not a complete news feed, and the keyword sentiment score is a crude proxy.
- The simulation ignores dividends, taxes, borrow, corporate actions beyond the provider's forward adjustment, market impact, queue position, partial fills and any Moomoo-specific execution constraints.
- The backtest enters at the next open but the live system would require a fresh quote and account snapshot; the gate's 300-second quote and 60-second account freshness rules still apply.
- `news-catalyst-v1` was defined before this evaluation, but it is a first draft. No parameter search or retrofitting was performed.

## 8. Reproduce

From the repository root, with the local fingerprint supplied through the environment (never printed):

```bash
.venv/Scripts/python -m app.research.demo \
  --bars backend/tests/fixtures/moomoo_daily_bars_2026-11-16.json \
  --news backend/tests/fixtures/moomoo_news_2026-11-17.json \
  --out evidence/sample-reports/decision-report-2026-11-17.md
```

If `COMPETITION_ACCOUNT_FINGERPRINT` is not set, the demo uses a clearly labelled local dry-run fingerprint; the account-lock rule is then a fixture check, not broker evidence.
