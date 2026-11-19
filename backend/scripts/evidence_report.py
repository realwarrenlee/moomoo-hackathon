"""Read-only sanitized competition evidence summary.

Aggregates existing local artifacts (SQLite ledger, Qoder run reports,
preflight/execution records, scheduler state, daily-bar snapshots and
historical research results) into one Markdown summary with explicit
PAPER / HISTORICAL provenance. Never contacts a broker, never prints
credentials or account fingerprints, and refuses to run while
ORDER_WRITES_ENABLED is true.

Usage:
    python -m scripts.evidence_report            # print to stdout
    python -m scripts.evidence_report --output evidence/sample-reports/summary.md
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EVIDENCE = REPO_ROOT / "evidence"
DATA = REPO_ROOT / "data"

MISSING = "not available"


def _refuse_writes() -> None:
    value = os.environ.get("ORDER_WRITES_ENABLED", "false").strip().lower()
    if value == "true":
        raise SystemExit(
            "evidence_report refuses to run with ORDER_WRITES_ENABLED=true"
        )


def _resolve_db(path: str | None) -> Path:
    if path:
        db = Path(path)
    else:
        raw = os.environ.get("DATABASE_URL", "")
        db = Path(raw.removeprefix("sqlite:///")) if raw.startswith("sqlite:///") else DATA / "mootrade.db"
    return db if db.is_absolute() else REPO_ROOT / db


def ledger_section(db: Path) -> str:
    if not db.exists():
        return f"- Ledger database `{db}` is {MISSING}; no local audit events.\n"
    connection = sqlite3.connect(db)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        lines: list[str] = []
        if "events" in tables:
            count = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            lines.append(f"- Audit events: {count}")
            rows = connection.execute(
                "SELECT event_type, COUNT(*) FROM events GROUP BY event_type ORDER BY 2 DESC, 1"
            ).fetchall()
            lines.append(
                "  " + "; ".join(f"{name}={n}" for name, n in rows)
                if rows
                else "  (no events)"
            )
        if "submissions" in tables:
            total = connection.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
            unknown = connection.execute(
                "SELECT COUNT(*) FROM submissions WHERE status='UNKNOWN'"
            ).fetchone()[0]
            lines.append(f"- Order submissions: {total} (UNKNOWN: {unknown})")
        if "order_approvals" in tables:
            approvals = connection.execute("SELECT COUNT(*) FROM order_approvals").fetchone()[0]
            lines.append(f"- Durable first-order approvals: {approvals}")
        if "controls" in tables:
            row = connection.execute(
                "SELECT value FROM controls WHERE name='kill_switch'"
            ).fetchone()
            engaged = bool(row and row[0])
            lines.append(f"- Kill switch: {'ENGAGED' if engaged else 'disengaged'}")
        if "equity_days" in tables:
            days = connection.execute("SELECT COUNT(*) FROM equity_days").fetchone()[0]
            lines.append(f"- Equity baseline days recorded: {days}")
        if not lines:
            lines.append(f"- Ledger database `{db}` exists but contains no recognised tables.")
        return "\n".join(lines) + "\n"
    finally:
        connection.close()


def qoder_section() -> str:
    artifacts = sorted(EVIDENCE.glob("qoder/qoder-*.json"))
    if not artifacts:
        return "- No Qoder run artifacts found under `evidence/qoder/`.\n"
    lines = ["| Run id | Mode | Strategy | Status | Outcome | Completed (UTC) |", "|---|---|---|---|---|---|"]
    for path in artifacts:
        try:
            run = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            lines.append(f"| `{path.stem}` | unreadable artifact | — | — | — | — |")
            continue
        completed = (run.get("completed_at_utc") or "")[:16].replace("T", " ")
        lines.append(
            "| `{id}` | {mode} | {strategy} | {status} | {outcome} | {completed} |".format(
                id=run.get("run_id", path.stem),
                mode=run.get("mode", MISSING),
                strategy=run.get("strategy_version", MISSING),
                status=run.get("status", MISSING),
                outcome=run.get("outcome", MISSING),
                completed=completed or MISSING,
            )
        )
    return "\n".join(lines) + "\n"


def preflight_section() -> str:
    artifacts = sorted(EVIDENCE.glob("preflight/preflight-*.json"))
    if not artifacts:
        return "- No preflight artifacts under `evidence/preflight/`.\n"
    lines = [
        "| Artifact | Checked (UTC) | Risk decision | Submission performed | Order endpoint contacted |",
        "|---|---|---|---|---|",
    ]
    for path in artifacts:
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        diagnostic = item.get("diagnostic_risk_evaluation") or {}
        preview = item.get("diagnostic_preview") or {}
        safety = item.get("safety") or {}
        lines.append(
            "| `{name}` | {checked} | {decision} | {submitted} | {contacted} |".format(
                name=path.name,
                checked=(item.get("checked_at_utc") or MISSING)[:16].replace("T", " "),
                decision=(diagnostic.get("decision") or item.get("decision") or MISSING),
                submitted=preview.get("submission_performed", safety.get("submission_performed", MISSING)),
                contacted=safety.get("order_endpoint_contacted", MISSING),
            )
        )
    return "\n".join(lines) + "\n"


def execution_section() -> str:
    artifacts = sorted(EVIDENCE.glob("execution/*.json"))
    if not artifacts:
        return "- No execution artifacts under `evidence/execution/`.\n"
    lines = ["| Artifact | Decision | Submission performed | Order endpoint contacted |", "|---|---|---|---|"]
    for path in artifacts:
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        safety = item.get("safety") or {}
        lines.append(
            "| `{name}` | {decision} | {submitted} | {contacted} |".format(
                name=path.name,
                decision=item.get("decision", MISSING),
                submitted=safety.get("submission_performed", item.get("submission_performed", MISSING)),
                contacted=safety.get("order_endpoint_contacted", item.get("order_endpoint_contacted", MISSING)),
            )
        )
    return "\n".join(lines) + "\n"


def market_data_section() -> str:
    snapshots = sorted(EVIDENCE.glob("current-market/*/daily-bars.json"))
    if not snapshots:
        return "- No daily-bar snapshots under `evidence/current-market/`.\n"
    latest = snapshots[-1]
    try:
        bars = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return f"- Latest snapshot `{latest}` is unreadable.\n"
    symbols = bars.get("symbols") if isinstance(bars, dict) else None
    lines = [
        f"- Latest snapshot: `{latest.relative_to(REPO_ROOT).as_posix()}`",
    ]
    if isinstance(symbols, dict):
        lines.append(f"  bars per symbol: {', '.join(f'{s}={len(v)}' for s, v in sorted(symbols.items()))}")
    for key in ("fetched_at_utc", "last_completed_session"):
        if isinstance(bars, dict) and bars.get(key):
            lines.append(f"  {key}: {bars[key]}")
    return "\n".join(lines) + "\n"


def scheduler_section() -> str:
    lines: list[str] = []
    state = DATA / "readonly_schedule.json"
    if state.exists():
        try:
            payload = json.loads(state.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        history = payload.get("history", []) if isinstance(payload, dict) else []
        lines.append(f"- Scheduler run history entries: {len(history)}")
        for entry in history[-3:]:
            lines.append(
                "  {key} | {status} | {outcome} | writes={writes} | catch_up={catch}".format(
                    key=entry.get("run_key", MISSING),
                    status=entry.get("status", MISSING),
                    outcome=entry.get("outcome", MISSING),
                    writes=entry.get("order_writes_enabled", MISSING),
                    catch=entry.get("catch_up", MISSING),
                )
            )
    else:
        lines.append(f"- Scheduler state `{state}` is {MISSING}.")
    events = DATA / "scheduler-events.jsonl"
    if events.exists():
        lines.append(f"- Scheduler event lines: {sum(1 for _ in events.open(encoding='utf-8'))}")
    else:
        lines.append(f"- Scheduler event log `{events}` is {MISSING}.")
    return "\n".join(lines) + "\n"


def _metric_keys(mapping: dict) -> list[str]:
    return [k for k in mapping if "return" in k or "drawdown" in k]


def research_section() -> str:
    studies = sorted(EVIDENCE.glob("research/*"))
    if not studies:
        return "- No historical research studies under `evidence/research/`.\n"
    lines: list[str] = []
    for folder in studies:
        if not folder.is_dir():
            continue
        results = folder / "results.json"
        if not results.exists():
            lines.append(f"- `{folder.name}`: no `results.json`; see raw artifacts in the folder.")
            continue
        try:
            item = json.loads(results.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            lines.append(f"- `{folder.name}`: unreadable `results.json`.")
            continue
        version = item.get("strategy_version") or item.get("baseline_version") or folder.name
        period = item.get("period")
        span = f"{period.get('start')} to {period.get('end')}" if isinstance(period, dict) else None
        if span is None:
            for key, value in item.items():
                if key.endswith("metrics") and isinstance(value, dict) and value.get("start_date"):
                    span = f"{value.get('start_date')} to {value.get('end_date')}"
                    break
        head = f"- `{version}` ({span or 'period not recorded'}):"
        comparison = item.get("comparison")
        if isinstance(comparison, dict):
            metrics = ", ".join(f"{k}={v}" for k, v in comparison.items() if k in _metric_keys(comparison))
            head += f" comparison[{metrics}]" if metrics else ""
        series: list[str] = []
        for key, value in item.items():
            if not isinstance(value, dict):
                continue
            if key.endswith("metrics"):
                parts = [f"{k}={v}" for k, v in value.items() if k in _metric_keys(value)]
                if parts:
                    series.append(f"{key}({', '.join(parts)})")
        results_map = item.get("results")
        if isinstance(results_map, dict):
            for name, result in results_map.items():
                if not isinstance(result, dict):
                    continue
                metrics = result.get("metrics")
                if isinstance(metrics, dict):
                    parts = [f"{k}={v}" for k, v in metrics.items() if k in _metric_keys(metrics)]
                    if parts:
                        series.append(f"{name}({', '.join(parts)})")
                else:
                    for sub_name, sub in result.items():
                        if isinstance(sub, dict):
                            parts = [f"{k}={v}" for k, v in sub.items() if k in _metric_keys(sub)]
                            if parts:
                                series.append(f"{name}/{sub_name}({', '.join(parts)})")
        if series:
            head += " " + "; ".join(series)
        lines.append(head)
    return "\n".join(lines) + "\n"


def broker_section(db: Path) -> str:
    if not db.exists():
        return "- Broker-confirmed orders/fills: none recorded; ledger database is missing.\n"
    connection = sqlite3.connect(db)
    try:
        filled = connection.execute(
            "SELECT COUNT(*) FROM events WHERE event_type IN ('FILL_CONFIRMED','ORDER_ACKNOWLEDGED')"
        ).fetchone()[0]
        submissions = connection.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
    except sqlite3.Error:
        return "- Broker-confirmed orders/fills: could not be determined (ledger schema mismatch).\n"
    finally:
        connection.close()
    if submissions == 0 and filled == 0:
        return "- Broker-confirmed orders/fills: **none**. No paper order has been submitted or filled; all order-path results to date are mock tests, previews or policy evaluations.\n"
    return f"- Broker-confirmed orders/fills: {filled} fill/acknowledgement events, {submissions} submission records. Inspect the ledger for details.\n"


def build_report(db: Path) -> str:
    generated = datetime.now(UTC).isoformat(timespec="seconds")
    return "\n".join(
        [
            "# MooTrade evidence summary (generated)",
            "",
            f"- Generated at (UTC): {generated}",
            "- Mode: `PAPER`. Sections below derive only from local artifacts already committed under `evidence/` and `data/`.",
            "- Provenance: ledger rows are `LOCAL_LEDGER`; Qoder runs are genuine cloud sessions; bar snapshots, preflights and execution records are real read-only provider evidence; research studies are `HISTORICAL` and never paper-account performance.",
            "- No credentials, fingerprints or full account identifiers appear in this report.",
            "",
            "## Ledger and safety state",
            "",
            ledger_section(db),
            "## Qoder Cloud Agent runs",
            "",
            qoder_section(),
            "## Read-only preflights",
            "",
            preflight_section(),
            "## Execution records (no order submitted)",
            "",
            execution_section(),
            "## Current-market daily bars",
            "",
            market_data_section(),
            "## Local scheduler",
            "",
            scheduler_section(),
            "## Broker-confirmed orders and fills",
            "",
            broker_section(db),
            "## Historical research (HISTORICAL, not paper performance)",
            "",
            research_section(),
            "## Missing or pending evidence",
            "",
            "- First autonomous strategy paper order: pending. The two QQQ broker-confirmed fills are diagnostics; UPRO/SPXU acceptance orders and the first strategy order remain pending. No paper-account performance is reported until then.",
            "- Account-exclusive `trade:write` scope: unverified (see `docs/integrations.md`).",
        ]
    )


def main() -> None:
    _refuse_writes()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="ledger path (default: DATABASE_URL or data/mootrade.db)")
    parser.add_argument("--output", help="write the report to this file instead of stdout")
    args = parser.parse_args()

    db = _resolve_db(args.db)
    report = build_report(db)
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(report + "\n", encoding="utf-8")
        print(f"evidence report written to {target.resolve()}")
    else:
        print(report)


if __name__ == "__main__":
    main()
