# Support inquiry draft — simulated order refused (ret_code=-5) for US.SH

Prepared 19 November 2026 after the owner's decision to ask challenge support. Send via the official challenge support channel; nothing here is confidential.

**Superseded 20 November 2026 — do not send.** The cause was verified locally from the official participation handbook (`https://moomoo-qoder-challenge-rgkelnyuzbm.qoder.website/`, fetched 20 Nov 00:21Z), which states under "Moomoo Paper Trading Account Terms & Conditions" §3: **"Exposure to stock/ETF may not exceed 40% of total initial account assets."** The approved BUY 1,764 SH (≈ USD 59.5–60.1k ≈ 60% of the account) exceeds the cap; the filled QQQ 1-share order did not. Classification: `VERIFIED_CONCENTRATION_LIMIT`. See `docs/evidence.md` (20 November section). Draft retained below for the record.

---

**Subject:** Simulated order input returns ret_code=-5 (backend business error) for US.SH on the challenge paper account

Account: **Moomoo x Qoder AI Paper Trading Agent Challenge** (id ending `0101`, `market_id=100`)
Endpoint: `POST /api/v1.0/sim-trade/{acc_id}/orders` (documented simulated-order input)

**Observed behaviour**

- 18 Nov: QQQ BUY 1 and SELL 1 submitted through this endpoint both filled and reconciled.
- 19 Nov, during the regular US session (`AFTERNOON`, 15:33–16:21 UTC): five submissions of **BUY 1,764 US.SH** (market order: `order_type=3`, `order_side=1`, `order_trade_time_type=1`) each returned HTTP 200 with `ret_code=-5`, `ret_msg='backend business error'`, and **no order was created** (verified against Today's Orders and order history after each attempt).

**Read-only checks that succeeded for the same account and symbol**

- `GET /api/v1.0/sim-trade/{acc_id}/max-buy-sell` → `ret_code=0`, `max_cash_buy_qty_round_lot=2442` (≥ 1,764).
- Stock basic info for `US.SH` → `NORMAL` state, ETF, lot size 1, not suspended.

**Questions**

1. Does the challenge paper account restrict certain ETF types (for example inverse ETFs such as SH)? If so, which instruments are eligible?
2. Is there a per-order notional or quantity limit that would refuse this order, and where is it documented?
3. What business rules map to `ret_code=-5` for this account, and is there any endpoint or response field that returns the specific reason?
