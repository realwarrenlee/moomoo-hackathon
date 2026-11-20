import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import {
  accountName,
  ageLabel,
  drawdownPercent,
  easternTimestamp,
  eventTone,
  grossExposurePct,
  humanEventName,
  humanState,
  investedValue,
  marketSession,
  money,
  outcomeLabel,
  outcomeTone,
  percent,
  ratioPercent,
  riskDecisionLabel,
  RISK_RULES,
  ruleLabel,
  shortDate,
  shortDateTime,
  utcTimestamp,
} from "./mootrade.ts"

test("ratioPercent converts a fractional return to percentage points", () => {
  assert.equal(ratioPercent(-0.0338749), "-3.39%")
  assert.equal(ratioPercent(0.0123), "1.23%")
  assert.equal(ratioPercent(null), "—")
})

test("recorded 5-day candidate returns render in percentage points", () => {
  const recorded = {
    IWM: "-0.0338749070829351173409790804",
    QQQ: "-0.0259071170972252888790755870",
    SPY: "-0.0169259588940998286147019357",
  }
  const rendered = Object.fromEntries(
    Object.entries(recorded).map(([symbol, value]) => [symbol, ratioPercent(Number(value))])
  )
  assert.deepEqual(rendered, {
    IWM: "-3.39%",
    QQQ: "-2.59%",
    SPY: "-1.69%",
  })
})

test("ratioPercent is not confused with already-scaled percent values", () => {
  assert.equal(percent(10), "10.00%")
  assert.notEqual(percent(-0.0338749), "-3.39%")
})

test("drawdownPercent always renders a loss magnitude as negative", () => {
  assert.equal(drawdownPercent(0.63), "-0.63%")
  assert.equal(drawdownPercent(-0.63), "-0.63%")
  assert.equal(drawdownPercent(0), "0.00%")
  assert.equal(drawdownPercent(undefined), "—")
})

test("shortDate does not shift date-only strings across timezones", () => {
  assert.equal(shortDate("2026-11-16"), "Nov 16, 26")
})

test("utcTimestamp labels broker data explicitly in UTC", () => {
  const rendered = utcTimestamp("2026-11-16T21:00:00Z")
  assert.match(rendered, /Nov 16, 2026/)
  assert.match(rendered, /UTC|GMT/)
})

test("ageLabel keeps large quote ages legible", () => {
  assert.equal(ageLabel(58150), "16.2h ago")
})

test("money always renders USD", () => {
  assert.equal(money("100000"), "$100,000.00")
})

test("easternTimestamp labels broker decisions in US Eastern time", () => {
  const rendered = easternTimestamp("2026-11-17T15:53:51Z")
  assert.match(rendered, /Nov 17, 2026/)
  assert.match(rendered, /10:53/)
  assert.match(rendered, /EST|EDT/)
})

test("humanState renders Moomoo US regular-session state unambiguously", () => {
  assert.equal(humanState("AFTERNOON"), "Regular session")
  assert.equal(humanState("PRE_MARKET_BEGIN"), "Pre-market")
  assert.equal(humanState("REJECT"), "Reject")
})

test("accountName masks the account number without repeating it", () => {
  assert.equal(accountName("****0101"), "····0101")
  assert.equal(accountName(null), "Competition account")
})

test("shortDateTime renders a compact UTC timestamp with an explicit zone", () => {
  assert.equal(shortDateTime("2026-11-18T06:56:39Z"), "Nov 18 · 06:56 UTC")
  assert.equal(shortDateTime(null), "—")
})

test("outcome labels and tones never present a policy rejection as success", () => {
  assert.equal(outcomeLabel("POLICY_REJECTED"), "Policy rejected")
  assert.equal(outcomeTone("POLICY_REJECTED"), "danger")
  assert.equal(outcomeTone("POLICY_APPROVAL"), "positive")
  assert.equal(outcomeTone("NO_TRADE"), "neutral")
})

test("risk rules and decisions use human labels", () => {
  assert.equal(ruleLabel("R007"), "Quote freshness")
  assert.equal(ruleLabel("R014"), "Approval or autonomous authorization")
  assert.equal(ruleLabel("R999"), "R999")
  assert.equal(riskDecisionLabel("REJECT"), "Rejected")
  assert.equal(riskDecisionLabel(null), "Not evaluated")
})

test("current rule catalogue is v2-only while historical rule labels remain readable", () => {
  assert.equal(RISK_RULES.R004, undefined)
  assert.equal(RISK_RULES.R005, undefined)
  assert.equal(ruleLabel("R004"), "Single-position exposure")
  assert.equal(ruleLabel("R005"), "Gross exposure")
  assert.equal(ruleLabel("R016"), "Minimum exposure floor")
  assert.equal(ruleLabel("R017"), "Maximum effective exposure")
  assert.equal(ruleLabel("R018"), "Declared target consistency")
})

test("risk page copy separates supervised permission from research and historical pins", () => {
  // Source-copy regression, not a browser-render test.
  const page = readFileSync(new URL("../app/(dashboard)/risk/page.tsx", import.meta.url), "utf8")
  assert.match(page, /\["R002"[^\n]+SPY\/SH only[^\n]+an AUTO_PAPER pin never widens this allowlist/)
  assert.match(page, /\["R013"[^\n]+at most 1 distinct position[^\n]+strategy separately permits only one/)
  assert.match(page, /\["R014"[^\n]+EVERY supervised BUY and SELL[^\n]+exact proposal and client order key/)
  assert.match(page, /\["R015"[^\n]+1x[^\n]+outside the universe and rejected regardless of size/)
  assert.match(page, /\["R016"[^\n]+10% strategy floor[^\n]+skipped in the supervised path[^\n]+R017 and R018 still apply/)
  assert.doesNotMatch(page, /First-order approval|initial paper order|Only symbols in the pinned/)
  assert.match(page, /Prepared supervised execution allowlist/)
  assert.match(page, /An active AUTO_PAPER pin authorises\r?\n\s+only the scheduled autonomous executor/)
})

test("audit event names are human-readable and tones stay semantic", () => {
  assert.equal(humanEventName("QODER_RUN_COMPLETED"), "Agent run completed")
  assert.equal(humanEventName("RISK_REJECTED"), "RiskGate rejected")
  assert.equal(eventTone("RISK_REJECTED"), "danger")
  assert.equal(eventTone("ORDER_UNKNOWN"), "warning")
  assert.equal(eventTone("RECONCILED"), "positive")
})

test("invested value and gross exposure derive from broker balances", () => {
  assert.equal(investedValue("100000", "92500"), 7500)
  assert.equal(investedValue("100000", "100000"), 0)
  assert.equal(investedValue(null, "100000"), null)
  assert.equal(grossExposurePct("100000", "92500"), 7.5)
  assert.equal(grossExposurePct("0", "0"), null)
})

test("marketSession distinguishes an open regular session from a closed market", () => {
  const quote = (overrides: { regular_session_open?: boolean; market_state?: string }) => ({
    symbol: "SPY",
    state: "CURRENT",
    provenance: "LIVE_BROKER_READ" as const,
    ...overrides,
  })
  assert.deepEqual(marketSession([quote({ regular_session_open: true })]), {
    open: true,
    label: "Regular session open",
  })
  assert.deepEqual(marketSession([quote({ market_state: "AFTER_HOURS" })]), {
    open: false,
    label: "After Hours",
  })
  assert.deepEqual(marketSession([]), { open: false, label: "Market closed" })
})
