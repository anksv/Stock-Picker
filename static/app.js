const sectorSelect = document.getElementById("sector");
const minPriceInput = document.getElementById("minPrice");
const maxPriceInput = document.getElementById("maxPrice");
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

function signalClass(signal) {
  return signal.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z-]/g, "");
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

function renderTable() {
  const rows = [...lastResults].sort((a, b) => {
    const av = a[sortKey], bv = b[sortKey];
    if (typeof av === "string") return sortDir * av.localeCompare(bv);
    return sortDir * ((av ?? 0) - (bv ?? 0));
  });

  resultsBody.innerHTML = "";
  for (const r of rows) {
    const tr = document.createElement("tr");
    const changeClass = r.change_pct_1d >= 0 ? "pos" : "neg";
    tr.innerHTML = `
      <td class="symbol-cell">${r.symbol}</td>
      <td>${r.sector}</td>
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

function showDetail(r) {
  detailTitle.textContent = `${r.symbol} · ${r.sector}`;
  const seasonCells = r.seasonality
    .map(
      (s) => `<div class="season-cell"><span class="m">${s.month}</span>${
        s.relative_pct === null ? "-" : (s.relative_pct > 0 ? "+" : "") + s.relative_pct + "%"
      }</div>`
    )
    .join("");
  detailBody.innerHTML = `
    <p><strong>Price:</strong> $${r.price.toFixed(2)} (${r.change_pct_1d >= 0 ? "+" : ""}${r.change_pct_1d}% today)</p>
    <p><strong>Signal:</strong> <span class="badge ${signalClass(r.signal)}">${r.signal}</span> &nbsp; <strong>Score:</strong> ${r.score}/100</p>
    <p><strong>SMA 50 / 200:</strong> ${r.sma50 ?? "-"} / ${r.sma200 ?? "-"}</p>
    <p><strong>RSI (14d):</strong> ${r.rsi14 ?? "-"}</p>
    <p><strong>52-week range:</strong> $${r.week52_low} &ndash; $${r.week52_high} (currently at ${r.week52_position_pct}% of range)</p>
    <p><strong>Historically cheapest month to buy:</strong> ${r.best_buy_month}</p>
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

document.querySelectorAll("th[data-key]").forEach((th) => {
  th.addEventListener("click", () => {
    const key = th.dataset.key;
    if (sortKey === key) {
      sortDir *= -1;
    } else {
      sortKey = key;
      sortDir = -1;
    }
    renderTable();
  });
});

async function scan() {
  scanBtn.disabled = true;
  statusEl.textContent = "Scanning market data... this can take up to a minute on first run.";
  resultsBody.innerHTML = "";
  try {
    const params = new URLSearchParams({
      sector: sectorSelect.value,
      min_price: minPriceInput.value || "0",
      max_price: maxPriceInput.value || "100000",
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

loadSectors().then(scan);
