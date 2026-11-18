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
import {
  drawdownPercent,
  percent,
  shortDate,
  shortMonthDay,
  signedPercent,
  utcTimestamp,
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
    <div className="rounded-lg border bg-popover px-3 py-2 text-[10px] shadow-md">
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

function DatasetView({ dataset }: { dataset: AnalyticsDataset }) {
  const rows = useMemo(() => {
    const dates = Array.from(
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
    <div className="space-y-4">
      {/* Equity Curves Chart */}
      <SectionCard
        title="Normalised equity curves (base 100)"
        description="Daily performance indexed to 100 for comparative trajectory analysis."
      >
        <div className="h-[340px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 9, fill: "var(--muted-foreground)" }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(value: string) => shortMonthDay(value)}
                minTickGap={36}
              />
              <YAxis
                domain={["auto", "auto"]}
                tick={{ fontSize: 9, fill: "var(--muted-foreground)" }}
                tickLine={false}
                axisLine={false}
                width={46}
              />
              <Tooltip content={<ChartTooltip />} />
              <Legend
                wrapperStyle={{ fontSize: 11, paddingTop: 12 }}
                iconType="circle"
                iconSize={7}
              />
              {dataset.curves.map((curve, index) => (
                <Line
                  key={curve.key}
                  type="monotone"
                  dataKey={curve.label}
                  stroke={LINE_COLORS[index % LINE_COLORS.length]}
                  strokeWidth={1.8}
                  dot={false}
                  connectNulls
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </SectionCard>

      {/* Historical Strategy Metrics Table */}
      <SectionCard
        title="Strategy performance metrics"
        description="Normalized historical performance metrics computed over frozen sample windows."
      >
        <TableShell>
          <table className="w-full text-left text-[11px]">
            <thead>
              <tr className="border-b text-[10px] text-muted-foreground">
                <th className="px-3 py-2 font-medium">Strategy</th>
                <th className="hidden px-3 py-2 font-medium md:table-cell">Sample window</th>
                <th className="px-3 py-2 text-right font-medium">Total return</th>
                <th className="hidden px-3 py-2 text-right font-medium sm:table-cell">
                  Max drawdown
                </th>
                <th className="hidden px-3 py-2 text-right font-medium lg:table-cell">
                  Volatility
                </th>
                <th className="px-3 py-2 text-right font-medium">Sharpe</th>
                <th className="hidden px-3 py-2 text-right font-medium xl:table-cell">Trades</th>
                <th className="hidden px-3 py-2 text-right font-medium lg:table-cell">
                  Exposure
                </th>
              </tr>
            </thead>
            <tbody>
              {dataset.metrics.length === 0 ? (
                <EmptyRow
                  colSpan={8}
                  label="No metrics available for this dataset."
                />
              ) : (
                dataset.metrics.map((metric) => (
                  <tr
                    key={`${metric.strategy}-${metric.period}`}
                    className="border-b last:border-0"
                  >
                    <td className="px-3 py-2">
                      <p className="font-medium">{metric.label}</p>
                      <p className="font-mono text-[9px] text-muted-foreground">
                        {metric.strategy}
                      </p>
                    </td>
                    <td className="hidden px-3 py-2 text-[10px] text-muted-foreground md:table-cell">
                      {metric.period}
                    </td>
                    <td
                      className={cn(
                        "px-3 py-2 text-right font-mono tabular-nums",
                        (metric.total_return_pct ?? 0) > 0
                          ? "text-emerald-600 dark:text-emerald-400"
                          : (metric.total_return_pct ?? 0) < 0
                            ? "text-rose-600 dark:text-rose-400"
                            : ""
                      )}
                    >
                      {signedPercent(metric.total_return_pct)}
                    </td>
                    <td className="hidden px-3 py-2 text-right font-mono tabular-nums text-amber-600 dark:text-amber-400 sm:table-cell">
                      {drawdownPercent(metric.max_drawdown_pct)}
                    </td>
                    <td className="hidden px-3 py-2 text-right font-mono tabular-nums lg:table-cell">
                      {percent(metric.annualized_volatility_pct)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums">
                      {metric.sharpe === null || metric.sharpe === undefined
                        ? "—"
                        : metric.sharpe.toFixed(2)}
                    </td>
                    <td className="hidden px-3 py-2 text-right font-mono tabular-nums xl:table-cell">
                      {metric.trades ?? "—"}
                    </td>
                    <td className="hidden px-3 py-2 text-right font-mono tabular-nums lg:table-cell">
                      {percent(metric.exposure_pct, 0)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </TableShell>
      </SectionCard>

      {/* Documented Constraints & Limitations */}
      {dataset.limitations.length > 0 ? (
        <details className="rounded-lg border bg-card px-4 py-3 text-xs">
          <summary className="cursor-pointer list-none font-medium text-foreground hover:text-foreground/80">
            Documented study constraints & limitations ({dataset.limitations.length})
          </summary>
          <ul className="mt-2 space-y-1 text-[11px] leading-relaxed text-muted-foreground">
            {dataset.limitations.map((limitation) => (
              <li key={limitation} className="flex gap-2">
                <span className="mt-1.5 size-1 shrink-0 rounded-full bg-muted-foreground" />
                <span>{limitation}</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  )
}

export default function AnalyticsPage() {
  const { data, error, loading, refreshing, refreshedAt, refresh } =
    useDashboard<AnalyticsResponse>("analytics", 300_000)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  if (loading && !data) return <LoadingPage />

  if (error && !data) {
    return (
      <div className="space-y-5 p-4 md:p-6">
        <PageHeader
          title="Performance Analytics"
          description="Historical research results and backtest simulations."
        />
        <StatePanel
          kind="error"
          title="Analytics unavailable"
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

  const datasets = data.datasets
  const dataset = datasets.find((item) => item.id === selectedId) ?? datasets[0]
  const window = dataset ? datasetWindow(dataset) : null

  return (
    <div className="space-y-5 p-4 md:p-6">
      <PageHeader
        title="Performance Analytics"
        description="Historical simulation and catalyst studies produced by the research pipeline."
        actions={
          <RefreshButton
            onClick={refresh}
            refreshing={refreshing}
            refreshedAt={refreshedAt}
          />
        }
      />

      {/* Clear Research Distinction Banner */}
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 rounded-lg border bg-card px-3.5 py-2 text-xs">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="font-semibold text-foreground">
            Historical Simulation Research
          </span>
          <span className="text-muted-foreground">·</span>
          <span className="text-muted-foreground">
            {data.paper_account_performance.available
              ? "Paper trades available"
              : "No filled paper trades; paper account P&L unavailable"}
          </span>
        </div>
        <span className="font-mono text-[11px] text-muted-foreground">
          Study generated {utcTimestamp(data.generated_at_utc)}
        </span>
      </div>

      {!dataset ? (
        <StatePanel
          title="No historical datasets"
          description="No backtest or catalyst evidence available."
        />
      ) : (
        <>
          {/* Quick Metrics Strip */}
          <MetricStrip>
            <Metric
              label="Selected study"
              value={dataset.label}
              detail={dataset.version ?? "Normalized daily series"}
            />
            <Metric
              label="Strategies evaluated"
              value={String(new Set(dataset.metrics.map((m) => m.strategy)).size)}
              detail="Frozen parameter logic"
            />
            <Metric
              label="Evaluation window"
              value={window?.start ? shortDate(window.start) : "—"}
              detail={window?.end ? `through ${shortDate(window.end)}` : "—"}
            />
            <Metric
              label="Available studies"
              value={String(datasets.length)}
              detail="Research datasets"
            />
          </MetricStrip>

          {/* Dataset Switcher Tabs */}
          {datasets.length > 1 ? (
            <div className="flex flex-wrap gap-1.5">
              {datasets.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setSelectedId(item.id)}
                  className={cn(
                    "rounded-md border px-3 py-1.5 text-xs font-medium transition-colors",
                    item.id === dataset.id
                      ? "bg-foreground text-background"
                      : "text-muted-foreground hover:bg-muted"
                  )}
                >
                  {item.label}
                </button>
              ))}
            </div>
          ) : null}

          <DatasetView dataset={dataset} />
        </>
      )}
    </div>
  )
}
