# Qoder read-only decision report

**PAPER / READ-ONLY — NO ORDER SUBMITTED OR APPROVED**

- Run ID: `qoder-62b08de4-d64f-43ab-b044-fe781eae393e`
- Mode: `HISTORICAL_DRY_RUN`
- Status: `COMPLETED`
- Outcome: `HISTORICAL_POLICY_APPROVAL`
- Strategy: `directional-event-v2`
- Evidence: pinned timestamped Moomoo historical fixtures, not a current broker snapshot.
- Authority: deterministic Python research and `RiskGate`; agent prose is non-authoritative.

## Genuine Cloud Agent sessions

- coordinator: `sess_00vuabejsh2ps1camch1`
- researcher: `sess_00vuabj8f629sgijb6c8`
- auditor: `sess_00vuabsfd6j9ct4ixyyp`

## Deterministic artifacts

### Research

```json
{
  "ok": true,
  "mode": "HISTORICAL_DRY_RUN",
  "run_id": "qoder-62b08de4-d64f-43ab-b044-fe781eae393e",
  "snapshot": {
    "strategy_version": "directional-event-v2",
    "decision_time_utc": "2026-09-21T21:00:00+00:00",
    "data_as_of_utc": "2026-09-21T21:00:00+00:00",
    "event": {
      "event_id": "syn-nasdaq-bull-2026-09-18",
      "category": "earnings",
      "title": "Synthetic large-cap technology earnings beat",
      "published_at_utc": "2026-09-18T20:30:00+00:00",
      "source": "Synthetic fixture",
      "url": "https://example.com/synthetic/nasdaq-bull-2026-09-18",
      "direction": "BULLISH",
      "direction_basis": "Synthetic reported results above the fixture expectation",
      "materiality": "HIGH",
      "theme": "nasdaq100",
      "benchmark": "QQQ",
      "reaction_session": "2026-09-21",
      "reaction_return": "0.028821245744430794131500175",
      "volume_ratio": "1.489043445248243047978201284",
      "confirmed": true,
      "reason": "Post-event price and volume confirmed the event direction"
    },
    "candidates": [
      {
        "event_id": "syn-nasdaq-bull-2026-09-18",
        "theme": "nasdaq100",
        "benchmark": "QQQ",
        "symbol": "QQQ",
        "direction": 1,
        "leverage": "1",
        "effective_exposure": "1",
        "close": "741.47",
        "reaction_return": "0.028821245744430794131500175",
        "volume_ratio": "1.489043445248243047978201284",
        "eligible": true,
        "selected": true,
        "reasons": [
          "Selected: confirmed event reaction with the least leveraged liquid instrument"
        ]
      }
    ],
    "selected_theme": "nasdaq100",
    "selected_symbol": "QQQ",
    "direction": "BULLISH",
    "no_trade_reason": null
  },
  "proposal": {
    "schema_version": "1",
    "proposal_id": "directional-event-v2-20260921-QQQ",
    "run_id": "qoder-62b08de4-d64f-43ab-b044-fe781eae393e",
    "strategy_version": "directional-event-v2",
    "decision_time_utc": "2026-09-21T21:00:00Z",
    "data_as_of_utc": "2026-09-21T21:00:00Z",
    "symbol": "QQQ",
    "action": "BUY",
    "requested_quantity": 6,
    "thesis": "Verified earnings event 'Synthetic large-cap technology earnings beat' was published at 2026-09-18T20:30:00+00:00 with bullish evidence (Synthetic reported results above the fixture expectation). The QQQ reaction session 2026-09-21 returned 2.8821% on a 1.49x volume ratio, confirming the direction. QQQ expresses +1x daily QQQ exposure at 1x leverage (effective exposure +1).",
    "invalidation": "Exit at the open after 5 completed sessions; no discretionary agent override.",
    "evidence_ids": [
      "event:syn-nasdaq-bull-2026-09-18",
      "bar:QQQ:2026-09-21",
      "bar:QQQ:20260921"
    ]
  },
  "notice": "Historical Moomoo evidence only; not a current broker snapshot or order authorization."
}
```

### Risk

```json
{
  "ok": true,
  "mode": "HISTORICAL_DRY_RUN",
  "run_id": "qoder-62b08de4-d64f-43ab-b044-fe781eae393e",
  "risk_decision": {
    "proposal_id": "directional-event-v2-20260921-QQQ",
    "policy_version": "risk-v1",
    "decision": "APPROVE",
    "reasons": [],
    "approved_quantity": 6,
    "account_snapshot_id": "qoder-dryrun-qoder-62b08de4-d64f-43ab-b044-fe781eae393e",
    "expires_at_utc": "2026-09-21T21:00:30Z"
  },
  "evaluated_at_utc": "2026-09-21T21:00:00+00:00",
  "control_context": "Hypothetical policy controls only; no owner approval, broker write or live account state.",
  "notice": "An APPROVE result is a policy evaluation, never an order authorization."
}
```

## Sanitized agent summaries

### coordinator_ready

READY qoder-62b08de4-d64f-43ab-b044-fe781eae393e

Mode: HISTORICAL_DRY_RUN

Boundary confirmed for read-only run qoder-62b08de4-d64f-43ab-b044-fe781eae393e. Strategy allowlist and selected strategy both: directional-event-v2. No tools used; no order discussed, created, approved, rejected or executed. This run remains NO_TRADE and is not an order, fill, owner approval or live-account claim.

### researcher

**Mode: HISTORICAL_DRY_RUN** — run_id `qoder-62b08de4-d64f-43ab-b044-fe781eae393e`, strategy `directional-event-v2`.

Note: the artifact did **not** return NO_TRADE — `no_trade_reason` is `null`. It returned a typed BUY *proposal* (research only, not an order authorization). I can't verify account/market state beyond this fixture snapshot.

**Snapshot**
- decision_time_utc / data_as_of_utc: `2026-09-21T21:00:00Z`
- Event: `syn-nasdaq-bull-2026-09-18`, category `earnings`, direction BULLISH, materiality HIGH, published `2026-09-18T20:30:00Z` (source: Synthetic fixture)
- Theme `nasdaq100`, benchmark QQQ, reaction session `2026-09-21`
- Reaction return `2.8821%`, volume ratio `1.49x`, `confirmed: true`
- Selected: QQQ, close `741.47`, leverage `1`, effective exposure `+1`; eligible & selected — "confirmed event reaction with the least leveraged liquid instrument"

**Proposal (non-authorizing)**
- proposal_id `directional-event-v2-20260921-QQQ`, action BUY, requested_quantity 6
- Invalidation: exit at open after 5 completed sessions; no discretionary agent override
- Evidence IDs: `event:syn-nasdaq-bull-2026-09-18`, `bar:QQQ:2026-09-21`, `bar:QQQ:20260921`

Tool notice: "Historical Moomoo evidence only; not a current broker snapshot or order authorization." Risk evaluation, approval, and execution are outside my scope.

### auditor

**Deterministic decision: APPROVE** (policy `risk-v1`, mode `HISTORICAL_DRY_RUN`)

- Run: `qoder-62b08de4-d64f-43ab-b044-fe781eae393e`
- Proposal: `directional-event-v2-20260921-QQQ` (QQQ, BUY, requested 6)
- Approved quantity: 6
- Rule IDs / reasons: **none triggered** — `reasons: []` came back empty, so the gate returned no rule identifiers (no blocking or flagging rules fired).
- Account snapshot: `qoder-dryrun-qoder-62b08de4-d64f-43ab-b044-fe781eae393e`
- Expires: 2026-09-21T21:00:30Z
- Evaluated at: 2026-09-21T21:00:00Z

Caveats that prose cannot override: this was a hypothetical policy evaluation with no live account state or broker access. An APPROVE is **not** owner authorization and **not** an order instruction; nothing was submitted. I have no execution access and made no changes to the proposal.

### coordinator_final

Closing read-only run qoder-62b08de4-d64f-43ab-b044-fe781eae393e. No tools called.

**Deterministic outcome:** HISTORICAL_POLICY_APPROVAL

- Proposal: directional-event-v2-20260921-QQQ (QQQ, BUY, requested 6)
- Strategy: directional-event-v2; theme nasdaq100; benchmark/symbol QQQ
- Evidence basis: synthetic earnings event syn-nasdaq-bull-2026-09-18 (HIGH materiality, BULLISH); reaction session 2026-09-21 returned 2.8821% on 1.49x volume, confirmed
- Invalidation: exit at open after 5 completed sessions; no discretionary override
- Risk gate: risk-v1 → APPROVE (hypothetical), approved quantity 6, no rule IDs fired (reasons: [])
- Account snapshot reference: qoder-dryrun-qoder-62b08de4-d64f-43ab-b044-fe781eae393e
- Evaluated 2026-09-21T21:00:00Z; decision expired 2026-09-21T21:00:30Z

**Limitations**

- This is a historical, hypothetical policy evaluation using a synthetic fixture — not current market data.
- The APPROVE is not owner authorization, not a current approval, and not an order instruction.
- Nothing was created, routed, submitted, or filled; no broker fill exists.
- No live account state or broker connectivity was consulted; the snapshot ID is a dry-run reference only.
- No execution occurred, so the run produced no trade action — NO_TRADE is preserved at the execution level.

Net: the supplied artifact shows only a deterministic historical policy approval of a hypothetical QQQ proposal; it is not a trade, fill, or live approval.

## Limitations

A historical policy approval is not owner authorization. Fresh trusted quote, account, position and order data, exact competition-account verification, durable idempotency and explicit first-order approval remain mandatory before any broker write.
