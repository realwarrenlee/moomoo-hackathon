"use client"

import Image from "next/image"
import Link from "next/link"
import {
  BotIcon,
  ChartNoAxesCombinedIcon,
  GaugeIcon,
  ScrollTextIcon,
  ShieldCheckIcon,
  WalletCardsIcon,
} from "lucide-react"

import { NavMain } from "@/components/nav-main"
import { useDashboard } from "@/components/mootrade/use-dashboard"
import {
  Sidebar,
  SidebarContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import type { HealthResponse } from "@/lib/mootrade"

const data = {
  navTrading: [
    { title: "Overview", url: "/dashboard", icon: <GaugeIcon /> },
    { title: "Portfolio & Orders", url: "/portfolio", icon: <WalletCardsIcon /> },
    { title: "Risk Centre", url: "/risk", icon: <ShieldCheckIcon /> },
  ],
  navIntelligence: [
    { title: "AI Agent Activity", url: "/agents", icon: <BotIcon /> },
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

function SystemStatus() {
  const { data, error } = useDashboard<HealthResponse>("health", 60_000)
  const online = !error && data?.state === "OK"
  const auth = data?.auth.authorization
  return (
    <div className="rounded-lg border px-3 py-2.5">
      <p className="text-[11px] font-medium text-muted-foreground">System</p>
      <div className="mt-2 space-y-1 text-[11px]">
        <div className="flex items-center justify-between gap-2">
          <span className="text-muted-foreground">API</span>
          <span className="flex items-center gap-1.5 whitespace-nowrap font-medium">
            <span
              className={`size-1.5 rounded-full ${
                online ? "bg-emerald-500" : "bg-rose-500"
              }`}
            />
            {online ? "Connected" : "Offline"}
          </span>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-muted-foreground">Moomoo</span>
          <span className="whitespace-nowrap font-medium">
            {auth === "PRESENT" ? "Authorized" : auth === "AUTH_REQUIRED" ? "Sign-in needed" : "Unavailable"}
          </span>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-muted-foreground">Writes</span>
          <span className="whitespace-nowrap font-mono text-[10px] font-semibold text-rose-600 dark:text-rose-300">
            DISABLED
          </span>
        </div>
      </div>
    </div>
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
        <div className="mt-auto px-2 pb-2">
          <SystemStatus />
        </div>
      </SidebarContent>
    </Sidebar>
  )
}
