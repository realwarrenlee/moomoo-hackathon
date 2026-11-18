# Qoder read-only decision report

**PAPER / READ-ONLY — NO ORDER SUBMITTED OR APPROVED**

- Run ID: `qoder-328aefff-7dde-4a98-ac76-99b3e0e33728`
- Mode: `CURRENT_MARKET_READ_ONLY`
- Status: `COMPLETED`
- Outcome: `POLICY_REJECTED`
- Strategy: `spy-directional`
- Evidence: current read-only Moomoo REST quotes/account plus a completed daily-bar snapshot.
- Authority: deterministic Python research and `RiskGate`; agent prose is non-authoritative.

## Genuine Cloud Agent sessions

- coordinator: `sess_00vuffkjlafwgresy62p`
- researcher: `sess_00vuffpgw47pdzx2s53d`
- auditor: `sess_00vufg56d34sgybrbybv`

## Deterministic artifacts

### Data collection

```json
{
  "mode": "post-close",
  "provenance": "CURRENT_MARKET_READ_ONLY",
  "collected_at_utc": "2026-11-18T06:56:02.796644+00:00",
  "us_eastern_time": "2026-11-18T01:56:02.796644-05:00",
  "quotes": [
    {
      "symbol": "SPY",
      "price": "732.44",
      "data_time_utc": "2026-11-17T21:00:00.194000+00:00",
      "age_seconds": 35762.6,
      "sec_status": "NORMAL",
      "suspended": false,
      "market_state": "AFTER_HOURS_END",
      "regular_session_open": false,
      "provenance": "LIVE_BROKER_READ"
    },
    {
      "symbol": "UPRO",
      "price": "126.54",
      "data_time_utc": "2026-11-17T21:00:00+00:00",
      "age_seconds": 35762.8,
      "sec_status": "NORMAL",
      "suspended": false,
      "market_state": "AFTER_HOURS_END",
      "regular_session_open": false,
      "provenance": "LIVE_BROKER_READ"
    },
    {
      "symbol": "SH",
      "price": "33.9",
      "data_time_utc": "2026-11-17T21:00:00.221000+00:00",
      "age_seconds": 35762.6,
      "sec_status": "NORMAL",
      "suspended": false,
      "market_state": "AFTER_HOURS_END",
      "regular_session_open": false,
      "provenance": "LIVE_BROKER_READ"
    },
    {
      "symbol": "SPXU",
      "price": "39.03",
      "data_time_utc": "2026-11-17T21:00:00.465000+00:00",
      "age_seconds": 35762.3,
      "sec_status": "NORMAL",
      "suspended": false,
      "market_state": "AFTER_HOURS_END",
      "regular_session_open": false,
      "provenance": "LIVE_BROKER_READ"
    }
  ],
  "account": {
    "masked_id": "****0101",
    "equity": "100000",
    "cash": "100000",
    "buying_power": "100000",
    "day_start_equity": "100000",
    "positions_count": 0,
    "open_orders_count": 0,
    "reconciled": true,
    "unknown_orders": 0,
    "as_of_utc": "2026-11-18T06:56:04.972877+00:00",
    "age_seconds": 0.0,
    "provenance": "LIVE_BROKER_READ"
  },
  "positions": [],
  "orders": {
    "today_count": 0,
    "history_count": 0,
    "open_count": 0
  },
  "history": {
    "path": "evidence\\current-market\\2026-11-17\\daily-bars.json",
    "source": {
      "provider": "Moomoo REST history-kline",
      "endpoint": "/api/v1.0/quote/{code}/history-kline",
      "arguments": {
        "ktype": 2,
        "autype": 1,
        "extended_time": 0,
        "num": 370
      },
      "fetched_at_utc": "2026-11-18T06:55:57.400545+00:00",
      "last_completed_session": "20261117",
      "note": "Read-only completed daily bars fetched from the documented Moomoo REST history-kline endpoint. No account identifiers or credentials are included."
    },
    "window": "post-close",
    "today_session_et": "2026-11-18",
    "last_completed_session": "2026-11-17",
    "today_bar_available": false,
    "expected_previous_session": "2026-11-17",
    "bars_per_symbol": {
      "SPY": 370,
      "UPRO": 370,
      "SH": 370,
      "SPXU": 370
    },
    "fetch_age_hours": 0.0,
    "complete": true
  },
  "validations": {
    "account_verified_paper": true,
    "account_reconciled": true,
    "account_age_seconds": 0.0,
    "regular_session_required": false,
    "quotes_collected": 4,
    "history_complete": true,
    "order_writes_enabled": false
  }
}
```

### Research

```json
{
  "ok": true,
  "mode": "CURRENT_MARKET_READ_ONLY",
  "run_id": "qoder-328aefff-7dde-4a98-ac76-99b3e0e33728",
  "snapshot": {
    "strategy_version": "spy-directional",
    "decision_time_utc": "2026-11-18T06:56:02.796644+00:00",
    "data_as_of_utc": "2026-11-17T21:00:00+00:00",
    "spy_session_date": "2026-11-17",
    "spy_close": "732.44",
    "spy_return_10d": "-0.0290448730695300589911844634",
    "spy_sma50": "762.88909302846",
    "spy_trend_pct": "-0.0399128697824024071163288049",
    "spy_volatility_20d": "0.23056703892967878",
    "market_state": "BEARISH",
    "direction": "BEARISH",
    "target_symbol": "SH",
    "target_effective_exposure": "-1",
    "current_symbol": null,
    "current_quantity": 0,
    "action": "BUY",
    "reentry_symbol": null,
    "candidates": [
      {
        "symbol": "SPY",
        "direction": 1,
        "leverage": "1",
        "effective_exposure": "1",
        "close": "732.44",
        "eligible": false,
        "selected": false,
        "reasons": [
          "Instrument direction does not match the SPY signal"
        ]
      },
      {
        "symbol": "UPRO",
        "direction": 1,
        "leverage": "3",
        "effective_exposure": "3",
        "close": "126.54",
        "eligible": false,
        "selected": false,
        "reasons": [
          "Instrument direction does not match the SPY signal",
          "Daily 3x execution requires separate leverage approval"
        ]
      },
      {
        "symbol": "SH",
        "direction": -1,
        "leverage": "1",
        "effective_exposure": "-1",
        "close": "33.9",
        "eligible": true,
        "selected": true,
        "reasons": []
      },
      {
        "symbol": "SPXU",
        "direction": -1,
        "leverage": "3",
        "effective_exposure": "-3",
        "close": "39.03",
        "eligible": false,
        "selected": false,
        "reasons": [
          "Daily 3x execution requires separate leverage approval"
        ]
      }
    ],
    "selected_symbol": "SH",
    "decision_reason": "BEARISH target SH; buy 147 shares for 5.0% effective exposure.",
    "no_trade_reason": null
  },
  "proposal": {
    "schema_version": "1",
    "proposal_id": "spy-directional-2026-11-17-SH-BUY",
    "run_id": "qoder-328aefff-7dde-4a98-ac76-99b3e0e33728",
    "strategy_version": "spy-directional",
    "decision_time_utc": "2026-11-18T06:56:02.796644Z",
    "data_as_of_utc": "2026-11-17T21:00:00Z",
    "symbol": "SH",
    "action": "BUY",
    "requested_quantity": 147,
    "thesis": "SPY closed at 732.44 with a 10-session return of -2.90%, a 50-session SMA of 762.89 and 23.06% annualized volatility. BEARISH targets SH at 1x daily leverage (-1 effective exposure), sized to 5% effective exposure.",
    "invalidation": "Exit at the next open after a neutral, opposite or volatility-ceiling signal. A leverage approval is required for UPRO or SPXU.",
    "evidence_ids": [
      "bar:SPY:2026-11-17",
      "bar:SH:20261117"
    ]
  },
  "notice": "Current read-only Moomoo evidence captured during the regular session; not an order, owner approval or fill."
}
```

### Risk

```json
{
  "ok": true,
  "mode": "CURRENT_MARKET_READ_ONLY",
  "run_id": "qoder-328aefff-7dde-4a98-ac76-99b3e0e33728",
  "risk_decision": {
    "proposal_id": "spy-directional-2026-11-17-SH-BUY",
    "policy_version": "risk-v1",
    "decision": "REJECT",
    "reasons": [
      {
        "rule_id": "R002",
        "message": "Symbol is outside the approved allowlist",
        "details": {
          "symbol": "SH"
        }
      },
      {
        "rule_id": "R007",
        "message": "Quote is stale (older than 300s)",
        "details": {
          "age_seconds": "35785.463417"
        }
      },
      {
        "rule_id": "R012",
        "message": "Orders are limited to the regular exchange session",
        "details": {}
      },
      {
        "rule_id": "R010",
        "message": "Order writes are disabled by control state",
        "details": {
          "writes_enabled": "False",
          "kill_switch": "False",
          "circuit_breaker": "False"
        }
      },
      {
        "rule_id": "R014",
        "message": "First paper order requires explicit owner approval",
        "details": {}
      }
    ],
    "approved_quantity": 0,
    "account_snapshot_id": "mm-69f3cf00dae8d52263f4",
    "expires_at_utc": "2026-11-18T06:56:55.684417Z"
  },
  "evaluated_at_utc": "2026-11-18T06:56:25.684417+00:00",
  "control_context": "Fresh read-only REST account and quote inputs with writes disabled; an APPROVE is not owner authorization.",
  "notice": "An APPROVE result is a policy evaluation, never an order authorization."
}
```

## Sanitized agent summaries

### coordinator_ready

READY qoder-328aefff-7dde-4a98-ac76-99b3e0e33728

Mode: CURRENT_MARKET_READ_ONLY. Strategy allowlist: spy-directional. Selected strategy: spy-directional.

Boundary: read-only coordination only — no tools, no order placement or approval, no credentials, no account identifiers, no repository or web access. This run is not an order, fill, owner approval, or live-account claim.

### researcher

I'll call the research tool once with the supplied inputs.
**Mode: CURRENT_MARKET_READ_ONLY** — run `qoder-328aefff-7dde-4a98-ac76-99b3e0e33728`, strategy `spy-directional`
Decision time `2026-11-18T06:56:02.796644+00:00`; data as of `2026-11-17T21:00:00+00:00` (SPY session `2026-11-17`).

**Trend / momentum / volatility (deterministic)**
- SPY close: **732.44**
- 10-session return: **-2.90%** (bearish momentum)
- 50-session SMA: **762.89**; trend vs SMA: **-3.99%** (price below SMA → bearish)
- 20-session annualized volatility: **23.06%**
- Market state / direction: **BEARISH**

**Target**
- Selected: **SH** (1x inverse, effective exposure **-1**), close 33.90 — eligible and selected.
- Not selected: SPY (direction mismatch), UPRO (direction mismatch + 3x leverage approval required), SPXU (3x leverage approval required).
- This is a live directional target, not **CASH**.

**Current holding and action**
- Holding: **none** (`current_symbol` null, `current_quantity` 0) — no **HOLD** outstanding.
- Action: **BUY** 147 SH, sized to 5.0% effective exposure.
- `no_trade_reason` is null, so no **NO_TRADE** flag was raised for this run.

**Proposal** `spy-directional-2026-11-17-SH-BUY`; evidence `bar:SPY:2026-11-17`, `bar:SH:20261117`. Invalidation: exit at next open on a neutral, opposite, or volatility-ceiling signal; leverage approval required for UPRO/SPXU.

Artifact notice states this is current read-only evidence captured during the regular session — not an order, owner approval, or fill. I cannot evaluate risk, approve, or execute anything; no broker or credential access.

### auditor

**Deterministic decision: REJECT** (policy_version risk-v1, mode CURRENT_MARKET_READ_ONLY). Approved quantity: 0.

Rule IDs triggered:
- **R002** — symbol `SH` is outside the approved allowlist
- **R007** — quote stale: 35,785.46s old vs 300s limit (data_as_of 2026-11-17T21:00Z vs 2026-11-18T06:56Z, ~10h gap; pre-market)
- **R012** — orders limited to regular exchange session
- **R010** — order writes disabled by control state (`writes_enabled=False`; kill_switch and circuit_breaker both False)
- **R014** — first paper order requires explicit owner approval

Strongest counterargument (does not change the outcome): the thesis itself is internally sound-ish and the exposure arithmetic is coherent — BEARISH → SH (daily -1x) at 5% effective exposure. If the allowlist were broader, a -1x inverse ETF is the correct non-leveraged vehicle, and its invalidation language is appropriately symmetric (exit on neutral/opposite/vol-ceiling). So R002 looks like a policy-scope gap rather than a flawed trade idea.

Downside: the lone real economic threat is a mean-reversion bounce — SPY at 732.44 vs 50-session SMA 762.89 (-4.0% below) with 23% annualized vol is an already-extended down move; buying inverse exposure after a -2.90% 10-session slide risks buying the bottom of the move, and -1x daily-reset products decay in choppy tape even when the end-to-end direction is flat.

Invalidation risk: the exit rule is signal-triggered at the *next* open, so it is one full session late; a single sharp reversal gap can hit before the modeled exit. Also note the invalidation text's leverage-approval clause (UPRO/SPXU) is irrelevant to SH — SH is -1x, not leveraged — so that clause is surplus and could mislead a future reader into thinking leverage gating covered this order.

Caveat: R007 and R012 mean the inputs were not even fresh/session-valid; even after fixing the allowlist and owner approval, this proposal would need a re-evaluation on fresh quotes inside RTH. Nothing here is owner authorization or an order instruction.

### coordinator_final

**Run closed:** qoder-328aefff-7dde-4a98-ac76-99b3e0e33728 — mode CURRENT_MARKET_READ_ONLY.

**Deterministic outcome:** `POLICY_REJECTED` (policy_version risk-v1). Approved quantity **0**. Proposal `spy-directional-2026-11-17-SH-BUY` (BUY, 147, symbol SH) was not approved — final state is a reject, i.e. NO_TRADE preserved. No order was created, approved, routed or executed.

**Reject reasons (as emitted):**
- R002 — SH is outside the approved allowlist
- R007 — quote stale (35,785.46s vs 300s limit; data 2026-11-17T21:00Z vs decision 2026-11-18T06:56Z, pre-market)
- R012 — orders limited to regular exchange session
- R010 — order writes disabled by control state (`writes_enabled=False`; kill_switch and circuit_breaker False)
- R014 — first paper order requires explicit owner approval

**Limitations:**
- Inputs were neither fresh nor session-valid, so even absent R002/R014 the proposal would require re-evaluation on fresh quotes during RTH.
- No account identifiers were used and none are asserted; `account_snapshot_id` is an opaque artifact value only.
- This is not a broker fill, not current approval, not per-order authorization, and not a statement about a live account or live market state.
- The strategy allowlist is limited to spy-directional; the auditor's note that a -1x inverse vehicle is a plausible construction for BEARISH is context only and carries no approval weight.

## Limitations

A current read-only policy evaluation is not owner authorization. It does not submit, approve or fill an order. Supervised paper execution remains blocked by disabled writes, outstanding first-order approval and unverified account-exclusive trade:write scope.
