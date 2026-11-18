"use client"

import {
  AlertTriangleIcon,
  ArchiveIcon,
  CircleAlertIcon,
  CircleCheckIcon,
  Loader2Icon,
  RefreshCwIcon,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import { clockTime, type Provenance } from "@/lib/mootrade"

const provenanceConfig: Record<Provenance, { label: string; tone: string; dot: string }> = {
  LIVE_BROKER_READ: {
    label: "Broker-verified PAPER",
    tone: "text-emerald-700 dark:text-emerald-300",
    dot: "bg-emerald-500",
  },
  HISTORICAL_BACKTEST: {
    label: "Historical simulation",
    tone: "text-amber-700 dark:text-amber-300",
    dot: "bg-amber-500",
  },
  HISTORICAL_QODER_RUN: {
    label: "Historical Qoder run",
    tone: "text-amber-700 dark:text-amber-300",
    dot: "bg-amber-500",
  },
  CURRENT_MARKET_READ_ONLY: {
    label: "Current market · read only",
    tone: "text-emerald-700 dark:text-emerald-300",
    dot: "bg-emerald-500",
  },
  RECORDED_REAL_PREFLIGHT: {
    label: "Recorded real preflight",
    tone: "text-muted-foreground",
    dot: "bg-sky-500",
  },
  LOCAL_LEDGER: {
    label: "Local ledger",
    tone: "text-muted-foreground",
    dot: "bg-muted-foreground/60",
  },
  LOCAL_CONTROLS: {
    label: "Local controls",
    tone: "text-muted-foreground",
    dot: "bg-muted-foreground/60",
  },
}

export function ProvenanceBadge({
  value,
  className,
}: {
  value: Provenance
  className?: string
}) {
  const config = provenanceConfig[value]
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-[11px] font-medium",
        config.tone,
        className
      )}
    >
      <span className={cn("size-1.5 rounded-full", config.dot)} />
      {config.label}
    </span>
  )
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string
  description?: string
  actions?: React.ReactNode
}) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="space-y-1">
        <h1 className="text-[22px] font-semibold tracking-tight md:text-2xl">
          {title}
        </h1>
        {description ? (
          <p className="max-w-2xl text-[13px] leading-relaxed text-muted-foreground">
            {description}
          </p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  )
}

export function RefreshButton({
  onClick,
  refreshing,
  refreshedAt,
}: {
  onClick: () => void
  refreshing?: boolean
  refreshedAt?: Date | null
}) {
  return (
    <div className="flex items-center gap-2">
      {refreshedAt ? (
        <span
          className="hidden text-[11px] text-muted-foreground sm:inline"
          title="When this dashboard page fetched the API. This is not the broker data timestamp."
        >
          Page fetched {clockTime(refreshedAt)}
        </span>
      ) : null}
      <Button
        variant="ghost"
        size="sm"
        onClick={onClick}
        disabled={refreshing}
        className="h-8 gap-1.5 px-2 text-xs"
      >
        <RefreshCwIcon className={cn("size-3.5", refreshing && "animate-spin")} />
        Refresh
      </Button>
    </div>
  )
}

export function Metric({
  label,
  value,
  detail,
  tone = "neutral",
}: {
  label: string
  value: React.ReactNode
  detail?: React.ReactNode
  tone?: "neutral" | "positive" | "warning" | "danger"
}) {
  const toneClass = {
    neutral: "",
    positive: "text-emerald-600 dark:text-emerald-400",
    warning: "text-amber-600 dark:text-amber-400",
    danger: "text-rose-600 dark:text-rose-400",
  }[tone]
  return (
    <div className="bg-card px-4 py-3">
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className={cn("mt-1 text-xl font-semibold tabular-nums tracking-tight", toneClass)}>
        {value}
      </p>
      {detail ? (
        <div className="mt-0.5 text-[11px] leading-snug text-muted-foreground">{detail}</div>
      ) : null}
    </div>
  )
}

export function MetricStrip({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-4">
      {children}
    </div>
  )
}

export function SectionCard({
  title,
  description,
  action,
  children,
  className,
  contentClassName,
}: {
  title: string
  description?: string
  action?: React.ReactNode
  children: React.ReactNode
  className?: string
  contentClassName?: string
}) {
  return (
    <Card className={cn("gap-3 rounded-lg py-4", className)}>
      <CardHeader className="grid-cols-[1fr_auto] items-start gap-3 px-4">
        <div className="space-y-0.5">
          <CardTitle className="text-[13px] font-semibold">{title}</CardTitle>
          {description ? (
            <CardDescription className="text-[11px] leading-relaxed">
              {description}
            </CardDescription>
          ) : null}
        </div>
        {action}
      </CardHeader>
      <CardContent className={cn("px-4", contentClassName)}>{children}</CardContent>
    </Card>
  )
}

export function NoticeBanner({
  tone = "warning",
  title,
  children,
}: {
  tone?: "warning" | "info" | "danger" | "success"
  title: string
  children?: React.ReactNode
}) {
  const config = {
    warning: {
      className: "border-amber-500/25 bg-amber-500/[0.05] text-amber-900 dark:text-amber-100",
      icon: AlertTriangleIcon,
    },
    info: {
      className: "border-border bg-muted/40 text-foreground",
      icon: CircleAlertIcon,
    },
    danger: {
      className: "border-rose-500/25 bg-rose-500/[0.05] text-rose-900 dark:text-rose-100",
      icon: CircleAlertIcon,
    },
    success: {
      className: "border-emerald-500/25 bg-emerald-500/[0.05] text-emerald-900 dark:text-emerald-100",
      icon: CircleCheckIcon,
    },
  }[tone]
  const Icon = config.icon
  return (
    <div className={cn("flex gap-2.5 rounded-lg border px-3 py-2.5", config.className)}>
      <Icon className="mt-0.5 size-3.5 shrink-0" />
      <div className="space-y-0.5">
        <p className="text-xs font-semibold">{title}</p>
        {children ? (
          <div className="text-[11px] leading-relaxed opacity-85">{children}</div>
        ) : null}
      </div>
    </div>
  )
}

export function StatePanel({
  kind = "empty",
  title,
  description,
  action,
}: {
  kind?: "empty" | "error" | "unavailable"
  title: string
  description: string
  action?: React.ReactNode
}) {
  const Icon =
    kind === "error" ? CircleAlertIcon : kind === "unavailable" ? CircleAlertIcon : ArchiveIcon
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-4 py-10 text-center">
      <Icon className="size-4 text-muted-foreground/70" />
      <div className="max-w-md space-y-1">
        <p className="text-[13px] font-medium">{title}</p>
        <p className="text-[11px] leading-relaxed text-muted-foreground">{description}</p>
      </div>
      {action}
    </div>
  )
}

export function LoadingBlock({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, index) => (
        <Skeleton key={index} className="h-10 w-full" />
      ))}
    </div>
  )
}

export function LoadingPage() {
  return (
    <div className="space-y-5 p-4 md:p-6">
      <div className="space-y-2">
        <Skeleton className="h-7 w-48" />
        <Skeleton className="h-4 w-full max-w-lg" />
      </div>
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="bg-card px-4 py-3">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="mt-2 h-6 w-28" />
          </div>
        ))}
      </div>
      <Skeleton className="h-64 w-full rounded-lg" />
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-48 w-full rounded-lg" />
        <Skeleton className="h-48 w-full rounded-lg" />
      </div>
    </div>
  )
}

export function Spinner() {
  return <Loader2Icon className="size-4 animate-spin text-muted-foreground" />
}

export function KeyValue({
  label,
  value,
  mono,
}: {
  label: string
  value: React.ReactNode
  mono?: boolean
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b py-2 last:border-0">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <span
        className={cn(
          "max-w-[64%] text-right text-[11px] font-medium",
          mono && "font-mono tabular-nums"
        )}
      >
        {value}
      </span>
    </div>
  )
}

export function EmptyRow({
  colSpan,
  label,
  tone = "muted",
}: {
  colSpan: number
  label: string
  tone?: "muted" | "warning"
}) {
  return (
    <tr>
      <td
        colSpan={colSpan}
        className={cn(
          "px-3 py-4 text-[11px]",
          tone === "warning" ? "text-amber-700 dark:text-amber-300" : "text-muted-foreground"
        )}
      >
        {label}
      </td>
    </tr>
  )
}

export function TableShell({ children }: { children: React.ReactNode }) {
  return <div className="overflow-x-auto rounded-lg border">{children}</div>
}
