"use client"

import Link from "next/link"
import {
  ArchiveIcon,
  ArrowRightIcon,
  CircleAlertIcon,
  InfoIcon,
  Loader2Icon,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import type { Tone } from "@/lib/mootrade"

export const toneStyles: Record<
  Tone,
  { pill: string; dot: string; text: string; bar: string }
> = {
  neutral: {
    pill: "border-border bg-muted/40 text-muted-foreground",
    dot: "bg-muted-foreground/70",
    text: "text-muted-foreground",
    bar: "bg-muted-foreground/60",
  },
  positive: {
    pill: "border-border bg-transparent text-emerald-700 dark:text-emerald-300",
    dot: "bg-emerald-600 dark:bg-emerald-400",
    text: "text-emerald-700 dark:text-emerald-300",
    bar: "bg-emerald-600 dark:bg-emerald-400",
  },
  warning: {
    pill: "border-border bg-transparent text-amber-700 dark:text-amber-300",
    dot: "bg-amber-600 dark:bg-amber-400",
    text: "text-amber-700 dark:text-amber-300",
    bar: "bg-amber-600 dark:bg-amber-400",
  },
  danger: {
    pill: "border-border bg-transparent text-rose-700 dark:text-rose-300",
    dot: "bg-rose-600 dark:bg-rose-400",
    text: "text-rose-700 dark:text-rose-300",
    bar: "bg-rose-600 dark:bg-rose-400",
  },
  info: {
    pill: "border-border bg-muted/20 text-muted-foreground",
    dot: "bg-muted-foreground/60",
    text: "text-muted-foreground",
    bar: "bg-muted-foreground/60",
  },
}

export function StatusPill({
  tone = "neutral",
  dot = false,
  className,
  children,
}: {
  tone?: Tone
  dot?: boolean
  className?: string
  children: React.ReactNode
}) {
  const styles = toneStyles[tone]
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-md border px-1.5 py-0.5 text-[11px] font-medium whitespace-nowrap",
        styles.pill,
        className
      )}
    >
      {dot ? <span className={cn("size-1.5 rounded-full", styles.dot)} /> : null}
      {children}
    </span>
  )
}

export function PageContainer({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        "mx-auto w-full max-w-[1440px] space-y-5 px-4 py-5 md:px-6 md:py-6",
        className
      )}
    >
      {children}
    </div>
  )
}

export function PageHeader({
  title,
  description,
  meta,
  actions,
}: {
  title: string
  description?: React.ReactNode
  meta?: React.ReactNode
  actions?: React.ReactNode
}) {
  return (
    <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
          {meta}
        </div>
        {description ? (
          <p className="max-w-3xl text-[13px] leading-relaxed text-muted-foreground">
            {description}
          </p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex shrink-0 items-center gap-2">{actions}</div>
      ) : null}
    </header>
  )
}

export function Section({
  title,
  description,
  action,
  children,
  className,
  bodyClassName,
  flush = false,
}: {
  title?: string
  description?: React.ReactNode
  action?: React.ReactNode
  children: React.ReactNode
  className?: string
  bodyClassName?: string
  flush?: boolean
}) {
  return (
    <section className={cn("overflow-hidden rounded-xl border bg-card", className)}>
      {title || action ? (
        <div className="flex items-start justify-between gap-3 border-b px-4 py-3">
          <div className="min-w-0 space-y-0.5">
            {title ? (
              <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
            ) : null}
            {description ? (
              <p className="text-xs leading-relaxed text-muted-foreground">
                {description}
              </p>
            ) : null}
          </div>
          {action ? <div className="shrink-0">{action}</div> : null}
        </div>
      ) : null}
      <div className={cn(flush ? "p-0" : "p-4", bodyClassName)}>{children}</div>
    </section>
  )
}

export function TableShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[13px] [&_tbody_tr:last-child_td]:border-b-0">
        {children}
      </table>
    </div>
  )
}

export function Th({
  children,
  align = "left",
  className,
}: {
  children?: React.ReactNode
  align?: "left" | "right" | "center"
  className?: string
}) {
  return (
    <th
      scope="col"
      className={cn(
        "border-b px-4 py-2.5 text-xs font-medium whitespace-nowrap text-muted-foreground",
        align === "right" && "text-right",
        align === "center" && "text-center",
        className
      )}
    >
      {children}
    </th>
  )
}

export function Td({
  children,
  align = "left",
  className,
}: {
  children?: React.ReactNode
  align?: "left" | "right" | "center"
  className?: string
}) {
  return (
    <td
      className={cn(
        "border-b px-4 py-2.5 align-middle",
        align === "right" && "text-right",
        align === "center" && "text-center",
        className
      )}
    >
      {children}
    </td>
  )
}

export function EmptyRow({
  colSpan,
  children,
}: {
  colSpan: number
  children: React.ReactNode
}) {
  return (
    <tr>
      <td
        colSpan={colSpan}
        className="px-4 py-5 text-[13px] text-muted-foreground"
      >
        {children}
      </td>
    </tr>
  )
}

export function Stat({
  label,
  value,
  hint,
  tone = "neutral",
  className,
}: {
  label: string
  value: React.ReactNode
  hint?: React.ReactNode
  tone?: Tone
  className?: string
}) {
  return (
    <div className={cn("bg-card px-4 py-3.5", className)}>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p
        className={cn(
          "mt-1 text-[22px] leading-tight font-semibold tracking-tight tabular-nums",
          tone !== "neutral" ? toneStyles[tone].text : "text-foreground"
        )}
      >
        {value}
      </p>
      {hint ? (
        <p className="mt-0.5 text-xs leading-snug text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  )
}

export function StatGrid({
  children,
  className,
  columns = 4,
}: {
  children: React.ReactNode
  className?: string
  columns?: 3 | 4
}) {
  return (
    <div
      className={cn(
        "grid grid-cols-2 gap-px overflow-hidden rounded-xl border bg-border",
        columns === 3 ? "sm:grid-cols-3" : "sm:grid-cols-4",
        className
      )}
    >
      {children}
    </div>
  )
}

export function Meter({
  label,
  value,
  display,
  tone = "neutral",
  hint,
}: {
  label: string
  value: number | null
  display: React.ReactNode
  tone?: Tone
  hint?: React.ReactNode
}) {
  const width = value === null ? 0 : Math.max(0, Math.min(100, value))
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-[13px] font-semibold tabular-nums">{display}</p>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
        <div
          className={cn("h-full rounded-full", toneStyles[tone].bar)}
          style={{ width: `${width}%` }}
        />
      </div>
      {hint ? <p className="text-[11px] text-muted-foreground">{hint}</p> : null}
    </div>
  )
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
    <div className="flex items-start justify-between gap-4 border-b py-2 text-[13px] last:border-b-0">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span
        className={cn(
          "min-w-0 text-right font-medium break-words",
          mono && "font-mono text-xs tabular-nums"
        )}
      >
        {value}
      </span>
    </div>
  )
}

export function InfoNote({
  tone = "info",
  icon,
  children,
  className,
}: {
  tone?: Tone
  icon?: React.ReactNode
  children: React.ReactNode
  className?: string
}) {
  const styles = toneStyles[tone]
  const StatusIcon = tone === "danger" || tone === "warning" ? CircleAlertIcon : InfoIcon
  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded-lg border bg-muted/20 px-3 py-2 text-xs leading-relaxed",
        className
      )}
    >
      <span className={cn("mt-0.5 shrink-0", styles.text)}>
        {icon ?? <StatusIcon className="size-3.5" />}
      </span>
      <div className="min-w-0 space-y-1">{children}</div>
    </div>
  )
}

export function Freshness({
  seconds,
  stale,
  className,
}: {
  seconds?: number | null
  stale?: boolean | null
  className?: string
}) {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) {
    return <span className={cn("text-xs text-muted-foreground", className)}>—</span>
  }
  const label =
    seconds < 90
      ? `${Math.round(seconds)}s old`
      : seconds < 5400
        ? `${Math.round(seconds / 60)}m old`
        : seconds < 172800
          ? `${(seconds / 3600).toFixed(1)}h old`
          : `${(seconds / 86400).toFixed(1)}d old`
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-xs whitespace-nowrap",
        stale
          ? "text-amber-600 dark:text-amber-400"
          : "text-muted-foreground",
        className
      )}
    >
      {stale ? <span className="size-1.5 rounded-full bg-amber-500" /> : null}
      {label}
    </span>
  )
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  className,
}: {
  options: { value: T; label: React.ReactNode }[]
  value: T
  onChange: (value: T) => void
  className?: string
}) {
  return (
    <div
      className={cn(
        "inline-flex items-center gap-0.5 rounded-lg border bg-muted/40 p-0.5",
        className
      )}
    >
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          aria-pressed={option.value === value}
          className={cn(
            "rounded-md px-2.5 py-1 text-xs font-medium whitespace-nowrap transition-colors",
            option.value === value
              ? "bg-background text-foreground shadow-xs"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

export function InlineLink({
  href,
  children,
}: {
  href: string
  children: React.ReactNode
}) {
  return (
    <Button
      variant="ghost"
      size="sm"
      className="-ml-2 h-7 gap-1 px-2 text-xs text-muted-foreground hover:text-foreground"
      render={<Link href={href} />}
      nativeButton={false}
    >
      {children}
      <ArrowRightIcon className="size-3" />
    </Button>
  )
}

export function DetailSheet({
  open,
  onOpenChange,
  title,
  description,
  children,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full gap-0 overflow-y-auto p-0 sm:max-w-lg">
        <SheetHeader className="border-b p-5 pr-12">
          <SheetTitle>{title}</SheetTitle>
          {description ? (
            <SheetDescription className="text-xs leading-relaxed">
              {description}
            </SheetDescription>
          ) : null}
        </SheetHeader>
        <div className="space-y-5 p-5">{children}</div>
      </SheetContent>
    </Sheet>
  )
}

export function PageState({
  title,
  description,
  onRetry,
  kind = "error",
}: {
  title: string
  description: string
  onRetry?: () => void
  kind?: "error" | "empty"
}) {
  const Icon = kind === "error" ? CircleAlertIcon : ArchiveIcon
  return (
    <div className="flex items-start gap-3 rounded-xl border bg-card p-4">
      <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
      <div className="min-w-0 space-y-1">
        <p className="text-sm font-medium">{title}</p>
        <p className="text-xs leading-relaxed text-muted-foreground">{description}</p>
        {onRetry ? (
          <Button variant="outline" size="sm" className="mt-2" onClick={onRetry}>
            Try again
          </Button>
        ) : null}
      </div>
    </div>
  )
}

export function LoadingPage() {
  return (
    <PageContainer>
      <div className="space-y-2">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-3.5 w-72" />
      </div>
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border bg-border sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="bg-card px-4 py-3.5">
            <Skeleton className="h-3 w-16" />
            <Skeleton className="mt-2 h-6 w-24" />
          </div>
        ))}
      </div>
      <Skeleton className="h-64 w-full rounded-xl" />
      <Skeleton className="h-40 w-full rounded-xl" />
    </PageContainer>
  )
}

export function Spinner() {
  return <Loader2Icon className="size-4 animate-spin text-muted-foreground" />
}
