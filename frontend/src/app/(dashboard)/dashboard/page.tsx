"use client"

import Link from "next/link"
import { ArrowRightIcon, CheckCircle2Icon, ShieldAlertIcon } from "lucide-react"

import {
  EmptyRow,
  KeyValue,
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
import { Button } from "@/components/ui/button"
import {
  ageLabel,
  humanState,
  money,
  strategyLabel,
  utcTimestamp,
  type AuditResponse,
  type OverviewResponse,
  type QuoteView,
} from "@/lib/mootrade"
import { cn } from "@/lib/utils"

function quoteStatus(quote: QuoteView) {
  if (quote.state === "UNAVAILABLE")
    return { label: "Unavailable", className: "text-muted-foreground" }
  if (quote.stale)
    return { label: "Stale", className: "text-amber-600 dark:text-amber-400" }
  if (quote.fresh)
    return { label: "Fresh", className: "text-emerald-600 dark:text-emerald-400" }
  return { label: quote.state, className: "text-muted-foreground" }
}

export default function OverviewPage() {
  const { data, error, loading, refreshing, refreshedAt, refresh } =
    useDashboard<OverviewResponse>("overview", 60_000)
  const audit = useDashboard<AuditResponse>("audit", 60_000)

  if (loading && !data) return <LoadingPage />

  if (error && !data) {
    return (
      <div className="space-y-5 p-4 md:p-6">
        <PageHeader
          title="Overview"
          description="Competition paper account status, market observations, and execution safety."
        />
        <StatePanel
          kind="error"
          title="Dashboard API unreachable"
          description={`${error} Start the local FastAPI backend to view paper account data.`}
          action={
            <Button variant="outline" size="sm" onClick={refresh}>
              Try again
            </Button>
          }
        />
      </div>
    )
  }

  if (!data) return null

  const account = data.account
  const run = data.latest_agent_run
  const unavailable = data.state === "UNAVAILABLE"
  const controls = data.safety

  return (
    <div className="space-y-5 p-4 md:p-6">
      <PageHeader
        title="Overview"
        description="Competition paper account status, market observations, and execution safety."
        actions={
          <RefreshButton
            onClick={refresh}
            refreshing={refreshing}
            refreshedAt={refreshedAt}
          />
        }
      />

      {/* Compact Account Context Bar */}
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-lg border bg-card px-3.5 py-2 text-xs">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="font-mono font-semibold tracking-tight text-foreground">
            {account?.masked_id ?? "—"}
          </span>
          <span className="text-muted-foreground">·</span>
          <span className="text-muted-foreground">
            {account?.title ?? "Moomoo Competition Sim Account"}
          </span>
          <span className="hidden text-muted-foreground sm:inline">·</span>
          <span className="hidden font-mono text-[11px] text-muted-foreground sm:inline">
            US Simulated (type {account?.account_type ?? 2})
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
          {account?.verified ? (
            <span className="flex items-center gap-1 font-medium text-emerald-600 dark:text-emerald-400">
              <CheckCircle2Icon className="size-3" />
              Verified
            </span>
          ) : null}
          <span className="text-muted-foreground">·</span>
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <span
              className={cn(
                "size-1.5 rounded-full",
                account?.reconciled ? "bg-emerald-500" : "bg-amber-500"
              )}
            />
            {account?.reconciled ? "Reconciled" : "Reconciliation attention"}
          </span>
          <span className="hidden text-muted-foreground md:inline">·</span>
          <span className="hidden font-mono text-muted-foreground md:inline">
            Snapshot {utcTimestamp(account?.as_of_utc)}
          </span>
        </div>
      </div>

      {data.warnings.length > 0 ? (
        <NoticeBanner
          tone={unavailable ? "danger" : "warning"}
          title={unavailable ? "Account data unavailable" : "Attention required"}
        >
          <ul className="list-disc space-y-0.5 pl-4">
            {data.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </NoticeBanner>
      ) : null}

      {/* Key Financial Metrics */}
      <MetricStrip>
        <Metric
          label="Paper equity"
          value={money(account?.equity)}
          detail={
            account
              ? `Snapshot ${ageLabel(account.age_seconds)}`
              : "Requires broker read connection"
          }
        />
        <Metric
          label="Cash balance"
          value={money(account?.cash)}
          detail="Unlevered broker cash"
        />
        <Metric
          label="Buying power"
          value={money(account?.buying_power)}
          detail="Cash-only sizing (US$5 buffer)"
        />
        <Metric
          label="Positions / orders"
          value={
            account
              ? `${account.positions_count ?? 0} / ${account.open_orders_count ?? 0}`
              : "—"
          }
          detail={
            account
              ? account.reconciled
                ? "Clean broker state"
                : "Reconciliation mismatch"
              : "No snapshot"
          }
          tone={account?.reconciled === false ? "warning" : "neutral"}
        />
      </MetricStrip>

      {/* Market Tape Table */}
      <SectionCard
        title="Market tape"
        description="Moomoo quote observations for approved ETF universe. Stale quotes are never treated as executable."
        contentClassName="space-y-2"
      >
        <TableShell>
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b text-left text-[10px] text-muted-foreground">
                <th className="px-3 py-2 font-medium">Symbol</th>
                <th className="px-3 py-2 text-right font-medium">Last</th>
                <th className="hidden px-3 py-2 font-medium md:table-cell">
                  Market data (UTC)
                </th>
                <th className="px-3 py-2 text-right font-medium">Age</th>
                <th className="hidden px-3 py-2 font-medium sm:table-cell">Session</th>
                <th className="px-3 py-2 text-right font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {data.quotes.length === 0 ? (
                <EmptyRow colSpan={6} label="No quote observations returned." />
              ) : (
                data.quotes.map((quote) => {
                  const status = quoteStatus(quote)
                  return (
                    <tr key={quote.symbol} className="border-b last:border-0">
                      <td className="px-3 py-2 font-mono font-semibold">{quote.symbol}</td>
                      <td className="px-3 py-2 text-right font-mono tabular-nums">
                        {money(quote.price)}
                      </td>
                      <td className="hidden px-3 py-2 font-mono text-[10px] text-muted-foreground md:table-cell">
                        {utcTimestamp(quote.as_of_utc)}
                      </td>
                      <td className="px-3 py-2 text-right text-muted-foreground">
                        {ageLabel(quote.age_seconds)}
                      </td>
                      <td className="hidden px-3 py-2 text-muted-foreground sm:table-cell">
                        {quote.market_state ? humanState(quote.market_state) : "—"}
                      </td>
                      <td className={cn("px-3 py-2 text-right font-medium", status.className)}>
                        {status.label}
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </TableShell>
      </SectionCard>

      {/* Tri-Column Operations Surface: Safety, Latest Agent Run, Recent Ledger */}
      <div className="grid gap-4 lg:grid-cols-3">
        {/* Execution Safety Status */}
        <SectionCard
          title="Execution safety"
          description="Deterministic preflight gate state."
        >
          <div className="flex items-center justify-between border-b pb-2">
            <span className="text-[11px] text-muted-foreground">Status</span>
            <span className="inline-flex items-center gap-1 font-mono text-[11px] font-semibold text-rose-600 dark:text-rose-400">
              <ShieldAlertIcon className="size-3" />
              LOCKED
            </span>
          </div>
          <KeyValue
            label="Order writes"
            value={
              <span className="text-rose-600 dark:text-rose-400">
                {controls.order_writes_enabled ? "ENABLED" : "DISABLED"}
              </span>
            }
          />
          <KeyValue
            label="Kill switch"
            value={controls.kill_switch_engaged ? "ENGAGED" : "Clear (persisted)"}
          />
          <KeyValue
            label="First order approval"
            value={
              controls.first_order_approval_count > 0
                ? `Approved (${controls.first_order_approval_count})`
                : "Not granted"
            }
          />
          <KeyValue
            label="Order transport"
            value={controls.broker_order_endpoint_available ? "Available" : "Not implemented"}
          />
          <Button
            render={<Link href="/risk" />}
            nativeButton={false}
            variant="ghost"
            size="sm"
            className="mt-2 -ml-2 h-7 px-2 text-[11px] text-muted-foreground hover:text-foreground"
          >
            Open Risk Centre
            <ArrowRightIcon className="size-3" />
          </Button>
        </SectionCard>

        {/* Latest Qoder Run */}
        <SectionCard
          title="Latest agent run"
          description="Most recent recorded Qoder evidence."
        >
          {run ? (
            <>
              <div className="flex items-baseline justify-between border-b pb-2">
                <span className="text-[13px] font-semibold">
                  {run.outcome === "NO_TRADE" ? "No trade" : run.outcome}
                </span>
                <span className="text-[11px] text-muted-foreground">
                  {strategyLabel(run.strategy_version)}
                </span>
              </div>
              <KeyValue label="Regime" value={run.regime_ok ? "Positive" : "Negative"} />
              <KeyValue
                label="Candidates"
                value={`${run.candidates.filter((c) => c.selected).length} selected / ${run.candidates.length}`}
              />
              <KeyValue label="Sessions" value={`${run.session_count} cloud sessions`} />
              <KeyValue label="Completed" value={utcTimestamp(run.completed_at_utc)} mono />
              <p className="mt-2 line-clamp-2 text-[11px] leading-relaxed text-muted-foreground">
                {run.no_trade_reason ?? run.regime_reason ?? "Historical dry run evidence."}
              </p>
              <Button
                render={<Link href="/agents" />}
                nativeButton={false}
                variant="ghost"
                size="sm"
                className="mt-2 -ml-2 h-7 px-2 text-[11px] text-muted-foreground hover:text-foreground"
              >
                Inspect agent activity
                <ArrowRightIcon className="size-3" />
              </Button>
            </>
          ) : (
            <StatePanel
              title="No agent run recorded"
              description="No completed Qoder run artifact found."
            />
          )}
        </SectionCard>

        {/* Recent Ledger Activity */}
        <SectionCard
          title="Audit ledger"
          description="Append-only immutable event log."
        >
          {audit.data?.events.length ? (
            <div className="divide-y">
              {audit.data.events.slice(0, 4).map((event) => (
                <div key={event.event_id} className="py-1.5 first:pt-0 last:pb-0">
                  <p className="line-clamp-1 text-[11px] font-medium leading-tight">
                    {event.summary}
                  </p>
                  <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">
                    {event.event_type} · {utcTimestamp(event.occurred_at_utc)}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <StatePanel
              title="No events"
              description="The ledger has no recorded events yet."
            />
          )}
          <Button
            render={<Link href="/audit" />}
            nativeButton={false}
            variant="ghost"
            size="sm"
            className="mt-2 -ml-2 h-7 px-2 text-[11px] text-muted-foreground hover:text-foreground"
          >
            Open Audit Log
            <ArrowRightIcon className="size-3" />
          </Button>
        </SectionCard>
      </div>
    </div>
  )
}
