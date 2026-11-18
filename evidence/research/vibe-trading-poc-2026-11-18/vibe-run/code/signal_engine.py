"""POC signal engine: MooTrade momentum-v1 rules, 10% target weight."""
from __future__ import annotations
import pandas as pd
from app.research.data import MarketHistory, NewsArchive, session_close_utc
from app.research.strategy import screen

class SignalEngine:
    def generate(self, data_map: dict[str, pd.DataFrame]) -> dict[str, pd.Series]:
        history = MarketHistory.from_file("backend/tests/fixtures/moomoo_daily_bars_2026-11-16.json")
        news = NewsArchive((), {"provider": "not used", "note": "momentum-v1 is price-only"})
        dates = history.session_dates()
        weights = {s: pd.Series(0.0, index=f.index, dtype=float) for s, f in data_map.items()}
        held = None
        for index in range(20, len(dates) - 1):
            snapshot = screen(history, news, session_close_utc(dates[index]), "momentum-v1")
            if held is not None:
                candidate = next((c for c in snapshot.candidates if c.symbol == held), None)
                if candidate is None or not candidate.above_sma:
                    held = None
            elif snapshot.selected_symbol is not None:
                held = snapshot.selected_symbol
            if held is not None:
                weights[held].iloc[index] = 0.10
        return weights
