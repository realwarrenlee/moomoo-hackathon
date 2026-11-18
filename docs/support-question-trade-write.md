# Support question — competition-account-only `trade:write`

**Status:** prepared, **not sent**. Do not request the scope, change OAuth consent or implement order submission until the answer is confirmed and the owner separately approves it.

## Verified documentation (checked 17 November 2026)

- OAuth scopes: <https://open.moomoo.com/api/overview/getting-started> — `trade:write` is defined as "Place, modify, and cancel orders, and complete order confirm". Granted scope echoes as space-separated values (e.g. `quote:read trade:read accid:123456`); the page does not say whether `accid:` restricts write access.
- Trading overview: <https://open.moomoo.com/api/trading/overview> — states that calling the securities trading APIs places real trades.
- Simulated order endpoint: <https://open.moomoo.com/api/sim-trade/input-order> — `POST /api/v1.0/sim-trade/{acc_id}/orders`, with `market` required to match the account (`100` = US margin). It states "Orders are not idempotent: on timeout or an unknown result, check today's orders before retrying." It does **not** state which OAuth scope is required.
- Authorized accounts: <https://open.moomoo.com/api/trading/account/get-accounts> — account metadata includes `account_type`, `market_id`, `acc_id` and `enable_market`.

## Context to include with the question

- Moomoo × Qoder AI Trading Agent Challenge, simulated competition account only (`account_type=2`, dedicated challenge title, masked account `****0101`).
- The current OAuth client consents to read access only; it has no `trade:write`.
- The documented simulated-order endpoint is `POST /api/v1.0/sim-trade/{acc_id}/orders`; the page does not state its required scope.
- The public documentation does not state whether `accid:<id>` narrows `trade:write` to that account, or whether a `trade:write` consent would also permit orders on the user's personal or live accounts.

## Question

> Can a Moomoo OAuth client be authorised with `trade:write` that is technically restricted to one simulated competition account (`account_type=2`) and guaranteed not to permit orders on the user's personal or live accounts?
>
> Does an `accid:<id>` binding limit write scope to that account, or is `trade:write` account-wide?
>
> Is `POST /api/v1.0/sim-trade/{acc_id}/orders` explicitly permitted for the Moomoo × Qoder AI Trading Agent Challenge — which scope does it require, and what competition-specific execution restrictions or order types apply?

## What we need in the answer

1. Whether write scope can be constrained to the competition account at the OAuth/client level.
2. What technically enforces that constraint (scope, account binding, token audience, server-side check).
3. Whether any residual write path to personal/live accounts would remain.
4. Any challenge-specific rules on instruments, order types, session restrictions or rate limits.

## Explicit non-actions until answered and approved

- No `trade:write` scope request or OAuth consent change.
- No order-submission implementation or order endpoint call.
- No change to `ORDER_WRITES_ENABLED=false`.
- No unattended or supervised order authorisation.
