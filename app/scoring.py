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


def _score_and_signal(price: float, sma50, sma200, rsi, pos_pct: float) -> tuple[int, str]:
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


def analyze_ticker(symbol: str, sector: str) -> StockResult | None:
    try:
        history = yf.Ticker(symbol).history(period="5y", interval="1d", auto_adjust=True)
    except Exception:
        return None

    if history is None or history.empty or len(history) < 60:
        return None

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

    score, signal = _score_and_signal(price, sma50, sma200, rsi14, week52_position_pct)

    return StockResult(
        symbol=symbol,
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
    )


def screen(symbols_with_sector: list[tuple[str, str]], min_price: float, max_price: float) -> list[dict]:
    results: list[dict] = []
    for symbol, sector in symbols_with_sector:
        result = analyze_ticker(symbol, sector)
        if result is None:
            continue
        if result.price < min_price or result.price > max_price:
            continue
        results.append(result.to_dict())

    results.sort(key=lambda r: r["score"], reverse=True)
    return results
