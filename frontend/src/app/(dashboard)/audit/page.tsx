"use client"

import { useMemo, useState } from "react"
import { SearchIcon } from "lucide-react"

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
import { useDashboard } from "@/components/mootrade/use-dashboard"
import { Input } from "@/components/ui/input"
import {
  eventTone,
  humanEventName,
  humanState,
  shortDateTime,
  utcTimestamp,
  type AuditEvent,
  type AuditResponse,
} from "@/lib/mootrade"

const SUMMARY_TERMS: [RegExp, string][] = [
  [/\bHISTORICAL_POLICY_APPROVAL\b/g, "Policy approved (historical)"],
  [/\bPOLICY_APPROVAL\b/g, "Policy approved"],
  [/\bPOLICY_REJECTED\b/g, "Policy rejected"],
  [/\bNO_TRADE\b/g, "No trade"],
  [/\bCURRENT_MARKET_READ_ONLY\b/g, "Current market read"],
  [/\bHISTORICAL_DRY_RUN\b/g, "Historical dry run"],
  [/proposal=present/g, "proposal captured"],
  [/proposal=none/g, "no proposal"],
]

function humanSummary(summary: string) {
  return SUMMARY_TERMS.reduce(
    (text, [pattern, replacement]) => text.replace(pattern, replacement),
    summary
  )
}

export default function AuditPage() {
  const { data, error, loading } = useDashboard<AuditResponse>("audit", 60_000)
  const [query, setQuery] = useState("")
  const [type, setType] = useState("ALL")
  const [selected, setSelected] = useState<AuditEvent | null>(null)

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
      <PageContainer>
        <PageHeader title="Audit Log" />
        <PageState title="Audit ledger unavailable" description={error} />
      </PageContainer>
    )
  }

  if (!data) return null

  return (
    <PageContainer>
      <PageHeader
        title="Audit Log"
        meta={
          <>
            <span className="text-xs text-muted-foreground">
              {data.counts.events} events
            </span>
            {data.counts.unknown_submissions ? (
              <StatusPill tone="danger" dot>
                Unknown order outcome
              </StatusPill>
            ) : null}
          </>
        }
      />

      <div className="flex flex-col gap-2.5 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative w-full sm:max-w-sm">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search summaries, sources or IDs"
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
            <option value="ALL">All event types</option>
            {types.map((item) => (
              <option key={item} value={item}>
                {humanEventName(item)}
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

      <Section flush>
        {filtered.length === 0 ? (
          <p className="px-4 py-5 text-[13px] text-muted-foreground">
            {events.length === 0
              ? "The append-only ledger contains no recorded events."
              : "No ledger events match the current filters."}
          </p>
        ) : (
          <>
            <div className="divide-y sm:hidden">
              {filtered.map((event) => (
                <button
                  key={`${event.event_id}-${event.occurred_at_utc}`}
                  type="button"
                  onClick={() => setSelected(event)}
                  aria-label={`Open ${humanEventName(event.event_type)} event`}
                  className="flex w-full flex-col px-4 py-2.5 text-left transition-colors hover:bg-muted/30 focus-visible:bg-muted/30 focus-visible:outline-none"
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="flex min-w-0 items-center gap-1.5">
                      <span className="truncate text-[13px] font-medium">
                        {humanEventName(event.event_type)}
                      </span>
                    </span>
                    <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
                      {shortDateTime(event.occurred_at_utc)}
                    </span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                    {humanSummary(event.summary)}
                  </p>
                </button>
              ))}
            </div>
            <div className="hidden sm:block">
        <TableShell>
          <thead>
            <tr>
              <Th className="hidden lg:table-cell">Time</Th>
              <Th>Event</Th>
              <Th className="hidden lg:table-cell">Source</Th>
              <Th>Summary</Th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <EmptyRow colSpan={4}>
                {events.length === 0
                  ? "The append-only ledger contains no recorded events."
                  : "No ledger events match the current filters."}
              </EmptyRow>
            ) : (
              filtered.map((event) => (
                <tr
                  key={`${event.event_id}-${event.occurred_at_utc}`}
                  tabIndex={0}
                  role="button"
                  aria-label={`Open ${humanEventName(event.event_type)} event`}
                  onClick={() => setSelected(event)}
                  onKeyDown={(event_) => {
                    if (event_.key === "Enter" || event_.key === " ") {
                      event_.preventDefault()
                      setSelected(event)
                    }
                  }}
                  className="cursor-pointer transition-colors hover:bg-muted/30 focus-visible:bg-muted/30 focus-visible:outline-none"
                >
                  <Td className="hidden whitespace-nowrap font-mono text-xs text-muted-foreground lg:table-cell">
                    {shortDateTime(event.occurred_at_utc)}
                  </Td>
                  <Td className="whitespace-nowrap">
                    <span className="flex items-center gap-1.5">
                      <span className="text-[13px] font-medium">
                        {humanEventName(event.event_type)}
                      </span>
                    </span>
                    <span className="mt-0.5 block font-mono text-[10px] text-muted-foreground lg:hidden">
                      {shortDateTime(event.occurred_at_utc)}
                    </span>
                  </Td>
                  <Td className="hidden whitespace-nowrap text-xs text-muted-foreground lg:table-cell">
                    {event.source ?? "—"}
                  </Td>
                  <Td className="text-[13px]">
                    <p className="line-clamp-2 leading-relaxed">
                      {humanSummary(event.summary)}
                    </p>
                  </Td>
                </tr>
              ))
            )}
          </tbody>
        </TableShell>
            </div>
          </>
        )}
      </Section>

      {query || type !== "ALL" ? (
        <p className="text-[11px] text-muted-foreground">
          Showing {filtered.length} of {events.length} events.
        </p>
      ) : null}

      <DetailSheet
        open={selected !== null}
        onOpenChange={(open) => {
          if (!open) setSelected(null)
        }}
        title={selected ? humanEventName(selected.event_type) : "Audit event"}
        description={
          selected
            ? `${utcTimestamp(selected.occurred_at_utc)} · ${selected.source ?? "unknown source"}`
            : undefined
        }
      >
        {selected ? (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <StatusPill tone={eventTone(selected.event_type)}>
                {humanEventName(selected.event_type)}
              </StatusPill>
              <span className="font-mono text-[11px] text-muted-foreground">
                {selected.event_type ?? "EVENT"}
              </span>
            </div>

            <p className="text-[13px] leading-relaxed">{selected.summary}</p>

            <div className="rounded-lg border px-3">
              <KeyValue label="Occurred" value={utcTimestamp(selected.occurred_at_utc)} mono />
              <KeyValue label="Event ID" value={selected.event_id ?? "—"} mono />
              <KeyValue label="Run ID" value={selected.run_id ?? "—"} mono />
              <KeyValue
                label="Correlation ID"
                value={selected.correlation_id ?? "—"}
                mono
              />
              <KeyValue label="Source" value={selected.source ?? "—"} mono />
              <KeyValue label="Provenance" value={humanState(selected.provenance)} />
            </div>

            <InfoNote>
              Append-only ledger entry. The reference implementation records proposals and
              policy outcomes before any broker submission; broker state remains the source
              of truth for fills.
            </InfoNote>
          </div>
        ) : null}
      </DetailSheet>
    </PageContainer>
  )
}
