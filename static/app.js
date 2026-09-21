const sectorSelect = document.getElementById("sector");
const continentSelect = document.getElementById("continent");
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
const DESCENDING_BY_DEFAULT = new Set(["price", "score", "change_pct_1d", "week52_position_pct", "rsi14"]);

function signalClass(signal) {
  return signal.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z-]/g, "");
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
      <td>${r.sector}</td>
      <td>${r.continent}</td>
      <td>$${r.price.toFixed(2)}</td>
      <td class="${changeClass}">${r.change_pct_1d.toFixed(2)}%</td>
      <td>${r.rsi14 ?? "-"}</td>
      <td>${r.week52_position_pct}%</td>
      <td>${r.score}</td>
      <td><span class="badge ${signalClass(r.signal)}">${r.signal}</span></td>
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
    <p style="color: var(--muted); margin-top: -8px;">${r.sector} &middot; ${r.continent}</p>
    <p><strong>Price:</strong> $${r.price.toFixed(2)} (${r.change_pct_1d >= 0 ? "+" : ""}${r.change_pct_1d}% today)</p>
    <p><strong>Signal:</strong> <span class="badge ${signalClass(r.signal)}">${r.signal}</span> &nbsp; <strong>Score:</strong> ${r.score}/100</p>
    <p><strong>SMA 50 / 200:</strong> ${r.sma50 ?? "-"} / ${r.sma200 ?? "-"}</p>
    <p><strong>RSI (14d):</strong> ${r.rsi14 ?? "-"}</p>
    <p><strong>52-week range:</strong> $${r.week52_low} &ndash; $${r.week52_high} (currently at ${r.week52_position_pct}% of range)</p>
    <p><strong>Historically cheapest month to buy:</strong> ${r.best_buy_month}</p>

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

    <p style="color: var(--muted); font-size: 12px; margin-top: 8px;">
      Seasonality below shows each month's average closing price relative to that year's mean, averaged over the last ~5 years. Negative = historically cheaper.
    </p>
    <div class="season-grid">${seasonCells}</div>
  `;
  detailPanel.classList.remove("hidden");
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
      min_price: minPriceInput.value || "0",
      max_price: maxPriceInput.value || "100000",
      require_growth: requireGrowthInput.checked,
      require_stable: requireStableInput.checked,
    });
    const res = await fetch(`/api/screen?${params}`);
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const data = await res.json();
    lastResults = data.results;
    statusEl.textContent = `${data.count} stocks match your filters. Click a row for details.`;
    renderTable();
  } catch (err) {
    statusEl.textContent = `Failed to scan: ${err.message}`;
  } finally {
    scanBtn.disabled = false;
  }
}

scanBtn.addEventListener("click", scan);

Promise.all([loadSectors(), loadContinents()]).then(scan);
