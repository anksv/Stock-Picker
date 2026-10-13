"""USD <-> EUR conversion from the live EUR/USD rate (Yahoo's EURUSD=X).

The rate is "USD per 1 EUR". It's cached for an hour; if a refresh fails, the
last good rate is reused for up to a day and flagged as stale rather than
silently pretending it's fresh. If there has never been a good rate, callers
get FxUnavailable - no fallback rate is invented.

Only USD and EUR are supported (the two currencies this app trades in).
Anything else raises ValueError so callers can fall back to showing the
asset's native currency instead of a wrong conversion.
"""
from __future__ import annotations

import threading
import time

import yfinance as yf

SUPPORTED = ("USD", "EUR")
CACHE_TTL_SECONDS = 60 * 60
STALE_MAX_SECONDS = 24 * 60 * 60

_lock = threading.Lock()
_cache: dict = {"rate": None, "fetched_at": 0.0, "as_of": None}


class FxUnavailable(Exception):
    pass


def _fetch() -> tuple[float, str]:
    closes = yf.Ticker("EURUSD=X").history(period="5d")["Close"].dropna()
    if closes.empty:
        raise FxUnavailable("No EUR/USD data returned")
    return float(closes.iloc[-1]), closes.index[-1].date().isoformat()


def eurusd() -> dict:
    """{"rate": USD per EUR, "as_of": date of the quote, "stale": bool}"""
    with _lock:
        now = time.time()
        age = now - _cache["fetched_at"]
        if _cache["rate"] is not None and age < CACHE_TTL_SECONDS:
            return {"rate": _cache["rate"], "as_of": _cache["as_of"], "stale": False}
        try:
            rate, as_of = _fetch()
            _cache.update(rate=rate, fetched_at=now, as_of=as_of)
            return {"rate": rate, "as_of": as_of, "stale": False}
        except Exception as exc:
            if _cache["rate"] is not None and age < STALE_MAX_SECONDS:
                return {"rate": _cache["rate"], "as_of": _cache["as_of"], "stale": True}
            raise FxUnavailable("EUR/USD rate unavailable") from exc


def convert(value: float, from_ccy: str, to_ccy: str, rate: float | None = None) -> float:
    """Converts between USD and EUR. Pass `rate` (USD per EUR) to reuse one
    rate across many conversions; otherwise the cached live rate is used.
    """
    from_ccy, to_ccy = from_ccy.upper(), to_ccy.upper()
    if from_ccy not in SUPPORTED or to_ccy not in SUPPORTED:
        raise ValueError(f"Unsupported currency pair {from_ccy}->{to_ccy}")
    if from_ccy == to_ccy:
        return value
    if rate is None:
        rate = eurusd()["rate"]
    return value * rate if from_ccy == "EUR" else value / rate
