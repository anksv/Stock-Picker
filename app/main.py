from __future__ import annotations

import logging
import re
import threading
import time
from contextlib import asynccontextmanager
import webbrowser
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import markov_journal
from app.markov import compute_markov
from app.portfolio import buy_portfolio, check_portfolio, delete_portfolio, list_portfolios
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

log = logging.getLogger("stock-picker")
JOURNAL_CHECK_INTERVAL_SECONDS = 12 * 60 * 60


def _all_tracked_symbols() -> list[str]:
    return markov_journal.tracked_symbols(tickers_for_filters("All", "All", "All"))


def _journal_loop() -> None:
    """Daily-ish check while the server is up: score finished predictions
    against real prices and log the model's fresh calls. Also available as a
    cron-able CLI (python -m app.markov_journal update).
    """
    time.sleep(20)  # let the app finish starting before hitting the network
    while True:
        try:
            result = markov_journal.maybe_update(_all_tracked_symbols(), min_hours=6)
            if result:
                log.info("Markov journal updated: %s", result)
        except Exception:
            log.exception("Markov journal update failed")
        time.sleep(JOURNAL_CHECK_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(_: FastAPI):
    threading.Thread(target=_journal_loop, daemon=True).start()
    yield


app = FastAPI(title="Stock Picker", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL_SECONDS = 15 * 60

# Markov outlook is built from completed weekly bars, so it only changes
# once a week - a long TTL is fine.
_MARKOV_CACHE: dict[str, tuple[float, dict | None]] = {}
_MARKOV_TTL_SECONDS = 60 * 60
_SYMBOL_PATTERN = re.compile(r"^[A-Za-z0-9.\-=^]{1,15}$")


def _markov_cached(symbol: str, include_name: bool = False) -> dict | None:
    now = time.time()
    cached = _MARKOV_CACHE.get(symbol)
    if cached and now - cached[0] < _MARKOV_TTL_SECONDS and (cached[1] is None or not include_name or cached[1].get("name")):
        return cached[1]
    result = compute_markov(symbol, include_name=include_name)
    _MARKOV_CACHE[symbol] = (now, result)
    return result


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


@app.get("/api/markov/universe")
def get_markov_universe(
    sector: str = Query(default="All"),
    continent: str = Query(default="All"),
    asset_type: str = Query(default="All"),
):
    symbols = tickers_for_filters(sector, continent, asset_type)
    results = []
    learning = markov_journal.learning_state(markov_journal.load_journal())
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(_markov_cached, sym): sym for sym in symbols}
        for future in as_completed(futures):
            sym = futures[future]
            result = future.result()
            if result is None:
                continue
            results.append(markov_journal.apply_learning({
                **result,
                "sector": sector_for_ticker(sym),
                "continent": continent_for_ticker(sym),
                "asset_type": asset_type_for_ticker(sym),
            }, learning))
    results.sort(key=lambda r: r["symbol"])
    return {"count": len(results), "learning": learning, "results": results}


@app.get("/api/markov/search")
def search_markov(symbol: str = Query(min_length=1, max_length=15)):
    symbol = symbol.strip().upper()
    if not _SYMBOL_PATTERN.match(symbol):
        raise HTTPException(status_code=400, detail="That doesn't look like a valid ticker symbol")
    result = _markov_cached(symbol, include_name=True)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No price data found for '{symbol}'")
    if asset_type_for_ticker(symbol) is None:
        markov_journal.track_symbol(symbol)  # searched tickers keep being logged and scored
    learning = markov_journal.learning_state(markov_journal.load_journal())
    return markov_journal.apply_learning({
        **result,
        "sector": sector_for_ticker(symbol),
        "continent": continent_for_ticker(symbol),
        "asset_type": asset_type_for_ticker(symbol),
    }, learning)


class NoteRequest(BaseModel):
    text: str


@app.get("/api/markov/journal")
def get_markov_journal():
    return markov_journal.summary()


@app.post("/api/markov/journal/update")
def update_markov_journal():
    return markov_journal.update_journal(_all_tracked_symbols())


@app.get("/api/markov/journal/asset")
def get_markov_journal_asset(symbol: str = Query(min_length=1, max_length=15)):
    return markov_journal.asset_record(markov_journal.load_journal(), symbol.strip().upper())


@app.post("/api/markov/journal/notes")
def add_markov_note(payload: NoteRequest):
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Note is empty")
    return markov_journal.add_note(payload.text)


@app.delete("/api/markov/journal/notes/{note_id}")
def delete_markov_note(note_id: str):
    if not markov_journal.delete_note(note_id):
        raise HTTPException(status_code=404, detail="Note not found")
    return {"deleted": note_id}


class TickerWeight(BaseModel):
    symbol: str
    weight: float


class PortfolioBuyRequest(BaseModel):
    name: str
    amount: float
    tickers: list[TickerWeight]
    force: bool = False


@app.get("/api/portfolios")
def get_portfolios():
    return {"portfolios": list_portfolios()}


@app.get("/api/portfolios/{name}")
def get_portfolio(name: str):
    try:
        return check_portfolio(name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/portfolios")
def create_portfolio(payload: PortfolioBuyRequest):
    tickers = [t.model_dump() for t in payload.tickers]
    try:
        return buy_portfolio(payload.name, payload.amount, tickers, force=payload.force)
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/portfolios/{name}")
def remove_portfolio(name: str):
    if not delete_portfolio(name):
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return {"deleted": name}


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
