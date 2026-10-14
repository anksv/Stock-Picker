# Stock Picker

A personal research tool that screens a curated universe of stocks by
industry sector and price range, scores them using simple technical
indicators, and suggests a historically favorable month to buy. It also
includes a paper-trade portfolio tracker: simulate investing a fixed amount
across a basket of tickers, then check back later for real profit/loss, and a
Markov Outlook page with next-week odds per asset.
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
  Hover any column header - in the Screener, the Portfolio positions table,
  and the Markov Outlook tables (including the Learning log and the
  transition matrix) - for a definition of that column: what it measures
  and how it's calculated.
- **ETFs and crypto**: neither is a company, so the revenue/earnings/
  margin/debt fundamentals and growth/stability filters don't apply to them
  (they'll never match "Growing" or "Financially stable" — that's expected,
  not a bug). Their score and business-quality label are based purely on
  their own price track record (CAGR and steadiness), not on financial
  statements. A crypto asset with under ~7 years of price history (e.g.
  Solana) is labeled "Insufficient History" rather than scored on too
  little data.
- **ETF checklist** ([`app/etf.py`](app/etf.py); "ETF Checklist" section in the
  detail panel, ETF labels in the **Quality** column): for ETFs the quality
  score comes from the structure of the fund, not its past returns, following
  a European investor's ETF checklist. It scores **cost** (TER), **fund size**
  (under 100M is flagged as closure risk), **diversification** (top-10
  holdings weight, single-holding and sector concentration) and
  **product risk**, plus a small domicile adjustment (Ireland's 15% US
  dividend withholding vs. Luxembourg's 30%, for equity funds). It also
  reports accumulating vs. distributing, currency hedging, UCITS/EU
  availability, domicile, and ISIN. Labels: Top-Tier / Solid / Fair / Weak ETF,
  **High-Risk Product** for leveraged/inverse/volatility ETFs (which are capped
  at a score of 45 and signalled **Short-Term Only** - never ranked as a
  long-term buy), and **Limited Data** when fewer than two of the three
  measurable checks (TER, size, concentration) are available.
  - *Deliberately not scored*, per the checklist: historical returns, the
    fund's base currency, and dividend yield (the "dividend trap" - a
    yield-focused fund such as ISPA.DE gets an explicit warning instead of a
    bonus).
  - *Unknown is unknown*: Yahoo Finance often omits TER, fund size, or
    domicile (e.g. the Vanguard funds have no TER; most iShares funds have no
    size). Missing values are listed as unknown, never penalized or guessed.
    Accumulating/distributing, hedged, swap-based and actively-managed are
    read from the fund name (reliable when providers label the product) or
    the dividend history; domicile comes from the ISIN when available, else
    from an explicit "Ireland"/"Luxembourg" in the fund manager's name.
  - *Not available for free*, so listed as manual checks instead: tracking
    error (check the provider's Performance page by ISIN), KID annual cost
    impact and exit policy, tax registration in your country, replication
    method when the name doesn't say, and country exposure.
  - *US-listed ETFs* (SPY, QQQ, ...) usually can't be bought by EU retail
    investors (no PRIIPs KID). They're flagged, and the **ETFs buyable in the
    EU only (UCITS)** checkbox hides them (strictly: it keeps only ETFs
    confirmed UCITS or EU-listed). The universe now includes 18 XETRA-listed
    UCITS ETFs for this reason - prices there are in EUR, which is why the app
    has a USD/EUR switch (see "USD / EUR display" below).
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
  Those point values (&plusmn;20, &plusmn;15, &plusmn;6, and the trend/RSI
  points) add up to a *raw* total that can exceed 100 or go below 0. It is
  then passed through a smooth soft clamp (`_rescale` in `app/scoring.py`)
  instead of being hard-cut at 0/100, which used to leave many strong assets
  tied at exactly 100. Raw totals from 40 to 70 are unchanged, so every
  Signal threshold (70 / 55 / 40) behaves exactly as before; above 70 the
  curve flattens gradually toward 100 and below 40 toward 0, never reaching
  either, so order is always preserved. The Score is shown to one decimal.
- **ETF type, theme and justETF link** (tags under the Type badge; "Fund type"
  and "Look it up" in the ETF Checklist): each ETF is tagged **Index fund /
  Actively managed / Leveraged / Inverse / Volatility / Commodity product /
  Crypto product** and **Broad market / Sector / theme / Bond / Commodity /
  crypto**, following the checklist's ETF-type and sector-and-theme notes.
  The type comes from the fund's category and name ("Index fund" is assumed
  when nothing says otherwise, which the tooltip states); the theme comes
  from the screener's own sector label. Commodity and crypto products hold
  the asset itself, so the holdings-diversification check is skipped for
  them instead of being listed as unknown. For funds that are EU-tradable and
  have an ISIN, the detail panel links to that fund's justETF profile,
  where tracking difference, country exposure and replication can be checked
  by hand. The link is a plain link you click: nothing is fetched from
  justETF automatically, in line with its terms against automated
  retrieval. US-domiciled funds get no link because justETF doesn't cover
  them.
- **Verdict and conflict flags** ("Verdict" column / "How the columns fit
  together" in the detail panel): relates the Quality and Valuation columns
  of each row. Quality is bucketed (75+ strong, 60+ steady, 40+ mixed, below
  weak) and crossed with the Valuation label, giving a plain-English read
  such as *Core buy: great business, cheap*, *Great business, wait for a
  dip*, or *Possible value trap* (cheap but weak). It deliberately ignores
  short-term timing, which is the Signal's job, and it does not change the
  Score or Signal. Crypto, assets with too little history and leveraged/
  inverse ETFs get a neutral or "not an investment" read instead. **Flags**
  mark where columns disagree, for example a Buy on an Overvalued stock, a
  Buy more than 5% below its 200-day average, RSI 65+ near the top of the
  52-week range, an Overbought - Wait on an otherwise good business, or a
  strong, cheap business with a Hold/Avoid. The table shows a &#9888; only for
  the serious ones; the milder notes are in the detail panel. The column
  sorts from most to least attractive.
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
- **Holding horizon** (Long-term / Short-term tag next to Buy and Strong Buy
  in the Signal column, and a "Holding horizon" section in the detail panel):
  tells you how long a buy is meant to be held, so you know how early or late
  to expect to sell. **Long-term** means the buy is backed by a durable asset
  (Quality of at least 60) whose Valuation isn't "Overvalued" - structure,
  not just a price move, so it can be held through swings. **Short-term**
  means it leans on momentum instead: Quality under 60, thin data, an
  "Overvalued" price, or crypto (which has no earnings or balance sheet, so
  there's nothing but price history to build a long-term case on - it is
  never tagged long-term, however high its score). Hold, Avoid, Overbought -
  Wait and Short-Term Only get no tag, since they already say what to do.
  The detail panel adds the reasons and **what to watch before selling**,
  using this asset's own numbers: for a short-term buy, a close below the
  50-day average, RSI passing 70, or the Signal dropping to Hold, checked
  weekly; for a long-term buy, Quality weakening, Valuation turning
  Overvalued, or a close below the 200-day average, reviewed quarterly (ETFs:
  a couple of times a year). It's a rule-based prompt to review, not a sell
  order and not financial advice - and because this universe is mostly large,
  durable companies, most buys come out long-term (about 9 in 10 today).
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
- **Competitive position** (the "Competitive Position" section of the detail
  panel - click a row; it is no longer a column in the results table):
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

Static files (the HTML/JS/CSS) are served with `Cache-Control: no-cache`, so
the browser re-checks them with the server on every load (an unchanged file
is just a tiny 304) and a normal reload always picks up an update. If a page
ever looks half-updated after you pull new code, restart the server and
hard-refresh once (Cmd+Shift+R) to flush copies cached before this was in place.

The first scan for a given sector/continent/asset-type combination fetches
live data and can take up to a couple of minutes (each ticker needs a
10-year price-history call, a fundamentals call, an annual-financials call,
and now a news call too); results are cached in-memory for 15 minutes. News
itself is cached separately per symbol for 20 minutes.

## Markov Outlook

A third page (**Markov Outlook**, `markov.html`; engine in
[`app/markov.py`](app/markov.py)) that estimates next-week odds for an asset
from its own price history using a simple Markov chain. It has two modes:

- **Pre-computed**: every stock/ETF/crypto in the universe, filterable by
  sector/continent/asset type and sortable. Cached for an hour (it only
  changes once a week) and loads in a few seconds since it needs just the
  price history.
- **Search any ticker**: type any symbol Yahoo Finance knows (including ones
  outside the universe, e.g. `VWCE.DE`) and get the same analysis.

**How it works**: completed weekly returns (up to ~10 years) are bucketed
into Down / Flat / Up, where Down/Up means beyond half a standard deviation
of *that asset's own* weekly moves. Counting how often each state was
followed by each state gives a 3x3 transition matrix; the asset's current
state picks out the row that gives next-week probabilities. The in-progress
week is excluded so it can't distort the current state.

**Why it's deliberately skeptical**: markets are close to memoryless, so
most assets' conditional odds sit near their usual base rate. Each result
therefore includes the *net edge* over the base rate, a significance test
(|z| >= 1.96), and a walk-forward backtest (matrix fitted on the first 60%
of weeks only, then used to call the direction of every later week,
compared to always guessing "up"). The label is **No Clear Edge** unless the
edge is >= 5 percentage points *and* significant. Scanning ~150 assets
produces a handful of "Favorable"/"Unfavorable" results by chance alone, and
in testing the backtest tied the always-up baseline even for assets
flagged Favorable - treat the page as a way to see the odds, not as a buy
signal. It is not folded into the Screener's score.

### Learning log (persistent memory)

The Markov Outlook page's third tab keeps a **prediction journal**
([`app/markov_journal.py`](app/markov_journal.py), saved to
`markov_journal/journal.json` - gitignored, crash-safe atomic writes, survives
restarts). The chain itself already refits from full history on every run, so
the memory that matters is a record of what it *said* versus what the market
*did*:

1. **Log**: once per week per tracked asset (the whole universe plus any
   ticker you've searched), the model's call is saved - state, Up/Flat/Down
   odds, predicted direction, label. A week is only logged if the model runs
   by Monday after that week ends; logging later would let part of the "future"
   week leak into a call that's supposed to come first.
2. **Score**: after the target week finishes, the call is compared with the
   real price move (start and end close come from a single price fetch, so
   dividend/split adjustments can't distort the return). Unfinished weeks are
   never scored.
3. **Learn**: the tab shows direction accuracy vs. always-guessing-up, a
   probability-skill score vs. each asset's usual odds, calibration ("when it
   said Up 40%+, how often did Up happen?"), whether Favorable/Unfavorable
   flags beat the usual rate, the biggest wrong calls (e.g. "called Up, it
   fell 7.9%"), and auto-written lessons. Once there are 200+ scored calls
   across 3+ distinct weeks, a **learning weight** (0-1, the pooled slope of
   outcomes against the model's deviation from usual odds) pulls the displayed
   odds toward usual by however much live results *don't* support them. If the
   model turns out to be noise the weight heads to 0 and the page says so; it
   only trusts the model more if the evidence earns it.
4. **Notes**: add your own notes on the same tab; they persist too.

It checks automatically ~20 seconds after the server starts and every 12
hours while it runs, or via the **Check real prices now** button. For a daily
job without the server running (e.g. cron):

```bash
python -m app.markov_journal update   # score finished weeks, log new calls
python -m app.markov_journal report   # print the scoreboard and lessons
```

Be realistic about speed: each asset gets one prediction a week, so the
journal needs several weeks before it says anything. The pooled view across
the universe fills faster, but all assets move with the market in any given
week, which is why learning waits for multiple distinct weeks.

## USD / EUR display

Every page has a **Show values in USD / EUR** switch at the top right, next to
the live rate (EUR/USD from Yahoo Finance, cached for an hour; if a refresh
fails the last rate is reused for up to a day and labelled "stale"; if there
has never been one the switch says so and values stay in their native
currency - no rate is ever invented). The choice is remembered across pages
and reloads.

- **Screener**: prices, 52-week range and ETF fund sizes are converted for
  display, and the **Min/Max Price** filters are interpreted in the selected
  currency (each asset's price is converted before comparing - e.g. a
  EUR 95 fund counts as USD 106.79 against a USD 100 limit). Switching re-runs
  the scan from the server's cache, and sorting by price orders by the
  displayed amount, so USD and EUR assets sort together correctly.
- **Portfolio**: totals, values and profit/loss are converted for display,
  and the amount you enter for a new portfolio is in the selected currency.
  Percentages never change with the currency.
- **Markov Outlook**: shows probabilities and percentages only, so there is
  nothing to convert; the switch is there for consistency and the page says so.
- Only USD and EUR convert. A value in any other currency is shown in its own
  currency and symbol rather than converted wrongly.

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
# Buy: split 1000 (USD by default) across tickers listed in a config file
python -m app.portfolio buy --name my-portfolio --amount 1000 \
  --config portfolio_config.json

# ...or invest 1000 EUR instead
python -m app.portfolio buy --name my-eur-portfolio --amount 1000 \
  --currency EUR --tickers AAPL:1,VWCE.DE:1

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

**On amounts and currency**: each portfolio has a currency (USD or EUR) - the
one its amount was entered in (`--currency`, or whichever currency is
selected at the top of the page when you click Buy). Assets priced in the
other currency are converted at the live EUR/USD rate when buying (so a
EUR 500 slice of a US stock becomes the right number of shares) and again when
checking, so currency movement counts toward profit/loss exactly as it
would for a real investor holding foreign assets. Assets priced in any other
currency are skipped rather than mis-converted. Portfolios saved before
currencies existed have no currency field and are read as USD, which is what
they were.

Portfolio records are saved as JSON files under `portfolios/` (gitignored -
these are your personal paper-trade records, not project data) and persist
between runs of the app.
