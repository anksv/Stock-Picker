"""Paper-trade portfolio tracker: "buy" a configured basket of stocks/ETFs
with a fixed amount split across them, then check back later to see real
profit/loss against current market prices.

No money moves and no broker is involved - this only simulates a purchase
by recording today's price and fractional share count per ticker, then
compares that to a later real price. It's a personal research aid, not
financial advice.

A portfolio has a currency (USD or EUR) - the one its amount is entered in.
Assets priced in a different currency (e.g. a EUR-priced XETRA ETF in a USD
portfolio) are converted at the live EUR/USD rate, both when buying and when
checking, so currency movement counts toward profit/loss just as it would for
a real investor. Records saved before this had no currency and are read as
USD, which is what they were.

Usable as a library (by app/main.py's API) or as a CLI:
    python -m app.portfolio buy --name my-portfolio --amount 1000 \\
        --currency EUR --config portfolio_config.json
    python -m app.portfolio status --name my-portfolio
    python -m app.portfolio list
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

from app import fx
from app.storage import atomic_write_json

PORTFOLIOS_DIR = Path(__file__).resolve().parent.parent / "portfolios"

CURRENCY_SYMBOLS = {"USD": "$", "EUR": "\u20ac"}

def _currency_note(currency: str, converted: bool) -> str:
    note = f"Amounts are in {currency}."
    if converted:
        note += (" Assets priced in another currency are converted at the live EUR/USD rate, "
                 "so currency movement since purchase counts toward profit/loss.")
    return note


@dataclass
class Position:
    symbol: str
    name: str
    weight_pct: float
    allocated_amount: float
    purchase_price: float
    shares: float
    price_currency: str = "USD"


def _fetch_price_and_name(symbol: str) -> tuple[float, str, str] | None:
    """Lightweight current-price lookup - deliberately not the full
    analyze_ticker pipeline (10y history, income statement, news), since a
    portfolio buy/check only needs today's price.
    """
    try:
        ticker = yf.Ticker(symbol)
        history = ticker.history(period="5d")
        if history is None or history.empty:
            return None
        price = round(float(history["Close"].dropna().iloc[-1]), 4)
        try:
            info = ticker.info or {}
        except Exception:
            info = {}
        name = info.get("longName") or info.get("shortName") or symbol
        return price, name, (info.get("currency") or "USD").upper()
    except Exception:
        return None


def _normalize_weights(entries: list[dict]) -> list[dict]:
    total_weight = sum(float(e["weight"]) for e in entries)
    if total_weight <= 0:
        raise ValueError("Ticker weights must sum to a positive number")
    return [
        {"symbol": e["symbol"].upper(), "weight_pct": round(float(e["weight"]) / total_weight * 100, 4)}
        for e in entries
    ]


def _portfolio_path(name: str) -> Path:
    safe_name = "".join(c for c in name if c.isalnum() or c in ("-", "_")) or "portfolio"
    return PORTFOLIOS_DIR / f"{safe_name}.json"


def buy_portfolio(name: str, amount: float, tickers: list[dict], force: bool = False, currency: str = "USD") -> dict:
    """Records a simulated purchase: splits `amount` (in `currency`) across
    `tickers` (each {"symbol", "weight"}) proportional to weight, at each
    ticker's current price, and saves it. Raises ValueError on bad input, and
    FileExistsError if a portfolio with this name already exists (unless
    force=True, which overwrites it).
    """
    currency = currency.upper()
    if currency not in fx.SUPPORTED:
        raise ValueError(f"Currency must be one of {', '.join(fx.SUPPORTED)}")
    if amount <= 0:
        raise ValueError("Amount must be positive")
    if not tickers:
        raise ValueError("At least one ticker is required")

    path = _portfolio_path(name)
    if path.exists() and not force:
        raise FileExistsError(f"Portfolio '{name}' already exists at {path}. Use force=True to overwrite.")

    normalized = _normalize_weights(tickers)

    priced = []
    skipped: list[str] = []
    for entry in normalized:
        result = _fetch_price_and_name(entry["symbol"])
        # An asset priced in a currency we can't convert would silently
        # corrupt the share count, so it's skipped rather than guessed.
        if result is None or result[2] not in fx.SUPPORTED:
            skipped.append(entry["symbol"])
            continue
        priced.append((entry, *result))

    if not priced:
        raise ValueError(f"Couldn't fetch a usable price for any of: {', '.join(e['symbol'] for e in normalized)}")

    rate = None
    converted = any(price_ccy != currency for _, _, _, price_ccy in priced)
    if converted:
        try:
            rate = fx.eurusd()["rate"]
        except fx.FxUnavailable as exc:
            raise ValueError("EUR/USD exchange rate unavailable right now - try again shortly") from exc

    positions: list[Position] = []
    for entry, price, ticker_name, price_ccy in priced:
        allocated_amount = round(amount * entry["weight_pct"] / 100, 2)
        allocated_native = fx.convert(allocated_amount, currency, price_ccy, rate)
        positions.append(Position(
            symbol=entry["symbol"],
            name=ticker_name,
            weight_pct=entry["weight_pct"],
            allocated_amount=allocated_amount,
            purchase_price=price,
            shares=allocated_native / price,
            price_currency=price_ccy,
        ))

    record = {
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "currency": currency,
        "total_invested": round(sum(p.allocated_amount for p in positions), 2),
        "fx_eurusd_at_purchase": rate,
        "positions": [asdict(p) for p in positions],
        "skipped_symbols": skipped,
    }

    atomic_write_json(path, record)
    return record


def load_portfolio(name: str) -> dict | None:
    path = _portfolio_path(name)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def list_portfolios() -> list[dict]:
    if not PORTFOLIOS_DIR.exists():
        return []
    summaries = []
    for path in sorted(PORTFOLIOS_DIR.glob("*.json")):
        try:
            record = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        summaries.append({
            "name": record["name"],
            "created_at": record["created_at"],
            "total_invested": record["total_invested"],
            "currency": record.get("currency", "USD"),
            "position_count": len(record["positions"]),
        })
    return summaries


def delete_portfolio(name: str) -> bool:
    path = _portfolio_path(name)
    if not path.exists():
        return False
    path.unlink()
    return True


def check_portfolio(name: str) -> dict:
    """Fetches current prices for every position and computes profit/loss
    against the recorded purchase, in the portfolio's own currency. Raises
    FileNotFoundError if no portfolio with this name has been bought yet, and
    fx.FxUnavailable if a conversion is needed but no EUR/USD rate exists.
    """
    record = load_portfolio(name)
    if record is None:
        raise FileNotFoundError(f"No portfolio named '{name}' - buy one first")

    currency = record.get("currency", "USD")  # records saved before currencies existed were USD
    created_at = datetime.fromisoformat(record["created_at"])
    days_held = (datetime.now(timezone.utc) - created_at).days

    needs_fx = any(pos.get("price_currency", "USD") != currency for pos in record["positions"])
    rate = fx.eurusd()["rate"] if needs_fx else None

    positions = []
    total_current_value = 0.0
    unavailable: list[str] = []
    for pos in record["positions"]:
        result = _fetch_price_and_name(pos["symbol"])
        if result is None:
            unavailable.append(pos["symbol"])
            continue
        current_price = result[0]
        price_ccy = pos.get("price_currency", "USD")
        current_value = round(fx.convert(pos["shares"] * current_price, price_ccy, currency, rate), 2)
        pl = round(current_value - pos["allocated_amount"], 2)
        pl_pct = round(pl / pos["allocated_amount"] * 100, 2) if pos["allocated_amount"] else 0.0
        total_current_value += current_value
        positions.append({
            **pos,
            "price_currency": price_ccy,
            "current_price": current_price,
            "current_value": current_value,
            "pl": pl,
            "pl_pct": pl_pct,
        })

    total_current_value = round(total_current_value, 2)
    total_invested = record["total_invested"]
    total_pl = round(total_current_value - total_invested, 2)
    total_pl_pct = round(total_pl / total_invested * 100, 2) if total_invested else 0.0

    return {
        "name": record["name"],
        "created_at": record["created_at"],
        "currency": currency,
        "days_held": days_held,
        "total_invested": total_invested,
        "total_current_value": total_current_value,
        "total_pl": total_pl,
        "total_pl_pct": total_pl_pct,
        "in_profit": total_pl >= 0,
        "positions": positions,
        "unavailable_symbols": unavailable,
        "currency_note": _currency_note(currency, needs_fx),
    }


def _sym(code: str) -> str:
    return CURRENCY_SYMBOLS.get(code, f"{code} ")


def _money(value: float, symbol: str) -> str:
    return f"{'-' if value < 0 else ''}{symbol}{abs(value):.2f}"


def _print_status_report(status: dict) -> None:
    ccy = _sym(status["currency"])
    verdict = "PROFIT" if status["in_profit"] else "LOSS"
    sign = "+" if status["total_pl"] >= 0 else ""
    print(f"\nPortfolio: {status['name']}  (bought {status['days_held']} day(s) ago, amounts in {status['currency']})")
    print(f"Invested:      {_money(status['total_invested'], ccy)}")
    print(f"Current value: {_money(status['total_current_value'], ccy)}")
    print(f"Result:        {verdict}  {sign}{_money(status['total_pl'], ccy)}  ({sign}{status['total_pl_pct']:.2f}%)")
    print(f"\n{'Symbol':<9}{'Shares':>10}{'Buy':>11}{'Now':>11}{'Priced in':>11}{'Value':>11}{'P/L':>12}{'P/L %':>10}")
    for p in status["positions"]:
        sign_p = "+" if p["pl"] >= 0 else ""
        pl_str = f"{sign_p}{p['pl']:.2f}"
        pl_pct_str = f"{sign_p}{p['pl_pct']:.2f}%"
        print(
            f"{p['symbol']:<9}{p['shares']:>10.4f}{p['purchase_price']:>11.2f}"
            f"{p['current_price']:>11.2f}{p['price_currency']:>11}{p['current_value']:>11.2f}"
            f"{pl_str:>12}{pl_pct_str:>10}"
        )
    if status["unavailable_symbols"]:
        print(f"\nCouldn't fetch a current price for: {', '.join(status['unavailable_symbols'])}")
    print(f"\n{status['currency_note']}")
    print("This is a paper-trade simulation, not financial advice or a real brokerage position.\n")


def _load_tickers_arg(args: argparse.Namespace) -> list[dict]:
    if args.config:
        config = json.loads(Path(args.config).read_text())
        return config["tickers"]
    if args.tickers:
        entries = []
        for chunk in args.tickers.split(","):
            symbol, _, weight = chunk.strip().partition(":")
            entries.append({"symbol": symbol.strip(), "weight": float(weight) if weight else 1})
        return entries
    raise SystemExit("Provide either --config <file.json> or --tickers SYM:WEIGHT,SYM:WEIGHT,...")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    buy_parser = subparsers.add_parser("buy", help="Simulate buying a basket of tickers with a fixed amount")
    buy_parser.add_argument("--name", required=True, help="Portfolio name, used to check on it later")
    buy_parser.add_argument("--amount", required=True, type=float, help="Total amount to invest, in --currency")
    buy_parser.add_argument("--currency", default="USD", choices=list(fx.SUPPORTED), help="Currency the amount is in (default USD)")
    buy_parser.add_argument("--config", help="Path to a JSON file with {\"tickers\": [{\"symbol\":..,\"weight\":..}]}")
    buy_parser.add_argument("--tickers", help="Inline alternative to --config, e.g. AAPL:40,MSFT:30,SPY:30")
    buy_parser.add_argument("--force", action="store_true", help="Overwrite an existing portfolio with this name")

    status_parser = subparsers.add_parser("status", help="Check profit/loss on a portfolio against current prices")
    status_parser.add_argument("--name", required=True)

    subparsers.add_parser("list", help="List all saved portfolios")

    args = parser.parse_args()

    if args.command == "buy":
        tickers = _load_tickers_arg(args)
        try:
            record = buy_portfolio(args.name, args.amount, tickers, force=args.force, currency=args.currency)
        except FileExistsError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        ccy = _sym(record["currency"])
        print(f"Bought portfolio '{record['name']}' for {ccy}{record['total_invested']:.2f}:")
        for p in record["positions"]:
            print(f"  {p['symbol']:<9} {p['weight_pct']:>6.2f}%  {ccy}{p['allocated_amount']:>9.2f}  @ {p['purchase_price']:.2f} {p['price_currency']}  -> {p['shares']:.4f} shares")
        if record["skipped_symbols"]:
            print(f"Skipped (no price found): {', '.join(record['skipped_symbols'])}")
        print(f"\nRun `python -m app.portfolio status --name {record['name']}` later to check profit/loss.")

    elif args.command == "status":
        try:
            status = check_portfolio(args.name)
        except (FileNotFoundError, fx.FxUnavailable) as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        _print_status_report(status)

    elif args.command == "list":
        portfolios = list_portfolios()
        if not portfolios:
            print("No portfolios yet. Create one with `python -m app.portfolio buy ...`.")
            return
        for p in portfolios:
            print(f"{p['name']:<20} invested {_sym(p['currency'])}{p['total_invested']:.2f}  ({p['position_count']} positions)  created {p['created_at']}")


if __name__ == "__main__":
    main()
