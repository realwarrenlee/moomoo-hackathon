"use client"

import { useMemo, useState } from "react"
import { SearchIcon } from "lucide-react"

import {
  EmptyRow,
  LoadingPage,
  Metric,
  MetricStrip,
  PageHeader,
  RefreshButton,
  SectionCard,
  StatePanel,
  TableShell,
} from "@/components/mootrade/primitives"
import { useDashboard } from "@/components/mootrade/use-dashboard"
import { Input } from "@/components/ui/input"
import {
  compactId,
  utcTimestamp,
  type AuditResponse,
} from "@/lib/mootrade"
import { cn } from "@/lib/utils"

function eventTone(eventType?: string | null) {
  if (!eventType) return "text-muted-foreground"
  if (
    eventType.includes("REJECT") ||
    eventType.includes("BLOCKED") ||
    eventType.includes("MISMATCH")
  )
    return "text-rose-600 dark:text-rose-400"
  if (eventType.startsWith("ORDER_") || eventType.startsWith("FILL_"))
    return "text-amber-600 dark:text-amber-400"
  if (eventType.startsWith("QODER_")) return "text-violet-600 dark:text-violet-400"
  if (
    eventType.includes("OK") ||
    eventType.includes("APPROVED") ||
    eventType.includes("CONFIRMED")
  )
    return "text-emerald-600 dark:text-emerald-400"
  return "text-muted-foreground"
}

export default function AuditPage() {
  const { data, error, loading, refreshing, refreshedAt, refresh } =
    useDashboard<AuditResponse>("audit", 60_000)
  const [query, setQuery] = useState("")
  const [type, setType] = useState("ALL")

  const events = useMemo(() => data?.events ?? [], [data])
  const types = useMemo(
    () =>
      Array.from(
        new Set(events.map((event) => event.event_type).filter(Boolean) as string[])
      ).sort(),
    [events]
  )
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return events.filter((event) => {
      if (type !== "ALL" && event.event_type !== type) return false
      if (!needle) return true
      return [event.summary, event.event_type, event.source, event.run_id]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(needle))
    })
  }, [events, query, type])

  if (loading && !data) return <LoadingPage />

  if (error && !data) {
    return (
      <div className="space-y-5 p-4 md:p-6">
        <PageHeader
          title="Audit Log"
          description="Local ledger events for proposals, policy outcomes, submissions and reconciliation."
        />
        <StatePanel
          kind="error"
          title="Audit ledger unavailable"
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

  return (
    <div className="space-y-5 p-4 md:p-6">
      <PageHeader
        title="Audit Log"
        description="Immutable SQLite ledger tracking proposals, risk gate decisions, submission records, and reconciliation."
        actions={
          <RefreshButton
            onClick={refresh}
            refreshing={refreshing}
            refreshedAt={refreshedAt}
          />
        }
      />

      {/* Ledger Metrics Strip */}
      <MetricStrip>
        <Metric
          label="Total events"
          value={String(data.counts.events)}
          detail="Immutable audit trail"
        />
        <Metric
          label="Submissions"
          value={String(data.counts.submissions)}
          detail="Durable broker records"
        />
        <Metric
          label="Unknown outcomes"
          value={data.counts.unknown_submissions ? "Detected" : "None (0)"}
          detail="Reconciliation clean"
          tone={data.counts.unknown_submissions ? "warning" : "neutral"}
        />
        <Metric
          label="Filtered events"
          value={String(filtered.length)}
          detail={type === "ALL" ? "All event categories" : type}
        />
      </MetricStrip>

      {/* Search & Filter Toolbar */}
      <div className="flex flex-col gap-2.5 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative flex-1 max-w-md">
          <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by summary, source or run ID..."
            className="h-8 pl-8 text-xs"
            aria-label="Filter audit events"
          />
        </div>
        <div className="flex items-center gap-2">
          <select
            value={type}
            onChange={(event) => setType(event.target.value)}
            aria-label="Filter by event type"
            className="h-8 rounded-md border bg-background px-2.5 text-xs text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <option value="ALL">All event types ({events.length})</option>
            {types.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          {query || type !== "ALL" ? (
            <button
              type="button"
              onClick={() => {
                setQuery("")
                setType("ALL")
              }}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Reset
            </button>
          ) : null}
        </div>
      </div>

      {/* Dense Chronological Audit Table */}
      <SectionCard
        title="Chronological event stream"
        description="Immutable ledger entries in reverse-chronological order."
      >
        <TableShell>
          <table className="w-full text-left text-[11px]">
            <thead>
              <tr className="border-b text-[10px] text-muted-foreground">
                <th className="px-3 py-2 font-medium">Time</th>
                <th className="px-3 py-2 font-medium">Event type</th>
                <th className="hidden px-3 py-2 font-medium md:table-cell">Source</th>
                <th className="px-3 py-2 font-medium">Summary</th>
                <th className="hidden px-3 py-2 font-medium lg:table-cell">Identifiers</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <EmptyRow
                  colSpan={5}
                  label={
                    events.length === 0
                      ? "The append-only ledger contains no recorded events."
                      : "No ledger events match the current filter criteria."
                  }
                />
              ) : (
                filtered.map((event) => (
                  <tr
                    key={`${event.event_id}-${event.occurred_at_utc}`}
                    className="border-b last:border-0 hover:bg-muted/30"
                  >
                    <td className="whitespace-nowrap px-3 py-2 font-mono text-[10px] text-muted-foreground">
                      {utcTimestamp(event.occurred_at_utc)}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2">
                      <span
                        className={cn(
                          "font-mono text-[10px] font-semibold",
                          eventTone(event.event_type)
                        )}
                      >
                        {event.event_type ?? "EVENT"}
                      </span>
                    </td>
                    <td className="hidden whitespace-nowrap px-3 py-2 text-[10px] text-muted-foreground md:table-cell">
                      {event.source ?? "—"}
                    </td>
                    <td className="px-3 py-2 text-foreground">
                      <p className="line-clamp-2 leading-relaxed">{event.summary}</p>
                    </td>
                    <td className="hidden whitespace-nowrap px-3 py-2 font-mono text-[10px] text-muted-foreground lg:table-cell">
                      <span>id:{compactId(event.event_id, 6, 4)}</span>
                      {event.run_id ? (
                        <span className="ml-2">run:{compactId(event.run_id, 6, 4)}</span>
                      ) : null}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </TableShell>
      </SectionCard>

      {/* Ledger Invariants Footer Note */}
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
        <span>
          SQLite append-only ledger · Preflight outcome and idempotency key are persisted before any broker write
        </span>
        <span>
          Last write {utcTimestamp(data.generated_at_utc)}
        </span>
      </div>
    </div>
  )
}
