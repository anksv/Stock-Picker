# Stock Picker

A personal research tool that screens a curated universe of stocks by
industry sector and price range, scores them using simple technical
indicators, and suggests a historically favorable month to buy. Running it
starts a local web server and opens the results in your browser.

**This is not financial advice.** Scores and "best month" suggestions are
derived from basic technical/seasonal heuristics over historical data and
carry no guarantee about future performance.

## How it works

- **Universe**: a curated list of liquid, well-known US-listed stocks grouped
  by sector (see [`app/universe.py`](app/universe.py)).
- **Screening**: filter by sector, min/max price, recent growth, and
  financial stability.
- **Scoring** (0-100, see [`app/scoring.py`](app/scoring.py)): combines
  50/200-day moving average trend, 14-day RSI, position within the 52-week
  range, and the two fundamentals checks below into a composite score and a
  signal (Strong Buy / Buy / Hold / Avoid / Overbought).
- **Seasonality**: for each stock, average daily closes (normalized per
  year) are grouped by calendar month over the last ~5 years to highlight
  the month that has historically been cheapest relative to the year.
- **Growth filter**: "Growing" means both revenue and earnings grew
  year-over-year in the most recently reported quarter (`revenueGrowth` and
  `earningsQuarterlyGrowth` from Yahoo Finance).
- **Stability filter**: "Financially stable" is a rough solvency proxy, not
  a real bankruptcy model — it requires a current ratio &ge; 1 (can cover
  short-term liabilities), debt/equity below 1.5x, and a positive profit
  margin.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python -m app.main
```

This starts a local server at `http://127.0.0.1:8000` and opens it in your
default browser automatically. Pick a sector and price range and click
**Scan**. Click any row for a detailed breakdown, including the month-by-month
seasonality chart.

The first scan for a sector fetches live data via `yfinance` and can take
up to a minute; results are cached in-memory for 15 minutes.

## Customizing the universe

Edit `UNIVERSE` in [`app/universe.py`](app/universe.py) to add, remove, or
regroup tickers.
