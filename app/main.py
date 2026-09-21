from __future__ import annotations

import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.scoring import analyze_ticker
from app.universe import all_sectors, sector_for_ticker, tickers_for_sector

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


@app.get("/api/sectors")
def get_sectors():
    return {"sectors": all_sectors()}


@app.get("/api/screen")
def get_screen(
    sector: str = Query(default="All"),
    min_price: float = Query(default=0.0, ge=0),
    max_price: float = Query(default=100000.0, gt=0),
    require_growth: bool = Query(default=False, description="Only include stocks with positive YoY revenue and earnings growth last quarter"),
    require_stable: bool = Query(default=False, description="Only include stocks that look financially stable (current ratio, debt/equity, profitability)"),
):
    cache_key = sector.lower()
    now = time.time()
    cached = _CACHE.get(cache_key)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        results = cached[1]
    else:
        symbols = tickers_for_sector(sector)
        results = []
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = {
                pool.submit(analyze_ticker, sym, sector_for_ticker(sym) or "Unknown"): sym
                for sym in symbols
            }
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    results.append(result.to_dict())
        results.sort(key=lambda r: r["score"], reverse=True)
        _CACHE[cache_key] = (now, results)

    filtered = [r for r in results if min_price <= r["price"] <= max_price]
    if require_growth:
        filtered = [r for r in filtered if r["quarterly_growth_positive"]]
    if require_stable:
        filtered = [r for r in filtered if r["financially_stable"]]
    filtered.sort(key=lambda r: r["score"], reverse=True)
    return {"count": len(filtered), "results": filtered}


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
