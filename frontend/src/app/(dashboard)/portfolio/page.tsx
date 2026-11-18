"use client"

import { useState } from "react"

import {
  DetailSheet,
  EmptyRow,
  Freshness,
  InfoNote,
  KeyValue,
  LoadingPage,
  PageContainer,
  PageHeader,
  PageState,
  Section,
  Segmented,
  Stat,
  StatGrid,
  StatusPill,
  Td,
  Th,
  TableShell,
} from "@/components/mootrade/primitives"
import { useDashboard } from "@/components/mootrade/use-dashboard"
import {
  investedValue,
  money,
  shortDateTime,
  utcTimestamp,
  type OrderView,
  type PortfolioResponse,
  type Tone,
} from "@/lib/mootrade"

function statusTone(status: string): Tone {
  const normalized = status.toUpperCase()
  if (["FILLED", "SUCCESS", "COMPLETE"].includes(normalized)) return "positive"
  if (["CANCELLED", "CANCELED", "FAILED", "REJECTED"].includes(normalized))
    return "danger"
  if (["UNKNOWN", "PENDING", "SUBMITTED", "PARTIAL"].includes(normalized))
    return "warning"
  return "neutral"
}

function statusTextClass(status: string) {
  const tone = statusTone(status)
  if (tone === "positive") return "text-emerald-700 dark:text-emerald-300"
  if (tone === "danger") return "text-rose-700 dark:text-rose-300"
  if (tone === "warning") return "text-amber-700 dark:text-amber-300"
  return "text-muted-foreground"
}

function OrdersTable({
  orders,
  emptyLabel,
  onSelect,
}: {
  orders: OrderView[]
  emptyLabel: string
  onSelect: (order: OrderView) => void
}) {
  return (
    <TableShell>
      <thead>
        <tr>
          <Th className="hidden sm:table-cell">Time</Th>
          <Th>Symbol</Th>
          <Th>Side</Th>
          <Th align="right">Qty / filled</Th>
          <Th align="right" className="hidden sm:table-cell">
            Avg fill
          </Th>
          <Th align="right">Status</Th>
        </tr>
      </thead>
      <tbody>
        {orders.length === 0 ? (
          <EmptyRow colSpan={6}>{emptyLabel}</EmptyRow>
        ) : (
          orders.map((order) => (
            <tr
              key={order.broker_order_id}
              onClick={() => onSelect(order)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault()
                  onSelect(order)
                }
              }}
              tabIndex={0}
              aria-label={`Open order ${order.symbol} ${order.side} ${order.status}`}
              className="cursor-pointer transition-colors hover:bg-muted/40 focus-visible:bg-muted/40 focus-visible:outline-none"
            >
              <Td className="hidden whitespace-nowrap text-xs text-muted-foreground sm:table-cell">
                {shortDateTime(order.updated_at_utc ?? order.created_at_utc)}
              </Td>
              <Td className="font-mono font-semibold">
                {order.symbol}
                <span className="block text-[10px] font-normal text-muted-foreground sm:hidden">
                  {shortDateTime(order.updated_at_utc ?? order.created_at_utc)}
                </span>
              </Td>
              <Td>
                <span className="font-mono text-xs font-semibold">
                  {order.side.toUpperCase()}
                </span>
              </Td>
              <Td align="right" className="tabular-nums">
                {order.quantity} / {order.filled_quantity}
              </Td>
              <Td align="right" className="hidden tabular-nums sm:table-cell">
                {money(order.average_fill_price)}
              </Td>
              <Td align="right">
                <span className={`text-xs font-medium ${statusTextClass(order.status)}`}>
                  {order.status}
                </span>
              </Td>
            </tr>
          ))
        )}
      </tbody>
    </TableShell>
  )
}

export default function PortfolioPage() {
  const { data, error, loading, refresh } =
    useDashboard<PortfolioResponse>("portfolio", 60_000)
  const [orderTab, setOrderTab] = useState<"today" | "history">("today")
  const [selectedOrder, setSelectedOrder] = useState<OrderView | null>(null)

  if (loading && !data) return <LoadingPage />

  if (!data) {
    return (
      <PageContainer>
        <PageHeader title="Portfolio & Orders" />
        <PageState
          title="Portfolio unavailable"
          description={error ?? "The read-only broker API returned no data."}
          onRetry={refresh}
        />
      </PageContainer>
    )
  }

  const account = data.account
  const invested = investedValue(account?.equity, account?.cash)
  const orders = orderTab === "today" ? data.today_orders : data.history_orders
  const brokerUnavailable = Boolean(data.reason) || !account

  return (
    <PageContainer>
      <PageHeader title="Portfolio & Orders" />

      {data.reason ? (
        <InfoNote tone="danger">
          <p className="font-medium">Broker connection unavailable</p>
          <p>{data.reason}</p>
        </InfoNote>
      ) : null}
      {data.warnings.length > 0 ? (
        <InfoNote tone="warning">
          <ul className="list-disc space-y-0.5 pl-4">
            {data.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </InfoNote>
      ) : null}

      <StatGrid>
        <Stat
          label="Equity"
          value={money(account?.equity)}
          hint={account ? <Freshness seconds={account.age_seconds} /> : "Unavailable"}
        />
        <Stat
          label="Invested"
          value={invested === null ? "—" : money(invested)}
          hint={brokerUnavailable ? "Unavailable" : undefined}
        />
        <Stat label="Cash" value={money(account?.cash)} />
        <Stat
          label="Open orders"
          value={brokerUnavailable ? "—" : String(data.open_orders.length)}
          hint={
            brokerUnavailable
              ? "Unavailable"
              : account?.reconciled === false
                ? "Reconciliation mismatch"
                : undefined
          }
          tone={account?.reconciled === false ? "warning" : "neutral"}
        />
      </StatGrid>

      <Section title="Positions" flush>
        <TableShell>
          <thead>
            <tr>
              <Th>Symbol</Th>
              <Th align="right">Quantity</Th>
              <Th align="right">Market value</Th>
            </tr>
          </thead>
          <tbody>
            {data.positions.length === 0 ? (
              <EmptyRow colSpan={3}>
                {brokerUnavailable
                  ? "Positions unavailable — the broker read failed."
                  : "No open positions reported by the broker."}
              </EmptyRow>
            ) : (
              data.positions.map((position) => (
                <tr key={position.symbol}>
                  <Td className="font-mono font-semibold">{position.symbol}</Td>
                  <Td align="right" className="tabular-nums">
                    {position.quantity}
                  </Td>
                  <Td align="right" className="tabular-nums">
                    {money(position.market_value)}
                  </Td>
                </tr>
              ))
            )}
          </tbody>
        </TableShell>
      </Section>

      <Section title="Open orders" flush>
        <TableShell>
          <thead>
            <tr>
              <Th>Symbol</Th>
              <Th>Side</Th>
              <Th align="right">Remaining</Th>
              <Th align="right">Reference</Th>
            </tr>
          </thead>
          <tbody>
            {data.open_orders.length === 0 ? (
              <EmptyRow colSpan={4}>
                {brokerUnavailable
                  ? "Open orders unavailable — the broker read failed."
                  : "No working orders reported by the broker."}
              </EmptyRow>
            ) : (
              data.open_orders.map((order, index) => (
                <tr key={`${order.symbol}-${index}`}>
                  <Td className="font-mono font-semibold">{order.symbol}</Td>
                  <Td>
                    <span className="font-mono text-xs">{order.side}</span>
                  </Td>
                  <Td align="right" className="tabular-nums">
                    {order.remaining_quantity}
                  </Td>
                  <Td align="right" className="tabular-nums">
                    {money(order.reference_price)}
                  </Td>
                </tr>
              ))
            )}
          </tbody>
        </TableShell>
      </Section>

      <Section
        title="Order activity"
        flush
        action={
          <Segmented
            value={orderTab}
            onChange={setOrderTab}
            options={[
              { value: "today", label: `Today (${data.today_orders.length})` },
              { value: "history", label: `History (${data.history_orders.length})` },
            ]}
          />
        }
      >
        <OrdersTable
          orders={orders}
          emptyLabel={
            orderTab === "today"
              ? "No orders recorded today."
              : "No historical orders recorded for this account."
          }
          onSelect={setSelectedOrder}
        />
      </Section>

      <DetailSheet
        open={Boolean(selectedOrder)}
        onOpenChange={(open) => {
          if (!open) setSelectedOrder(null)
        }}
        title={
          selectedOrder
            ? `${selectedOrder.side.toUpperCase()} ${selectedOrder.symbol}`
            : "Order"
        }
        description="Broker order record. An acknowledgement is not a fill."
      >
        {selectedOrder ? (
          <div className="space-y-2">
            <KeyValue
              label="Status"
              value={
                <StatusPill tone={statusTone(selectedOrder.status)}>
                  {selectedOrder.status}
                </StatusPill>
              }
            />
            <KeyValue label="Order ID" value={selectedOrder.broker_order_id} mono />
            <KeyValue
              label="Quantity"
              value={`${selectedOrder.quantity} · filled ${selectedOrder.filled_quantity}`}
              mono
            />
            <KeyValue label="Limit price" value={money(selectedOrder.price)} mono />
            <KeyValue
              label="Average fill"
              value={money(selectedOrder.average_fill_price)}
              mono
            />
            <KeyValue
              label="Created"
              value={utcTimestamp(selectedOrder.created_at_utc)}
            />
            <KeyValue
              label="Updated"
              value={utcTimestamp(selectedOrder.updated_at_utc)}
            />
            <KeyValue label="Remark" value={selectedOrder.remark || "—"} mono />
            <KeyValue label="Source" value={selectedOrder.provenance} mono />
          </div>
        ) : null}
      </DetailSheet>
    </PageContainer>
  )
}
