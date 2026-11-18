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

**1:45–2:25 — Execution boundary.** The first supervised paper BUY/SELL is still pending, so show the read-only preview and its exact payload, `submission_performed: false`, and the `R010`/`R014` fail-closed reasons. State plainly that no broker-confirmed order or fill exists yet. If a supervised order is completed before submission, show the genuine order/fill from the ledger instead; never present a mock as broker evidence.

**2:25–3:00 — Results and reuse.** Compare equity to a benchmark with sample warnings. Show reusable skills, tests, clean installation, and one limitation or failure that was detected and handled.

## Evidence that exists today

- `evidence/qoder/` — sanitised Qoder run artifacts, session IDs, tool calls and deterministic outcomes (including the current `spy-directional` POLICY_REJECTED run).
- `evidence/preflight/` — real read-only preflight snapshots that contacted no order endpoint.
- `evidence/execution/` — supervised preview diagnostics; no fill exists.
- `evidence/current-market/` — timestamped completed daily-bar snapshots.
- `evidence/research/` — retired-strategy studies, the Moomoo capability audit and the Vibe-Trading POC, explicitly historical.
- `evidence/scheduler/` — Task Scheduler registration and run evidence.
- Dashboard captures were removed from the repository in the 18 November cleanup; regenerate them from the running dashboard when needed.

There is **no** `evidence/paper-orders/` because no broker order or fill has occurred. Never manufacture logs or favourable results; add new evidence folders only when genuine evidence exists.

## Submission checklist

- [ ] Runnable trading-agent package with README and locked dependency versions.
- [ ] Qoder-generated deck.
- [ ] Strategy thesis, version, entry/exit and invalidation conditions.
- [ ] Risk thresholds, kill-switch implementation and tests.
- [ ] Decision, order, fill and equity records (redacted).
- [ ] Documentation of what worked, what failed and why.
- [ ] Third-party attribution and licence compliance.
- [ ] Final link/format confirmed against the current organiser instructions.
