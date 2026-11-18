"use client"

import { useState } from "react"

import { AgentWorkflow } from "@/components/mootrade/agent-workflow"
import {
  DetailSheet,
  EmptyRow,
  InfoNote,
  KeyValue,
  LoadingPage,
  PageContainer,
  PageHeader,
  PageState,
  Section,
  StatusPill,
  TableShell,
  Td,
  Th,
} from "@/components/mootrade/primitives"
import { Button } from "@/components/ui/button"
import { useDashboard } from "@/components/mootrade/use-dashboard"
import {
  compactId,
  easternTimestamp,
  humanState,
  money,
  outcomeLabel,
  outcomeTone,
  ratioPercent,
  riskDecisionLabel,
  ruleLabel,
  strategyLabel,
  utcTimestamp,
  type AgentCandidate,
  type AgentsResponse,
} from "@/lib/mootrade"
import { cn } from "@/lib/utils"

const SUMMARY_LABELS: Record<string, string> = {
  coordinator_ready: "Coordinator · Initialize",
  researcher: "Market Researcher · Analysis",
  research: "Market Researcher · Analysis",
  auditor: "Independent Risk Auditor · Review",
  risk_review: "Independent Risk Auditor · Review",
  coordinator_final: "Coordinator · Final decision",
  strategy: "Strategy · Screening",
}

function summaryLabel(role: string) {
  return SUMMARY_LABELS[role] ?? humanState(role)
}

function agentText(text: string) {
  return text.replace(/\*\*/g, "").replace(/`/g, "")
}

function directionLabel(direction?: number | null) {
  if (direction === 1) return "Bullish"
  if (direction === -1) return "Bearish"
  return "—"
}

function screeningLabel(candidate: AgentCandidate) {
  if (candidate.selected) return "Selected"
  if (candidate.eligible) return "Eligible"
  return "Not eligible"
}

export default function AgentsPage() {
  const { data, error, loading, refresh } = useDashboard<AgentsResponse>("agents", 120_000)
  const [evidenceOpen, setEvidenceOpen] = useState(false)

  const runs = data?.runs ?? []
  const run = runs[0]

  if (loading && !data) return <LoadingPage />

  if (error && !data) {
    return (
      <PageContainer>
        <PageHeader title="Agent Activity" />
        <PageState
          title="Agent evidence unavailable"
          description={error}
          onRetry={() => void refresh()}
        />
      </PageContainer>
    )
  }

  if (!run) {
    return (
      <PageContainer>
        <PageHeader title="Agent Activity" />
        <PageState
          kind="empty"
          title="No Qoder run evidence"
          description="No completed Qoder evidence artifact was found. This page never substitutes synthetic agent output."
        />
      </PageContainer>
    )
  }

  const risk = run.risk_decision
  const decision = risk?.decision?.toUpperCase()
  const rejected = decision === "REJECT" || decision === "REJECTED"
  const approved = decision === "APPROVE" || decision === "APPROVED"
  const proposal = run.proposal
  const proposalText = proposal
    ? [proposal.action, proposal.requested_quantity, proposal.symbol]
        .filter((value) => value !== null && value !== undefined && value !== "")
        .join(" ")
    : null
  const headline = proposalText
    ? proposalText
    : run.target_symbol
      ? `Target ${run.target_symbol}`
      : "No order proposed"

  const outcome = rejected
    ? "Blocked by RiskGate — no order placed."
    : approved
      ? "Approved by RiskGate — no order submitted."
      : run.outcome === "AGENT_ERROR"
        ? "Run failed — no order placed."
        : proposal
          ? "Proposal only — execution not evaluated."
          : "No order proposed."

  const provenanceLabel =
    run.provenance === "CURRENT_MARKET_READ_ONLY"
      ? "Current market · read-only"
      : run.provenance === "HISTORICAL_QODER_RUN"
        ? "Historical run"
        : humanState(run.provenance)

  const marketMetrics = [
    { label: "SPY close", value: money(run.spy_close) },
    {
      label: "10-session return",
      value: ratioPercent(run.spy_return_10d ? Number(run.spy_return_10d) : null),
    },
    { label: "50-session SMA", value: money(run.spy_sma50) },
    {
      label: "20-session volatility",
      value: ratioPercent(
        run.spy_volatility_20d ? Number(run.spy_volatility_20d) : null
      ),
    },
  ]

  return (
    <PageContainer>
      <PageHeader title="Agent Activity" />

      <Section title="Latest decision">
        <div className="space-y-2">
          <p className="text-2xl font-semibold tracking-tight">{headline}</p>
          <p className="max-w-2xl text-[13px] leading-relaxed text-muted-foreground">
            {run.decision_reason ?? run.no_trade_reason ?? "No decision reason recorded."}
          </p>
          <p
            className={cn(
              "text-[13px] font-medium",
              rejected ? "text-rose-700 dark:text-rose-300" : "text-foreground"
            )}
          >
            {outcome}
          </p>
          <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1 pt-1 text-xs text-muted-foreground">
            <span>
              Signal{" "}
              <span className="font-medium text-foreground">
                {run.market_state ? humanState(run.market_state) : "—"}
              </span>
            </span>
            <span>
              Target{" "}
              <span className="font-medium text-foreground">
                {run.target_symbol ?? "CASH"}
              </span>
            </span>
            <span>
              Exposure{" "}
              <span className="font-medium text-foreground">
                {run.target_effective_exposure
                  ? `${run.target_effective_exposure}x`
                  : "—"}
              </span>
            </span>
          </div>
        </div>
      </Section>

      <Section
        title="Decision timeline"
        action={
          <Button
            variant="ghost"
            size="sm"
            className="-mr-2 h-7 px-2 text-xs text-muted-foreground hover:text-foreground"
            onClick={() => setEvidenceOpen(true)}
          >
            View full evidence
          </Button>
        }
      >
        <AgentWorkflow run={run} />
      </Section>

      <Section title="Market context">
        <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
          {marketMetrics.map((metric) => (
            <div key={metric.label}>
              <dt className="text-xs text-muted-foreground">{metric.label}</dt>
              <dd className="mt-1 font-mono text-sm font-semibold tabular-nums">
                {metric.value}
              </dd>
            </div>
          ))}
        </dl>
      </Section>

      {risk ? (
        <Section
          title={rejected ? "Why execution was blocked" : "RiskGate review"}
        >
          {risk.reasons.length ? (
            <ul className="space-y-2 text-[13px] leading-relaxed">
              {risk.reasons.map((reason) => (
                <li
                  key={`${reason.rule_id}-${reason.message}`}
                  className="flex gap-2"
                >
                  <span
                    aria-hidden
                    className="mt-[7px] size-1 shrink-0 rounded-full bg-muted-foreground/50"
                  />
                  <span>{reason.message ?? ruleLabel(reason.rule_id)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[13px] text-muted-foreground">
              {rejected
                ? "The RiskGate returned no detailed reasons."
                : "No blocking rules were returned."}
            </p>
          )}
        </Section>
      ) : null}

      <DetailSheet
        open={evidenceOpen}
        onOpenChange={setEvidenceOpen}
        title="Full run evidence"
        description={
          run.run_id ? compactId(run.run_id, 10, 6) : "Qoder run evidence"
        }
      >
        <div className="space-y-5">
          <div className="space-y-2">
            <p className="text-xs font-medium">Run metadata</p>
            <div className="grid gap-x-6 rounded-lg border px-3 py-1 sm:grid-cols-2">
              <KeyValue
                label="Run ID"
                value={run.run_id ? compactId(run.run_id, 10, 6) : "—"}
                mono
              />
              <KeyValue label="Strategy" value={strategyLabel(run.strategy_version)} />
              <KeyValue label="Mode" value={humanState(run.mode)} mono />
              <KeyValue label="Sessions" value={String(run.session_count)} mono />
              <KeyValue label="Status" value={humanState(run.status)} />
              <KeyValue
                label="Decision time"
                value={utcTimestamp(run.decision_time_utc)}
                mono
              />
              <KeyValue
                label="Completed"
                value={utcTimestamp(run.completed_at_utc)}
                mono
              />
              <KeyValue
                label="Data as of"
                value={utcTimestamp(run.data_as_of_utc)}
                mono
              />
              <KeyValue label="Provenance" value={provenanceLabel} />
            </div>
          </div>

          {data?.notice || run.notice ? (
            <InfoNote>{run.notice ?? data?.notice}</InfoNote>
          ) : null}

          <div className="space-y-2">
            <p className="text-xs font-medium">Final decision</p>
            <div className="rounded-lg border px-3">
              <KeyValue label="Decision" value={headline} />
              <KeyValue
                label="Outcome"
                value={
                  <StatusPill tone={outcomeTone(run.outcome)}>
                    {outcomeLabel(run.outcome)}
                  </StatusPill>
                }
              />
              <KeyValue
                label="Reason"
                value={run.decision_reason ?? run.no_trade_reason ?? "—"}
              />
              <KeyValue
                label="RiskGate"
                value={risk ? riskDecisionLabel(risk.decision) : "Not evaluated"}
              />
              <KeyValue
                label="Approved quantity"
                value={String(risk?.approved_quantity ?? 0)}
                mono
              />
              <KeyValue label="Policy version" value={risk?.policy_version ?? "—"} mono />
            </div>
          </div>

          {risk?.reasons.length ? (
            <div className="space-y-2">
              <p className="text-xs font-medium">Failed rules</p>
              {risk.reasons.map((reason) => (
                <div
                  key={`${reason.rule_id}-${reason.message}`}
                  className="rounded-lg border px-3 py-2"
                >
                  <p className="text-xs text-muted-foreground">
                    <span className="font-mono">{reason.rule_id ?? "RULE"}</span> ·{" "}
                    {ruleLabel(reason.rule_id)}
                  </p>
                  <p className="mt-0.5 text-[13px]">{reason.message ?? "Rule failed"}</p>
                </div>
              ))}
            </div>
          ) : null}

          <div className="space-y-2">
            <p className="text-xs font-medium">Candidate instruments</p>
            <TableShell>
              <thead>
                <tr>
                  <Th>Symbol</Th>
                  <Th>Direction</Th>
                  <Th align="right">Leverage</Th>
                  <Th align="right">Exposure</Th>
                  <Th align="right">Close</Th>
                  <Th align="right">Screening</Th>
                </tr>
              </thead>
              <tbody>
                {run.candidates.length === 0 ? (
                  <EmptyRow colSpan={6}>
                    No candidate instruments recorded for this run.
                  </EmptyRow>
                ) : (
                  run.candidates.map((candidate) => (
                    <tr key={candidate.symbol ?? "none"}>
                      <Td className="font-mono font-semibold">
                        {candidate.symbol ?? "—"}
                      </Td>
                      <Td className="text-muted-foreground">
                        {directionLabel(candidate.direction)}
                      </Td>
                      <Td
                        align="right"
                        className="font-mono tabular-nums text-muted-foreground"
                      >
                        {candidate.leverage ? `${candidate.leverage}x` : "—"}
                      </Td>
                      <Td
                        align="right"
                        className="font-mono tabular-nums text-muted-foreground"
                      >
                        {candidate.effective_exposure ?? "—"}
                      </Td>
                      <Td align="right" className="font-mono tabular-nums">
                        {money(candidate.close)}
                      </Td>
                      <Td align="right">
                        <span
                          className={
                            candidate.selected
                              ? "font-medium text-foreground"
                              : "text-muted-foreground"
                          }
                        >
                          {screeningLabel(candidate)}
                        </span>
                      </Td>
                    </tr>
                  ))
                )}
              </tbody>
            </TableShell>
          </div>

          <div className="space-y-2">
            <p className="text-xs font-medium">Agent transcripts</p>
            {run.summaries.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No transcript text was recorded for this run.
              </p>
            ) : (
              <div className="space-y-3">
                {run.summaries.map((summary) => (
                  <div key={summary.role} className="overflow-hidden rounded-lg border">
                    <p className="border-b px-3 py-2 text-[11px] font-medium text-muted-foreground">
                      {summaryLabel(summary.role)}
                    </p>
                    <p className="px-3 py-2 font-mono text-[11px] leading-relaxed break-words whitespace-pre-wrap text-muted-foreground">
                      {agentText(summary.text)}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>

          {run.data_collection ? (
            <div className="space-y-2">
              <p className="text-xs font-medium">Captured market data</p>
              <TableShell>
                <thead>
                  <tr>
                    <Th>Symbol</Th>
                    <Th>Quote time</Th>
                    <Th align="right">Age</Th>
                    <Th className="hidden sm:table-cell">Session</Th>
                  </tr>
                </thead>
                <tbody>
                  {run.data_collection.quotes.length === 0 ? (
                    <EmptyRow colSpan={4}>No quote observations recorded.</EmptyRow>
                  ) : (
                    run.data_collection.quotes.map((quote) => (
                      <tr key={quote.symbol ?? quote.data_time_utc ?? "quote"}>
                        <Td className="font-mono font-semibold">{quote.symbol ?? "—"}</Td>
                        <Td className="font-mono text-[11px] break-words text-muted-foreground">
                          {utcTimestamp(quote.data_time_utc)}
                        </Td>
                        <Td align="right" className="text-muted-foreground">
                          {quote.age_seconds === null || quote.age_seconds === undefined
                            ? "—"
                            : `${Math.round(quote.age_seconds)}s`}
                        </Td>
                        <Td className="hidden text-muted-foreground sm:table-cell">
                          {quote.market_state ? humanState(quote.market_state) : "—"}
                        </Td>
                      </tr>
                    ))
                  )}
                </tbody>
              </TableShell>
              <p className="text-[11px] leading-relaxed text-muted-foreground">
                Captured {utcTimestamp(run.data_collection.collected_at_utc)}
                {run.data_collection.us_eastern_time
                  ? ` · ${easternTimestamp(run.data_collection.us_eastern_time)}`
                  : ""}
                {run.data_collection.account_as_of_utc
                  ? ` · Account snapshot ${utcTimestamp(
                      run.data_collection.account_as_of_utc
                    )}`
                  : ""}
                {run.data_collection.account_age_seconds !== null &&
                run.data_collection.account_age_seconds !== undefined
                  ? ` · ${Math.round(run.data_collection.account_age_seconds)}s old`
                  : ""}
              </p>
            </div>
          ) : null}

          <div className="space-y-2">
            <p className="text-xs font-medium">Execution boundary</p>
            <div className="rounded-lg border px-3">
              <KeyValue label="Order submitted" value="No submission recorded" />
              <KeyValue label="Broker order ID" value="None in this artifact" mono />
              <KeyValue label="Fill" value="None in this artifact" />
            </div>
            <p className="text-xs leading-relaxed text-muted-foreground">
              {rejected
                ? "The proposal was blocked at the RiskGate. No broker order or fill exists for this run."
                : risk
                  ? "Policy approval does not authorise a submission. Owner approval and execution-time checks remain."
                  : "No order proposal reached execution."}
            </p>
            <ul className="space-y-1 text-xs leading-relaxed text-muted-foreground">
              <li>Agent output is untrusted evidence; it never dispatches an order.</li>
              <li>Research and strategy sessions hold zero broker write permissions.</li>
              <li>The RiskGate re-evaluates sizing and quotes independently of agent text.</li>
            </ul>
          </div>
        </div>
      </DetailSheet>
    </PageContainer>
  )
}
