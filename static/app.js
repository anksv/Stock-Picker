const sectorSelect = document.getElementById("sector");
const continentSelect = document.getElementById("continent");
const assetTypeSelect = document.getElementById("assetType");
const minPriceInput = document.getElementById("minPrice");
const maxPriceInput = document.getElementById("maxPrice");
const requireGrowthInput = document.getElementById("requireGrowth");
const requireStableInput = document.getElementById("requireStable");
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
const DESCENDING_BY_DEFAULT = new Set(["price", "score", "change_pct_1d", "week52_position_pct", "rsi14", "business_quality_score", "vs_sector_return_pct"]);

function signalClass(signal) {
  return signal.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z-]/g, "");
}

function qualityClass(label) {
  return "quality-" + label.toLowerCase().replace(/\s*\/\s*/g, "-").replace(/\s+/g, "-");
}

const ASSET_TYPE_LABELS = { ETF: "ETFs only", Stock: "Stocks only", Bitcoin: "Bitcoin only" };
const ASSET_TYPE_CLASSES = { ETF: "etf-type", Bitcoin: "crypto-type" };

function isCompanyStock(r) {
  return r.asset_type === "Stock";
}

function assetTypeClass(assetType) {
  return ASSET_TYPE_CLASSES[assetType] || "stock-type";
}

function nonCompanyNote(assetType) {
  if (assetType === "Bitcoin") {
    return "Bitcoin isn't a company - it has no revenue, earnings, or management team, so financial-statement fundamentals don't apply. Quality below is based purely on its own price track record.";
  }
  return "ETFs are funds, not companies, so revenue/earnings/margin/debt fundamentals don't apply. Quality below is based on the fund's own price track record.";
}

function sortValue(row, key) {
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
    const changeClass = r.change_pct_1d >= 0 ? "pos" : "neg";
    tr.innerHTML = `
      <td class="symbol-cell" title="${r.name}">${r.symbol}</td>
      <td><span class="badge ${assetTypeClass(r.asset_type)}">${r.asset_type}</span></td>
      <td>${r.sector}</td>
      <td>${r.continent}</td>
      <td>$${r.price.toFixed(2)}</td>
      <td class="${changeClass}">${r.change_pct_1d.toFixed(2)}%</td>
      <td>${r.rsi14 ?? "-"}</td>
      <td>${r.week52_position_pct}%</td>
      <td>${r.score}</td>
      <td>
        <span class="badge ${signalClass(r.signal)}">${r.signal}</span>
        ${r.is_new_listing ? '<span class="badge new" title="Listed on the market less than 10 years ago">New</span>' : ""}
      </td>
      <td><span class="badge ${qualityClass(r.business_quality_label)}" title="${r.business_quality_label} (${r.business_quality_score}/100)">${r.business_quality_label}</span></td>
      <td class="${r.vs_sector_return_pct === null ? "" : r.vs_sector_return_pct >= 0 ? "pos" : "neg"}" title="3-month return vs. average of same-sector peers in your current results">${r.vs_sector_return_pct === null ? "-" : pct(r.vs_sector_return_pct)}</td>
      <td>${r.best_buy_month}</td>
    `;
    tr.addEventListener("click", () => showDetail(r));
    resultsBody.appendChild(tr);
  }
}

function pct(v) {
  return v === null || v === undefined ? "-" : `${v > 0 ? "+" : ""}${v}%`;
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
    <p><strong>Price:</strong> $${r.price.toFixed(2)} (${r.change_pct_1d >= 0 ? "+" : ""}${r.change_pct_1d}% today)</p>
    <p>
      <strong>Signal:</strong> <span class="badge ${signalClass(r.signal)}">${r.signal}</span>
      ${r.is_new_listing ? '<span class="badge new">New</span>' : ""}
      &nbsp; <strong>Score:</strong> ${r.score}/100
    </p>
    <p><strong>SMA 50 / 200:</strong> ${r.sma50 ?? "-"} / ${r.sma200 ?? "-"}</p>
    <p><strong>RSI (14d):</strong> ${r.rsi14 ?? "-"}</p>
    <p><strong>52-week range:</strong> $${r.week52_low} &ndash; $${r.week52_high} (currently at ${r.week52_position_pct}% of range)</p>
    <p><strong>Historically cheapest month to buy:</strong> ${r.best_buy_month}</p>
    <p><strong>Listed since:</strong> ${r.listing_date ?? "unknown"}${r.years_listed !== null && r.years_listed !== undefined ? ` (${r.years_listed} years ago)` : ""}</p>

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
      "Peers" are other ${r.sector} assets in your current filters, not a fixed competitor list - this is a real computed number, but the peer group shrinks if you narrow the sector/continent/asset-type filters (Bitcoin is currently the only asset tagged "Cryptocurrency", so it has no peers to compare against).
    </p>

    <h3 style="margin-bottom: 6px;">Recent News</h3>
    <div id="newsSection"><p style="color: var(--muted); font-size: 13px;">Loading recent news&hellip;</p></div>

    <p style="color: var(--muted); font-size: 12px; margin-top: 8px;">
      Seasonality below shows each month's average closing price relative to that year's mean, averaged over the last ~10 years. Negative = historically cheaper.
    </p>
    <div class="season-grid">${seasonCells}</div>
  `;
  detailPanel.classList.remove("hidden");
  loadNews(r.symbol);
}

function newsSentimentClass(label) {
  return "news-" + label.toLowerCase().replace(/\s+/g, "-");
}

async function loadNews(symbol) {
  const container = document.getElementById("newsSection");
  try {
    const res = await fetch(`/api/news/${encodeURIComponent(symbol)}`);
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const data = await res.json();
    // The panel may have been closed/reopened on a different symbol while this was in flight.
    const current = document.getElementById("newsSection");
    if (!current) return;

    if (!data.headlines.length) {
      current.innerHTML = `<p style="color: var(--muted); font-size: 13px;">No recent news found for ${symbol}.</p>`;
      return;
    }

    const items = data.headlines
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
              <div style="color: var(--muted); font-size: 12px;">${h.publisher ?? "Unknown source"}${date ? " &middot; " + date : ""}</div>
            </div>
          </li>
        `;
      })
      .join("");

    current.innerHTML = `
      <p>
        <strong>Headline tally:</strong>
        <span class="badge ${newsSentimentClass(data.sentiment_label)}">${data.sentiment_label}</span>
      </p>
      <ul class="news-list">${items}</ul>
      <p style="color: var(--muted); font-size: 12px;">
        This is a plain positive/negative keyword count over the headlines below, not real sentiment analysis or NLP - it can easily misread a headline (e.g. "beats" about a competitor). Read the linked articles yourself before acting on anything here.
      </p>
    `;
  } catch (err) {
    const current = document.getElementById("newsSection");
    if (current) {
      current.innerHTML = `<p style="color: var(--muted); font-size: 13px;">Couldn't load news: ${err.message}</p>`;
    }
  }
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

async function scan() {
  scanBtn.disabled = true;
  statusEl.textContent = "Scanning market data... this can take up to a minute on first run.";
  resultsBody.innerHTML = "";
  try {
    const params = new URLSearchParams({
      sector: sectorSelect.value,
      continent: continentSelect.value,
      asset_type: assetTypeSelect.value,
      min_price: minPriceInput.value || "0",
      max_price: maxPriceInput.value || "100000",
      require_growth: requireGrowthInput.checked,
      require_stable: requireStableInput.checked,
    });
    const res = await fetch(`/api/screen?${params}`);
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const data = await res.json();
    lastResults = data.results;
    statusEl.textContent = data.count
      ? `${data.count} stocks match your filters. Click a row for details.`
      : `0 stocks match your filters. Double-check Min/Max Price - some assets fall outside the default range (e.g. Bitcoin trades around $80k+, well above the default $1000 max).`;
    renderTable();
  } catch (err) {
    statusEl.textContent = `Failed to scan: ${err.message}`;
  } finally {
    scanBtn.disabled = false;
  }
}

scanBtn.addEventListener("click", scan);

// Bitcoin trades around $80k+, well above the default $1000 max price - if
// someone switches to "Bitcoin only" without having touched Max Price,
// widen it for them so the obvious first scan isn't a silent zero-result trap.
assetTypeSelect.addEventListener("change", () => {
  if (assetTypeSelect.value === "Bitcoin" && Number(maxPriceInput.value) <= 1000) {
    maxPriceInput.value = "200000";
  }
});

Promise.all([loadSectors(), loadContinents(), loadAssetTypes()]).then(scan);
