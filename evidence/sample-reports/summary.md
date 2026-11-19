# MooTrade evidence summary (generated)

- Generated at (UTC): 2026-11-19T01:47:03+00:00
- Mode: `PAPER`. Sections below derive only from local artifacts already committed under `evidence/` and `data/`.
- Provenance: ledger rows are `LOCAL_LEDGER`; Qoder runs are genuine cloud sessions; bar snapshots, preflights and execution records are real read-only provider evidence; research studies are `HISTORICAL` and never paper-account performance.
- No credentials, fingerprints or full account identifiers appear in this report.

## Ledger and safety state

- Audit events: 101
  QODER_TOOL_RESULT=15; POLICY_APPROVED=13; PROPOSAL_CREATED=13; EXECUTION_BLOCKED=11; POLICY_REJECTED=11; QODER_RUN_STARTED=11; QODER_RUN_COMPLETED=9; RECONCILIATION_MISMATCH=6; AUTO_PAPER_ACTIVATED=2; ORDER_ACKNOWLEDGED=2; ORDER_SUBMISSION_STARTED=2; RECONCILIATION_OK=2; RISK_MONITOR_RESULT=2; AGENT_ERROR=1; LEDGER_REPAIR=1
- Order submissions: 2 (UNKNOWN: 0)
- Durable first-order approvals: 2
- Kill switch: disengaged
- Equity baseline days recorded: 3

## Qoder Cloud Agent runs

| Run id | Mode | Strategy | Status | Outcome | Completed (UTC) |
|---|---|---|---|---|---|
| `qoder-05d6227e-7069-47d3-97b9-d56032d87614` | HISTORICAL_DRY_RUN | directional-event-v2 | COMPLETED | HISTORICAL_POLICY_APPROVAL | 2026-11-18 05:58 |
| `qoder-08ac0d92-8f55-475a-a348-6b5e50d72e66` | CURRENT_MARKET_READ_ONLY | momentum-v1 | COMPLETED | NO_TRADE | 2026-11-17 15:54 |
| `qoder-12bd7001-ee8a-4d65-b94e-7c3075140b32` | CURRENT_MARKET_READ_ONLY | spy-directional | COMPLETED | POLICY_REJECTED | 2026-11-18 15:51 |
| `qoder-328aefff-7dde-4a98-ac76-99b3e0e33728` | CURRENT_MARKET_READ_ONLY | spy-directional | COMPLETED | POLICY_REJECTED | 2026-11-18 06:56 |
| `qoder-5abed69d-8fbc-4342-a51f-e46814f3941c` | HISTORICAL_DRY_RUN | momentum-v1 | COMPLETED | NO_TRADE | 2026-11-17 11:32 |
| `qoder-62b08de4-d64f-43ab-b044-fe781eae393e` | HISTORICAL_DRY_RUN | directional-event-v2 | COMPLETED | HISTORICAL_POLICY_APPROVAL | 2026-11-18 05:59 |
| `qoder-6316a9da-02c9-49ec-982e-2366d1ca20b2` | CURRENT_MARKET_READ_ONLY | spy-directional | COMPLETED | POLICY_REJECTED | 2026-11-19 01:45 |
| `qoder-83bc0a47-e238-4672-a5cc-42e8080180ce` | CURRENT_MARKET_READ_ONLY | momentum-v1 | COMPLETED | NO_TRADE | 2026-11-18 01:11 |
| `qoder-b5802072-58a5-42b1-b935-5c7942ed8946` | HISTORICAL_DRY_RUN | directional-event-v2 | AGENT_ERROR | NO_TRADE | 2026-11-18 05:56 |
| `qoder-bc9eb9e3-8b3f-46f8-9f20-8f2eb94f541a` | CURRENT_MARKET_READ_ONLY | momentum-v1 | COMPLETED | NO_TRADE | 2026-11-17 15:54 |

## Read-only preflights

| Artifact | Checked (UTC) | Risk decision | Submission performed | Order endpoint contacted |
|---|---|---|---|---|
| `preflight-2026-11-17.json` | 2026-11-17 13:08 | REJECT | False | False |
| `preflight-2026-11-17T155320Z.json` | 2026-11-17 15:53 | REJECT | False | False |
| `preflight-2026-11-18T023015Z.json` | 2026-11-18 02:30 | REJECT | False | False |
| `preflight-2026-11-18T071616Z.json` | 2026-11-18 07:16 | REJECT | False | False |

## Execution records (no order submitted)

| Artifact | Decision | Submission performed | Order endpoint contacted |
|---|---|---|---|
| `diagnostic-buy-candidate-2026-11-18T024420Z.json` | not available | False | False |
| `diagnostic-roundtrip-2026-11-18.json` | not available | not available | not available |
| `execution-preflight-2026-11-18T025133Z.json` | DEFERRED_TO_NEXT_REGULAR_SESSION | False | False |

## Current-market daily bars

- Latest snapshot: `evidence/current-market/2026-11-18/daily-bars.json`
  bars per symbol: SH=370, SPXU=370, SPY=370, UPRO=370

## Local scheduler

- Scheduler run history entries: 4
  2026-11-17 | COMPLETED | NO_TRADE | writes=False | catch_up=True
  2026-11-18 | ABANDONED | not available | writes=False | catch_up=True
  2026-11-18 | COMPLETED | POLICY_REJECTED | writes=False | catch_up=True
- Scheduler event lines: 8

## Broker-confirmed orders and fills

- Broker-confirmed orders/fills: 2 fill/acknowledgement events, 2 submission records. Inspect the ledger for details.

## Historical research (HISTORICAL, not paper performance)

- `sec-earnings-relative-momentum-v1` (period not recorded): development/catalyst(total_return_pct=-2.414280851169525, max_drawdown_pct=2.812341218412224); development/SPY(total_return_pct=5.3176257747899704, max_drawdown_pct=9.133129160735596); development/QQQ(total_return_pct=4.681019316218025, max_drawdown_pct=12.188370008021769); development/cash(total_return_pct=0.0, max_drawdown_pct=0.0); development/momentum-v1(total_return_pct=-2.8373886564435393, max_drawdown_pct=9.640083084948914); development/news-catalyst-v1(total_return_pct=0.0, max_drawdown_pct=0.0); holdout/catalyst(total_return_pct=-1.2535948069579252, max_drawdown_pct=2.5687005637740685); holdout/SPY(total_return_pct=13.136877135965987, max_drawdown_pct=5.91587621455801); holdout/QQQ(total_return_pct=13.781673740233035, max_drawdown_pct=14.82373693494458); holdout/cash(total_return_pct=0.0, max_drawdown_pct=0.0); holdout/momentum-v1(total_return_pct=2.5025864763994927, max_drawdown_pct=11.676767319858277); holdout/news-catalyst-v1(total_return_pct=1.5573815485994247, max_drawdown_pct=11.027432828495725)
- `directional-event-2026-11-18`: no `results.json`; see raw artifacts in the folder.
- `etf-trend-baseline-v1` (2026-04-01 to 2026-11-16): comparison[trend_total_return_pct=0.2572, spy_10pct_total_return_pct=1.3137, spy_full_total_return_pct=13.1369, excess_return_vs_spy_10pct_pct=-1.0565, drawdown_difference_vs_spy_10pct_pct=0.0577] trend_baseline(total_return_pct=0.2572, max_drawdown_pct=0.6338); spy_hold_10pct(total_return_pct=1.3137, max_drawdown_pct=0.6915); spy_hold_100pct(total_return_pct=13.1369, max_drawdown_pct=5.9159); cash(total_return_pct=0.0, max_drawdown_pct=0.0)
- `momentum-v1` (2025-06-27 to 2026-11-16): comparison[prior_total_return_pct=-0.4058, deployable_total_return_pct=0.0895, total_return_difference_pct=0.4953, prior_max_drawdown_pct=11.6768, deployable_max_drawdown_pct=1.2156, drawdown_difference_pct=-10.4612, spy_10pct_total_return_pct=2.0709, spy_10pct_max_drawdown_pct=1.0225, spy_average_exposure_total_return_pct=1.371, spy_same_schedule_total_return_pct=0.4326]
- `moomoo-signal-observation`: no `results.json`; see raw artifacts in the folder.
- `moomoo-tech-audit-2026-11-18`: no `results.json`; see raw artifacts in the folder.
- `stock-selection-prereg-2026-11-18`: no `results.json`; see raw artifacts in the folder.
- `vibe-trading-poc-2026-11-18` (2025-06-27 to 2026-11-16): vibe_metrics(total_return=0.0008945874243704299, annual_return=0.0006458682393446491, max_drawdown=-0.012155503827850125, benchmark_return=0.223148, excess_return=-0.222253); mootrade_metrics(total_return=0.0008945874243702079, max_drawdown=0.012155503827849986, average_trade_return=0.0003364596920778945)

## Missing or pending evidence

- First autonomous strategy paper order: pending. The two QQQ broker-confirmed fills are diagnostics; UPRO/SPXU acceptance orders and the first strategy order remain pending. No paper-account performance is reported until then.
- Account-exclusive `trade:write` scope: unverified (see `docs/integrations.md`).
