import json
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.models.contracts import (
    OrderRecord,
    OrderRequest,
    OrderStatus,
    TradingActivation,
    can_transition,
)


class SQLiteLedger:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    occurred_at_utc TEXT NOT NULL,
                    run_id TEXT,
                    event_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    payload_redacted_json TEXT NOT NULL,
                    correlation_id TEXT,
                    schema_version TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS events_no_update
                BEFORE UPDATE ON events
                BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS events_no_delete
                BEFORE DELETE ON events
                BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
                CREATE TABLE IF NOT EXISTS controls (
                    name TEXT PRIMARY KEY,
                    value INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS submissions (
                    client_order_key TEXT PRIMARY KEY,
                    proposal_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    order_json TEXT
                );
                CREATE TABLE IF NOT EXISTS order_approvals (
                    client_order_key TEXT PRIMARY KEY,
                    proposal_id TEXT NOT NULL,
                    approved_at_utc TEXT NOT NULL,
                    approved_by TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS equity_days (
                    account_fingerprint TEXT NOT NULL,
                    trading_day TEXT NOT NULL,
                    day_start_equity TEXT NOT NULL,
                    peak_equity TEXT NOT NULL,
                    PRIMARY KEY (account_fingerprint, trading_day)
                );
                CREATE TABLE IF NOT EXISTS trading_activations (
                    activation_id TEXT PRIMARY KEY,
                    activated_at_utc TEXT NOT NULL,
                    activated_by TEXT NOT NULL,
                    account_fingerprint TEXT NOT NULL,
                    strategy_version TEXT NOT NULL,
                    allowed_symbols_json TEXT NOT NULL,
                    risk_policy_version TEXT NOT NULL,
                    max_single_exposure TEXT,
                    max_total_exposure TEXT,
                    position_fraction TEXT,
                    min_effective_exposure_fraction TEXT,
                    max_effective_exposure_fraction TEXT,
                    max_daily_drawdown TEXT NOT NULL,
                    paper_only INTEGER NOT NULL,
                    order_writes_enabled INTEGER NOT NULL,
                    schema_version TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS trading_activations_no_update
                BEFORE UPDATE ON trading_activations
                BEGIN SELECT RAISE(ABORT, 'trading activations are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS trading_activations_no_delete
                BEFORE DELETE ON trading_activations
                BEGIN SELECT RAISE(ABORT, 'trading activations are append-only'); END;
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(trading_activations)")
            }
            for column in (
                "min_effective_exposure_fraction",
                "max_effective_exposure_fraction",
            ):
                if column not in columns:
                    # Pre-risk-v2 databases keep their risk-v1 activation rows
                    # intact; the nullable columns let both versions coexist.
                    connection.execute(
                        f"ALTER TABLE trading_activations ADD COLUMN {column} TEXT"
                    )
            notnull_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(trading_activations)")
                if row["notnull"]
            }
            if "max_single_exposure" in notnull_columns:
                # Databases created before the dual risk-policy change hold the
                # risk-v1 limit columns as NOT NULL, which rejects risk-v2 pins
                # that leave them null. Rebuild the table with the nullable
                # schema, preserving every existing activation row.
                with connection:
                    connection.executescript(
                        """
                        ALTER TABLE trading_activations
                        RENAME TO trading_activations_pre_risk_v2;
                        CREATE TABLE trading_activations (
                            activation_id TEXT PRIMARY KEY,
                            activated_at_utc TEXT NOT NULL,
                            activated_by TEXT NOT NULL,
                            account_fingerprint TEXT NOT NULL,
                            strategy_version TEXT NOT NULL,
                            allowed_symbols_json TEXT NOT NULL,
                            risk_policy_version TEXT NOT NULL,
                            max_single_exposure TEXT,
                            max_total_exposure TEXT,
                            position_fraction TEXT,
                            min_effective_exposure_fraction TEXT,
                            max_effective_exposure_fraction TEXT,
                            max_daily_drawdown TEXT NOT NULL,
                            paper_only INTEGER NOT NULL,
                            order_writes_enabled INTEGER NOT NULL,
                            schema_version TEXT NOT NULL
                        );
                        INSERT INTO trading_activations (
                            activation_id, activated_at_utc, activated_by,
                            account_fingerprint, strategy_version,
                            allowed_symbols_json, risk_policy_version,
                            max_single_exposure, max_total_exposure,
                            position_fraction, min_effective_exposure_fraction,
                            max_effective_exposure_fraction, max_daily_drawdown,
                            paper_only, order_writes_enabled, schema_version
                        )
                        SELECT
                            activation_id, activated_at_utc, activated_by,
                            account_fingerprint, strategy_version,
                            allowed_symbols_json, risk_policy_version,
                            max_single_exposure, max_total_exposure,
                            position_fraction, min_effective_exposure_fraction,
                            max_effective_exposure_fraction, max_daily_drawdown,
                            paper_only, order_writes_enabled, schema_version
                        FROM trading_activations_pre_risk_v2;
                        DROP TABLE trading_activations_pre_risk_v2;
                        CREATE TRIGGER trading_activations_no_update
                        BEFORE UPDATE ON trading_activations
                        BEGIN SELECT RAISE(ABORT, 'trading activations are append-only'); END;
                        CREATE TRIGGER trading_activations_no_delete
                        BEFORE DELETE ON trading_activations
                        BEGIN SELECT RAISE(ABORT, 'trading activations are append-only'); END;
                        """
                    )

    def append_event(
        self,
        event_type: str,
        occurred_at_utc: datetime,
        run_id: str | None,
        source: str,
        payload: dict[str, Any],
        correlation_id: str | None = None,
    ) -> str:
        event_id = str(uuid4())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO events (
                    event_id, occurred_at_utc, run_id, event_type, source,
                    payload_redacted_json, correlation_id, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    occurred_at_utc.isoformat(),
                    run_id,
                    event_type,
                    source,
                    json.dumps(payload, default=str, sort_keys=True, separators=(",", ":")),
                    correlation_id,
                    "1",
                ),
            )
        return event_id

    def list_events(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM events ORDER BY rowid").fetchall()
        return [
            {
                **dict(row),
                "payload_redacted_json": json.loads(row["payload_redacted_json"]),
            }
            for row in rows
        ]

    def set_kill_switch(self, engaged: bool) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO controls (name, value) VALUES ('kill_switch', ?)
                ON CONFLICT(name) DO UPDATE SET value = excluded.value
                """,
                (int(engaged),),
            )

    def kill_switch_engaged(self) -> bool:
        with self._connect() as connection:
            row = connection.execute("SELECT value FROM controls WHERE name = 'kill_switch'").fetchone()
        return bool(row["value"]) if row else False

    def reserve_submission(self, request: OrderRequest) -> bool:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO submissions (client_order_key, proposal_id, status, request_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        request.client_order_key,
                        request.proposal_id,
                        OrderStatus.SUBMITTING.value,
                        request.model_dump_json(),
                    ),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def submission_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM submissions").fetchone()
        return int(row["count"])

    def approve_first_order(
        self,
        client_order_key: str,
        proposal_id: str,
        approved_at_utc: datetime,
        approved_by: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO order_approvals (client_order_key, proposal_id, approved_at_utc, approved_by)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(client_order_key) DO NOTHING
                """,
                (client_order_key, proposal_id, approved_at_utc.isoformat(), approved_by),
            )

    def order_approval_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM order_approvals"
            ).fetchone()
        return int(row["count"])

    def is_first_order_approved(self, client_order_key: str, proposal_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM order_approvals
                WHERE client_order_key = ? AND proposal_id = ?
                """,
                (client_order_key, proposal_id),
            ).fetchone()
        return row is not None

    def observe_equity(
        self,
        account_fingerprint: str,
        equity: Decimal,
        observed_at_utc: datetime,
    ) -> tuple[Decimal, Decimal]:
        if observed_at_utc.tzinfo is None:
            raise ValueError("equity observation timestamp must include a timezone")
        if equity <= 0:
            raise ValueError("equity must be positive")
        # Regular-session US trading stays within one UTC calendar day; after-hours is out of scope.
        trading_day = observed_at_utc.astimezone(UTC).date().isoformat()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT day_start_equity, peak_equity FROM equity_days
                WHERE account_fingerprint = ? AND trading_day = ?
                """,
                (account_fingerprint, trading_day),
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO equity_days (
                        account_fingerprint, trading_day, day_start_equity, peak_equity
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (account_fingerprint, trading_day, str(equity), str(equity)),
                )
                return equity, equity
            day_start = Decimal(row["day_start_equity"])
            peak = Decimal(row["peak_equity"])
            if equity > peak:
                peak = equity
                connection.execute(
                    """
                    UPDATE equity_days SET peak_equity = ?
                    WHERE account_fingerprint = ? AND trading_day = ?
                    """,
                    (str(peak), account_fingerprint, trading_day),
                )
        return day_start, peak

    def record_order(self, order: OrderRecord) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM submissions WHERE client_order_key = ?",
                (order.client_order_key,),
            ).fetchone()
            if row is None:
                raise RuntimeError("order must be reserved before it is recorded")
            current = OrderStatus(row["status"])
            if not can_transition(current, order.status):
                raise ValueError(
                    f"illegal order transition: {current.value} -> {order.status.value}"
                )
            connection.execute(
                """
                UPDATE submissions SET status = ?, order_json = ?
                WHERE client_order_key = ?
                """,
                (order.status.value, order.model_dump_json(), order.client_order_key),
            )

    def submission_for_proposal(self, proposal_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM submissions WHERE proposal_id = ?", (proposal_id,)
            ).fetchone()

    def list_submissions(self) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT client_order_key, proposal_id, status, request_json, order_json
                FROM submissions ORDER BY rowid
                """
            ).fetchall()

    def has_unknown_submissions(self) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM submissions WHERE status = ? LIMIT 1",
                (OrderStatus.UNKNOWN.value,),
            ).fetchone()
        return row is not None

    def order_for_proposal(self, proposal_id: str) -> OrderRecord | None:
        row = self.submission_for_proposal(proposal_id)
        if row is None or row["order_json"] is None:
            return None
        return OrderRecord.model_validate_json(row["order_json"])

    def order_for_key(self, client_order_key: str) -> OrderRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT order_json FROM submissions WHERE client_order_key = ?",
                (client_order_key,),
            ).fetchone()
        if row is None or row["order_json"] is None:
            return None
        return OrderRecord.model_validate_json(row["order_json"])

    def record_trading_activation(self, activation: TradingActivation) -> str:
        activation_id = str(uuid4())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO trading_activations (
                    activation_id, activated_at_utc, activated_by,
                    account_fingerprint, strategy_version, allowed_symbols_json,
                    risk_policy_version, max_single_exposure, max_total_exposure,
                    position_fraction, min_effective_exposure_fraction,
                    max_effective_exposure_fraction, max_daily_drawdown, paper_only,
                    order_writes_enabled, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    activation_id,
                    activation.activated_at_utc.isoformat(),
                    activation.activated_by,
                    activation.account_fingerprint,
                    activation.strategy_version,
                    json.dumps(list(activation.allowed_symbols)),
                    activation.risk_policy_version,
                    str(activation.max_single_exposure)
                    if activation.max_single_exposure is not None
                    else None,
                    str(activation.max_total_exposure)
                    if activation.max_total_exposure is not None
                    else None,
                    str(activation.position_fraction)
                    if activation.position_fraction is not None
                    else None,
                    str(activation.min_effective_exposure_fraction)
                    if activation.min_effective_exposure_fraction is not None
                    else None,
                    str(activation.max_effective_exposure_fraction)
                    if activation.max_effective_exposure_fraction is not None
                    else None,
                    str(activation.max_daily_drawdown),
                    1,
                    1,
                    activation.schema_version,
                ),
            )
        return activation_id

    def latest_trading_activation(self) -> TradingActivation | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM trading_activations ORDER BY activated_at_utc DESC, rowid DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return TradingActivation(
            activated_at_utc=row["activated_at_utc"],
            activated_by=row["activated_by"],
            account_fingerprint=row["account_fingerprint"],
            strategy_version=row["strategy_version"],
            allowed_symbols=tuple(json.loads(row["allowed_symbols_json"])),
            risk_policy_version=row["risk_policy_version"],
            max_single_exposure=(
                Decimal(row["max_single_exposure"]) if row["max_single_exposure"] else None
            ),
            max_total_exposure=(
                Decimal(row["max_total_exposure"]) if row["max_total_exposure"] else None
            ),
            position_fraction=(
                Decimal(row["position_fraction"]) if row["position_fraction"] else None
            ),
            min_effective_exposure_fraction=(
                Decimal(row["min_effective_exposure_fraction"])
                if row["min_effective_exposure_fraction"]
                else None
            ),
            max_effective_exposure_fraction=(
                Decimal(row["max_effective_exposure_fraction"])
                if row["max_effective_exposure_fraction"]
                else None
            ),
            max_daily_drawdown=Decimal(row["max_daily_drawdown"]),
        )

    def latest_event_payload(
        self, event_type: str, symbol: str | None = None
    ) -> tuple[dict[str, Any], int] | None:
        with self._connect() as connection:
            if symbol is None:
                row = connection.execute(
                    """
                    SELECT payload_redacted_json, rowid FROM events
                    WHERE event_type = ? ORDER BY rowid DESC LIMIT 1
                    """,
                    (event_type,),
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT payload_redacted_json, rowid FROM events
                    WHERE event_type = ? AND json_extract(payload_redacted_json, '$.symbol') = ?
                    ORDER BY rowid DESC LIMIT 1
                    """,
                    (event_type, symbol),
                ).fetchone()
        if row is None:
            return None
        return json.loads(row["payload_redacted_json"]), int(row["rowid"])
