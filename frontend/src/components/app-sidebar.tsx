"use client"

import { useState } from "react"
import Image from "next/image"
import Link from "next/link"
import {
  ArrowUpRightIcon,
  BotIcon,
  ChartNoAxesCombinedIcon,
  GaugeIcon,
  ScrollTextIcon,
  ShieldCheckIcon,
  WalletCardsIcon,
} from "lucide-react"

import { NavMain } from "@/components/nav-main"
import {
  DetailSheet,
  Freshness,
  InfoNote,
  KeyValue,
  StatusPill,
} from "@/components/mootrade/primitives"
import { useDashboard } from "@/components/mootrade/use-dashboard"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import {
  accountName,
  shortDateTime,
  utcTimestamp,
  type HealthResponse,
  type OverviewResponse,
} from "@/lib/mootrade"

const data = {
  navTrading: [
    { title: "Overview", url: "/dashboard", icon: <GaugeIcon /> },
    { title: "Portfolio & Orders", url: "/portfolio", icon: <WalletCardsIcon /> },
    { title: "Risk Centre", url: "/risk", icon: <ShieldCheckIcon /> },
  ],
  navIntelligence: [
    { title: "Agent Activity", url: "/agents", icon: <BotIcon /> },
    {
      title: "Performance Analytics",
      url: "/analytics",
      icon: <ChartNoAxesCombinedIcon />,
    },
  ],
  navSystem: [
    { title: "Audit Log", url: "/audit", icon: <ScrollTextIcon /> },
  ],
}

function AccountCard() {
  const [open, setOpen] = useState(false)
  const health = useDashboard<HealthResponse>("health", 60_000)
  const overview = useDashboard<OverviewResponse>("overview", 0)

  const account = overview.data?.account ?? null
  const controls = overview.data?.safety ?? null
  const apiOnline = !health.error && health.data?.state === "OK"
  const auth = health.data?.auth
  const authLabel =
    auth?.authorization === "PRESENT"
      ? "Broker authorised"
      : auth?.authorization === "AUTH_REQUIRED"
        ? "Broker sign-in required"
        : "Broker unavailable"

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Open account and system details"
        className="w-full rounded-lg border bg-card/60 px-3 py-2.5 text-left transition-colors hover:bg-sidebar-accent"
      >
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] font-medium text-muted-foreground">
            Competition paper account
          </span>
        </div>
        <div className="mt-1 flex items-center justify-between gap-2">
          {account?.masked_id ? (
            <span className="font-mono text-[13px] font-semibold tracking-tight">
              {accountName(account.masked_id)}
            </span>
          ) : (
            <span className="text-xs text-muted-foreground">ID unavailable</span>
          )}
          <ArrowUpRightIcon className="size-3 text-muted-foreground" />
        </div>
        <div className="mt-1 flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <span
            className={`size-1.5 rounded-full ${
              apiOnline && auth?.authorization === "PRESENT"
                ? "bg-muted-foreground/60"
                : "bg-rose-600 dark:bg-rose-400"
            }`}
          />
          <span className="truncate">{authLabel}</span>
        </div>
      </button>

      <DetailSheet
        open={open}
        onOpenChange={setOpen}
        title="Account & system"
        description="Verified competition paper account and read-only connection state. This dashboard exposes no order, approval or control actions."
      >
        <div className="space-y-2">
          <p className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
            Account
          </p>
          <KeyValue
            label="Account"
            value={account ? accountName(account.masked_id) : "Unavailable"}
            mono
          />
          <KeyValue
            label="Verification"
            value={
              account?.verified ? (
                <StatusPill tone="neutral">Fingerprint verified</StatusPill>
              ) : (
                <StatusPill tone="warning">Not verified</StatusPill>
              )
            }
          />
          <KeyValue label="Title" value={account?.title ?? "—"} />
          <KeyValue
            label="Provider classification"
            value={
              account
                ? `US simulated · type ${account.account_type ?? 2} · market ${account.market_id ?? 100}`
                : "—"
            }
          />
          <KeyValue
            label="Reconciliation"
            value={
              account ? (
                account.reconciled ? (
                  <StatusPill tone="neutral">Reconciled</StatusPill>
                ) : (
                  <StatusPill tone="warning">Attention required</StatusPill>
                )
              ) : (
                "—"
              )
            }
          />
          <KeyValue
            label="Unknown orders"
            value={account?.unknown_orders ?? "—"}
            mono
          />
          <KeyValue
            label="Snapshot"
            value={
              account?.as_of_utc ? (
                <span className="inline-flex items-center gap-2">
                  {utcTimestamp(account.as_of_utc)}
                  <Freshness seconds={account.age_seconds} />
                </span>
              ) : (
                "—"
              )
            }
          />
        </div>

        <div className="space-y-2">
          <p className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
            Connection
          </p>
          <KeyValue
            label="Dashboard API"
            value={
              apiOnline ? (
                <StatusPill tone="neutral">Connected</StatusPill>
              ) : (
                <StatusPill tone="danger" dot>
                  Offline
                </StatusPill>
              )
            }
          />
          <KeyValue label="Moomoo OAuth" value={authLabel} />
          <KeyValue
            label="Token expiry"
            value={auth?.expires_at_utc ? shortDateTime(auth.expires_at_utc) : "—"}
            mono
          />
          <KeyValue
            label="Trade scope"
            value={
              auth?.trade_write_granted ? (
                <StatusPill tone="danger">Granted</StatusPill>
              ) : (
                "Not granted"
              )
            }
          />
          <KeyValue
            label="Audit ledger"
            value={
              health.data?.database.available ? "Available" : "Unavailable"
            }
          />
        </div>

        <div className="space-y-2">
          <p className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
            Execution controls
          </p>
          <KeyValue
            label="Order writes"
            value={<StatusPill tone="neutral">Disabled</StatusPill>}
          />
          <KeyValue
            label="Kill switch"
            value={
              controls?.kill_switch_engaged ? (
                <StatusPill tone="neutral">Engaged</StatusPill>
              ) : (
                "Clear (persisted)"
              )
            }
          />
          <KeyValue
            label="First-order approval"
            value={
              controls && controls.first_order_approval_count > 0
                ? `Approved (${controls.first_order_approval_count})`
                : "Not granted"
            }
          />
          <KeyValue
            label="Order endpoint"
            value={controls?.broker_order_endpoint_available ? "Available" : "Disabled"}
          />
          <KeyValue
            label="Submissions recorded"
            value={
              controls
                ? `${controls.submission_count}${
                    controls.unknown_submissions ? " · unknown outcome" : ""
                  }`
                : "—"
            }
          />
        </div>

        <InfoNote tone="neutral">
          Internal identifiers, provider classifications and timestamps are shown
          here only. Normal views use the masked account and relative freshness.
        </InfoNote>
      </DetailSheet>
    </>
  )
}

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  return (
    <Sidebar variant="inset" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" render={<Link href="/dashboard" />}>
              <Image
                src="/moomoo.png"
                alt=""
                width={32}
                height={32}
                className="size-8 rounded-lg"
                priority
              />
              <span className="truncate text-sm font-semibold tracking-tight">
                MooTrade
              </span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={data.navTrading} label="Trading" />
        <NavMain items={data.navIntelligence} label="Intelligence" />
        <NavMain items={data.navSystem} label="System" />
      </SidebarContent>
      <SidebarFooter className="p-2">
        <AccountCard />
      </SidebarFooter>
    </Sidebar>
  )
}
