export const DASHBOARD_REFRESH_EVENT = "mootrade:refresh"

export type Tone = "neutral" | "positive" | "warning" | "danger" | "info"

export type Provenance =
  | "LIVE_BROKER_READ"
  | "HISTORICAL_BACKTEST"
  | "HISTORICAL_QODER_RUN"
  | "CURRENT_MARKET_READ_ONLY"
  | "RECORDED_REAL_PREFLIGHT"
  | "LOCAL_LEDGER"
  | "LOCAL_CONTROLS"

export type ApiState =
  | "LIVE"
  | "STALE"
  | "PARTIAL"
  | "UNAVAILABLE"
  | "LOCKED"
  | "HISTORICAL"
  | "EMPTY"
  | "OK"

export type AccountView = {
  masked_id: string
  title?: string | null
  market_id?: number | null
  account_type?: number | null
  verified?: boolean | null
  equity?: string | null
  cash?: string | null
  buying_power?: string | null
  day_start_equity?: string | null
  peak_equity?: string | null
  positions_count?: number | null
  open_orders_count?: number | null
  reconciled?: boolean | null
  unknown_orders?: number | null
  gross_exposure_pct?: number | null
  effective_exposure_pct?: number | null
  as_of_utc?: string | null
  age_seconds?: number | null
  provenance: Provenance
}

export type QuoteView = {
  symbol: string
  state: string
  price?: string | null
  as_of_utc?: string | null
  age_seconds?: number | null
  fresh?: boolean | null
  stale?: boolean | null
  sec_status?: string | null
  suspended?: boolean | null
  market_state?: string | null
  regular_session_open?: boolean | null
  error?: string | null
  provenance: Provenance
}

export type SafetyView = {
  trading_mode: string
  order_writes_enabled: boolean
  kill_switch_engaged: boolean
  first_order_approval_count: number
  submission_count: number
  unknown_submissions: boolean
  broker_order_endpoint_available: boolean
  provenance: Provenance
}

export type AgentSummary = { role: string; text: string }

export type AgentCandidate = {
  symbol?: string | null
  direction?: number | null
  leverage?: string | null
  effective_exposure?: string | null
  close?: string | null
  eligible?: boolean | null
  selected?: boolean | null
  reasons: string[]
}

export type AgentProposal = {
  proposal_id?: string | null
  symbol?: string | null
  action?: string | null
  requested_quantity?: number | null
  thesis?: string | null
  invalidation?: string | null
}

export type AgentRiskDecision = {
  policy_version?: string | null
  decision?: string | null
  approved_quantity?: number | null
  reasons: { rule_id?: string | null; message?: string | null }[]
}

export type AgentRun = {
  run_id?: string | null
  mode: string
  strategy_version?: string | null
  status?: string | null
  outcome?: string | null
  notice?: string | null
  completed_at_utc?: string | null
  session_count: number
  decision_time_utc?: string | null
  data_as_of_utc?: string | null
  spy_session_date?: string | null
  spy_close?: string | null
  spy_return_10d?: string | null
  spy_sma50?: string | null
  spy_trend_pct?: string | null
  spy_volatility_20d?: string | null
  market_state?: string | null
  direction?: string | null
  target_symbol?: string | null
  target_effective_exposure?: string | null
  current_symbol?: string | null
  current_quantity?: number | null
  action?: string | null
  reentry_symbol?: string | null
  decision_reason?: string | null
  selected_symbol?: string | null
  proposal?: AgentProposal | null
  risk_decision?: AgentRiskDecision | null
  no_trade_reason?: string | null
  candidates: AgentCandidate[]
  summaries: AgentSummary[]
  data_collection?: {
    collected_at_utc?: string | null
    us_eastern_time?: string | null
    quotes: {
      symbol?: string | null
      data_time_utc?: string | null
      age_seconds?: number | null
      market_state?: string | null
    }[]
    account_as_of_utc?: string | null
    account_age_seconds?: number | null
    regular_session_required?: boolean | null
  } | null
  provenance: Provenance
}

export type OverviewResponse = {
  state: ApiState
  generated_at_utc: string
  mode: "PAPER"
  read_only: boolean
  account: AccountView | null
  quotes: QuoteView[]
  safety: SafetyView
  latest_agent_run: AgentRun | null
  warnings: string[]
}

export type PortfolioResponse = {
  state: ApiState
  generated_at_utc: string
  mode: "PAPER"
  read_only: boolean
  reason?: string | null
  account: {
    masked_id: string
    equity: string
    cash: string
    buying_power: string
    positions_count: number
    open_orders_count: number
    reconciled: boolean
    unknown_orders: number
    as_of_utc?: string | null
    age_seconds?: number | null
    provenance: Provenance
  } | null
  positions: {
    symbol: string
    quantity: number
    market_value: string
    provenance: Provenance
  }[]
  open_orders: {
    symbol: string
    side: string
    remaining_quantity: number
    reference_price: string
    provenance: Provenance
  }[]
  today_orders: OrderView[]
  history_orders: OrderView[]
  warnings: string[]
}

export type OrderView = {
  broker_order_id: string
  symbol: string
  side: string
  status: string
  quantity: number
  filled_quantity: number
  price: string
  average_fill_price: string
  created_at_utc?: string | null
  updated_at_utc?: string | null
  remark: string
  provenance: Provenance
}

export type PreflightView = {
  kind?: string | null
  mode?: string | null
  checked_at_utc?: string | null
  decision?: string | null
  rejection_rule_ids: string[]
  reasons: string[]
  submission_performed?: boolean | null
  order_endpoint_contacted?: boolean | null
  scope_trade_write?: boolean | null
  quotes: {
    symbol: string
    last_price?: number | null
    data_time_utc?: string | null
    age_seconds?: number | null
    sec_status?: string | null
    suspension?: boolean | null
    market_state?: string | null
  }[]
  provenance: Provenance
}

export type RiskResponse = {
  state: ApiState
  generated_at_utc: string
  mode: "PAPER"
  read_only: boolean
  policy_version: string
  limits: {
    max_single_exposure_pct?: number | null
    max_total_exposure_pct?: number | null
    min_effective_exposure_pct?: number | null
    max_effective_exposure_pct?: number | null
    max_leverage?: number | null
    max_open_positions: number
    max_daily_drawdown_pct: number
    max_quote_age_seconds: number
    max_account_age_seconds: number
    buying_power_buffer_usd: number
  }
  allowed_symbols?: string[] | null
  controls: SafetyView
  execution_locked: boolean
  lock_reasons: string[]
  account: AccountView | null
  quotes: QuoteView[]
  last_real_preflight: PreflightView | null
  warnings: string[]
}

export type AgentsResponse = {
  state: ApiState
  generated_at_utc: string
  mode: "PAPER"
  read_only: boolean
  notice: string
  runs: AgentRun[]
}

export type CurvePoint = { date: string; value: number }
export type Curve = { key: string; label: string; points: CurvePoint[] }

export type MetricRow = {
  strategy: string
  label: string
  period: string
  total_return_pct?: number | null
  max_drawdown_pct?: number | null
  annualized_volatility_pct?: number | null
  sharpe?: number | null
  trades?: number | null
  exposure_pct?: number | null
  provenance: Provenance
}

export type AnalyticsDataset = {
  id: string
  label: string
  version?: string | null
  period: Record<string, string>
  generated_at_utc?: string | null
  curves: Curve[]
  metrics: MetricRow[]
  limitations: string[]
  provenance: Provenance
}

export type AnalyticsResponse = {
  state: ApiState
  generated_at_utc: string
  mode: "PAPER"
  read_only: boolean
  notice: string
  paper_account_performance: {
    available: boolean
    reason: string
    provenance: Provenance
  }
  datasets: AnalyticsDataset[]
}

export type AuditEvent = {
  event_id?: string | null
  occurred_at_utc?: string | null
  event_type?: string | null
  source?: string | null
  run_id?: string | null
  correlation_id?: string | null
  summary: string
  provenance: Provenance
}

export type AuditResponse = {
  state: ApiState
  generated_at_utc: string
  mode: "PAPER"
  read_only: boolean
  counts: {
    events: number
    submissions: number
    unknown_submissions: boolean
  }
  events: AuditEvent[]
  notice: string
}

export type HealthResponse = {
  state: ApiState
  generated_at_utc: string
  mode: "PAPER"
  read_only: boolean
  trading_mode: string
  order_writes_enabled: boolean
  auth: {
    authorization: string
    reason?: string | null
    trade_write_granted?: boolean | null
    account_lock_configured: boolean
    expires_at_utc?: string | null
  }
  database: { available: boolean; provenance: Provenance }
}

export class DashboardFetchError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = "DashboardFetchError"
    this.status = status
  }
}

export async function fetchDashboard<T>(path: string): Promise<T> {
  const response = await fetch(`/api/mootrade/${path}`, {
    cache: "no-store",
    headers: { Accept: "application/json" },
  })
  if (!response.ok) {
    let detail = `Dashboard API returned ${response.status}`
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === "string") detail = body.detail
    } catch {
      // Keep the status-based message.
    }
    throw new DashboardFetchError(detail, response.status)
  }
  return (await response.json()) as T
}

export function money(value?: string | number | null, digits = 2): string {
  if (value === null || value === undefined || value === "") return "—"
  const number = typeof value === "number" ? value : Number(value)
  if (!Number.isFinite(number)) return "—"
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(number)
}

export function percent(value?: number | null, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—"
  return `${value.toFixed(digits)}%`
}

export function ratioPercent(value?: number | null, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—"
  return `${(value * 100).toFixed(digits)}%`
}

export function drawdownPercent(value?: number | null, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—"
  if (value === 0) return `${(0).toFixed(digits)}%`
  return `-${Math.abs(value).toFixed(digits)}%`
}

export function signedPercent(value?: number | null, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—"
  const prefix = value > 0 ? "+" : ""
  return `${prefix}${value.toFixed(digits)}%`
}

export function ageLabel(seconds?: number | null): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "—"
  if (seconds < 90) return `${Math.round(seconds)}s ago`
  if (seconds < 5400) return `${Math.round(seconds / 60)}m ago`
  if (seconds < 172800) return `${(seconds / 3600).toFixed(1)}h ago`
  return `${(seconds / 86400).toFixed(1)}d ago`
}

export function timestamp(value?: string | null): string {
  if (!value) return "—"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "—"
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(date)
}

export function utcTimestamp(value?: string | null): string {
  if (!value) return "—"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "—"
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
    timeZoneName: "short",
  }).format(date)
}

export function easternTimestamp(value?: string | null): string {
  if (!value) return "—"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "—"
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "America/New_York",
    timeZoneName: "short",
  }).format(date)
}

export function clockTime(date: Date): string {
  return new Intl.DateTimeFormat("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZoneName: "short",
  }).format(date)
}

function parseDateOnly(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (!match) return null
  return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])))
}

export function shortDate(value?: string | null): string {
  if (!value) return "—"
  const dateOnly = parseDateOnly(value)
  const date = dateOnly ?? new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "2-digit",
    ...(dateOnly ? { timeZone: "UTC" } : {}),
  }).format(date)
}

export function shortMonthDay(value?: string | null): string {
  if (!value) return "—"
  const dateOnly = parseDateOnly(value)
  const date = dateOnly ?? new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    ...(dateOnly ? { timeZone: "UTC" } : {}),
  }).format(date)
}

const MARKET_STATE_LABELS: Record<string, string> = {
  AFTERNOON: "Regular session",
  MORNING: "Regular session",
  PRE_MARKET_BEGIN: "Pre-market",
  PRE_MARKET_END: "Pre-market closed",
  AFTER_HOURS_BEGIN: "After hours",
  AFTER_HOURS_END: "After hours closed",
}

export function humanState(value?: string | null): string {
  if (!value) return "Unknown"
  if (MARKET_STATE_LABELS[value]) return MARKET_STATE_LABELS[value]
  return value
    .split("_")
    .map((word) => word.charAt(0) + word.slice(1).toLowerCase())
    .join(" ")
}

export function compactId(value?: string | null, head = 10, tail = 6): string {
  if (!value) return "—"
  if (value.length <= head + tail + 1) return value
  return `${value.slice(0, head)}…${value.slice(-tail)}`
}

export function strategyLabel(value?: string | null): string {
  return value || "—"
}

export function shortDateTime(value?: string | null): string {
  if (!value) return "—"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "—"
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
    hour12: false,
    timeZoneName: "short",
  })
    .format(date)
    .replace(",", " ·")
}

export function accountName(maskedId?: string | null): string {
  if (!maskedId) return "Competition account"
  return maskedId.replace(/^\*+/, "····")
}

const OUTCOME_LABELS: Record<string, string> = {
  POLICY_REJECTED: "Policy rejected",
  POLICY_APPROVAL: "Policy approved",
  HISTORICAL_POLICY_APPROVAL: "Policy approved",
  NO_TRADE: "No trade",
  AGENT_ERROR: "Agent error",
  COMPLETED: "Completed",
}

export function outcomeLabel(value?: string | null): string {
  if (!value) return "No decision"
  return OUTCOME_LABELS[value] ?? humanState(value)
}

export function outcomeTone(value?: string | null): Tone {
  switch (value) {
    case "POLICY_APPROVAL":
    case "HISTORICAL_POLICY_APPROVAL":
      return "positive"
    case "POLICY_REJECTED":
      return "danger"
    case "AGENT_ERROR":
      return "danger"
    default:
      return "neutral"
  }
}

export const RISK_RULES: Record<string, string> = {
  R001: "Account verification",
  R002: "Execution allowlist",
  R003: "No short positions",
  R004: "Single-position exposure",
  R005: "Gross exposure",
  R006: "Daily drawdown stop",
  R007: "Quote freshness",
  R008: "Cash-only buying power",
  R009: "Reconciled broker state",
  R010: "Order control state",
  R011: "Duplicate submission",
  R012: "Regular trading session",
  R013: "Position count",
  R014: "First-order approval",
  R015: "Leverage limit",
  R016: "Minimum exposure floor",
  R017: "Maximum effective exposure",
  R018: "Declared target consistency",
}

export function ruleLabel(ruleId?: string | null): string {
  if (!ruleId) return "Rule"
  return RISK_RULES[ruleId] ?? ruleId
}

export function riskDecisionLabel(decision?: string | null): string {
  if (!decision) return "Not evaluated"
  const normalized = decision.toUpperCase()
  if (normalized === "APPROVE" || normalized === "APPROVED") return "Approved"
  if (normalized === "REJECT" || normalized === "REJECTED") return "Rejected"
  return humanState(decision)
}

const EVENT_LABELS: Record<string, string> = {
  QODER_RUN_STARTED: "Agent run started",
  QODER_RUN_COMPLETED: "Agent run completed",
  QODER_TOOL_RESULT: "Agent tool result",
  RISK_APPROVED: "RiskGate approved",
  RISK_REJECTED: "RiskGate rejected",
  ORDER_SUBMITTED: "Order submitted",
  ORDER_REJECTED: "Order rejected",
  ORDER_FILLED: "Order filled",
  ORDER_CANCELLED: "Order cancelled",
  ORDER_UNKNOWN: "Order outcome unknown",
  FILL_RECORDED: "Fill recorded",
  RECONCILED: "Broker state reconciled",
  RECONCILIATION_MISMATCH: "Reconciliation mismatch",
  KILL_SWITCH_ENGAGED: "Kill switch engaged",
  KILL_SWITCH_CLEARED: "Kill switch cleared",
  FIRST_ORDER_APPROVED: "First order approved",
}

export function humanEventName(eventType?: string | null): string {
  if (!eventType) return "Event"
  return EVENT_LABELS[eventType] ?? humanState(eventType)
}

export function eventTone(eventType?: string | null): Tone {
  if (!eventType) return "neutral"
  if (eventType.includes("REJECT") || eventType.includes("BLOCKED") || eventType.includes("MISMATCH"))
    return "danger"
  if (eventType.includes("UNKNOWN")) return "warning"
  if (eventType.startsWith("ORDER_") || eventType.startsWith("FILL_")) return "info"
  if (eventType.startsWith("QODER_")) return "info"
  if (eventType.includes("APPROVED") || eventType.includes("CONFIRMED") || eventType.includes("RECONCILED"))
    return "positive"
  return "neutral"
}

export function investedValue(
  equity?: string | null,
  cash?: string | null
): number | null {
  if (equity === null || equity === undefined || cash === null || cash === undefined)
    return null
  const equityNumber = Number(equity)
  const cashNumber = Number(cash)
  if (!Number.isFinite(equityNumber) || !Number.isFinite(cashNumber)) return null
  return Math.max(0, equityNumber - cashNumber)
}

export function grossExposurePct(
  equity?: string | null,
  cash?: string | null
): number | null {
  const invested = investedValue(equity, cash)
  const equityNumber = Number(equity)
  if (invested === null || !Number.isFinite(equityNumber) || equityNumber <= 0)
    return null
  return (invested / equityNumber) * 100
}

export function marketSession(quotes: QuoteView[]): { open: boolean; label: string } {
  if (quotes.some((quote) => quote.regular_session_open)) {
    return { open: true, label: "Regular session open" }
  }
  const state = quotes.find((quote) => quote.market_state)?.market_state
  return { open: false, label: state ? humanState(state) : "Market closed" }
}
