"""Fetches price history and computes a simple technical + seasonal score
for each ticker.

IMPORTANT: this is a heuristic screener for personal research only. It is
NOT financial advice and makes no guarantee of future performance.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd
import yfinance as yf

MONTH_NAMES = list(calendar.month_abbr)  # index 1-12


@dataclass
class StockResult:
    symbol: str
    name: str
    sector: str
    price: float
    change_pct_1d: float
    sma50: float | None
    sma200: float | None
    rsi14: float | None
    week52_low: float
    week52_high: float
    week52_position_pct: float
    best_buy_month: str
    seasonality: list
    revenue_growth_pct: float | None
    earnings_growth_pct: float | None
    profit_margin_pct: float | None
    current_ratio: float | None
    debt_to_equity: float | None
    quarterly_growth_positive: bool
    financially_stable: bool
    score: int
    signal: str

    def to_dict(self):
        return asdict(self)


def _rsi(closes: pd.Series, period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean().iloc[-1]
    avg_loss = loss.rolling(period).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)


def _seasonality(history: pd.DataFrame) -> tuple[str, list]:
    """Average each year's daily closes normalized to that year's mean,
    then average by calendar month. Lower = historically cheaper month.
    Returns (best_month_name, [{month, relative_pct}, ...]).
    """
    df = history.copy()
    df["year"] = df.index.year
    df["month"] = df.index.month
    df["yearly_mean"] = df.groupby("year")["Close"].transform("mean")
    df["relative"] = df["Close"] / df["yearly_mean"] - 1.0

    monthly = df.groupby("month")["relative"].mean() * 100
    monthly = monthly.reindex(range(1, 13))

    seasonality = [
        {"month": MONTH_NAMES[m], "relative_pct": round(v, 2) if pd.notna(v) else None}
        for m, v in monthly.items()
    ]
    if monthly.dropna().empty:
        return "N/A", seasonality
    best_month_num = int(monthly.idxmin())
    return MONTH_NAMES[best_month_num], seasonality


def _score_and_signal(
    price: float,
    sma50,
    sma200,
    rsi,
    pos_pct: float,
    quarterly_growth_positive: bool,
    financially_stable: bool,
) -> tuple[int, str]:
    score = 50

    if sma50 is not None and sma200 is not None:
        if sma50 > sma200:
            score += 15
        else:
            score -= 15
        if price > sma50:
            score += 10
        else:
            score -= 5
        if price > sma200:
            score += 10
        else:
            score -= 5

    if rsi is not None:
        if rsi < 30:
            score += 10
        elif rsi > 70:
            score -= 20
        elif rsi < 50:
            score += 5

    if pos_pct < 30:
        score += 10
    elif pos_pct > 90:
        score -= 10

    if quarterly_growth_positive:
        score += 5
    if financially_stable:
        score += 5

    score = int(max(0, min(100, score)))

    if rsi is not None and rsi > 70:
        signal = "Overbought - Wait"
    elif score >= 70:
        signal = "Strong Buy"
    elif score >= 55:
        signal = "Buy"
    elif score >= 40:
        signal = "Hold"
    else:
        signal = "Avoid"

    return score, signal


def _fundamentals(info: dict) -> dict:
    """Pull revenue/earnings growth and balance-sheet health out of
    yfinance's `.info` dict. Fields are best-effort and frequently missing,
    so every value is treated as optional.
    """
    revenue_growth = info.get("revenueGrowth")
    earnings_growth = info.get("earningsQuarterlyGrowth")
    profit_margin = info.get("profitMargins")
    current_ratio = info.get("currentRatio")
    debt_to_equity = info.get("debtToEquity")

    revenue_growth_pct = round(revenue_growth * 100, 1) if revenue_growth is not None else None
    earnings_growth_pct = round(earnings_growth * 100, 1) if earnings_growth is not None else None
    profit_margin_pct = round(profit_margin * 100, 1) if profit_margin is not None else None
    current_ratio = round(float(current_ratio), 2) if current_ratio is not None else None
    debt_to_equity = round(float(debt_to_equity), 1) if debt_to_equity is not None else None

    # "Last quarter's results showed positive signs they'll keep growing":
    # both revenue and earnings grew year-over-year in the most recent quarter.
    quarterly_growth_positive = bool(
        revenue_growth_pct is not None and revenue_growth_pct > 0
        and earnings_growth_pct is not None and earnings_growth_pct > 0
    )

    # "Enough revenue, won't go bankrupt": can cover short-term liabilities
    # (current ratio >= 1), isn't over-leveraged (debt/equity < 1.5x), and is
    # actually profitable. This is a rough solvency proxy, not a real
    # bankruptcy model.
    financially_stable = bool(
        current_ratio is not None and current_ratio >= 1
        and debt_to_equity is not None and debt_to_equity < 150
        and profit_margin_pct is not None and profit_margin_pct > 0
    )

    return {
        "revenue_growth_pct": revenue_growth_pct,
        "earnings_growth_pct": earnings_growth_pct,
        "profit_margin_pct": profit_margin_pct,
        "current_ratio": current_ratio,
        "debt_to_equity": debt_to_equity,
        "quarterly_growth_positive": quarterly_growth_positive,
        "financially_stable": financially_stable,
    }


def analyze_ticker(symbol: str, sector: str) -> StockResult | None:
    ticker = yf.Ticker(symbol)
    try:
        history = ticker.history(period="5y", interval="1d", auto_adjust=True)
    except Exception:
        return None

    if history is None or history.empty or len(history) < 60:
        return None

    try:
        info = ticker.info or {}
    except Exception:
        info = {}

    name = info.get("longName") or info.get("shortName") or symbol
    fundamentals = _fundamentals(info)

    closes = history["Close"].dropna()
    price = round(float(closes.iloc[-1]), 2)
    prev = float(closes.iloc[-2]) if len(closes) > 1 else price
    change_pct_1d = round((price - prev) / prev * 100, 2) if prev else 0.0

    sma50 = round(float(closes.rolling(50).mean().iloc[-1]), 2) if len(closes) >= 50 else None
    sma200 = round(float(closes.rolling(200).mean().iloc[-1]), 2) if len(closes) >= 200 else None
    rsi14 = _rsi(closes)

    last_year = closes.tail(252)
    week52_low = round(float(last_year.min()), 2)
    week52_high = round(float(last_year.max()), 2)
    span = (week52_high - week52_low) or 1.0
    week52_position_pct = round((price - week52_low) / span * 100, 1)

    best_month, seasonality = _seasonality(history)

    score, signal = _score_and_signal(
        price,
        sma50,
        sma200,
        rsi14,
        week52_position_pct,
        fundamentals["quarterly_growth_positive"],
        fundamentals["financially_stable"],
    )

    return StockResult(
        symbol=symbol,
        name=name,
        sector=sector,
        price=price,
        change_pct_1d=change_pct_1d,
        sma50=sma50,
        sma200=sma200,
        rsi14=rsi14,
        week52_low=week52_low,
        week52_high=week52_high,
        week52_position_pct=week52_position_pct,
        best_buy_month=best_month,
        seasonality=seasonality,
        score=score,
        signal=signal,
        **fundamentals,
    )


def screen(
    symbols_with_sector: list[tuple[str, str]],
    min_price: float,
    max_price: float,
    require_growth: bool = False,
    require_stable: bool = False,
) -> list[dict]:
    results: list[dict] = []
    for symbol, sector in symbols_with_sector:
        result = analyze_ticker(symbol, sector)
        if result is None:
            continue
        if result.price < min_price or result.price > max_price:
            continue
        if require_growth and not result.quarterly_growth_positive:
            continue
        if require_stable and not result.financially_stable:
            continue
        results.append(result.to_dict())

    results.sort(key=lambda r: r["score"], reverse=True)
    return results
