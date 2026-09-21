"""Fetches price history and computes a simple technical + seasonal score
for each ticker.

IMPORTANT: this is a heuristic screener for personal research only. It is
NOT financial advice and makes no guarantee of future performance.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf

NEW_LISTING_YEARS_THRESHOLD = 10

MONTH_NAMES = list(calendar.month_abbr)  # index 1-12


@dataclass
class StockResult:
    symbol: str
    name: str
    sector: str
    continent: str
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
    listing_date: str | None
    years_listed: float | None
    is_new_listing: bool
    years_of_price_history: float
    price_cagr_10y_pct: float | None
    price_volatility_10y_pct: float | None
    profitable_years_ratio: float | None
    gross_margin_pct: float | None
    rnd_to_revenue_pct: float | None
    business_quality_score: int
    business_quality_label: str
    is_durable_compounder: bool
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
    business_quality_score: int,
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

    # Long-term business quality (10y price compounding, profitability track
    # record, margin/customer-loyalty proxy, low product-experimentation
    # spend) is weighted as heavily as the short-term technicals above: up to
    # +/-20 points.
    score += round((business_quality_score - 50) * 0.4)

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


def _listing_age(info: dict) -> dict:
    """How long the stock has traded publicly, from yfinance's
    `firstTradeDateMilliseconds`. This is the exchange listing date (IPO),
    not necessarily when the company was founded, so `is_new_listing` means
    "newly public" rather than "newly founded".
    """
    first_trade_ms = info.get("firstTradeDateMilliseconds")
    if not first_trade_ms:
        return {"listing_date": None, "years_listed": None, "is_new_listing": False}

    listed_at = datetime.fromtimestamp(first_trade_ms / 1000, tz=timezone.utc)
    years_listed = round((datetime.now(timezone.utc) - listed_at).days / 365.25, 1)

    return {
        "listing_date": listed_at.date().isoformat(),
        "years_listed": years_listed,
        "is_new_listing": years_listed < NEW_LISTING_YEARS_THRESHOLD,
    }


def _annual_series(income_stmt: pd.DataFrame, row: str) -> pd.Series:
    if income_stmt is None or income_stmt.empty or row not in income_stmt.index:
        return pd.Series(dtype=float)
    return income_stmt.loc[row].dropna().sort_index()


def _business_quality(history: pd.DataFrame, income_stmt: pd.DataFrame) -> dict:
    """Long-term "is this a durable, loyal-customer business, or one that's
    still experimenting?" score. Approximated from what's actually available
    for free:
      - up to ~10 years of price history -> long-run compounding (CAGR) and
        year-to-year steadiness (low volatility = fewer wild swings).
      - up to ~4-5 years of annual financials -> was it profitable every
        year, does it hold a stable/high gross margin (pricing power that
        only comes from customers who keep buying), and how much of revenue
        goes to R&D (low or unreported ~= relying on an established product
        line rather than constant new-product bets).
    Yahoo Finance doesn't expose a full 10 years of income statements for
    free, so the profitability/margin/R&D checks cover fewer years than the
    price trend does; that's disclosed via `years_of_price_history` and by
    treating a missing track record as neutral rather than penalizing it.
    """
    closes = history["Close"].dropna()
    years_of_price_history = round((closes.index[-1] - closes.index[0]).days / 365.25, 1) if len(closes) > 1 else 0.0

    price_cagr_10y_pct = None
    price_volatility_10y_pct = None
    if years_of_price_history >= 7 and float(closes.iloc[0]) > 0:
        price_cagr_10y_pct = round(
            ((float(closes.iloc[-1]) / float(closes.iloc[0])) ** (1 / years_of_price_history) - 1) * 100, 1
        )
        yearly_returns = closes.resample("YE").last().dropna().pct_change().dropna() * 100
        if len(yearly_returns) >= 3:
            price_volatility_10y_pct = round(float(yearly_returns.std()), 1)

    net_income = _annual_series(income_stmt, "NetIncome")
    revenue = _annual_series(income_stmt, "TotalRevenue")
    gross_profit = _annual_series(income_stmt, "GrossProfit")
    rnd = _annual_series(income_stmt, "ResearchAndDevelopment")

    profitable_years_ratio = (
        round(float((net_income > 0).sum()) / len(net_income), 2) if len(net_income) > 0 else None
    )

    gross_margin_pct = None
    common_years = gross_profit.index.intersection(revenue.index)
    if len(common_years) > 0:
        margins = (gross_profit.loc[common_years] / revenue.loc[common_years]).replace([np.inf, -np.inf], np.nan).dropna()
        if len(margins) > 0:
            gross_margin_pct = round(float(margins.mean()) * 100, 1)

    rnd_reported = len(rnd) > 0
    rnd_to_revenue_pct = None
    rnd_years = rnd.index.intersection(revenue.index)
    if len(rnd_years) > 0:
        ratios = (rnd.loc[rnd_years] / revenue.loc[rnd_years]).replace([np.inf, -np.inf], np.nan).dropna()
        if len(ratios) > 0:
            rnd_to_revenue_pct = round(float(ratios.mean()) * 100, 1)

    have_track_record = price_cagr_10y_pct is not None or profitable_years_ratio is not None
    score = 50

    if price_cagr_10y_pct is not None:
        if price_cagr_10y_pct >= 15:
            score += 20
        elif price_cagr_10y_pct >= 8:
            score += 12
        elif price_cagr_10y_pct >= 0:
            score += 4
        else:
            score -= 15

    if profitable_years_ratio is not None:
        if profitable_years_ratio >= 1.0:
            score += 15
        elif profitable_years_ratio >= 0.75:
            score += 6
        elif profitable_years_ratio >= 0.5:
            score -= 2
        else:
            score -= 15

    if gross_margin_pct is not None:
        if gross_margin_pct >= 50:
            score += 12
        elif gross_margin_pct >= 35:
            score += 7
        elif gross_margin_pct >= 20:
            score += 2
        else:
            score -= 5

    if price_volatility_10y_pct is not None:
        if price_volatility_10y_pct <= 15:
            score += 8
        elif price_volatility_10y_pct <= 25:
            score += 4
        elif price_volatility_10y_pct > 40:
            score -= 8

    # "Without experimenting much on new products, clients stayed loyal":
    # reward low R&D-to-revenue, and treat a missing R&D line as a sign the
    # business isn't R&D-driven at all (e.g. consumer staples) rather than
    # penalizing it for lack of data.
    if rnd_to_revenue_pct is not None:
        if rnd_to_revenue_pct < 3:
            score += 5
        elif rnd_to_revenue_pct < 8:
            score += 1
        elif rnd_to_revenue_pct < 15:
            score -= 3
        else:
            score -= 8
    elif not rnd_reported:
        score += 5

    score = int(max(0, min(100, score))) if have_track_record else 50

    if not have_track_record:
        label = "Insufficient History"
    elif score >= 75:
        label = "Durable Compounder"
    elif score >= 60:
        label = "Steady"
    elif score >= 40:
        label = "Mixed"
    else:
        label = "Volatile / Experimental"

    return {
        "years_of_price_history": years_of_price_history,
        "price_cagr_10y_pct": price_cagr_10y_pct,
        "price_volatility_10y_pct": price_volatility_10y_pct,
        "profitable_years_ratio": profitable_years_ratio,
        "gross_margin_pct": gross_margin_pct,
        "rnd_to_revenue_pct": rnd_to_revenue_pct,
        "business_quality_score": score,
        "business_quality_label": label,
        "is_durable_compounder": label == "Durable Compounder",
    }


def analyze_ticker(symbol: str, sector: str, continent: str) -> StockResult | None:
    ticker = yf.Ticker(symbol)
    try:
        history = ticker.history(period="10y", interval="1d", auto_adjust=True)
    except Exception:
        return None

    if history is None or history.empty or len(history) < 60:
        return None

    try:
        info = ticker.info or {}
    except Exception:
        info = {}

    try:
        income_stmt = ticker.get_income_stmt(freq="yearly")
    except Exception:
        income_stmt = pd.DataFrame()

    name = info.get("longName") or info.get("shortName") or symbol
    fundamentals = _fundamentals(info)
    listing_age = _listing_age(info)
    business_quality = _business_quality(history, income_stmt)

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
        business_quality["business_quality_score"],
    )

    return StockResult(
        symbol=symbol,
        name=name,
        sector=sector,
        continent=continent,
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
        **listing_age,
        **business_quality,
    )
