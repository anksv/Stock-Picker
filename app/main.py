from __future__ import annotations

import threading
import time
import webbrowser
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.news import get_news_signal
from app.scoring import analyze_ticker
from app.universe import (
    all_asset_types,
    all_continents,
    all_sectors,
    asset_type_for_ticker,
    continent_for_ticker,
    sector_for_ticker,
    tickers_for_filters,
)

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR.parent / "static"

app = FastAPI(title="Stock Picker")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL_SECONDS = 15 * 60


def _attach_peer_comparison(results: list[dict]) -> None:
    """How competitors can impact a stock, approximated as: 3-month price
    return vs. the average of its same-sector peers within this result set
    (i.e. peers matching the current sector/continent/asset-type filters,
    not a fixed competitor list - narrowing the filters narrows the peer
    group). Mutates each result dict in place.
    """
    by_sector: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_sector[r["sector"]].append(r)

    for group in by_sector.values():
        for r in group:
            peer_returns = [
                p["return_3m_pct"] for p in group
                if p is not r and p["return_3m_pct"] is not None
            ]
            if r["return_3m_pct"] is None or not peer_returns:
                r["sector_peer_avg_return_3m_pct"] = None
                r["vs_sector_return_pct"] = None
                continue
            peer_avg = sum(peer_returns) / len(peer_returns)
            r["sector_peer_avg_return_3m_pct"] = round(peer_avg, 1)
            r["vs_sector_return_pct"] = round(r["return_3m_pct"] - peer_avg, 1)


@app.get("/api/sectors")
def get_sectors():
    return {"sectors": all_sectors()}


@app.get("/api/continents")
def get_continents():
    return {"continents": all_continents()}


@app.get("/api/asset-types")
def get_asset_types():
    return {"asset_types": all_asset_types()}


@app.get("/api/screen")
def get_screen(
    sector: str = Query(default="All"),
    continent: str = Query(default="All"),
    asset_type: str = Query(default="All"),
    min_price: float = Query(default=0.0, ge=0),
    max_price: float = Query(default=100000.0, gt=0),
    require_growth: bool = Query(default=False, description="Only include stocks with positive YoY revenue and earnings growth last quarter"),
    require_stable: bool = Query(default=False, description="Only include stocks that look financially stable (current ratio, debt/equity, profitability)"),
):
    cache_key = f"{sector.lower()}|{continent.lower()}|{asset_type.lower()}"
    now = time.time()
    cached = _CACHE.get(cache_key)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        results = cached[1]
    else:
        symbols = tickers_for_filters(sector, continent, asset_type)
        results = []
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = {
                pool.submit(
                    analyze_ticker,
                    sym,
                    sector_for_ticker(sym) or "Unknown",
                    continent_for_ticker(sym) or "Unknown",
                    asset_type_for_ticker(sym) or "Stock",
                ): sym
                for sym in symbols
            }
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    results.append(result.to_dict())
        _attach_peer_comparison(results)
        results.sort(key=lambda r: r["score"], reverse=True)
        _CACHE[cache_key] = (now, results)

    filtered = [r for r in results if min_price <= r["price"] <= max_price]
    if require_growth:
        filtered = [r for r in filtered if r["quarterly_growth_positive"]]
    if require_stable:
        filtered = [r for r in filtered if r["financially_stable"]]
    filtered.sort(key=lambda r: r["score"], reverse=True)
    return {"count": len(filtered), "results": filtered}


@app.get("/api/news/{symbol}")
def get_news(symbol: str, name: str = Query(default="")):
    """Fetched on demand (only when a stock's detail panel is opened), not
    during a full scan - news is a per-symbol call that would otherwise
    slow every screen down for a feature most results never get viewed.
    `name` (the company/asset name) improves the Google News search query -
    ticker symbols alone are often too ambiguous or too obscure to match.
    """
    symbol = symbol.upper()
    if asset_type_for_ticker(symbol) is None:
        raise HTTPException(status_code=404, detail="Unknown symbol")
    return get_news_signal(symbol, name or None)


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


def _open_browser(url: str, delay: float = 1.2):
    time.sleep(delay)
    webbrowser.open(url)


def main():
    host, port = "127.0.0.1", 8000
    url = f"http://{host}:{port}"
    threading.Thread(target=_open_browser, args=(url,), daemon=True).start()
    print(f"Starting Stock Picker at {url}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
