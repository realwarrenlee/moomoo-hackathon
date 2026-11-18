# Vibe-Trading integration verdict (Phase 4)

**PAPER / HISTORICAL RESEARCH — NO BROKER, APPROVAL OR ORDER**

Assessment date: 2026-11-18. Vibe-Trading `0.1.19`, pinned commit
`a8d815d17ec054a34dbdfc7ce8d1d9972566b709`, MIT licence with bundled Qlib
factor notices. Research only; `ORDER_WRITES_ENABLED=false` throughout.

## Verdict

**Recommendation B — use Vibe-Trading as a separate, pinned research tool.
Do not embed it in the MooTrade production research, risk or execution path.
Retain MooTrade's existing deterministic implementation.**

This is the smallest functional approach supported by the evidence. Vibe
executed the frozen protocol correctly and reproduced MooTrade's momentum-v1
equity curve exactly, but only after custom loader, whole-share and benchmark
adaptations. The full Vibe runner was blocked in this environment, the frozen
strategy hypothesis failed its pre-registered comparator, and Vibe would add a
large dependency surface without a demonstrated production need.

`C` (reject entirely) is the fallback if a separate research environment is
not wanted. `A` (reuse selected modules in production) is not justified by this
POC.

## What was actually inspected and run

Inspected source:

- `Vibe-Trading/agent/backtest/loaders/base.py:953` (`DataLoaderProtocol.fetch`)
  and `:209` (`validate_ohlc`).
- `Vibe-Trading/agent/backtest/engines/global_equity.py:60`
  (`GlobalEquityEngine`), `:172` (`round_size`), `:228` (`apply_slippage`).
- `Vibe-Trading/agent/backtest/engines/base.py:246` (`_align`), `:981`
  (`run_backtest`), `:1290` (`_execute_bars`), `:1799`
  (`_execute_target_rebalance`), `:2388` (`_write_artifacts`).
- `Vibe-Trading/agent/backtest/runner.py:1461` (`main`), `benchmark.py:103`
  (`resolve_benchmark`), `rebalance_mask.py`, `models.py`,
  `signal_timing.py`, `loaders/local_loader.py`, `frozen.py`, and
  `src/tools/path_utils.py:383` (`safe_run_dir`).
- `Vibe-Trading/pyproject.toml`, `LICENSE`, `NOTICE`.

Inspected MooTrade source:

- `backend/app/research/data.py:11` (`UNIVERSE` is `IWM/QQQ/SPY`),
  `strategy.py:158` (`screen` is single-name), and
  `evaluate.py:100` (`simulate_strategy` is single-position).
- `backend/app/broker/moomoo_history.py`, `moomoo_rest.py`, and
  `moomoo_auth.py` for the read-only history contract.

Actually run:

1. **Phase 2 POC:** a real Vibe `GlobalEquityEngine` backtest on 370 Moomoo
   daily bars per symbol (SPY/QQQ/IWM, 2025-05-29 to 2026-11-16), compared with
   `simulate_strategy`. Vibe and MooTrade held identical shares and produced an
   equity difference below `$1e-10`; both ended at `$100,089.46` after 23
   round trips.
2. **Phase 3 protocol:** 210 read-only Moomoo `history-kline` requests covering
   the 20-stock frozen universe plus SPY, 2015-01-02 to 2024-12-31, `ktype=2`,
   `autype=1`, `extended_time=0`. Every symbol has all 2,516 provider US
   sessions. One pre-registered run plus three benchmark runs through the Vibe
   engine with a weekly execution mask.
3. Validation before the result: exact calendar coverage, OHLC checks,
   chronological order, no 2025+ bars, independent recomputation of first/
   middle/last weekly selections, target constraints, and a truncation/
   future-perturbation look-ahead test over 235 weeks. All passed.
4. Fill-episode P&L reconciles to equity P&L within `$2.4e-10`.

Not run: the full Vibe agent runner, Vibe factor library (Alpha101/GTJA191),
Vibe data gateway, Qoder Cloud Agent integration, or any LLM-driven Vibe
workflow.

## Numerical results

Phase 2 (same data, same rules):

| Run | Total return | Final value | Max drawdown | Round trips |
|---|---:|---:|---:|---:|
| Vibe `GlobalEquityEngine` | 0.0895% | $100,089.46 | 1.2156% | 23 |
| MooTrade `simulate_strategy` | 0.0895% | $100,089.46 | 1.2156% | 23 |

The original comparison exposed a MooTrade metric-base defect:
`backend/app/research/evaluate.py` divided by the first post-entry equity point
and omitted the initial curve value. That defect is corrected; both engines now
measure return on the $100,000 initial equity. The residual curve difference is
`5.8e-11`, which is floating-point noise, not an execution difference.

Phase 3 (frozen `volume-confirmed-relative-strength-v1`, 2016-01-04 to
2024-12-31, 470 weekly rebalances):

| Run | Total return | CAGR | Volatility | Max drawdown | Average gross | Sharpe |
|---|---:|---:|---:|---:|---:|---:|
| Strategy | 36.82% | 3.55% | 4.91% | -5.29% | 14.28% | 0.735 |
| SPY at strategy weekly gross | 20.47% | 2.09% | 2.43% | -3.09% | 14.24% | 0.867 |
| SPY constant 30% | 47.89% | 4.45% | 5.32% | -11.25% | 29.89% | 0.846 |
| Equal-weight 20 stocks, 30% gross | 107.48% | 8.46% | 6.08% | -9.69% | 29.17% | 1.367 |
| Cash | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | n/a |

**Pre-registered rejection rule triggered.** The strategy beat exposure-matched
SPY by 16.34 percentage points but trailed the equal-weight comparator by 70.67
points and had a lower Sharpe than all three equity comparators. It did not
depend on a handful of episodes (top three = 27.4% of net P&L; 514 completed
episodes). Under the frozen rule, the hypothesis is rejected. No parameter
search, no re-run on 2025-2026, and no deployment follow.

Caveats that prevent over-reading the rejection: the equal-weight comparator
averaged 29.17% gross versus the strategy's 14.28%, so part of the raw-return
gap is an exposure difference; the fixed universe has survivorship and
selection bias; forward-adjusted prices use post-hoc factors; volume is raw and
split-unadjusted; and the 30% gross limit is a weekly target, with 291 sessions
closing slightly above 30% from intraweek drift.

## Comparison with MooTrade's current research implementation

| Dimension | Vibe-Trading | MooTrade current |
|---|---|---|
| Scope | General multi-asset, multi-position target weights | Fixed `IWM/QQQ/SPY`; one selected symbol per run |
| Strategy expression | `SignalEngine.generate` target-weight contract | Hard-coded `momentum-v1` / `news-catalyst-v1` |
| Rebalance | Explicit weekly mask, hold or rebalance | Next-open single-position entry/exit |
| Verification | `validate_ohlc`, fill-P&L reconciliation, look-ahead harness, run card | Chronological/OHLC checks and metric regression tests; no fill-level reconciliation |
| Reproducibility | Per-run `equity.csv`, `fills.jsonl`, `positions.csv`, `target_positions.csv`, `trades.csv`, metrics, run card | In-memory `BacktestResult` plus Markdown report |
| Cost model | Configurable slippage/commission; 2 bps used | Fixed 2 bps |
| Dependency surface | Heavy: pandas `<3`, numpy, yfinance, fastmcp, langchain, langgraph, tushare, akshare, ccxt, duckdb, scikit-learn, exchange-calendars | Light: pydantic, httpx, fastapi, uvicorn, qca-sdk |
| Runner readiness | Full runner blocked by missing `fastmcp` and a module-level `yfinance` import; engine invoked in-process with benchmark stub | Runs locally today |
| Maintenance risk | Private engine internals used for weekly rebalance and whole-share override; pinned commit required | Small codebase under project control; corrected metric defect covered by regression tests |
| Direct comparison | Phase 2 equity identical to MooTrade | Cannot run the 20-stock protocol without modifying production research code |

## Why B, not A or C

**Why not A (reuse modules in production):** the integration needed a custom
`DataLoaderProtocol` adapter, a precomputed target-weight signal engine, a
`GlobalEquityEngine.round_size` subclass for whole shares, an explicit weekly
`rebalance_mask`, and a `sys.modules` stub for `backtest.benchmark` to avoid
`yfinance`. The full runner still needed `fastmcp`, `safe_run_dir` and a
specific run-directory layout. Vibe also requires `pandas<3.0` while this
environment has `pandas 3.1.1`; the engine ran, but not on a supported
combination. Embedding that into MooTrade would add a large dependency and
maintenance burden, and the rejected hypothesis removes the immediate reason
to do so. Production changes would touch `backend/pyproject.toml`, new
research adapters and tests; none are justified now.

**Why not C (reject entirely):** Vibe is genuinely useful as an external
research tool. It ran a multi-symbol, weekly, target-weight protocol that the
current MooTrade engine cannot express, produced a complete fill/equity
artifact set, and its comparison exposed a metric-base bug that was then
corrected. Keeping it outside the production path preserves that capability at
near-zero coupling.

## Precise changes for the recommended architecture

**Vibe integration:** no production dependency or runtime import. The Vibe
workflow did not modify `RiskGate`, the scheduler or the dashboard. A separate
execution-readiness milestone later added a disabled simulated-order transport,
a paper broker facade and a separate unused execution OAuth client; those are
not part of this research integration and `ORDER_WRITES_ENABLED` remains false.

**Research evidence (keep, no production import):**

- `evidence/research/vibe-trading-poc-2026-11-18/run_poc.py`
- `evidence/research/vibe-trading-poc-2026-11-18/fetch_protocol_data.py`
- `evidence/research/vibe-trading-poc-2026-11-18/run_protocol_eval.py`
- `evidence/research/vibe-trading-poc-2026-11-18/protocol-report.md`
- `evidence/research/vibe-trading-poc-2026-11-18/protocol-results.json`
- `evidence/research/vibe-trading-poc-2026-11-18/integration-verdict.md` (this file)

Optional, if the separate tool is retained: add a pinned `requirements.txt`
and a short run README in that evidence directory. Pin the Vibe commit and use
Python 3.11-3.13 with `pandas<3.0`; do not install Vibe's full dependency set
into the MooTrade backend environment.

**Separate, owner-approved bug fix (not part of this POC):**
`backend/app/research/evaluate.py:57-60` should base total return, CAGR and
drawdown on `INITIAL_EQUITY` and include the starting equity point. This is a
production research change and should be handled as its own reviewed task.

## Authority and safety

No broker write path was imported, no OAuth scope changed, no RiskGate policy
changed, no order submitted, and no 2025-2026 bar for the 20-stock protocol
universe was read. The earlier 2025-2026 ETF holdout was not reused. The
competition paper account and `ORDER_WRITES_ENABLED=false` boundary are
unchanged. A Vibe backtest is research evidence, not a broker fill and not
trading approval.
