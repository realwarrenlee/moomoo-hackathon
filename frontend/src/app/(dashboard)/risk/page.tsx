"use client"

import {
  EmptyRow,
  LoadingPage,
  Metric,
  MetricStrip,
  NoticeBanner,
  PageHeader,
  RefreshButton,
  SectionCard,
  StatePanel,
  TableShell,
} from "@/components/mootrade/primitives"
import { useDashboard } from "@/components/mootrade/use-dashboard"
import {
  ageLabel,
  humanState,
  money,
  percent,
  utcTimestamp,
  type PreflightView,
  type RiskResponse,
} from "@/lib/mootrade"
import { cn } from "@/lib/utils"

const RULES = [
  ["R001", "Account verified", "Exact competition paper fingerprint and paper environment."],
  ["R002", "Allowlist universe", "Only SPY, QQQ and IWM may be evaluated or proposed."],
  ["R003", "No short positions", "NO_TRADE is never submitted; sell size cannot exceed holdings."],
  ["R004", "Single exposure cap", "Post-order instrument exposure must stay within 10% of equity."],
  ["R005", "Gross exposure cap", "Post-order gross exposure must stay within 30% of equity."],
  ["R006", "Daily drawdown stop", "New buying halted if daily portfolio drawdown reaches 2%."],
  ["R007", "Fresh quote data", "Quote ≤300s and account snapshot ≤60s. Stale and future timestamps fail closed."],
  ["R008", "Cash-only buying power", "Unlevered cash balance after a US$5 buffer must cover the order."],
  ["R009", "Reconciled broker state", "Account state must reconcile cleanly with zero unknown orders."],
  ["R010", "Control switch state", "Order writes, kill switch and circuit breaker must all permit execution."],
  ["R011", "Idempotency enforcement", "A proposal with a durable submission record cannot repeat."],
  ["R012", "Regular trading session", "Order proposals are limited strictly to the regular exchange session."],
  ["R013", "Position count limit", "Post-order open positions cannot exceed three."],
  ["R014", "First order approval", "The initial paper order requires explicit owner approval."],
] as const

function passBlock(ok: boolean | null | undefined) {
  if (ok === null || ok === undefined)
    return { label: "UNKNOWN", className: "text-muted-foreground" }
  return ok
    ? { label: "PASS", className: "text-emerald-600 dark:text-emerald-400" }
    : { label: "BLOCK", className: "text-rose-600 dark:text-rose-400" }
}

function PreflightSection({ preflight }: { preflight: PreflightView | null }) {
  if (!preflight) {
    return (
      <SectionCard
        title="Recorded real preflight"
        description="Execution-time read-only preflight audit evidence."
      >
        <StatePanel
          title="No preflight artifact recorded"
          description="No execution preflight artifact has been recorded in this environment."
        />
      </SectionCard>
    )
  }

  const rejected = preflight.decision?.toUpperCase() !== "APPROVE"
  return (
    <SectionCard
      title="Recorded real preflight audit"
      description="Real read-only preflight evaluated against the competition paper account. No order was dispatched."
      contentClassName="space-y-3"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 border-b pb-2.5">
        <div className="flex items-center gap-2.5">
          <span
            className={cn(
              "font-mono text-sm font-bold tracking-tight",
              rejected ? "text-rose-600 dark:text-rose-400" : "text-emerald-600 dark:text-emerald-400"
            )}
          >
            {humanState(preflight.decision)}
          </span>
          <span className="text-muted-foreground">·</span>
          <span className="text-xs text-muted-foreground">
            {preflight.kind ?? "preflight"} · Recorded{" "}
            {utcTimestamp(preflight.checked_at_utc)}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 text-[10px] font-mono text-muted-foreground">
          <span>submission_performed={String(preflight.submission_performed)}</span>
          <span>·</span>
          <span>endpoint_contacted={String(preflight.order_endpoint_contacted)}</span>
          <span>·</span>
          <span>trade:write={String(preflight.scope_trade_write)}</span>
        </div>
      </div>

      {preflight.reasons.length > 0 ? (
        <div className="space-y-1.5 rounded-lg border border-rose-500/20 bg-rose-500/[0.03] p-3 text-xs">
          <p className="font-medium text-foreground">
            Rejection rules triggered:{" "}
            <span className="font-mono font-semibold text-rose-600 dark:text-rose-400">
              {preflight.rejection_rule_ids.join(", ") || "none"}
            </span>
          </p>
          <ul className="space-y-1 text-[11px] leading-relaxed text-muted-foreground">
            {preflight.reasons.map((reason, index) => (
              <li key={`${index}-${reason}`} className="flex gap-2">
                <span className="mt-1.5 size-1 shrink-0 rounded-full bg-rose-500/80" />
                <span>{reason}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {preflight.quotes.length > 0 ? (
        <TableShell>
          <table className="w-full text-left text-[11px]">
            <thead>
              <tr className="border-b text-[10px] text-muted-foreground">
                <th className="px-3 py-2 font-medium">Symbol</th>
                <th className="px-3 py-2 text-right font-medium">Last price</th>
                <th className="px-3 py-2 text-right font-medium">Age</th>
                <th className="hidden px-3 py-2 font-medium md:table-cell">Quote time (UTC)</th>
                <th className="hidden px-3 py-2 font-medium lg:table-cell">Security status</th>
                <th className="hidden px-3 py-2 font-medium xl:table-cell">Session</th>
              </tr>
            </thead>
            <tbody>
              {preflight.quotes.map((quote) => (
                <tr key={quote.symbol} className="border-b last:border-0">
                  <td className="px-3 py-2 font-mono font-semibold">{quote.symbol}</td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">
                    {money(quote.last_price)}
                  </td>
                  <td
                    className={cn(
                      "px-3 py-2 text-right font-mono tabular-nums",
                      (quote.age_seconds ?? 0) > 300
                        ? "text-amber-600 dark:text-amber-400"
                        : "text-muted-foreground"
                    )}
                  >
                    {ageLabel(quote.age_seconds)}
                  </td>
                  <td className="hidden px-3 py-2 font-mono text-[10px] text-muted-foreground md:table-cell">
                    {utcTimestamp(quote.data_time_utc)}
                  </td>
                  <td className="hidden px-3 py-2 text-[10px] text-muted-foreground lg:table-cell">
                    {quote.sec_status ?? "—"}
                    {quote.suspension ? " (SUSPENDED)" : ""}
                  </td>
                  <td className="hidden px-3 py-2 text-muted-foreground xl:table-cell">
                    {humanState(quote.market_state)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableShell>
      ) : null}
    </SectionCard>
  )
}

export default function RiskPage() {
  const { data, error, loading, refreshing, refreshedAt, refresh } =
    useDashboard<RiskResponse>("risk", 60_000)

  if (loading && !data) return <LoadingPage />

  if (error && !data) {
    return (
      <div className="space-y-5 p-4 md:p-6">
        <PageHeader
          title="Risk Centre"
          description="Deterministic RiskGate policy limits, live gate inputs and preflight audit records."
        />
        <StatePanel
          kind="error"
          title="Risk state unavailable"
          description={error}
          action={
            <RefreshButton
              onClick={refresh}
              refreshing={refreshing}
              refreshedAt={refreshedAt}
            />
          }
        />
      </div>
    )
  }

  if (!data) return null

  const controls = data.controls
  const account = data.account
  const accountFresh =
    account?.age_seconds !== null && account?.age_seconds !== undefined
      ? account.age_seconds <= data.limits.max_account_age_seconds
      : null

  return (
    <div className="space-y-5 p-4 md:p-6">
      <PageHeader
        title="Risk Centre"
        description="The deterministic RiskGate is the final authority on order eligibility. Neither LLMs nor this UI can override its decision."
        actions={
          <RefreshButton
            onClick={refresh}
            refreshing={refreshing}
            refreshedAt={refreshedAt}
          />
        }
      />

      {/* Unified Authoritative Execution Safety Surface */}
      <div className="rounded-lg border border-rose-500/20 bg-rose-500/[0.03] p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-rose-500/15 pb-2.5">
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs font-bold text-rose-600 dark:text-rose-400">
              EXECUTION LOCKED
            </span>
            <span className="text-muted-foreground">·</span>
            <span className="text-xs text-muted-foreground">
              Deterministic preflight gate enforces read-only boundary
            </span>
          </div>
          <span className="font-mono text-[10px] text-muted-foreground">
            Policy {data.policy_version} · Submissions {controls.submission_count}
          </span>
        </div>

        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded border bg-card/60 px-3 py-2">
            <p className="text-[10px] text-muted-foreground">Order writes</p>
            <p className="font-mono text-xs font-semibold text-rose-600 dark:text-rose-400">
              {controls.order_writes_enabled ? "ENABLED" : "DISABLED"}
            </p>
          </div>
          <div className="rounded border bg-card/60 px-3 py-2">
            <p className="text-[10px] text-muted-foreground">Kill switch</p>
            <p className="text-xs font-semibold">
              {controls.kill_switch_engaged ? "ENGAGED" : "Clear (persisted)"}
            </p>
          </div>
          <div className="rounded border bg-card/60 px-3 py-2">
            <p className="text-[10px] text-muted-foreground">First order approval</p>
            <p className="text-xs font-semibold">
              {controls.first_order_approval_count > 0
                ? `Approved (${controls.first_order_approval_count})`
                : "Not granted"}
            </p>
          </div>
          <div className="rounded border bg-card/60 px-3 py-2">
            <p className="text-[10px] text-muted-foreground">Order transport</p>
            <p className="text-xs font-semibold">
              {controls.broker_order_endpoint_available ? "Available" : "Not implemented"}
            </p>
          </div>
        </div>

        {data.lock_reasons.length > 0 ? (
          <div className="mt-3 space-y-1">
            <p className="text-[11px] font-medium text-foreground">Active safety blockers:</p>
            <ul className="grid gap-1 text-[11px] text-muted-foreground md:grid-cols-2">
              {data.lock_reasons.map((reason) => (
                <li key={reason} className="flex gap-2">
                  <span className="mt-1.5 size-1 shrink-0 rounded-full bg-rose-500/80" />
                  <span>{reason}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>

      {data.warnings.length > 0 ? (
        <NoticeBanner tone="warning" title="Gate input observations">
          <ul className="list-disc space-y-0.5 pl-4">
            {data.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </NoticeBanner>
      ) : null}

      {/* Quantitative Risk Limits Strip */}
      <MetricStrip>
        <Metric
          label="Single exposure limit"
          value={percent(data.limits.max_single_exposure_pct, 0)}
          detail="10% equity cap per symbol"
        />
        <Metric
          label="Gross exposure limit"
          value={percent(data.limits.max_total_exposure_pct, 0)}
          detail={`Max ${data.limits.max_open_positions} positions`}
        />
        <Metric
          label="Daily drawdown limit"
          value={percent(data.limits.max_daily_drawdown_pct, 1)}
          detail="Halt buying at 2.0% loss"
        />
        <Metric
          label="Freshness thresholds"
          value={`${data.limits.max_quote_age_seconds}s / ${data.limits.max_account_age_seconds}s`}
          detail="Quote / Account snapshot"
        />
      </MetricStrip>

      {/* Live Gate Inputs Table */}
      <SectionCard
        title="Live gate inputs & freshness evaluation"
        description="Current market data and broker state evaluated against RiskGate criteria."
      >
        <div className="mb-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b pb-2 text-xs">
          <div className="flex items-center gap-3">
            <span className="text-muted-foreground">Account {account?.masked_id ?? "—"}</span>
            <span className="text-muted-foreground">·</span>
            <span className="font-semibold text-emerald-600 dark:text-emerald-400">
              {passBlock(account?.verified === true && accountFresh === true).label}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-muted-foreground">Reconciliation</span>
            <span className="text-muted-foreground">·</span>
            <span className="font-semibold text-emerald-600 dark:text-emerald-400">
              {passBlock(account ? account.reconciled === true && !account.unknown_orders : null).label}
            </span>
          </div>
        </div>

        <TableShell>
          <table className="w-full text-left text-[11px]">
            <thead>
              <tr className="border-b text-[10px] text-muted-foreground">
                <th className="px-3 py-2 font-medium">Symbol</th>
                <th className="px-3 py-2 text-right font-medium">Last price</th>
                <th className="px-3 py-2 text-right font-medium">Age</th>
                <th className="hidden px-3 py-2 font-medium md:table-cell">Quote time (UTC)</th>
                <th className="hidden px-3 py-2 font-medium lg:table-cell">Market session</th>
                <th className="px-3 py-2 text-right font-medium">Gate status</th>
              </tr>
            </thead>
            <tbody>
              {data.quotes.length === 0 ? (
                <EmptyRow colSpan={6} label="No quote observations returned." />
              ) : (
                data.quotes.map((quote) => {
                  const state = passBlock(quote.fresh === true)
                  return (
                    <tr key={quote.symbol} className="border-b last:border-0">
                      <td className="px-3 py-2 font-mono font-semibold">{quote.symbol}</td>
                      <td className="px-3 py-2 text-right font-mono tabular-nums">
                        {quote.price ? money(quote.price) : "—"}
                      </td>
                      <td className="px-3 py-2 text-right text-muted-foreground">
                        {ageLabel(quote.age_seconds)}
                      </td>
                      <td className="hidden px-3 py-2 font-mono text-[10px] text-muted-foreground md:table-cell">
                        {utcTimestamp(quote.as_of_utc)}
                      </td>
                      <td className="hidden px-3 py-2 text-muted-foreground lg:table-cell">
                        {quote.regular_session_open ? "Regular session" : "Closed"}
                      </td>
                      <td className={cn("px-3 py-2 text-right font-medium", state.className)}>
                        {state.label}
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </TableShell>
      </SectionCard>

      {/* Recorded Real Preflight */}
      <PreflightSection preflight={data.last_real_preflight} />

      {/* 14 Deterministic Rules Reference Table */}
      <SectionCard
        title="Deterministic rule catalogue"
        description="14 deterministic checks enforced before any order dispatch. If any single rule fails, execution is blocked."
      >
        <TableShell>
          <table className="w-full text-left text-[11px]">
            <thead>
              <tr className="border-b text-[10px] text-muted-foreground">
                <th className="w-16 px-3 py-2 font-medium">Rule</th>
                <th className="w-48 px-3 py-2 font-medium">Check name</th>
                <th className="px-3 py-2 font-medium">Requirement & condition</th>
              </tr>
            </thead>
            <tbody>
              {RULES.map(([id, name, description]) => (
                <tr key={id} className="border-b last:border-0">
                  <td className="px-3 py-2 font-mono font-semibold text-muted-foreground">
                    {id}
                  </td>
                  <td className="px-3 py-2 font-medium text-foreground">{name}</td>
                  <td className="px-3 py-2 text-muted-foreground">{description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableShell>
      </SectionCard>
    </div>
  )
}
