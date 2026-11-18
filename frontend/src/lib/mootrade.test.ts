import assert from "node:assert/strict"
import test from "node:test"

import {
  ageLabel,
  drawdownPercent,
  easternTimestamp,
  humanState,
  money,
  percent,
  ratioPercent,
  shortDate,
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
