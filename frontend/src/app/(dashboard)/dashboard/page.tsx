"use client"

import {
  Freshness,
  InfoNote,
  InlineLink,
  KeyValue,
  LoadingPage,
  PageContainer,
  PageHeader,
  PageState,
  Section,
  Stat,
  StatGrid,
} from "@/components/mootrade/primitives"
import { useDashboard } from "@/components/mootrade/use-dashboard"
import {
  investedValue,
  marketSession,
  money,
  outcomeLabel,
  type OverviewResponse,
} from "@/lib/mootrade"
import { cn } from "@/lib/utils"

export default function OverviewPage() {
  const { data, error, loading, refresh } =
    useDashboard<OverviewResponse>("overview", 60_000)

  if (loading && !data) return <LoadingPage />

  if (!data) {
    return (
      <PageContainer>
        <PageHeader title="Overview" />
        <PageState
          title="Dashboard API unreachable"
          description={`${error ?? "No response"} Start the local MooTrade read-only API to view paper account data.`}
          onRetry={refresh}
        />
      </PageContainer>
    )
  }

  const account = data.account
  const run = data.latest_agent_run
  const safety = data.safety
  const session = marketSession(data.quotes)
  const spy = data.quotes.find((quote) => quote.symbol === "SPY")
  const invested = investedValue(account?.equity, account?.cash)
  const staleQuotes = data.quotes.filter((quote) => quote.stale)

  const blockers: string[] = []
  if (!safety.order_writes_enabled) blockers.push("Order writes are disabled")
  if (safety.first_order_approval_count === 0)
    blockers.push("No first-order owner approval")
  if (!session.open) blockers.push(`${session.label} · regular session required`)
  if (staleQuotes.length > 0)
    blockers.push(`${staleQuotes.length} quotes older than 300s`)
  if (!safety.broker_order_endpoint_available)
    blockers.push("No order endpoint is enabled")

  const warnings = data.warnings.filter((warning) => {
    if (warning === "US regular market session is not open.") return false
    if (!session.open && warning.includes("outside the 300-second")) return false
    return true
  })
  const unavailable = data.state === "UNAVAILABLE"

  const proposal = run?.proposal
  const proposalText = proposal
    ? [proposal.action, proposal.requested_quantity, proposal.symbol]
        .filter((value) => value !== null && value !== undefined && value !== "")
        .join(" ")
    : null
  const headline = proposalText ?? outcomeLabel(run?.outcome)
  const decision = run?.risk_decision?.decision?.toUpperCase()
  const rejected = decision === "REJECT" || decision === "REJECTED"
  const approved = decision === "APPROVE" || decision === "APPROVED"
  const outcome = !run
    ? null
    : rejected
      ? "Blocked by RiskGate — no order placed."
      : approved
        ? "Approved by RiskGate — no order submitted."
        : run.outcome === "AGENT_ERROR"
          ? "Run failed — no order placed."
          : proposal
            ? "Proposal only — execution not evaluated."
            : "No order proposed."

  return (
    <PageContainer>
      <PageHeader title="Overview" />

      {unavailable ? (
        <InfoNote tone="danger">
          <p className="font-medium">Account data unavailable</p>
          <ul className="list-disc space-y-0.5 pl-4">
            {(data.warnings.length ? data.warnings : ["No broker response."]).map(
              (warning) => (
                <li key={warning}>{warning}</li>
              )
            )}
          </ul>
        </InfoNote>
      ) : warnings.length > 0 ? (
        <InfoNote tone="warning">
          <ul className="list-disc space-y-0.5 pl-4">
            {warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </InfoNote>
      ) : null}

      <StatGrid columns={3}>
        <Stat
          label="Equity"
          value={money(account?.equity)}
          hint={
            account ? (
              <span className="inline-flex items-center gap-1">
                Account snapshot · <Freshness seconds={account.age_seconds} />
              </span>
            ) : (
              "Broker read unavailable"
            )
          }
        />
        <Stat
          label="Invested"
          value={invested === null ? "—" : money(invested)}
          hint={
            account ? `${account.positions_count ?? 0} open positions` : "Positions unavailable"
          }
        />
        <Stat label="Cash" value={money(account?.cash)} />
      </StatGrid>

      <div className="grid gap-5 lg:grid-cols-3">
        <Section className="lg:col-span-2" title="Latest AI decision">
          {run ? (
            <div className="space-y-2.5">
              <p className="text-2xl font-semibold tracking-tight">{headline}</p>
              <p className="max-w-2xl text-[13px] leading-relaxed text-muted-foreground">
                {run.decision_reason ?? run.no_trade_reason ?? "No decision reason recorded."}
              </p>
              {outcome ? (
                <p
                  className={cn(
                    "text-[13px] font-medium",
                    rejected
                      ? "text-rose-700 dark:text-rose-300"
                      : "text-foreground"
                  )}
                >
                  {outcome}
                </p>
              ) : null}
              <InlineLink href="/agents">Open decision evidence</InlineLink>
            </div>
          ) : (
            <p className="py-4 text-[13px] text-muted-foreground">
              No completed agent run is recorded. The dashboard never substitutes
              synthetic agent output.
            </p>
          )}
        </Section>

        <Section title="Trading eligibility">
          {blockers.length > 0 ? (
            <ul className="space-y-2">
              {blockers.slice(0, 3).map((blocker) => (
                <li
                  key={blocker}
                  className="flex gap-2 text-xs leading-relaxed text-muted-foreground"
                >
                  <span className="mt-1.5 size-1 shrink-0 rounded-full bg-muted-foreground/50" />
                  <span>{blocker}</span>
                </li>
              ))}
              {blockers.length > 3 ? (
                <li className="pl-3 text-xs text-muted-foreground">
                  +{blockers.length - 3} more checks
                </li>
              ) : null}
            </ul>
          ) : (
            <p className="text-xs text-muted-foreground">
              All deterministic checks pass.
            </p>
          )}
          <div className="mt-3 border-t pt-2">
            <InlineLink href="/risk">Risk Centre</InlineLink>
          </div>
        </Section>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Section title="Positions" action={<InlineLink href="/portfolio">Portfolio</InlineLink>}>
          <KeyValue
            label="Open positions"
            value={
              !account
                ? "Unavailable"
                : (account.positions_count ?? 0) > 0
                  ? `${account.positions_count} · ${money(invested)}`
                  : "None"
            }
          />
          <KeyValue
            label="Open orders"
            value={account ? String(account.open_orders_count ?? 0) : "—"}
            mono
          />
          {account && !account.reconciled ? (
            <p className="mt-2 flex gap-2 text-xs leading-relaxed text-amber-700 dark:text-amber-300">
              <span className="mt-1.5 size-1 shrink-0 rounded-full bg-amber-600 dark:bg-amber-400" />
              Reconciliation mismatch — review broker state.
            </p>
          ) : null}
          {account && (account.unknown_orders ?? 0) > 0 ? (
            <p className="mt-2 flex gap-2 text-xs leading-relaxed text-rose-700 dark:text-rose-300">
              <span className="mt-1.5 size-1 shrink-0 rounded-full bg-rose-600 dark:bg-rose-400" />
              Unknown order outcomes detected.
            </p>
          ) : null}
          <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
            {!account
              ? "Positions and orders are unknown while the broker read is unavailable."
              : (account.positions_count ?? 0) > 0
                ? "Holdings are read from the broker."
                : "No open positions — all equity is held in cash."}
          </p>
        </Section>

        <Section title="Market" action={<InlineLink href="/risk">Gate inputs</InlineLink>}>
          <KeyValue label="Session" value={session.label} />
          <KeyValue
            label="SPY last"
            value={spy?.price ? money(spy.price) : "—"}
            mono
          />
          <KeyValue
            label="Quote freshness"
            value={
              spy ? (
                <Freshness seconds={spy.age_seconds} stale={spy.stale} />
              ) : (
                "Unavailable"
              )
            }
          />
        </Section>
      </div>
    </PageContainer>
  )
}
