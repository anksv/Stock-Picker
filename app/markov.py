"""Markov-chain outlook for a stock/ETF/crypto from its own price history.

Weekly returns are bucketed into three states - Down, Flat, Up - using a
threshold of half a standard deviation of that asset's own weekly returns
(so a bond ETF and Bitcoin are each judged against their own normal range).
A transition matrix is estimated from the 10-year history, and the asset's
current state is looked up in it to get next-week probabilities.

IMPORTANT: markets are close to memoryless, so for most assets these
probabilities sit near the asset's long-run base rate. Each result therefore
carries (a) a significance check of the current state's edge over the base
rate and (b) a walk-forward backtest against an "always predict up"
baseline. The label defaults to "No Clear Edge" unless the edge is both
large and statistically significant. This is a research aid, not a forecast
and not financial advice.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import yfinance as yf

STATE_NAMES = ["Down", "Flat", "Up"]
MIN_WEEKS = 104  # ~2 years of completed weeks
SIGMA_K = 0.5  # Down/Up threshold = +/- SIGMA_K * stdev of weekly returns
SMOOTHING = 1.0  # add-one smoothing so a rarely-seen state can't give 0%/100%
Z_SIGNIFICANT = 1.96  # two-sided ~95%
MIN_NET_EDGE_PCT = 5.0  # percentage points of (P(Up) - P(Down)) vs. base rate
WALK_FORWARD_TRAIN_RATIO = 0.6


def _states(returns: np.ndarray, threshold: float) -> np.ndarray:
    return np.where(returns > threshold, 2, np.where(returns < -threshold, 0, 1))


def _counts(states: np.ndarray) -> np.ndarray:
    counts = np.zeros((3, 3))
    np.add.at(counts, (states[:-1], states[1:]), 1)
    return counts


def _transition_matrix(counts: np.ndarray) -> np.ndarray:
    smoothed = counts + SMOOTHING
    return smoothed / smoothed.sum(axis=1, keepdims=True)


def _weekly_returns(history: pd.DataFrame) -> pd.Series:
    closes = history["Close"].dropna()
    weekly = closes.resample("W-FRI").last().dropna()
    # The in-progress week would distort both the current state and the
    # learned transitions, so only completed weeks are used.
    if len(weekly) and weekly.index[-1] >= pd.Timestamp.now(tz=weekly.index.tz).normalize():
        weekly = weekly.iloc[:-1]
    return weekly.pct_change().dropna()


def _walk_forward(returns: np.ndarray) -> dict | None:
    """Fits the matrix on the first 60% of weeks only, then predicts the
    direction of every later week from the prior week's state, and compares
    that to simply always guessing "up".
    """
    n = len(returns)
    split = int(n * WALK_FORWARD_TRAIN_RATIO)
    if split < 52 or n - split < 26:
        return None

    threshold = SIGMA_K * returns[:split].std()
    states = _states(returns, threshold)
    matrix = _transition_matrix(_counts(states[:split]))

    correct = up_weeks = total = 0
    for i in range(split - 1, n - 1):
        predicted_up = matrix[states[i], 2] >= matrix[states[i], 0]
        actual_up = returns[i + 1] > 0
        correct += int(predicted_up == actual_up)
        up_weeks += int(actual_up)
        total += 1

    return {
        "weeks": total,
        "accuracy_pct": round(correct / total * 100, 1),
        "baseline_accuracy_pct": round(up_weeks / total * 100, 1),
    }


def _z(p: float, base: float, n: float) -> float:
    if n <= 0 or base <= 0 or base >= 1:
        return 0.0
    return (p - base) / math.sqrt(base * (1 - base) / n)


def compute_markov(symbol: str, history: pd.DataFrame | None = None, include_name: bool = False) -> dict | None:
    """Returns None if no price data exists for the symbol; otherwise a
    result dict (with outlook_label "Insufficient History" if there are too
    few completed weeks to estimate anything).
    """
    ticker = yf.Ticker(symbol)
    if history is None:
        try:
            history = ticker.history(period="10y", interval="1d", auto_adjust=True)
        except Exception:
            return None
    if history is None or history.empty:
        return None

    name = None
    if include_name:
        try:
            info = ticker.info or {}
            name = info.get("longName") or info.get("shortName")
        except Exception:
            name = None

    returns = _weekly_returns(history)
    base_result = {"symbol": symbol, "name": name, "weeks_of_history": int(len(returns))}

    if len(returns) < MIN_WEEKS:
        return {**base_result, "outlook_label": "Insufficient History"}

    values = returns.to_numpy()
    threshold = SIGMA_K * values.std()
    states = _states(values, threshold)
    counts = _counts(states)
    matrix = _transition_matrix(counts)

    current = int(states[-1])
    row = matrix[current]
    row_n = counts[current].sum()
    total_transitions = counts.sum()
    base_down, base_flat, base_up = (counts.sum(axis=0) / total_transitions).tolist()

    z_up = _z(row[2], base_up, row_n)
    z_down = _z(row[0], base_down, row_n)
    net_edge_pct = ((row[2] - row[0]) - (base_up - base_down)) * 100
    significant = max(abs(z_up), abs(z_down)) >= Z_SIGNIFICANT

    if significant and net_edge_pct >= MIN_NET_EDGE_PCT:
        label = "Favorable"
    elif significant and net_edge_pct <= -MIN_NET_EDGE_PCT:
        label = "Unfavorable"
    else:
        label = "No Clear Edge"

    followed = values[1:][states[:-1] == current]
    four_week = np.linalg.matrix_power(matrix, 4)[current]
    stationary = np.linalg.matrix_power(matrix, 500)[0]

    return {
        **base_result,
        "as_of_week_ending": returns.index[-1].date().isoformat(),
        "current_state": STATE_NAMES[current],
        "last_week_return_pct": round(float(values[-1]) * 100, 2),
        "state_threshold_pct": round(float(threshold) * 100, 2),
        "p_down_next": round(float(row[0]) * 100, 1),
        "p_flat_next": round(float(row[1]) * 100, 1),
        "p_up_next": round(float(row[2]) * 100, 1),
        "p_up_4w": round(float(four_week[2]) * 100, 1),
        "base_down": round(base_down * 100, 1),
        "base_flat": round(base_flat * 100, 1),
        "base_up": round(base_up * 100, 1),
        "stationary_up": round(float(stationary[2]) * 100, 1),
        "net_edge_pct": round(float(net_edge_pct), 1),
        "z_up": round(float(z_up), 2),
        "z_down": round(float(z_down), 2),
        "significant": bool(significant),
        "sample_size": int(row_n),
        "expected_next_week_return_pct": round(float(followed.mean()) * 100, 2) if len(followed) else None,
        "avg_weekly_return_pct": round(float(values.mean()) * 100, 2),
        "transition_matrix_pct": [[round(float(v) * 100, 1) for v in r] for r in matrix],
        "transition_counts": [[int(v) for v in r] for r in counts],
        "backtest": _walk_forward(values),
        "outlook_label": label,
    }
