"use client"

import { useMemo, useState } from "react"
import { ChevronDownIcon } from "lucide-react"

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
import {
  compactId,
  easternTimestamp,
  humanState,
  money,
  ratioPercent,
  shortDate,
  strategyLabel,
  utcTimestamp,
  type AgentsResponse,
} from "@/lib/mootrade"
import { cn } from "@/lib/utils"

const ROLE_LABELS: Record<string, string> = {
  coordinator_ready: "Coordinator · Initialize",
  researcher: "Research Agent · Screening",
  research: "Research Agent · Screening",
  auditor: "Risk Review Agent · Independent Audit",
  risk_review: "Risk Review Agent · Independent Audit",
  coordinator_final: "Coordinator · Final Decision",
  strategy: "Strategy Agent",
}

function agentText(text: string) {
  return text.replace(/\*\*/g, "").replace(/`/g, "")
}

function roleLabel(role: string) {
  return ROLE_LABELS[role] ?? humanState(role)
}

export default function AgentsPage() {
  const { data, error, loading, refreshing, refreshedAt, refresh } =
    useDashboard<AgentsResponse>("agents", 120_000)
  const [selectedIndex, setSelectedIndex] = useState(0)

  const runs = data?.runs ?? []
  const run = runs[Math.min(selectedIndex, Math.max(runs.length - 1, 0))]

  const candidateCount = useMemo(
    () => (run ? run.candidates.filter((candidate) => candidate.eligible).length : 0),
    [run]
  )

  if (loading && !data) return <LoadingPage />

  return (
    <div className="space-y-5 p-4 md:p-6">
      <PageHeader
        title="AI Agent Activity"
        description="Qoder Cloud Agent orchestration for market research, candidate screening, and risk review."
        actions={
          <RefreshButton
            onClick={refresh}
            refreshing={refreshing}
            refreshedAt={refreshedAt}
          />
        }
      />

      {/* Run Selector & Mode Context */}
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-lg border bg-card px-3.5 py-2 text-xs">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="font-medium text-foreground">
            {run?.provenance === "CURRENT_MARKET_READ_ONLY"
              ? "Current Market Dry Run"
              : "Historical Qoder Dry Run"}
          </span>
          <span className="text-muted-foreground">·</span>
          <span className="text-muted-foreground">Read-Only Strategy Evaluation</span>
        </div>

        {runs.length > 1 ? (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] text-muted-foreground">Runs:</span>
            {runs.map((item, index) => (
              <button
                key={item.run_id ?? index}
                type="button"
                onClick={() => setSelectedIndex(index)}
                className={cn(
                  "rounded border px-2 py-0.5 font-mono text-[10px] transition-colors",
                  index === selectedIndex
                    ? "bg-foreground text-background"
                    : "text-muted-foreground hover:bg-muted"
                )}
              >
                {compactId(item.run_id, 8, 4)}
              </button>
            ))}
          </div>
        ) : run?.run_id ? (
          <span className="font-mono text-[11px] text-muted-foreground">
            Run {compactId(run.run_id, 8, 6)}
          </span>
        ) : null}
      </div>

      {data?.notice ? (
        <NoticeBanner tone="info" title="Evidence boundary">
          {data.notice}
        </NoticeBanner>
      ) : null}

      {error && !data ? (
        <StatePanel
          kind="error"
          title="Agent evidence unavailable"
          description={error}
          action={
            <RefreshButton
              onClick={refresh}
              refreshing={refreshing}
              refreshedAt={refreshedAt}
            />
          }
        />
      ) : null}

      {!run ? (
        <StatePanel
          title="No Qoder run evidence"
          description="No completed Qoder evidence artifact was found. This page never substitutes synthetic agent output."
        />
      ) : (
        <>
          {/* Key Run Metrics */}
          <MetricStrip>
            <Metric
              label="Decision outcome"
              value={run.outcome === "NO_TRADE" ? "No trade" : run.outcome}
              detail={run.no_trade_reason ?? "Strategy criteria not met"}
              tone={run.outcome === "NO_TRADE" ? "warning" : "positive"}
            />
            <Metric
              label="Regime state"
              value={run.regime_ok ? "Positive" : "Negative"}
              detail={run.regime_reason ?? "SPY below 20-session SMA"}
            />
            <Metric
              label="Candidates"
              value={`${run.candidates.filter((c) => c.selected).length} / ${run.candidates.length}`}
              detail={`${candidateCount} passed initial filter`}
            />
            <Metric
              label="Completed"
              value={shortDate(run.completed_at_utc)}
              detail={`${run.session_count} agent sessions`}
            />
          </MetricStrip>

          {/* Structured Agent Workflow / Roles */}
          <SectionCard
            title="Agent workflow & transcripts"
            description="Sequential cloud agent execution. Transcripts are expandable model evidence and cannot authorize trading."
          >
            {run.summaries.length > 0 ? (
              <div className="divide-y">
                {run.summaries.map((summary) => (
                  <details
                    key={`${summary.role}-${summary.text.slice(0, 24)}`}
                    className="group py-2.5 first:pt-0 last:pb-0"
                  >
                    <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-xs font-medium text-foreground hover:text-foreground/80">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold">{roleLabel(summary.role)}</span>
                        <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[9px] text-muted-foreground">
                          {summary.role}
                        </span>
                      </div>
                      <span className="flex items-center gap-1 text-[11px] font-normal text-muted-foreground group-open:hidden">
                        Expand <ChevronDownIcon className="size-3" />
                      </span>
                      <span className="hidden text-[11px] font-normal text-muted-foreground group-open:inline">
                        Collapse
                      </span>
                    </summary>
                    <div className="mt-2.5 rounded border bg-muted/30 p-3">
                      <p className="max-h-96 overflow-y-auto whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-muted-foreground">
                        {agentText(summary.text)}
                      </p>
                    </div>
                  </details>
                ))}
              </div>
            ) : (
              <StatePanel
                title="No agent summaries"
                description="This run artifact contains no agent summary text."
              />
            )}
          </SectionCard>

          {/* Strategy Candidates Table */}
          <SectionCard
            title="Strategy candidates"
            description="Technical values and screening criteria captured at decision time."
          >
            <TableShell>
              <table className="w-full text-left text-[11px]">
                <thead>
                  <tr className="border-b text-[10px] text-muted-foreground">
                    <th className="px-3 py-2 font-medium">Symbol</th>
                    <th className="hidden px-3 py-2 text-right font-medium sm:table-cell">
                      Close
                    </th>
                    <th className="hidden px-3 py-2 text-right font-medium md:table-cell">
                      SMA 20
                    </th>
                    <th className="px-3 py-2 text-right font-medium">5d return</th>
                    <th className="hidden px-3 py-2 text-right font-medium lg:table-cell">
                      News (+/tot)
                    </th>
                    <th className="hidden px-3 py-2 font-medium xl:table-cell">
                      Screening evidence
                    </th>
                    <th className="px-3 py-2 text-right font-medium">State</th>
                  </tr>
                </thead>
                <tbody>
                  {run.candidates.length === 0 ? (
                    <EmptyRow
                      colSpan={7}
                      label="No candidates recorded for this run."
                    />
                  ) : (
                    run.candidates.map((candidate) => (
                      <tr
                        key={candidate.symbol ?? candidate.close ?? "candidate"}
                        className={cn(
                          "border-b last:border-0",
                          candidate.selected && "bg-emerald-500/[0.04]"
                        )}
                      >
                        <td className="px-3 py-2 font-mono font-semibold">
                          {candidate.symbol ?? "—"}
                        </td>
                        <td className="hidden px-3 py-2 text-right font-mono tabular-nums sm:table-cell">
                          {money(candidate.close)}
                        </td>
                        <td className="hidden px-3 py-2 text-right font-mono tabular-nums md:table-cell">
                          {money(candidate.sma20)}
                        </td>
                        <td
                          className={cn(
                            "px-3 py-2 text-right font-mono tabular-nums",
                            Number(candidate.return_5d) > 0
                              ? "text-emerald-600 dark:text-emerald-400"
                              : "text-rose-600 dark:text-rose-400"
                          )}
                        >
                          {ratioPercent(
                            candidate.return_5d === null
                              ? null
                              : Number(candidate.return_5d)
                          )}
                        </td>
                        <td className="hidden px-3 py-2 text-right font-mono tabular-nums text-muted-foreground lg:table-cell">
                          {candidate.positive_news_count ?? 0} /{" "}
                          {candidate.news_count ?? 0}
                        </td>
                        <td className="hidden max-w-[280px] px-3 py-2 text-[10px] leading-snug text-muted-foreground xl:table-cell">
                          {candidate.reasons.length
                            ? candidate.reasons.join(" · ")
                            : "No reasons recorded"}
                        </td>
                        <td
                          className={cn(
                            "px-3 py-2 text-right font-medium",
                            candidate.selected
                              ? "text-emerald-600 dark:text-emerald-400"
                              : candidate.eligible
                                ? "text-sky-600 dark:text-sky-400"
                                : "text-muted-foreground"
                          )}
                        >
                          {candidate.selected
                            ? "Selected"
                            : candidate.eligible
                              ? "Eligible"
                              : "Rejected"}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </TableShell>
          </SectionCard>

          {/* Runtime Data Evidence (when present) */}
          {run.data_collection ? (
            <SectionCard
              title="Execution evidence capture"
              description="Broker quotes and timestamps recorded during agent execution."
              contentClassName="space-y-2"
            >
              <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10px] text-muted-foreground">
                <span>
                  Collected {utcTimestamp(run.data_collection.collected_at_utc)}
                </span>
                <span>·</span>
                <span>
                  Account as of {utcTimestamp(run.data_collection.account_as_of_utc)}
                </span>
                {run.data_collection.us_eastern_time ? (
                  <>
                    <span>·</span>
                    <span>
                      US Eastern{" "}
                      {easternTimestamp(run.data_collection.us_eastern_time)}
                    </span>
                  </>
                ) : null}
              </div>
              <TableShell>
                <table className="w-full text-[11px]">
                  <thead>
                    <tr className="border-b text-left text-[10px] text-muted-foreground">
                      <th className="px-3 py-2 font-medium">Symbol</th>
                      <th className="px-3 py-2 font-medium">Quote time (UTC)</th>
                      <th className="px-3 py-2 text-right font-medium">Age</th>
                      <th className="px-3 py-2 font-medium">Session</th>
                    </tr>
                  </thead>
                  <tbody>
                    {run.data_collection.quotes.length === 0 ? (
                      <EmptyRow colSpan={4} label="No quote observations recorded." />
                    ) : (
                      run.data_collection.quotes.map((quote) => (
                        <tr
                          key={quote.symbol ?? quote.data_time_utc ?? "quote"}
                          className="border-b last:border-0"
                        >
                          <td className="px-3 py-2 font-mono font-semibold">
                            {quote.symbol ?? "—"}
                          </td>
                          <td className="px-3 py-2 font-mono text-[10px] text-muted-foreground">
                            {utcTimestamp(quote.data_time_utc)}
                          </td>
                          <td className="px-3 py-2 text-right text-muted-foreground">
                            {quote.age_seconds === null || quote.age_seconds === undefined
                              ? "—"
                              : `${Math.round(quote.age_seconds)}s`}
                          </td>
                          <td className="px-3 py-2 text-muted-foreground">
                            {quote.market_state ? humanState(quote.market_state) : "—"}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </TableShell>
            </SectionCard>
          ) : null}

          {/* Safe Technical Metadata & Boundary Note */}
          <div className="grid gap-4 lg:grid-cols-2">
            <SectionCard
              title="Run metadata"
              description="Verified cloud session properties."
            >
              <div className="grid gap-x-6 sm:grid-cols-2">
                <KeyValue label="Strategy" value={strategyLabel(run.strategy_version)} />
                <KeyValue label="Mode" value={humanState(run.mode)} mono />
                <KeyValue label="Status" value={humanState(run.status)} />
                <KeyValue label="Sessions" value={String(run.session_count)} mono />
                <KeyValue
                  label="Decision time"
                  value={utcTimestamp(run.decision_time_utc)}
                  mono
                />
                <KeyValue label="Completed" value={shortDate(run.completed_at_utc)} mono />
              </div>
            </SectionCard>

            <SectionCard
              title="Execution isolation"
              description="Safety invariants for agent activity."
            >
              <ul className="space-y-1.5 text-[11px] leading-relaxed text-muted-foreground">
                <li>Agent decisions are stored as untrusted proposals; they never directly dispatch orders.</li>
                <li>Research and strategy sessions operate in read-only sandbox mode with zero broker write access.</li>
                <li>The deterministic risk gate independently re-evaluates all proposal sizing and quotes.</li>
              </ul>
            </SectionCard>
          </div>
        </>
      )}
    </div>
  )
}
