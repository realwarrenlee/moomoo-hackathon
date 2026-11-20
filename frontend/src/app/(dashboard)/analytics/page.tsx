"use client"

import { useMemo, useState } from "react"
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import {
  EmptyRow,
  InfoNote,
  LoadingPage,
  PageContainer,
  PageHeader,
  PageState,
  Section,
  Segmented,
  TableShell,
  Td,
  Th,
} from "@/components/mootrade/primitives"
import { useDashboard } from "@/components/mootrade/use-dashboard"
import {
  drawdownPercent,
  percent,
  shortDate,
  shortMonthDay,
  signedPercent,
  type AnalyticsDataset,
  type AnalyticsResponse,
} from "@/lib/mootrade"
import { cn } from "@/lib/utils"

const LINE_COLORS = ["#22c55e", "#38bdf8", "#a78bfa", "#f59e0b"]

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: { name?: string; value?: number; color?: string }[]
  label?: string
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border bg-popover px-3 py-2 text-[11px] shadow-md">
      <p className="mb-1 font-mono text-muted-foreground">{label}</p>
      {payload.map((item) => (
        <p key={item.name} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5">
            <span className="size-1.5 rounded-full" style={{ background: item.color }} />
            {item.name}
          </span>
          <span className="font-mono tabular-nums">
            {typeof item.value === "number" ? item.value.toFixed(2) : item.value}
          </span>
        </p>
      ))}
    </div>
  )
}

function datasetWindow(dataset: AnalyticsDataset) {
  const holdout = dataset.period.holdout?.split(" to ")
  const development = dataset.period.development?.split(" to ")
  return {
    start: dataset.period.start ?? holdout?.[0] ?? development?.[0],
    end: dataset.period.end ?? holdout?.[1] ?? development?.[1],
  }
}

function EquityChart({ dataset }: { dataset: AnalyticsDataset }) {
  const rows = useMemo(() => {
    const dates = dataset.axis_dates?.length
      ? dataset.axis_dates
      : Array.from(
          new Set(dataset.curves.flatMap((curve) => curve.points.map((point) => point.date)))
        ).sort()
    return dates.map((date) => {
      const row: Record<string, string | number | null> = { date }
      for (const curve of dataset.curves) {
        row[curve.label] = curve.points.find((point) => point.date === date)?.value ?? null
      }
      return row
    })
  }, [dataset])

  return (
    <div className="h-[320px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(value: string) => shortMonthDay(value)}
            minTickGap={40}
          />
          <YAxis
            domain={["auto", "auto"]}
            tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
            tickLine={false}
            axisLine={false}
            width={44}
          />
          <Tooltip content={<ChartTooltip />} />
          <Legend wrapperStyle={{ fontSize: 11, paddingTop: 12 }} iconType="circle" iconSize={7} />
          {dataset.curves.map((curve, index) => (
            <Line
              key={curve.key}
              type="monotone"
              dataKey={curve.label}
              stroke={LINE_COLORS[index % LINE_COLORS.length]}
              strokeWidth={1.8}
              dot={false}
              connectNulls={!dataset.axis_dates?.length}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function AnalyticsPage() {
  const { data, error, loading } = useDashboard<AnalyticsResponse>("analytics", 300_000)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  if (loading && !data) return <LoadingPage />

  if (error && !data) {
    return (
      <PageContainer>
        <PageHeader title="Performance Analytics" />
        <PageState title="Analytics unavailable" description={error} />
      </PageContainer>
    )
  }

  if (!data) return null

  const datasets = data.datasets
  const dataset = datasets.find((item) => item.id === selectedId) ?? datasets[0]
  const window = dataset ? datasetWindow(dataset) : null

  return (
    <PageContainer>
      <PageHeader title="Performance Analytics" />

      {!data.paper_account_performance.available ? (
        <InfoNote tone="warning">
          <span className="font-medium">No paper-account equity observations yet.</span>{" "}
          {data.paper_account_performance.reason} SPY below is the benchmark from
          completed Moomoo daily bars.
        </InfoNote>
      ) : null}

      {!dataset ? (
        <PageState
          kind="empty"
          title="No competition-period evidence yet"
          description="Paper-account equity and completed SPY daily bars appear here once the competition period produces data."
        />
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            {datasets.length > 1 ? (
              <Segmented
                options={datasets.map((item) => ({ value: item.id, label: item.label }))}
                value={dataset.id}
                onChange={setSelectedId}
              />
            ) : (
              <p className="text-sm font-medium">{dataset.label}</p>
            )}
            <p className="text-xs text-muted-foreground">
              {window?.start ? shortDate(window.start) : "—"} –{" "}
              {window?.end ? shortDate(window.end) : "—"}
            </p>
          </div>

          <Section title="Equity curves" description="Normalised to 100 · competition period" flush>
            <div className="p-4">
              <EquityChart dataset={dataset} />
            </div>
          </Section>

          <Section title="Competition performance" flush>
            <TableShell>
              <thead>
                <tr>
                  <Th>Strategy</Th>
                  <Th align="right">Return</Th>
                  <Th align="right">Max DD</Th>
                  <Th align="right" className="hidden sm:table-cell">
                    Volatility
                  </Th>
                  <Th align="right">Sharpe</Th>
                  <Th align="right" className="hidden lg:table-cell">
                    Exposure
                  </Th>
                  <Th align="right" className="hidden xl:table-cell">
                    Trades
                  </Th>
                </tr>
              </thead>
              <tbody>
                {dataset.metrics.length === 0 ? (
                  <EmptyRow colSpan={7}>No metrics available for this dataset.</EmptyRow>
                ) : (
                  dataset.metrics.map((metric) => (
                    <tr key={`${metric.strategy}-${metric.period}`}>
                      <Td>
                        <p className="font-medium">{metric.label}</p>
                      </Td>
                      <Td
                        align="right"
                        className={cn(
                          "font-mono tabular-nums",
                          (metric.total_return_pct ?? 0) > 0
                            ? "text-emerald-600 dark:text-emerald-400"
                            : (metric.total_return_pct ?? 0) < 0
                              ? "text-rose-600 dark:text-rose-400"
                              : ""
                        )}
                      >
                        {signedPercent(metric.total_return_pct)}
                      </Td>
                      <Td align="right" className="font-mono tabular-nums">
                        {drawdownPercent(metric.max_drawdown_pct)}
                      </Td>
                      <Td align="right" className="hidden font-mono tabular-nums sm:table-cell">
                        {percent(metric.annualized_volatility_pct)}
                      </Td>
                      <Td align="right" className="font-mono tabular-nums">
                        {metric.sharpe === null || metric.sharpe === undefined
                          ? "—"
                          : metric.sharpe.toFixed(2)}
                      </Td>
                      <Td align="right" className="hidden font-mono tabular-nums lg:table-cell">
                        {percent(metric.exposure_pct, 0)}
                      </Td>
                      <Td align="right" className="hidden font-mono tabular-nums xl:table-cell">
                        {metric.trades ?? "—"}
                      </Td>
                    </tr>
                  ))
                )}
              </tbody>
            </TableShell>
          </Section>

          {dataset.limitations.length > 0 ? (
            <details className="group overflow-hidden rounded-xl border bg-card">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
                <p className="text-sm font-semibold">Study limitations</p>
                <span className="text-xs text-muted-foreground">
                  {dataset.limitations.length} documented
                </span>
              </summary>
              <ul className="space-y-1.5 border-t p-4 text-xs leading-relaxed text-muted-foreground">
                {dataset.limitations.map((limitation) => (
                  <li key={limitation} className="flex gap-2">
                    <span className="mt-1.5 size-1 shrink-0 rounded-full bg-muted-foreground" />
                    <span>{limitation}</span>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </>
      )}
    </PageContainer>
  )
}
