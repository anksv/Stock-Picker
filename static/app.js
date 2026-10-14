const sectorSelect = document.getElementById("sector");
const continentSelect = document.getElementById("continent");
const assetTypeSelect = document.getElementById("assetType");
const minPriceInput = document.getElementById("minPrice");
const maxPriceInput = document.getElementById("maxPrice");
const requireGrowthInput = document.getElementById("requireGrowth");
const requireStableInput = document.getElementById("requireStable");
const euEtfOnlyInput = document.getElementById("euEtfOnly");
const scanBtn = document.getElementById("scanBtn");
const statusEl = document.getElementById("status");
const resultsBody = document.getElementById("resultsBody");
const detailPanel = document.getElementById("detailPanel");
const detailTitle = document.getElementById("detailTitle");
const detailBody = document.getElementById("detailBody");
const closeDetail = document.getElementById("closeDetail");

let lastResults = [];
let sortKey = "score";
let sortDir = -1;

const MONTH_ORDER = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DESCENDING_BY_DEFAULT = new Set(["price", "score", "week52_position_pct", "rsi14", "business_quality_score", "valuation_score", "verdict_rank"]);

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const EXCHANGE_NAMES = { GER: "XETRA", STU: "Stuttgart", FRA: "Frankfurt", AMS: "Euronext Amsterdam", PCX: "NYSE Arca", NMS: "NASDAQ", NGM: "NASDAQ", NYQ: "NYSE", CCC: "Crypto market" };

// Each asset's amounts are in its own currency (r.currency); Currency converts
// them to whatever is selected at the top of the page.
function money(r, v) {
  return Currency.format(v, r.currency);
}

function compactAmount(r, v) {
  return Currency.compact(v, r.currency);
}

function signalClass(signal) {
  return signal.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z-]/g, "");
}

function qualityClass(label) {
  return "quality-" + label.toLowerCase().replace(/\s*\/\s*/g, "-").replace(/\s+/g, "-");
}

function valuationClass(label) {
  return "valuation-" + label.toLowerCase().replace(/\s+/g, "-");
}

const ASSET_TYPE_LABELS = { ETF: "ETFs only", Stock: "Stocks only", Crypto: "Crypto only" };
const ASSET_TYPE_CLASSES = { ETF: "etf-type", Crypto: "crypto-type" };

function isCompanyStock(r) {
  return r.asset_type === "Stock";
}

function assetTypeClass(assetType) {
  return ASSET_TYPE_CLASSES[assetType] || "stock-type";
}

function nonCompanyNote(assetType) {
  if (assetType === "Crypto") {
    return "Cryptocurrencies aren't companies - they have no revenue, earnings, or management team, so financial-statement fundamentals don't apply. Quality below is based purely on their own price track record.";
  }
  return "ETFs are funds, not companies, so revenue/earnings/margin/debt fundamentals don't apply. Quality below is based on the fund's own price track record.";
}

function sortValue(row, key) {
  if (key === "price") return Currency.amount(row.price, row.currency);
  if (key === "best_buy_month") {
    const idx = MONTH_ORDER.indexOf(row[key]);
    return idx === -1 ? MONTH_ORDER.length : idx;
  }
  return row[key];
}

async function loadSectors() {
  const res = await fetch("/api/sectors");
  const data = await res.json();
  for (const s of data.sectors) {
    const opt = document.createElement("option");
    opt.value = s;
    opt.textContent = s;
    sectorSelect.appendChild(opt);
  }
}

async function loadContinents() {
  const res = await fetch("/api/continents");
  const data = await res.json();
  for (const c of data.continents) {
    const opt = document.createElement("option");
    opt.value = c;
    opt.textContent = c;
    continentSelect.appendChild(opt);
  }
}

async function loadAssetTypes() {
  const res = await fetch("/api/asset-types");
  const data = await res.json();
  for (const t of data.asset_types) {
    const opt = document.createElement("option");
    opt.value = t;
    opt.textContent = ASSET_TYPE_LABELS[t] || `${t} only`;
    assetTypeSelect.appendChild(opt);
  }
}

function renderTable() {
  const rows = [...lastResults].sort((a, b) => {
    const av = sortValue(a, sortKey), bv = sortValue(b, sortKey);
    if (typeof av === "string") return sortDir * av.localeCompare(bv);
    return sortDir * ((av ?? 0) - (bv ?? 0));
  });

  resultsBody.innerHTML = "";
  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="symbol-cell" title="${r.name}">${r.symbol}</td>
      <td><span class="badge ${assetTypeClass(r.asset_type)}">${r.asset_type}</span>${etfTags(r)}</td>
      <td>${r.sector}</td>
      <td>${r.continent}</td>
      <td title="${EXCHANGE_NAMES[r.exchange] ?? r.exchange ?? ""}">${money(r, r.price)}</td>
      <td>${r.rsi14 ?? "-"}</td>
      <td>${r.week52_position_pct}%</td>
      <td><span class="badge ${qualityClass(r.business_quality_label)}" title="${r.business_quality_label} (${r.business_quality_score}/100)">${r.business_quality_label}</span></td>
      <td><span class="badge ${valuationClass(r.valuation_label)}" title="${r.valuation_label} (${r.valuation_score}/100)">${r.valuation_label}</span></td>
      <td>${r.score.toFixed(1)}</td>
      <td>
        <span class="badge ${signalClass(r.signal)}">${r.signal}</span>
        ${horizonBadge(r)}
        ${r.is_new_listing ? '<span class="badge new" title="Listed on the market less than 10 years ago">New</span>' : ""}
      </td>
      <td>${verdictCell(r)}</td>
      <td>${r.best_buy_month}</td>
    `;
    tr.addEventListener("click", () => showDetail(r));
    resultsBody.appendChild(tr);
  }
}

function pct(v) {
  return v === null || v === undefined ? "-" : `${v > 0 ? "+" : ""}${v}%`;
}

function etfFact(label, value) {
  return `<p style="margin:4px 0"><strong>${label}:</strong> ${value}</p>`;
}

function renderEtfChecklist(r) {
  const e = r.etf;
  const yn = (v) => (v === true ? "yes" : v === false ? "no" : "unknown");
  const flags = e.flags.map((f) => `<li class="lesson ${f.kind}">${esc(f.text)}</li>`).join("");
  const unknown = e.unknown_checks.length
    ? `<p class="muted"><strong>Not stated by the data source (unknown, not penalized):</strong> ${e.unknown_checks.map(esc).join(", ")}.</p>`
    : "";
  const manual = e.manual_checks.map((m) => `<li>${esc(m)}</li>`).join("");
  const risk = e.risk_type ? `<span class="badge quality-high-risk-product">${esc(e.risk_type)} - short-term only</span>` : "";

  return `
    <h3 style="margin-bottom: 6px;">ETF Checklist (structure &amp; cost)</h3>
    <p>
      <span class="badge ${qualityClass(r.business_quality_label)}">${esc(r.business_quality_label)}</span> ${risk}
      &nbsp; <strong>ETF score:</strong> ${e.etf_score}/100
      <span class="muted">(${e.checks_known} of 3 measurable checks available: cost, size, diversification)</span>
    </p>
    ${etfFact("Fund type", `${esc(r.etf.etf_type)} <span class="muted">&middot; ${esc(r.etf.theme)}</span>`)}
    ${r.etf.justetf_url ? etfFact("Look it up", `<a href="${esc(r.etf.justetf_url)}" target="_blank" rel="noopener noreferrer">Open on justETF</a> <span class="muted">(tracking difference, country exposure, replication - see the checks below)</span>`) : ""}
    ${etfFact("Expense ratio (TER)", e.expense_ratio_pct === null ? "unknown" : `${e.expense_ratio_pct}% a year`)}
    ${etfFact("Fund size", compactAmount(r, e.fund_size))}
    ${etfFact("Top 10 holdings", e.top10_pct === null ? "unknown" : `${e.top10_pct}% of the fund` + (e.max_holding_pct ? ` (largest single holding ${e.max_holding_pct}%)` : ""))}
    ${e.max_sector ? etfFact("Largest sector", `${esc(e.max_sector.name)} ${e.max_sector.pct}%`) : ""}
    ${etfFact("Distribution", e.distribution ? `${e.distribution} <span class="muted">(from ${esc(e.distribution_source)})</span>` : "unknown")}
    ${etfFact("Domicile", e.domicile ? `${esc(e.domicile)} <span class="muted">(from ${esc(e.domicile_source)})</span>` : "unknown")}
    ${etfFact("Buyable by EU retail investors", `${yn(e.eu_retail_eligible)} <span class="muted">(${e.ucits ? "UCITS fund" : "not marked UCITS"}; usual brokers only offer UCITS/KID funds)</span>`)}
    ${etfFact("Currency-hedged", yn(e.currency_hedged))}
    ${etfFact("Replication", e.replication ? esc(e.replication) : "not stated by the data source")}
    ${e.management_style ? etfFact("Management", esc(e.management_style)) : ""}
    ${etfFact("ISIN", e.isin ? esc(e.isin) : "not available - look it up on the provider's site")}
    ${etfFact("Listed on", `${esc(EXCHANGE_NAMES[r.exchange] ?? r.exchange ?? "?")} in ${esc(r.currency)}`)}

    <ul class="lessons" style="margin-top:10px">${flags}</ul>
    ${unknown}
    <p class="muted"><strong>Deliberately not scored</strong>, following the checklist: historical returns (past growth ${r.price_cagr_10y_pct !== null ? `${pct(r.price_cagr_10y_pct)}/yr over ${r.years_of_price_history} years, shown for reference only` : "not available"}), the fund's base currency, and dividend yield (a dividend-trap signal).</p>
    <p class="muted" style="margin-bottom:2px"><strong>Check these yourself</strong> (not available from the free data source):</p>
    <ul class="muted" style="margin-top:2px; padding-left:18px">${manual}</ul>
  `;
}

const HORIZON_TIPS = {
  "Long-term": "Backed by a durable asset (Quality 60+) whose price isn't stretched, so it is meant to be held through swings and reviewed periodically. Click the row for what to watch.",
  "Short-term": "Leans on momentum rather than a durable, reasonably priced asset (or is crypto, which has no earnings to anchor a long-term case), so watch it closely and expect to exit sooner. Click the row for what to watch.",
};

// Only serious conflicts get a marker in the table; the milder notes are in the
// detail panel so the column stays readable.
const ETF_TYPE_TIPS = {
  "Index fund": "Tracks an index. Assumed when the fund name doesn't say it is actively managed, leveraged or a commodity product - confirm in the KID.",
  "Actively managed": "A manager picks the holdings (named 'active' in the fund name): may outperform an index, but usually costs more.",
  "Leveraged": "Multiplies daily moves and resets every day: risky, not for long-term holding.",
  "Inverse": "Bets against the market and resets daily: at most a short-term trade.",
  "Volatility": "Tracks market volatility and decays by design: short-term trading only.",
  "Commodity product": "Holds a commodity such as gold, not companies (a 'product exchange' fund).",
  "Crypto product": "Holds a coin such as Bitcoin, not companies (a 'product exchange' fund).",
};
const ETF_THEME_TIPS = {
  "Broad market": "Spread across a whole market, such as MSCI World or the S&P 500.",
  "Sector / theme": "Focused on one sector or theme, such as defense or semiconductors: less diversified.",
  "Bond": "Holds bonds rather than shares.",
  "Commodity / crypto": "Holds a commodity or coin directly.",
};
const ETF_TYPE_RISKY = new Set(["Leveraged", "Inverse", "Volatility"]);

// Two small tags under the ETF badge: what kind of fund it is, and how broad.
function etfTags(r) {
  if (!r.etf) return "";
  const risky = ETF_TYPE_RISKY.has(r.etf.etf_type) ? " risky" : "";
  return `<div class="etf-tags">
    <span class="etf-tag${risky}" title="${esc(ETF_TYPE_TIPS[r.etf.etf_type] || "")}">${esc(r.etf.etf_type)}</span>
    <span class="etf-tag" title="${esc(ETF_THEME_TIPS[r.etf.theme] || "")}">${esc(r.etf.theme)}</span>
  </div>`;
}

function verdictCell(r) {
  const warns = r.flags.filter((f) => f.level === "warn");
  const marker = warns.length
    ? ` <span class="flag-marker warn" title="${esc(warns.map((f) => f.text).join("\n"))}">\u26A0 ${warns.length}</span>`
    : "";
  return `<span class="badge verdict-${r.verdict_tone}">${esc(r.verdict)}</span>${marker}`;
}

// How the Quality, Valuation, Signal and trend columns of this row fit together.
function renderVerdict(r) {
  const flags = r.flags.map((f) => `<li class="lesson ${f.level === "warn" ? "warn" : "info"}">${esc(f.text)}</li>`).join("");
  return `
    <h3 style="margin-bottom: 6px;">How the columns fit together</h3>
    <p style="margin: 4px 0">
      <strong>Verdict:</strong> <span class="badge verdict-${r.verdict_tone}">${esc(r.verdict)}</span>
      <span class="muted">Quality ${esc(r.business_quality_label)} (${r.business_quality_score}) &times; Valuation ${esc(r.valuation_label)}</span>
    </p>
    ${r.flags.length
      ? `<ul class="lessons" style="margin: 6px 0 8px">${flags}</ul>`
      : '<p class="muted" style="margin: 4px 0 8px">No conflicts: Signal, Quality, Valuation and trend point the same way.</p>'}
    <p class="muted">The Verdict reads only business quality against price and ignores short-term timing; the Signal covers timing. Flags mark where they disagree. A rule-based prompt, not advice.</p>
  `;
}

function horizonBadge(r) {
  if (!r.horizon) return "";
  const cls = r.horizon === "Long-term" ? "horizon-long" : "horizon-short";
  return `<span class="badge horizon ${cls}" title="${esc(HORIZON_TIPS[r.horizon])}">${esc(r.horizon)}</span>`;
}

// What to watch before selling. The levels come from this asset's own numbers;
// the horizon and its reasons come from the server.
function renderHorizon(r) {
  if (!r.horizon) return "";
  const long = r.horizon === "Long-term";
  const reasons = r.horizon_reasons.map((t) => `<li class="lesson info">${esc(t)}</li>`).join("");

  const triggers = [];
  if (long) {
    triggers.push(r.etf
      ? "The ETF checks worsen: cost rises, the fund shrinks toward the 100M minimum, or it becomes concentrated."
      : `Quality weakens from ${esc(r.business_quality_label)} (${r.business_quality_score}/100).`);
    if (r.valuation_label !== "No Valuation Data") triggers.push(`Valuation turns Overvalued (now ${esc(r.valuation_label)}).`);
    if (r.sma200 !== null) triggers.push(`The price closes below its 200-day average (${money(r, r.sma200)}) - the long-term trend has broken.`);
    triggers.push(r.etf ? "Review a couple of times a year; a long-term fund rarely needs more." : "Review quarterly, for example after each earnings report.");
  } else {
    if (r.sma50 !== null) triggers.push(`The price closes below its 50-day average (${money(r, r.sma50)}) - the short-term trend has turned.`);
    triggers.push(`RSI(14) climbs above 70 (now ${r.rsi14 ?? "n/a"}) - the move may be overextended and the Signal switches to Overbought - Wait.`);
    triggers.push("The Signal falls to Hold or lower.");
    triggers.push("Check weekly - this is a tactical position, not a set-and-forget one.");
  }

  return `
    <h3 style="margin-bottom: 6px;">Holding horizon: ${horizonBadge(r)}</h3>
    <ul class="lessons" style="margin: 6px 0 8px">${reasons}</ul>
    <p style="margin: 4px 0"><strong>When to reconsider selling</strong></p>
    <ul style="margin: 2px 0 6px; padding-left: 18px; font-size: 13px">${triggers.map((t) => `<li>${t}</li>`).join("")}</ul>
    <p class="muted">A rule-based prompt to review, built from the Quality, Valuation and trend figures on this page - not a sell order and not financial advice.</p>
  `;
}

function showDetail(r) {
  detailTitle.textContent = r.name && r.name !== r.symbol ? `${r.name} (${r.symbol})` : r.symbol;
  const seasonCells = r.seasonality
    .map(
      (s) => `<div class="season-cell"><span class="m">${s.month}</span>${
        s.relative_pct === null ? "-" : (s.relative_pct > 0 ? "+" : "") + s.relative_pct + "%"
      }</div>`
    )
    .join("");
  detailBody.innerHTML = `
    <p style="color: var(--muted); margin-top: -8px;">${r.asset_type} &middot; ${r.sector} &middot; ${r.continent}</p>
    <p><strong>Price:</strong> ${money(r, r.price)} (${r.change_pct_1d >= 0 ? "+" : ""}${r.change_pct_1d}% today)</p>
    <p>
      <strong>Signal:</strong> <span class="badge ${signalClass(r.signal)}">${r.signal}</span>
      ${horizonBadge(r)}
      ${r.is_new_listing ? '<span class="badge new">New</span>' : ""}
      &nbsp; <strong>Score:</strong> ${r.score.toFixed(1)}/100
    </p>
    ${renderVerdict(r)}
    ${renderHorizon(r)}
    <p><strong>SMA 50 / 200:</strong> ${r.sma50 ?? "-"} / ${r.sma200 ?? "-"}</p>
    <p><strong>RSI (14d):</strong> ${r.rsi14 ?? "-"}</p>
    <p><strong>52-week range:</strong> ${money(r, r.week52_low)} &ndash; ${money(r, r.week52_high)} (currently at ${r.week52_position_pct}% of range)</p>
    <p><strong>Historically cheapest month to buy:</strong> ${r.best_buy_month}</p>
    <p><strong>Listed since:</strong> ${r.listing_date ?? "unknown"}${r.years_listed !== null && r.years_listed !== undefined ? ` (${r.years_listed} years ago)` : ""}</p>

    ${r.etf ? renderEtfChecklist(r) : `
    ${!isCompanyStock(r) ? `
    <p style="color: var(--muted); font-size: 12px;">
      ${nonCompanyNote(r.asset_type)}
    </p>
    ` : `
    <h3 style="margin-bottom: 6px;">Fundamentals</h3>
    <p>
      <span class="badge ${r.quarterly_growth_positive ? "buy" : "avoid"}">${r.quarterly_growth_positive ? "Growing" : "No recent growth"}</span>
      &nbsp;
      <span class="badge ${r.financially_stable ? "buy" : "avoid"}">${r.financially_stable ? "Financially stable" : "Elevated risk"}</span>
    </p>
    <p><strong>Revenue growth (YoY, last quarter):</strong> ${pct(r.revenue_growth_pct)}</p>
    <p><strong>Earnings growth (YoY, last quarter):</strong> ${pct(r.earnings_growth_pct)}</p>
    <p><strong>Profit margin:</strong> ${pct(r.profit_margin_pct)}</p>
    <p><strong>Current ratio:</strong> ${r.current_ratio ?? "-"} &nbsp; <strong>Debt/Equity:</strong> ${r.debt_to_equity ?? "-"}</p>
    `}

    <h3 style="margin-bottom: 6px;">Business Quality (Long-Term)</h3>
    <p>
      <span class="badge ${qualityClass(r.business_quality_label)}">${r.business_quality_label}</span>
      &nbsp; <strong>Quality score:</strong> ${r.business_quality_score}/100
    </p>
    <p><strong>Price growth:</strong> ${r.price_cagr_10y_pct !== null ? `${pct(r.price_cagr_10y_pct)}/yr over ${r.years_of_price_history} years` : `not enough history yet (${r.years_of_price_history} years)`}</p>
    <p><strong>Year-to-year steadiness:</strong> ${r.price_volatility_10y_pct !== null ? `&plusmn;${r.price_volatility_10y_pct}% swing in annual returns (lower = steadier)` : "-"}</p>
    ${!isCompanyStock(r) ? "" : `
    <p><strong>Profitable years:</strong> ${r.profitable_years_ratio !== null ? `${Math.round(r.profitable_years_ratio * 100)}% of reported fiscal years` : "-"}</p>
    <p><strong>Gross margin (pricing power / customer loyalty):</strong> ${pct(r.gross_margin_pct)}</p>
    <p><strong>R&amp;D spend (product experimentation):</strong> ${r.rnd_to_revenue_pct !== null ? `${pct(r.rnd_to_revenue_pct)} of revenue` : "not reported - likely not an R&amp;D-driven business"}</p>
    `}
    <p style="color: var(--muted); font-size: 12px;">
      Based on up to 10 years of price history and the last ~4-5 fiscal years Yahoo Finance reports for free. A high score favors steady compounding, a consistent profit record, strong stable margins, and low reliance on new-product bets - i.e. a loyal customer base buying the same core products, rather than a company still experimenting to find one.
    </p>

`}

    <h3 style="margin-bottom: 6px;">Valuation</h3>
    <p>
      <span class="badge ${valuationClass(r.valuation_label)}">${r.valuation_label}</span>
      &nbsp; <strong>Valuation score:</strong> ${r.valuation_score}/100
    </p>
    <p><strong>Trailing P/E:</strong> ${r.trailing_pe ?? "-"} &nbsp; <strong>Forward P/E:</strong> ${r.forward_pe ?? "-"}</p>
    <p><strong>PEG ratio:</strong> ${r.peg_ratio ?? "-"}${r.peg_ratio !== null ? (r.peg_ratio <= 1 ? " (cheap relative to growth)" : r.peg_ratio > 3 ? " (expensive relative to growth)" : "") : ""}</p>
    <p><strong>Analyst consensus:</strong> ${r.analyst_recommendation ? `${r.analyst_recommendation} (${r.analyst_recommendation_mean}/5, ${r.analyst_opinion_count ?? "?"} analysts)` : "no analyst coverage"}</p>
    <p style="color: var(--muted); font-size: 12px;">
      P/E and PEG come from Yahoo Finance; "PEG &le; 1" is the classic Peter Lynch cheap-relative-to-growth rule of thumb, not a guarantee. Analyst consensus is Yahoo's own aggregation of sell-side analyst ratings (1 = Strong Buy, 5 = Strong Sell) - note this is <strong>not</strong> Zacks Investment Research data, since Zacks Rank/Style Scores are a paid subscription product with no free public API. A stock with no earnings (P/E) or no analyst coverage (funds, small/foreign names) is valued on whatever of the three is available, or shown "No Valuation Data" if none are.
    </p>

    <h3 style="margin-bottom: 6px;">Competitive Position</h3>
    <p><strong>3-month return:</strong> ${pct(r.return_3m_pct)}</p>
    <p><strong>${r.sector} sector peer average (3m):</strong> ${pct(r.sector_peer_avg_return_3m_pct)}</p>
    <p>
      <strong>vs. peers:</strong>
      ${r.vs_sector_return_pct === null
        ? "not enough peers or history to compare"
        : `<span class="${r.vs_sector_return_pct >= 0 ? "pos" : "neg"}">${r.vs_sector_return_pct >= 0 ? "Outperforming" : "Underperforming"} by ${Math.abs(r.vs_sector_return_pct)}%</span>`}
    </p>
    <p style="color: var(--muted); font-size: 12px;">
      "Peers" are other ${r.sector} assets in your current filters, not a fixed competitor list - this is a real computed number, but the peer group shrinks if you narrow the sector/continent/asset-type filters, and can be too small to be meaningful (e.g. "Cryptocurrency" currently has only a few members).
    </p>

    <h3 style="margin-bottom: 6px;">Recent News</h3>
    ${renderNews(r)}

    <p style="color: var(--muted); font-size: 12px; margin-top: 8px;">
      Seasonality below shows each month's average closing price relative to that year's mean, averaged over the last ~10 years. Negative = historically cheaper.
    </p>
    <div class="season-grid">${seasonCells}</div>
  `;
  detailPanel.classList.remove("hidden");
}

function newsSentimentClass(label) {
  return "news-" + label.toLowerCase().replace(/\s+/g, "-");
}

function renderNews(r) {
  if (!r.news_headlines.length) {
    return `<p style="color: var(--muted); font-size: 13px;">No recent news found for ${r.symbol}.</p>`;
  }

  const items = r.news_headlines
    .map((h) => {
      const date = h.published_at ? new Date(h.published_at).toLocaleDateString() : "";
      const title = h.url
        ? `<a href="${h.url}" target="_blank" rel="noopener noreferrer">${h.title}</a>`
        : h.title;
      return `
        <li class="news-item">
          <span class="news-dot ${h.sentiment}"></span>
          <div>
            <div>${title}</div>
            <div style="color: var(--muted); font-size: 12px;">${h.publisher ?? "Unknown source"}${date ? " &middot; " + date : ""} &middot; via ${h.source_channel}</div>
          </div>
        </li>
      `;
    })
    .join("");

  return `
    <p>
      <strong>Headline tally:</strong>
      <span class="badge ${newsSentimentClass(r.news_sentiment_label)}">${r.news_sentiment_label}</span>
      &nbsp; <strong>Score impact:</strong>
      <span class="${r.news_score_adjustment > 0 ? "pos" : r.news_score_adjustment < 0 ? "neg" : ""}">${r.news_score_adjustment > 0 ? "+" : ""}${r.news_score_adjustment} raw points</span>
    </p>
    <ul class="news-list">${items}</ul>
    <p style="color: var(--muted); font-size: 12px;">
      Merged from Yahoo Finance's own feed and Google News (which surfaces real newspaper/wire coverage - Reuters, Bloomberg, WSJ, etc. - when they cover this ticker). The colored dot, and the score impact above, come from a plain positive/negative keyword count, not real sentiment analysis or NLP - it can easily misread a headline (e.g. "beats" about a competitor). Read the linked articles yourself before acting on anything here. This is intentionally a small, capped nudge to the Score/Signal only - it does not affect Business Quality or Financial Stability, which stay based on structural/factual data.
    </p>
  `;
}

closeDetail.addEventListener("click", () => detailPanel.classList.add("hidden"));
detailPanel.addEventListener("click", (e) => {
  if (e.target === detailPanel) detailPanel.classList.add("hidden");
});

const sortableHeaders = document.querySelectorAll("th[data-key]");

function updateSortIndicators() {
  sortableHeaders.forEach((th) => {
    th.dataset.sort = th.dataset.key === sortKey ? (sortDir === 1 ? "asc" : "desc") : "none";
  });
}

sortableHeaders.forEach((th) => {
  th.addEventListener("click", () => {
    const key = th.dataset.key;
    if (sortKey === key) {
      sortDir *= -1;
    } else {
      sortKey = key;
      sortDir = DESCENDING_BY_DEFAULT.has(key) ? -1 : 1;
    }
    updateSortIndicators();
    renderTable();
  });
});

updateSortIndicators();

let rescanQueued = false;

async function scan() {
  if (scanBtn.disabled) {
    rescanQueued = true; // a scan is already running; run again once it finishes
    return;
  }
  scanBtn.disabled = true;
  statusEl.textContent = "Scanning market data and news... this can take a couple of minutes on first run.";
  resultsBody.innerHTML = "";
  try {
    const params = new URLSearchParams({
      sector: sectorSelect.value,
      continent: continentSelect.value,
      asset_type: assetTypeSelect.value,
      currency: Currency.display,
      min_price: minPriceInput.value || "0",
      max_price: maxPriceInput.value || "100000",
      require_growth: requireGrowthInput.checked,
      require_stable: requireStableInput.checked,
      eu_etf_only: euEtfOnlyInput.checked,
    });
    const res = await fetch(`/api/screen?${params}`);
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const data = await res.json();
    lastResults = data.results;
    statusEl.textContent = data.count
      ? `${data.count} stocks match your filters. Click a row for details.`
      : `0 stocks match your filters. Double-check Min/Max Price - some assets fall outside the default range (e.g. Bitcoin trades around 80,000 USD, far above the default max of 1000).`;
    renderTable();
  } catch (err) {
    statusEl.textContent = `Failed to scan: ${err.message}`;
  } finally {
    scanBtn.disabled = false;
    if (rescanQueued) {
      rescanQueued = false;
      scan();
    }
  }
}

scanBtn.addEventListener("click", scan);

// Switching USD/EUR re-runs the (server-cached) scan so the min/max price
// filter is applied in the new currency, and closes any open detail panel
// rather than leaving it showing the old currency.
Currency.onChange(() => {
  detailPanel.classList.add("hidden");
  scan();
});

// Bitcoin trades around 80,000 USD, far above the default max price of 1000 - if
// someone switches to "Crypto only" without having touched Max Price,
// widen it for them so the obvious first scan isn't a silent zero-result trap.
assetTypeSelect.addEventListener("change", () => {
  if (assetTypeSelect.value === "Crypto" && Number(maxPriceInput.value) <= 1000) {
    maxPriceInput.value = "200000";
  }
});

Promise.all([Currency.ready, loadSectors(), loadContinents(), loadAssetTypes()]).then(scan);
