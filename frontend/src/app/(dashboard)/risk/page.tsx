"use client"

import { ChevronDownIcon } from "lucide-react"

import {
  EmptyRow,
  Freshness,
  InfoNote,
  KeyValue,
  LoadingPage,
  Meter,
  PageContainer,
  PageHeader,
  PageState,
  Section,
  StatusPill,
  TableShell,
  Td,
  Th,
} from "@/components/mootrade/primitives"
import { useDashboard } from "@/components/mootrade/use-dashboard"
import {
  RISK_RULES,
  grossExposurePct,
  humanState,
  investedValue,
  money,
  percent,
  ruleLabel,
  shortDateTime,
  signedPercent,
  type RiskResponse,
} from "@/lib/mootrade"

const EXECUTION_ALLOWLIST = ["SPY", "QQQ", "IWM"] as const
const RESEARCH_UNIVERSE = [
  { symbol: "SPY", exposure: "1x long" },
  { symbol: "UPRO", exposure: "3x long" },
  { symbol: "SH", exposure: "1x inverse" },
  { symbol: "SPXU", exposure: "3x inverse" },
] as const

function blockerText(reason: string): string {
  if (reason === "ORDER_WRITES_ENABLED=false")
    return "Order writes are disabled by configuration."
  if (reason.includes("first-order"))
    return "No first-order owner approval is recorded."
  if (reason.includes("fresh quote"))
    return "No quote is fresh enough to execute (300s window)."
  if (reason.includes("regular market session"))
    return "The US regular session is closed."
  if (reason.includes("no order endpoint"))
    return "The read-only adapter exposes no order endpoint."
  return reason
}

function RulesReference() {
  return (
    <details className="group">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-[13px] font-medium text-foreground">
        Show rule catalogue ({Object.keys(RISK_RULES).length})
        <ChevronDownIcon className="size-3.5 text-muted-foreground transition-transform group-open:rotate-180" />
      </summary>
      <div className="-mx-4 mt-3 border-t">
        <TableShell>
          <thead>
            <tr>
              <Th className="w-12 sm:w-16">Rule</Th>
              <Th className="w-14 sm:w-40 lg:w-56">Check</Th>
              <Th>Requirement</Th>
            </tr>
          </thead>
          <tbody>
            {[
              ["R001", "Account verified", "Exact competition paper fingerprint and paper environment."],
              ["R002", "Execution allowlist", "Only SPY, QQQ and IWM are eligible for execution. Other research candidates are rejected here before sizing."],
              ["R003", "No short positions", "NO_TRADE is never submitted; sell size cannot exceed holdings."],
              ["R004", "Single-position exposure", "Post-order instrument exposure stays within 10% of equity."],
              ["R005", "Gross exposure", "Post-order gross exposure stays within 30% of equity."],
              ["R006", "Daily drawdown stop", "New buying halts if daily drawdown reaches 2%."],
              ["R007", "Quote freshness", "Quote ≤300s and account snapshot ≤60s; stale data fails closed."],
              ["R008", "Cash-only buying power", "Unlevered cash after a US$5 buffer must cover the order."],
              ["R009", "Reconciled broker state", "Broker state reconciles cleanly with zero unknown orders."],
              ["R010", "Order control state", "Writes, kill switch and circuit breaker must permit execution."],
              ["R011", "Duplicate submission", "A proposal with a durable submission record cannot repeat."],
              ["R012", "Regular trading session", "Orders are limited to the regular exchange session."],
              ["R013", "Position count", "Post-order open positions cannot exceed three."],
              ["R014", "First-order approval", "The initial paper order requires explicit owner approval."],
              ["R015", "Leveraged product approval", "Leveraged candidates also need separate, opt-in leverage approval, even within the allowlist."],
            ].map(([id, name, description]) => (
              <tr key={id}>
                <Td className="font-mono text-xs text-muted-foreground">{id}</Td>
                <Td className="font-medium">{name}</Td>
                <Td className="text-muted-foreground">{description}</Td>
              </tr>
            ))}
          </tbody>
        </TableShell>
      </div>
    </details>
  )
}

export default function RiskPage() {
  const { data, error, loading, refresh } =
    useDashboard<RiskResponse>("risk", 60_000)

  if (loading && !data) return <LoadingPage />

  if (!data) {
    return (
      <PageContainer>
        <PageHeader title="Risk Centre" />
        <PageState
          title="Risk state unavailable"
          description={error ?? "The read-only broker API returned no data."}
          onRetry={refresh}
        />
      </PageContainer>
    )
  }

  const account = data.account
  const controls = data.controls
  const grossExposure = grossExposurePct(account?.equity, account?.cash)
  const invested = investedValue(account?.equity, account?.cash)
  const equity = Number(account?.equity)
  const dayStart = Number(account?.day_start_equity)
  const dailyChangePct =
    typeof account?.equity === "string" &&
    typeof account?.day_start_equity === "string" &&
    Number.isFinite(equity) &&
    Number.isFinite(dayStart) &&
    dayStart > 0
      ? ((equity - dayStart) / dayStart) * 100
      : null

  const controlBlockers = data.lock_reasons.filter(
    (reason) => !/quote|session/i.test(reason)
  )
  const marketBlockers = data.lock_reasons.filter((reason) =>
    /quote|session/i.test(reason)
  )
  const preflight = data.last_real_preflight
  const preflightRejected =
    preflight?.decision?.toUpperCase() !== "APPROVE"

  return (
    <PageContainer>
      <PageHeader title="Risk Centre" />

      {data.warnings.length > 0 ? (
        <InfoNote tone="warning">
          <ul className="list-disc space-y-0.5 pl-4">
            {data.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </InfoNote>
      ) : null}

      <Section
        title="Execution eligibility"
        action={
          <StatusPill tone="neutral">
            {data.execution_locked ? "Blocked" : "Eligible"}
          </StatusPill>
        }
      >
        <p className="text-[13px] text-muted-foreground">
          The deterministic RiskGate is the final authority on order eligibility.
          Neither the agents nor this UI can override it.
        </p>

        {data.lock_reasons.length > 0 ? (
          <div className="mt-4 grid gap-5 sm:grid-cols-2">
            {controlBlockers.length > 0 ? (
              <div>
                <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                  Controls
                </h3>
                <ul className="mt-2 space-y-2">
                  {controlBlockers.map((reason) => (
                    <li
                      key={reason}
                      className="flex gap-2 text-[13px] leading-snug"
                    >
                      <span className="mt-1.5 size-1 shrink-0 rounded-full bg-muted-foreground/50" />
                      <span>{blockerText(reason)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {marketBlockers.length > 0 ? (
              <div>
                <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                  Market conditions
                </h3>
                <ul className="mt-2 space-y-2">
                  {marketBlockers.map((reason) => (
                    <li
                      key={reason}
                      className="flex gap-2 text-[13px] leading-snug"
                    >
                      <span
                        className={`mt-1.5 size-1 shrink-0 rounded-full ${
                          /quote/i.test(reason)
                            ? "bg-amber-600 dark:bg-amber-400"
                            : "bg-muted-foreground/50"
                        }`}
                      />
                      <span>{blockerText(reason)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : (
          <p className="mt-3 text-[13px] text-muted-foreground">
            All deterministic checks pass.
          </p>
        )}

        {controls.unknown_submissions ? (
          <p className="mt-4 flex gap-2 border-t pt-3 text-xs text-rose-700 dark:text-rose-300">
            <span className="mt-1.5 size-1 shrink-0 rounded-full bg-rose-600 dark:bg-rose-400" />
            Unknown order outcomes detected — reconcile broker state before further
            submissions.
          </p>
        ) : null}
      </Section>

      <Section title="Exposure & limits" description="Cash-only paper account.">
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="space-y-4">
            <Meter
              label="Gross exposure"
              value={grossExposure === null ? null : (grossExposure / data.limits.max_total_exposure_pct) * 100}
              display={`${grossExposure === null ? "—" : `${grossExposure.toFixed(1)}%`} / ${percent(data.limits.max_total_exposure_pct, 0)}`}
              hint={invested === null ? "No broker snapshot" : `${money(invested)} invested`}
            />
            <Meter
              label="Open positions"
              value={
                account
                  ? (account.positions_count ?? 0) / data.limits.max_open_positions * 100
                  : null
              }
              display={`${account?.positions_count ?? "—"} / ${data.limits.max_open_positions}`}
              hint="Cash-only, maximum three open positions"
            />
            <Meter
              label="Daily P&L"
              value={
                dailyChangePct === null
                  ? null
                  : (Math.abs(Math.min(0, dailyChangePct)) /
                      data.limits.max_daily_drawdown_pct) *
                    100
              }
              display={
                dailyChangePct === null
                  ? "—"
                  : `${signedPercent(dailyChangePct)} / -${percent(data.limits.max_daily_drawdown_pct, 0)} stop`
              }
              tone={
                dailyChangePct !== null &&
                dailyChangePct <= -data.limits.max_daily_drawdown_pct
                  ? "danger"
                  : "neutral"
              }
              hint={
                account?.day_start_equity
                  ? `Day start equity ${money(account.day_start_equity)}`
                  : "Day-start equity unavailable"
              }
            />
          </div>

          <div>
            <KeyValue
              label="Single-position limit"
              value={percent(data.limits.max_single_exposure_pct, 0)}
              mono
            />
            <KeyValue
              label="Gross exposure limit"
              value={percent(data.limits.max_total_exposure_pct, 0)}
              mono
            />
            <KeyValue
              label="Maximum positions"
              value={data.limits.max_open_positions}
              mono
            />
            <KeyValue
              label="Daily drawdown stop"
              value={percent(data.limits.max_daily_drawdown_pct, 1)}
              mono
            />
            <KeyValue
              label="Quote / account freshness"
              value={`${data.limits.max_quote_age_seconds}s / ${data.limits.max_account_age_seconds}s`}
              mono
            />
            <KeyValue
              label="Cash buffer"
              value={money(data.limits.buying_power_buffer_usd)}
              mono
            />
          </div>
        </div>
      </Section>

      <Section
        title="Live gate inputs"
        description="Source-quote age, not page refresh age."
        flush
      >
        <TableShell>
          <thead>
            <tr>
              <Th>Symbol</Th>
              <Th align="right">Last</Th>
              <Th className="hidden lg:table-cell">Session</Th>
              <Th align="right">Quote age</Th>
              <Th className="hidden lg:table-cell">Quote time</Th>
            </tr>
          </thead>
          <tbody>
            {data.quotes.length === 0 ? (
              <EmptyRow colSpan={5}>No quote observations returned.</EmptyRow>
            ) : (
              data.quotes.map((quote) => (
                <tr key={quote.symbol}>
                  <Td className="font-mono font-semibold">{quote.symbol}</Td>
                  <Td align="right" className="tabular-nums">
                    {quote.price ? money(quote.price) : "—"}
                  </Td>
                  <Td className="hidden text-muted-foreground lg:table-cell">
                    {quote.regular_session_open
                      ? "Regular session"
                      : humanState(quote.market_state)}
                  </Td>
                  <Td align="right">
                    <Freshness seconds={quote.age_seconds} stale={quote.stale} />
                  </Td>
                  <Td className="hidden whitespace-nowrap text-xs text-muted-foreground lg:table-cell">
                    {shortDateTime(quote.as_of_utc)}
                  </Td>
                </tr>
              ))
            )}
          </tbody>
        </TableShell>
      </Section>

      <Section title="Research universe vs execution allowlist">
        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
              Execution allowlist
            </h3>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {EXECUTION_ALLOWLIST.map((symbol) => (
                <span
                  key={symbol}
                  className="rounded-md border bg-muted/40 px-2 py-0.5 font-mono text-xs font-semibold"
                >
                  {symbol}
                </span>
              ))}
            </div>
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
              Only these symbols can pass the gate. Anything else is rejected at R002
              before sizing.
            </p>
          </div>
          <div>
            <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
              Research universe
            </h3>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {RESEARCH_UNIVERSE.map((instrument) => (
                <span
                  key={instrument.symbol}
                  className="rounded-md border px-2 py-0.5 font-mono text-xs font-semibold"
                >
                  {instrument.symbol}
                  <span className="ml-1.5 font-sans text-[10px] font-normal text-muted-foreground">
                    {instrument.exposure}
                  </span>
                </span>
              ))}
            </div>
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
              Screened by the strategy; non-allowlisted candidates fail R002, and
              leveraged products also require the opt-in R015 approval.
            </p>
          </div>
        </div>
      </Section>

      <details className="group rounded-xl border bg-card">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
          <span className="flex flex-wrap items-baseline gap-x-2">
            <span className="text-sm font-semibold">Recorded preflight</span>
            <span className="text-xs text-muted-foreground">
              {preflight
                ? `${preflightRejected ? "Rejected" : "Approved"} · ${shortDateTime(preflight.checked_at_utc)} · no order was dispatched`
                : "None recorded"}
            </span>
          </span>
          <ChevronDownIcon className="size-3.5 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
        </summary>
        <div className="border-t p-4">
          {preflight ? (
            <div className="space-y-4">
              {preflight.reasons.length > 0 ? (
                <ul className="space-y-2">
                  {preflight.reasons.map((reason, index) => {
                    const embedded = /^(R\d{3})\b/.exec(reason)?.[1]
                    const ruleId = embedded ?? preflight.rejection_rule_ids[index]
                    return (
                      <li
                        key={`${ruleId ?? "rule"}-${index}`}
                        className="flex gap-2 text-[13px] leading-snug"
                      >
                        <span className="mt-1.5 size-1 shrink-0 rounded-full bg-muted-foreground/50" />
                        <span>
                          {ruleId ? (
                            <span className="font-mono text-xs text-muted-foreground">
                              {ruleId}
                            </span>
                          ) : null}{" "}
                          {ruleLabel(ruleId)} — {reason.replace(/^R\d{3}\s*/, "")}
                        </span>
                      </li>
                    )
                  })}
                </ul>
              ) : null}

              <div className="grid gap-x-4 sm:grid-cols-2">
                <KeyValue
                  label="Submission performed"
                  value={String(preflight.submission_performed)}
                  mono
                />
                <KeyValue
                  label="Endpoint contacted"
                  value={String(preflight.order_endpoint_contacted)}
                  mono
                />
                <KeyValue
                  label="Trade write scope"
                  value={String(preflight.scope_trade_write)}
                  mono
                />
                <KeyValue
                  label="Preflight kind"
                  value={preflight.kind ?? "—"}
                  mono
                />
              </div>

              {preflight.quotes.length > 0 ? (
                <TableShell>
                  <thead>
                    <tr>
                      <Th>Symbol</Th>
                      <Th align="right">Last</Th>
                      <Th align="right" className="hidden sm:table-cell">Age</Th>
                      <Th className="hidden lg:table-cell">Quote time</Th>
                      <Th>Status</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {preflight.quotes.map((quote) => (
                      <tr key={quote.symbol}>
                        <Td className="font-mono font-semibold">
                          {quote.symbol}
                        </Td>
                        <Td align="right" className="tabular-nums">
                          {money(quote.last_price)}
                        </Td>
                        <Td align="right" className="hidden sm:table-cell">
                          <Freshness
                            seconds={quote.age_seconds}
                            stale={(quote.age_seconds ?? 0) > 300}
                          />
                        </Td>
                        <Td className="hidden text-xs text-muted-foreground lg:table-cell">
                          {shortDateTime(quote.data_time_utc)}
                        </Td>
                        <Td className="text-xs text-muted-foreground">
                          {quote.sec_status ?? "—"}
                          {quote.suspension ? " · suspended" : ""}
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </TableShell>
              ) : null}
            </div>
          ) : (
            <p className="text-[13px] text-muted-foreground">
              No execution preflight artifact is recorded in this environment.
            </p>
          )}
        </div>
      </details>

      <Section title="Deterministic rule catalogue" description="Any single failure blocks execution.">
        <RulesReference />
      </Section>
    </PageContainer>
  )
}
