"use client"

import { useState } from "react"
import { CheckCircle2Icon } from "lucide-react"

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
  ageLabel,
  compactId,
  money,
  utcTimestamp,
  type OrderView,
  type PortfolioResponse,
} from "@/lib/mootrade"
import { cn } from "@/lib/utils"

function statusTone(status: string) {
  const normalized = status.toUpperCase()
  if (["FILLED", "SUCCESS", "COMPLETE"].includes(normalized))
    return "text-emerald-600 dark:text-emerald-400"
  if (["CANCELLED", "CANCELED", "FAILED", "REJECTED"].includes(normalized))
    return "text-rose-600 dark:text-rose-400"
  if (["UNKNOWN", "PENDING", "SUBMITTED", "PARTIAL"].includes(normalized))
    return "text-amber-600 dark:text-amber-400"
  return "text-muted-foreground"
}

function OrdersTable({
  orders,
  emptyLabel,
}: {
  orders: OrderView[]
  emptyLabel: string
}) {
  return (
    <TableShell>
      <table className="w-full text-left text-[11px]">
        <thead>
          <tr className="border-b text-[10px] text-muted-foreground">
            <th className="hidden px-3 py-2 font-medium sm:table-cell">Order ID</th>
            <th className="px-3 py-2 font-medium">Symbol</th>
            <th className="px-3 py-2 font-medium">Side</th>
            <th className="px-3 py-2 text-right font-medium">Qty / filled</th>
            <th className="hidden px-3 py-2 text-right font-medium md:table-cell">Price</th>
            <th className="hidden px-3 py-2 text-right font-medium md:table-cell">Avg fill</th>
            <th className="px-3 py-2 font-medium">Status</th>
            <th className="hidden px-3 py-2 font-medium lg:table-cell">Updated</th>
          </tr>
        </thead>
        <tbody>
          {orders.length === 0 ? (
            <EmptyRow colSpan={8} label={emptyLabel} />
          ) : (
            orders.map((order) => (
              <tr key={order.broker_order_id} className="border-b last:border-0">
                <td className="hidden px-3 py-2 font-mono text-[10px] text-muted-foreground sm:table-cell">
                  {compactId(order.broker_order_id, 8, 5)}
                </td>
                <td className="px-3 py-2 font-mono font-semibold">{order.symbol}</td>
                <td
                  className={cn(
                    "px-3 py-2 font-mono text-[10px] font-semibold",
                    order.side.toUpperCase() === "BUY"
                      ? "text-emerald-600 dark:text-emerald-400"
                      : "text-rose-600 dark:text-rose-400"
                  )}
                >
                  {order.side.toUpperCase()}
                </td>
                <td className="px-3 py-2 text-right font-mono tabular-nums">
                  {order.quantity} / {order.filled_quantity}
                </td>
                <td className="hidden px-3 py-2 text-right font-mono tabular-nums md:table-cell">
                  {money(order.price)}
                </td>
                <td className="hidden px-3 py-2 text-right font-mono tabular-nums md:table-cell">
                  {money(order.average_fill_price)}
                </td>
                <td className={cn("px-3 py-2 font-medium", statusTone(order.status))}>
                  {order.status}
                </td>
                <td className="hidden whitespace-nowrap px-3 py-2 text-[10px] text-muted-foreground lg:table-cell">
                  {utcTimestamp(order.updated_at_utc ?? order.created_at_utc)}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </TableShell>
  )
}

export default function PortfolioPage() {
  const { data, error, loading, refreshing, refreshedAt, refresh } =
    useDashboard<PortfolioResponse>("portfolio", 60_000)
  const [orderTab, setOrderTab] = useState<"today" | "history">("today")

  if (loading && !data) return <LoadingPage />

  if (error && !data) {
    return (
      <div className="space-y-5 p-4 md:p-6">
        <PageHeader
          title="Portfolio & Orders"
          description="Read-only positions and order book retrieved from the competition paper account."
        />
        <StatePanel
          kind="error"
          title="Portfolio unavailable"
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

  const account = data.account

  return (
    <div className="space-y-5 p-4 md:p-6">
      <PageHeader
        title="Portfolio & Orders"
        description="Live positions and order book read directly from the Moomoo paper account."
        actions={
          <RefreshButton
            onClick={refresh}
            refreshing={refreshing}
            refreshedAt={refreshedAt}
          />
        }
      />

      {/* Account Verification & Snapshot Context */}
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-lg border bg-card px-3.5 py-2 text-xs">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="font-mono font-semibold text-foreground">
            {account?.masked_id ?? "—"}
          </span>
          <span className="text-muted-foreground">·</span>
          <span className="text-muted-foreground">
            Broker source: Moomoo REST · competition PAPER account
          </span>
          <span className="hidden text-muted-foreground sm:inline">·</span>
          <span className="hidden text-muted-foreground sm:inline">
            Fills backed by broker confirmation only
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
          <span className="flex items-center gap-1.5 font-medium text-emerald-600 dark:text-emerald-400">
            <CheckCircle2Icon className="size-3" />
            {account?.reconciled ? "State reconciled" : "Reconciliation attention"}
          </span>
          <span className="text-muted-foreground">·</span>
          <span className="font-mono text-muted-foreground">
            Snapshot {utcTimestamp(account?.as_of_utc)}
          </span>
        </div>
      </div>

      {data.warnings.length > 0 ? (
        <NoticeBanner tone="warning" title="Broker snapshot warnings">
          <ul className="list-disc space-y-0.5 pl-4">
            {data.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </NoticeBanner>
      ) : null}

      {data.reason ? (
        <NoticeBanner tone="danger" title="Broker connection note">
          {data.reason}
        </NoticeBanner>
      ) : null}

      {/* Financial Metrics Strip */}
      {account ? (
        <MetricStrip>
          <Metric
            label="Equity"
            value={money(account.equity)}
            detail={`Snapshot ${ageLabel(account.age_seconds)}`}
          />
          <Metric
            label="Cash balance"
            value={money(account.cash)}
            detail="Broker cash"
          />
          <Metric
            label="Buying power"
            value={money(account.buying_power)}
            detail="Cash-only (unlevered)"
          />
          <Metric
            label="Open orders / positions"
            value={`${account.open_orders_count} / ${account.positions_count}`}
            detail={`${account.unknown_orders} unknown orders`}
            tone={account.unknown_orders > 0 ? "warning" : "neutral"}
          />
        </MetricStrip>
      ) : null}

      {/* Positions & Working Orders Grid */}
      <div className="grid gap-4 lg:grid-cols-2">
        <SectionCard
          title="Positions"
          description="Current portfolio holdings reported by the broker."
        >
          <TableShell>
            <table className="w-full text-left text-[11px]">
              <thead>
                <tr className="border-b text-[10px] text-muted-foreground">
                  <th className="px-3 py-2 font-medium">Symbol</th>
                  <th className="px-3 py-2 text-right font-medium">Quantity</th>
                  <th className="px-3 py-2 text-right font-medium">Market value</th>
                </tr>
              </thead>
              <tbody>
                {data.positions.length === 0 ? (
                  <EmptyRow
                    colSpan={3}
                    label="No open positions reported in broker snapshot."
                  />
                ) : (
                  data.positions.map((position) => (
                    <tr key={position.symbol} className="border-b last:border-0">
                      <td className="px-3 py-2 font-mono font-semibold">
                        {position.symbol}
                      </td>
                      <td className="px-3 py-2 text-right font-mono tabular-nums">
                        {position.quantity}
                      </td>
                      <td className="px-3 py-2 text-right font-mono tabular-nums">
                        {money(position.market_value)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </TableShell>
        </SectionCard>

        <SectionCard
          title="Open orders"
          description="Active working orders in the broker order book."
        >
          <TableShell>
            <table className="w-full text-left text-[11px]">
              <thead>
                <tr className="border-b text-[10px] text-muted-foreground">
                  <th className="px-3 py-2 font-medium">Symbol</th>
                  <th className="px-3 py-2 font-medium">Side</th>
                  <th className="px-3 py-2 text-right font-medium">Remaining</th>
                  <th className="px-3 py-2 text-right font-medium">Reference</th>
                </tr>
              </thead>
              <tbody>
                {data.open_orders.length === 0 ? (
                  <EmptyRow
                    colSpan={4}
                    label="No working orders reported by broker."
                  />
                ) : (
                  data.open_orders.map((order, index) => (
                    <tr
                      key={`${order.symbol}-${index}`}
                      className="border-b last:border-0"
                    >
                      <td className="px-3 py-2 font-mono font-semibold">
                        {order.symbol}
                      </td>
                      <td className="px-3 py-2 font-mono text-[10px]">
                        {order.side}
                      </td>
                      <td className="px-3 py-2 text-right font-mono tabular-nums">
                        {order.remaining_quantity}
                      </td>
                      <td className="px-3 py-2 text-right font-mono tabular-nums">
                        {money(order.reference_price)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </TableShell>
        </SectionCard>
      </div>

      {/* Tabbed Order Activity (Today / History) */}
      <SectionCard
        title="Order activity"
        description="Broker order records for the current session and historical activity."
        action={
          <div className="flex gap-1 rounded-lg border bg-muted/40 p-0.5">
            <button
              type="button"
              onClick={() => setOrderTab("today")}
              className={cn(
                "rounded px-2.5 py-1 text-xs font-medium transition-colors",
                orderTab === "today"
                  ? "bg-background text-foreground shadow-xs"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              Today ({data.today_orders.length})
            </button>
            <button
              type="button"
              onClick={() => setOrderTab("history")}
              className={cn(
                "rounded px-2.5 py-1 text-xs font-medium transition-colors",
                orderTab === "history"
                  ? "bg-background text-foreground shadow-xs"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              History ({data.history_orders.length})
            </button>
          </div>
        }
      >
        {orderTab === "today" ? (
          <OrdersTable
            orders={data.today_orders}
            emptyLabel="No orders submitted or returned for today's regular session."
          />
        ) : (
          <OrdersTable
            orders={data.history_orders}
            emptyLabel="No historical orders recorded for this competition paper account."
          />
        )}
      </SectionCard>

      {/* Safe Account Snapshot & State Handling Details */}
      <div className="grid gap-4 lg:grid-cols-2">
        <SectionCard
          title="Account snapshot details"
          description="Sanitized metadata from the latest broker read."
        >
          <div className="grid gap-x-6 sm:grid-cols-2">
            <KeyValue label="Masked ID" value={account?.masked_id ?? "—"} mono />
            <KeyValue label="Positions" value={String(account?.positions_count ?? "0")} mono />
            <KeyValue label="Open orders" value={String(account?.open_orders_count ?? "0")} mono />
            <KeyValue label="Unknown orders" value={String(account?.unknown_orders ?? "0")} mono />
            <KeyValue label="Snapshot age" value={ageLabel(account?.age_seconds)} />
            <KeyValue label="Snapshot time" value={utcTimestamp(account?.as_of_utc)} mono />
          </div>
        </SectionCard>

        <SectionCard
          title="Reconciliation & safety policy"
          description="Broker state invariants enforced before execution."
        >
          <ul className="space-y-1.5 text-[11px] leading-relaxed text-muted-foreground">
            <li>Any ambiguous response or submission timeout transitions the order to <span className="font-mono text-foreground">UNKNOWN</span> without blind retries.</li>
            <li>Positions and fills are reconciled on restart and after every order event.</li>
            <li>Order writes are persistently disabled (<span className="font-mono text-foreground">ORDER_WRITES_ENABLED=false</span>).</li>
          </ul>
        </SectionCard>
      </div>
    </div>
  )
}
