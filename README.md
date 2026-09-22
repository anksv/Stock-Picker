# Stock Picker

A personal research tool that screens a curated universe of stocks by
industry sector and price range, scores them using simple technical
indicators, and suggests a historically favorable month to buy. It also
includes a paper-trade portfolio tracker: simulate investing a fixed amount
across a basket of tickers, then check back later for real profit/loss.
Running it starts a local web server and opens the results in your
browser.

**This is not financial advice.** Scores and "best month" suggestions are
derived from basic technical/seasonal heuristics over historical data and
carry no guarantee about future performance.

## How it works

- **Universe**: a curated list of liquid, well-known stocks, ETFs, and
  cryptocurrencies (Bitcoin, Ethereum, Solana) tagged by sector, continent,
  and asset type (see [`app/universe.py`](app/universe.py)). Non-US names
  are mostly USD-denominated ADRs so prices stay comparable across the
  whole universe. Sector-focused ETFs (e.g. `XLK` for Technology) reuse the
  same sector names as stocks so they can be compared side by side;
  broad-market, bond, and commodity ETFs get their own pseudo-sectors
  ("Broad Market", "Fixed Income", "Commodities") since GICS sectors don't
  apply to them. Cryptocurrencies trade 24/7 with no single listing venue,
  so they're tagged continent="Global" and sector="Cryptocurrency" instead
  of a geography or GICS sector that doesn't really fit.
- **Screening**: filter by sector, continent, asset type
  (stocks/ETFs/crypto/any combination), min/max price, recent growth, and
  financial stability.
- **ETFs and crypto**: neither is a company, so the revenue/earnings/
  margin/debt fundamentals and growth/stability filters don't apply to them
  (they'll never match "Growing" or "Financially stable" — that's expected,
  not a bug). Their score and business-quality label are based purely on
  their own price track record (CAGR and steadiness), not on financial
  statements. A crypto asset with under ~7 years of price history (e.g.
  Solana) is labeled "Insufficient History" rather than scored on too
  little data.
- **Scoring** (0-100, see [`app/scoring.py`](app/scoring.py)): combines
  50/200-day moving average trend, 14-day RSI, position within the 52-week
  range, the two fundamentals checks below, long-term business quality,
  valuation, and recent news sentiment (all described below) into a
  composite score and a signal (Strong Buy / Buy / Hold / Avoid /
  Overbought). Business quality is weighted as heavily as the short-term
  technicals (up to &plusmn;20 of the 100 points), so a steady long-term
  compounder with weak near-term momentum can still score well, and a
  volatile, loss-making business can't overcome a poor long-term record
  just by looking technically "oversold". Valuation is weighted a bit less
  (up to &plusmn;15) since P/E-style ratios are blunter and more
  context-dependent. News sentiment is a much smaller, capped nudge
  (&plusmn;6, &plusmn;2 for "Mixed") — see the news bullet for why it's
  kept deliberately small and scoped to the score only, not Business
  Quality or Financial Stability.
- **Valuation** ("Valuation" column / detail panel section): "is the
  current price a good deal", independent of how good the business itself
  is (that's what Business Quality answers). Built from three free Yahoo
  Finance fields: trailing P/E, PEG ratio (P/E divided by expected earnings
  growth — PEG &le; 1 is the classic Peter Lynch "cheap relative to growth"
  rule of thumb), and Yahoo's own aggregated analyst consensus (1 = Strong
  Buy ... 5 = Strong Sell across covering analysts). **This is not Zacks
  Investment Research data** — Zacks Rank/Style Scores are a paid
  subscription product with no free public API, so there's no legitimate
  free way to pull them in; Yahoo's analyst-consensus aggregation is the
  closest free, real equivalent. A stock with no earnings (no P/E, common
  for young/loss-making companies), no growth estimate (no PEG), or no
  analyst coverage (ETFs, crypto, small/foreign names) is scored on
  whatever of the three is available, or shown "No Valuation Data" if none
  are — never penalized just for missing data.
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
- **Competitive position** ("vs Sector (3m)" column / detail panel):
  compares an asset's own 3-month price return to the average 3-month
  return of other assets tagged with the same sector *within your current
  sector/continent/asset-type filters* — not a fixed competitor list. This
  is a real, computed number (not fabricated), but the peer group narrows
  if you narrow the filters, and it's a price-performance proxy for
  competitive pressure, not a real competitive/market-share analysis. Not
  folded into the score.
- **Recent news** (detail panel; see [`app/news.py`](app/news.py)): the
  stock's latest headlines merged from two free sources — Yahoo Finance's
  own per-ticker feed, and Google News RSS searched by company name (which
  is what actually surfaces real newspaper/wire-service coverage — Reuters,
  Bloomberg, WSJ, AP, etc. — for a ticker, since none of those outlets has
  a free public API of their own). Each headline shows which source it
  came from and is tagged with a positive/negative/neutral dot from a
  **plain keyword count** — not real sentiment analysis, NLP, or an LLM
  reading the articles. It can easily misread a headline (e.g. "beats"
  about a competitor, an unrelated market headline that mentions the
  ticker). Treat it as a pointer to read the linked articles yourself, not
  a verdict.
  Fetched once per stock *during the scan* (not lazily on click) precisely
  because it now feeds the score, so the Signal shown in the table and the
  breakdown in the detail panel always agree; cached per symbol for 20
  minutes so repeat scans don't re-fetch. Google's own feed license
  restricts the RSS to "a personal feed reader for personal, non-commercial
  use" — fine for this local, single-user tool as-is, but don't adapt this
  code to redistribute the feed or run it as a shared/commercial service.
- **Why news only moves the Score, not Business Quality or Financial
  Stability**: those two are deliberately built from structural, factual
  data — a 10-year price/profitability track record and actual
  balance-sheet ratios (current ratio, debt/equity, profit margin). A
  company's real solvency or long-term durability doesn't change because
  of today's headlines, and blending in a noisy keyword count would make
  those labels less trustworthy (e.g. a financially solid company getting
  flagged "elevated risk" over one unrelated negative headline). News
  sentiment is scoped to the Score/Signal instead, alongside the other
  short-term factors (RSI, moving averages) that are already allowed to
  move day-to-day, and capped small (&plusmn;6, &plusmn;2 for "Mixed")
  relative to those (up to &plusmn;20) given how unreliable the underlying
  keyword count is. The exact points applied are shown in the detail
  panel's Recent News section ("Score impact").
- **On geography and politics**: deliberately not included. There's no
  reliable free, live data source for "how geography/local politics
  impacts this stock" — faking that with hardcoded per-country notes would
  risk being stale or wrong while looking authoritative, in a tool meant
  to inform real decisions. Continent is shown as context; if you have
  access to a real news/political-risk data API you'd like wired in
  instead, that's a natural extension point in `app/news.py`.

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
live data and can take up to a couple of minutes (each ticker needs a
10-year price-history call, a fundamentals call, an annual-financials call,
and now a news call too); results are cached in-memory for 15 minutes. News
itself is cached separately per symbol for 20 minutes.

## Customizing the universe

Edit `STOCKS` in [`app/universe.py`](app/universe.py) to add, remove, or
retag tickers by sector/continent/asset type.

## Portfolio tracker (paper trading)

A separate feature (see [`app/portfolio.py`](app/portfolio.py)) for
"if I'd invested $X across these tickers, would I be up or down by now?" -
no money moves and no broker is involved. It simulates a purchase by
recording today's price and the resulting fractional share count per
ticker, then compares that to a later real price when you check back.

**Web UI**: the **Portfolio** tab (`portfolio.html`) in the running app.
Name the portfolio, set an amount, add tickers with relative weights (they
don't need to sum to 100 - e.g. weights of 2 and 1 mean the first ticker
gets 2/3 of the amount), click **Buy Portfolio**. Click **Check P/L** any
time afterward to see current profit/loss per ticker and overall.

**CLI** (same underlying data, useful for scripting or a cron job):

```bash
# Buy: split $1000 across tickers listed in a config file
python -m app.portfolio buy --name my-portfolio --amount 1000 \
  --config portfolio_config.json

# ...or inline, without a config file (SYMBOL:WEIGHT,...)
python -m app.portfolio buy --name my-portfolio --amount 1000 \
  --tickers AAPL:40,MSFT:30,SPY:30

# Check profit/loss any time later, e.g. after 10 days
python -m app.portfolio status --name my-portfolio

# List all saved portfolios
python -m app.portfolio list
```

Copy [`portfolio_config.example.json`](portfolio_config.example.json) to
`portfolio_config.json` (gitignored, since it's your own input) and edit
the ticker/weight list. Weights are relative, not percentages that must sum
to 100.

**On amounts and currency**: whatever number you pass as `--amount` (or
enter in the web form) is treated as a plain USD-equivalent number, not
converted from EUR or any other currency - every price in this app is
USD-denominated. If you're thinking in EUR, convert to USD yourself first
if you want the simulation to reflect a real amount; this was a deliberate
simplification (no live FX conversion), not an oversight.

Portfolio records are saved as JSON files under `portfolios/` (gitignored -
these are your personal paper-trade records, not project data) and persist
between runs of the app.
