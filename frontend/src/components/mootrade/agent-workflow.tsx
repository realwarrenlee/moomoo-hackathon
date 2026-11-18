"use client"

import { riskDecisionLabel, type AgentRun } from "@/lib/mootrade"
import { cn } from "@/lib/utils"

type Stage = {
  role: string
  outcome: string
}

export function AgentWorkflow({ run }: { run: AgentRun }) {
  const selected = run.candidates.find((candidate) => candidate.selected)
  const risk = run.risk_decision
  const failedRules = risk?.reasons.length ?? 0
  const auditorRecorded = run.summaries.some(
    (summary) => summary.role === "auditor" || summary.role === "risk_review"
  )
  const proposal = run.proposal
  const proposalText = proposal
    ? [proposal.action, proposal.requested_quantity, proposal.symbol]
        .filter((value) => value !== null && value !== undefined && value !== "")
        .join(" ")
    : null

  const stages: Stage[] = [
    {
      role: "Coordinator",
      outcome:
        run.session_count > 0
          ? "Started run"
          : "No session recorded",
    },
    {
      role: "Market Researcher",
      outcome: selected?.symbol
        ? `Selected ${selected.symbol}`
        : "No candidate selected",
    },
    {
      role: "Risk Auditor",
      outcome: risk
        ? auditorRecorded
          ? failedRules
            ? `Identified ${failedRules} ${
                failedRules === 1 ? "blocker" : "blockers"
              }`
            : "No blockers"
          : "Review not recorded"
        : "Not evaluated",
    },
    {
      role: "Coordinator",
      outcome: proposalText ? `Proposed ${proposalText}` : "No proposal",
    },
    {
      role: "RiskGate",
      outcome: risk ? riskDecisionLabel(risk.decision) : "Not reached",
    },
  ]

  return (
    <div>
      <ol
        aria-label="Decision stages"
        className="relative hidden grid-cols-5 lg:grid"
      >
        <span
          aria-hidden
          className="absolute top-[2.5px] right-[10%] left-[10%] h-px bg-border"
        />
        {stages.map((stage, index) => {
          const final = index === stages.length - 1
          return (
            <li
              key={`${stage.role}-${stage.outcome}`}
              className="relative flex flex-col items-center px-3 text-center"
            >
              <span
                aria-hidden
                className={cn(
                  "relative z-10 size-1.5 rounded-full",
                  final ? "bg-foreground" : "bg-muted-foreground/60"
                )}
              />
              <p
                className={cn(
                  "mt-2 text-xs",
                  final
                    ? "font-semibold text-foreground"
                    : "font-medium text-foreground/90"
                )}
              >
                {stage.role}
              </p>
              <p
                className={cn(
                  "mt-0.5 text-xs leading-snug",
                  final
                    ? "font-medium text-foreground"
                    : "text-muted-foreground"
                )}
              >
                {stage.outcome}
              </p>
            </li>
          )
        })}
      </ol>

      <ol aria-label="Decision stages" className="lg:hidden">
        {stages.map((stage, index) => {
          const final = index === stages.length - 1
          return (
            <li
              key={`${stage.role}-${stage.outcome}`}
              className="relative pb-4 pl-5 last:pb-0"
            >
              {!final ? (
                <span
                  aria-hidden
                  className="absolute top-2.5 bottom-0 left-[2.5px] w-px bg-border"
                />
              ) : null}
              <span
                aria-hidden
                className={cn(
                  "absolute top-[5px] left-0 size-1.5 rounded-full",
                  final ? "bg-foreground" : "bg-muted-foreground/60"
                )}
              />
              <p
                className={cn(
                  "text-xs",
                  final
                    ? "font-semibold text-foreground"
                    : "font-medium text-foreground/90"
                )}
              >
                {stage.role}
              </p>
              <p
                className={cn(
                  "mt-0.5 text-xs leading-snug",
                  final
                    ? "font-medium text-foreground"
                    : "text-muted-foreground"
                )}
              >
                {stage.outcome}
              </p>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
