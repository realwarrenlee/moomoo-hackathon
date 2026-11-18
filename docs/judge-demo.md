# Judging evidence and demo script

## Official stated rubric (subject to organiser changes)

| Category | Weight | Demonstrable evidence |
|---|---:|---|
| Qoder + Cloud Agents | 30% | Genuine cloud runs, multi-agent roles, scheduled automation, reusable skills and MCP tool usage |
| Strategy & risk | 30% | Falsifiable thesis, explicit invalidation, pre-trade policy gate, limits, kill switch and test results |
| Risk-adjusted return | 25% | Paper-account fills, equity, exposure, drawdown, matched benchmark and frank sample limitations |
| Reusability & documentation | 15% | Runnable repo, setup, scripts, redacted logs, tests, Qoder-generated deck |

## Three-minute presentation

**0:00–0:25 — Product.** Open MooTrade Overview; verify paper-account identity, equity, exposure and time of last broker sync. State that the goal is inspectable autonomous trading, not a promise of guaranteed alpha.

**0:25–1:05 — Autonomous reasoning.** Open a genuine Qoder Cloud Agent run; show data timestamps, research evidence, strategy signal and independent risk review. Include an example `NO_TRADE` when conditions are not met.

**1:05–1:45 — Risk protection.** Replay a clearly labelled *mock-only* oversized proposal. Show exact policy ID, exposure calculation and proof that the broker adapter was never called.

**1:45–2:25 — Actual paper execution.** Show a genuine Moomoo competition paper order from the ledger, broker status/fill and reconciled position. If the market is closed, replay recorded real events and show original timestamps; don't pretend it just executed.

**2:25–3:00 — Results and reuse.** Compare equity to a benchmark with sample warnings. Show reusable skills, tests, clean installation, and one limitation or failure that was detected and handled.

## Required evidence file types

- `evidence/agent-runs/` — sanitized Qoder run IDs, handoffs and tool names.
- `evidence/paper-orders/` — redacted actual Moomoo order/fill/account-state evidence.
- `evidence/risk-tests/` — test outputs demonstrating pre-broker rejection, unknown result handling and kill switch.
- `evidence/metrics/` — timestamped paper-account and benchmark observations, calculation scripts/definitions.
- `evidence/demo/` — screenshots or recorded replay, clearly marked `REAL PAPER`, `MOCK TEST` or `REPLAY`.

These folders are to be created **only when genuine evidence exists**. Never manufacture logs or favourable results.

## Submission checklist

- [ ] Runnable trading-agent package with README and locked dependency versions.
- [ ] Qoder-generated deck.
- [ ] Strategy thesis, version, entry/exit and invalidation conditions.
- [ ] Risk thresholds, kill-switch implementation and tests.
- [ ] Decision, order, fill and equity records (redacted).
- [ ] Documentation of what worked, what failed and why.
- [ ] Third-party attribution and licence compliance.
- [ ] Final link/format confirmed against the current organiser instructions.
