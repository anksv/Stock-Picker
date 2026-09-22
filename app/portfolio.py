"""Paper-trade portfolio tracker: "buy" a configured basket of stocks/ETFs
with a fixed amount split across them, then check back later to see real
profit/loss against current market prices.

No money moves and no broker is involved - this only simulates a purchase
by recording today's price and fractional share count per ticker, then
compares that to a later real price. It's a personal research aid, not
financial advice.

Amounts are treated as plain USD-equivalent numbers, not converted from any
other currency, since every price in this app is USD-denominated (see
README). If you're thinking in EUR or another currency, convert the amount
yourself before passing it in.

Usable as a library (by app/main.py's API) or as a CLI:
    python -m app.portfolio buy --name my-portfolio --amount 1000 \\
        --config portfolio_config.json
    python -m app.portfolio status --name my-portfolio
    python -m app.portfolio list
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

PORTFOLIOS_DIR = Path(__file__).resolve().parent.parent / "portfolios"

CURRENCY_NOTE = (
    "Amount is treated as a plain USD-equivalent number, not converted from "
    "EUR or any other currency - every price in this app is USD-denominated."
)


@dataclass
class Position:
    symbol: str
    name: str
    weight_pct: float
    allocated_amount: float
    purchase_price: float
    shares: float


def _fetch_price_and_name(symbol: str) -> tuple[float, str] | None:
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
        return price, name
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


def _atomic_write_json(path: Path, data: dict) -> None:
    """Writes via a temp file + os.replace so a crash or power loss mid-save
    can never leave a half-written, corrupted portfolio file - the rename is
    atomic, so readers always see either the old file or the fully-new one.
    """
    path.parent.mkdir(exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(data, indent=2))
        os.replace(tmp_path, path)
    except BaseException:
        os.unlink(tmp_path)
        raise


def buy_portfolio(name: str, amount: float, tickers: list[dict], force: bool = False) -> dict:
    """Records a simulated purchase: splits `amount` across `tickers`
    (each {"symbol", "weight"}) proportional to weight, at each ticker's
    current price, and saves it. Raises ValueError on bad input, and
    FileExistsError if a portfolio with this name already exists (unless
    force=True, which overwrites it).
    """
    if amount <= 0:
        raise ValueError("Amount must be positive")
    if not tickers:
        raise ValueError("At least one ticker is required")

    path = _portfolio_path(name)
    if path.exists() and not force:
        raise FileExistsError(f"Portfolio '{name}' already exists at {path}. Use force=True to overwrite.")

    normalized = _normalize_weights(tickers)

    positions: list[Position] = []
    skipped: list[str] = []
    for entry in normalized:
        symbol = entry["symbol"]
        result = _fetch_price_and_name(symbol)
        if result is None:
            skipped.append(symbol)
            continue
        price, ticker_name = result
        allocated_amount = round(amount * entry["weight_pct"] / 100, 2)
        shares = allocated_amount / price
        positions.append(Position(
            symbol=symbol,
            name=ticker_name,
            weight_pct=entry["weight_pct"],
            allocated_amount=allocated_amount,
            purchase_price=price,
            shares=shares,
        ))

    if not positions:
        raise ValueError(f"Couldn't fetch a price for any of: {', '.join(e['symbol'] for e in normalized)}")

    record = {
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "total_invested": round(sum(p.allocated_amount for p in positions), 2),
        "currency_note": CURRENCY_NOTE,
        "positions": [asdict(p) for p in positions],
        "skipped_symbols": skipped,
    }

    _atomic_write_json(path, record)
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
    against the recorded purchase. Raises FileNotFoundError if no
    portfolio with this name has been bought yet.
    """
    record = load_portfolio(name)
    if record is None:
        raise FileNotFoundError(f"No portfolio named '{name}' - buy one first")

    created_at = datetime.fromisoformat(record["created_at"])
    days_held = (datetime.now(timezone.utc) - created_at).days

    positions = []
    total_current_value = 0.0
    unavailable: list[str] = []
    for pos in record["positions"]:
        result = _fetch_price_and_name(pos["symbol"])
        if result is None:
            unavailable.append(pos["symbol"])
            continue
        current_price, _ = result
        current_value = round(pos["shares"] * current_price, 2)
        pl = round(current_value - pos["allocated_amount"], 2)
        pl_pct = round(pl / pos["allocated_amount"] * 100, 2) if pos["allocated_amount"] else 0.0
        total_current_value += current_value
        positions.append({
            **pos,
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
        "days_held": days_held,
        "total_invested": total_invested,
        "total_current_value": total_current_value,
        "total_pl": total_pl,
        "total_pl_pct": total_pl_pct,
        "in_profit": total_pl >= 0,
        "positions": positions,
        "unavailable_symbols": unavailable,
        "currency_note": record.get("currency_note", CURRENCY_NOTE),
    }


def _print_status_report(status: dict) -> None:
    verdict = "PROFIT" if status["in_profit"] else "LOSS"
    sign = "+" if status["total_pl"] >= 0 else ""
    print(f"\nPortfolio: {status['name']}  (bought {status['days_held']} day(s) ago)")
    print(f"Invested:      ${status['total_invested']:.2f}")
    print(f"Current value: ${status['total_current_value']:.2f}")
    print(f"Result:        {verdict}  {sign}${status['total_pl']:.2f}  ({sign}{status['total_pl_pct']:.2f}%)")
    print(f"\n{'Symbol':<8}{'Shares':>10}{'Buy $':>10}{'Now $':>10}{'Value $':>10}{'P/L $':>12}{'P/L %':>10}")
    for p in status["positions"]:
        sign_p = "+" if p["pl"] >= 0 else ""
        pl_str = f"{sign_p}{p['pl']:.2f}"
        pl_pct_str = f"{sign_p}{p['pl_pct']:.2f}%"
        print(
            f"{p['symbol']:<8}{p['shares']:>10.4f}{p['purchase_price']:>10.2f}"
            f"{p['current_price']:>10.2f}{p['current_value']:>10.2f}"
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
    buy_parser.add_argument("--amount", required=True, type=float, help="Total amount to invest (USD-equivalent)")
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
            record = buy_portfolio(args.name, args.amount, tickers, force=args.force)
        except FileExistsError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"Bought portfolio '{record['name']}' for ${record['total_invested']:.2f}:")
        for p in record["positions"]:
            print(f"  {p['symbol']:<8} {p['weight_pct']:>6.2f}%  ${p['allocated_amount']:>9.2f}  @ ${p['purchase_price']:.2f}  -> {p['shares']:.4f} shares")
        if record["skipped_symbols"]:
            print(f"Skipped (no price found): {', '.join(record['skipped_symbols'])}")
        print(f"\nRun `python -m app.portfolio status --name {record['name']}` later to check profit/loss.")

    elif args.command == "status":
        try:
            status = check_portfolio(args.name)
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        _print_status_report(status)

    elif args.command == "list":
        portfolios = list_portfolios()
        if not portfolios:
            print("No portfolios yet. Create one with `python -m app.portfolio buy ...`.")
            return
        for p in portfolios:
            print(f"{p['name']:<20} invested ${p['total_invested']:.2f}  ({p['position_count']} positions)  created {p['created_at']}")


if __name__ == "__main__":
    main()
