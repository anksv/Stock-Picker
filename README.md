# Stock Picker

A personal research tool that screens a curated universe of stocks by
industry sector and price range, scores them using simple technical
indicators, and suggests a historically favorable month to buy. Running it
starts a local web server and opens the results in your browser.

**This is not financial advice.** Scores and "best month" suggestions are
derived from basic technical/seasonal heuristics over historical data and
carry no guarantee about future performance.

## How it works

- **Universe**: a curated list of liquid, well-known stocks and ETFs tagged
  by sector, continent, and asset type (see
  [`app/universe.py`](app/universe.py)). Non-US names are mostly
  USD-denominated ADRs so prices stay comparable across the whole universe.
  Sector-focused ETFs (e.g. `XLK` for Technology) reuse the same sector
  names as stocks so they can be compared side by side; broad-market, bond,
  and commodity ETFs get their own pseudo-sectors ("Broad Market", "Fixed
  Income", "Commodities") since GICS sectors don't apply to them.
- **Screening**: filter by sector, continent, asset type (stocks/ETFs/both),
  min/max price, recent growth, and financial stability.
- **ETFs**: are funds, not companies, so the revenue/earnings/margin/debt
  fundamentals and growth/stability filters don't apply to them (an ETF
  will never match "Growing" or "Financially stable" — that's expected, not
  a bug). Their score and business-quality label are based purely on the
  fund's own price track record (CAGR and steadiness), not on financial
  statements.
- **Scoring** (0-100, see [`app/scoring.py`](app/scoring.py)): combines
  50/200-day moving average trend, 14-day RSI, position within the 52-week
  range, the two fundamentals checks below, and long-term business quality
  (next bullet) into a composite score and a signal (Strong Buy / Buy /
  Hold / Avoid / Overbought). Business quality is weighted as heavily as
  the short-term technicals (up to &plusmn;20 of the 100 points), so a
  steady long-term compounder with weak near-term momentum can still score
  well, and a volatile, loss-making business can't overcome a poor
  long-term record just by looking technically "oversold".
- **Business quality** ("Business Quality" column / detail panel section):
  answers "has this been a durable, loyal-customer business, or one still
  experimenting?" using what Yahoo Finance exposes for free — up to 10
  years of price history for long-run compounding (CAGR) and year-to-year
  steadiness, plus the last ~4-5 fiscal years of financials for: whether
  every year was profitable, gross margin (a proxy for pricing power that
  only comes from customers who keep buying), and R&amp;D spend as a share
  of revenue (low or unreported ~= relying on an established product line
  rather than constant new-product bets, since many non-R&amp;D-driven
  businesses like consumer staples don't report an R&amp;D line at all). A
  young stock without enough history is labeled "Insufficient History" and
  scored neutrally rather than penalized.
- **Seasonality**: for each stock, average daily closes (normalized per
  year) are grouped by calendar month over the last ~10 years to highlight
  the month that has historically been cheapest relative to the year.
- **Growth filter**: "Growing" means both revenue and earnings grew
  year-over-year in the most recently reported quarter (`revenueGrowth` and
  `earningsQuarterlyGrowth` from Yahoo Finance).
- **Stability filter**: "Financially stable" is a rough solvency proxy, not
  a real bankruptcy model — it requires a current ratio &ge; 1 (can cover
  short-term liabilities), debt/equity below 1.5x, and a positive profit
  margin.
- **New listing highlight**: a blue "New" badge appears next to the signal
  when the stock has traded on the market for less than 10 years (based on
  Yahoo Finance's first-trade date). This reflects listing age, not
  necessarily how old the company itself is.

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
default browser automatically. Pick a sector, continent, asset type, and
price range and click **Scan**. Click any row for a detailed breakdown,
including the company name and the month-by-month seasonality chart.

The first scan for a given sector/continent/asset-type combination fetches
live data via `yfinance` and can take up to a minute or two (each ticker
needs a 10-year price-history call, a fundamentals call, and an
annual-financials call); results are cached in-memory for 15 minutes.

## Customizing the universe

Edit `STOCKS` in [`app/universe.py`](app/universe.py) to add, remove, or
retag tickers by sector/continent/asset type.
