const pfNameInput = document.getElementById("pfName");
const pfAmountInput = document.getElementById("pfAmount");
const tickerRowsBody = document.getElementById("tickerRowsBody");
const addTickerBtn = document.getElementById("addTickerBtn");
const buyBtn = document.getElementById("buyBtn");
const pfStatusEl = document.getElementById("pfStatus");
const portfolioListEl = document.getElementById("portfolioList");

function addTickerRow(symbol = "", weight = 1) {
  const tr = document.createElement("tr");
  tr.innerHTML = `
    <td><input type="text" class="ticker-symbol" placeholder="AAPL" value="${symbol}" style="text-transform:uppercase" /></td>
    <td><input type="number" class="ticker-weight" min="0" step="0.1" value="${weight}" style="width:80px" /></td>
    <td><button type="button" class="remove-row-btn" title="Remove">&times;</button></td>
  `;
  tr.querySelector(".remove-row-btn").addEventListener("click", () => tr.remove());
  tickerRowsBody.appendChild(tr);
}

addTickerBtn.addEventListener("click", () => addTickerRow());

function collectTickers() {
  return Array.from(tickerRowsBody.querySelectorAll("tr"))
    .map((tr) => ({
      symbol: tr.querySelector(".ticker-symbol").value.trim().toUpperCase(),
      weight: parseFloat(tr.querySelector(".ticker-weight").value),
    }))
    .filter((t) => t.symbol && !Number.isNaN(t.weight) && t.weight > 0);
}

async function buyPortfolio() {
  const name = pfNameInput.value.trim();
  const amount = parseFloat(pfAmountInput.value);
  const tickers = collectTickers();

  if (!name) {
    pfStatusEl.textContent = "Give the portfolio a name.";
    return;
  }
  if (!amount || amount <= 0) {
    pfStatusEl.textContent = "Enter a positive amount.";
    return;
  }
  if (!tickers.length) {
    pfStatusEl.textContent = "Add at least one ticker with a weight.";
    return;
  }

  buyBtn.disabled = true;
  pfStatusEl.textContent = "Buying...";
  try {
    const res = await fetch("/api/portfolios", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, amount, tickers }),
    });
    const data = await res.json();
    if (!res.ok) {
      if (res.status === 409) {
        const overwrite = confirm(`Portfolio "${name}" already exists. Overwrite it with a new purchase?`);
        if (overwrite) {
          const res2 = await fetch("/api/portfolios", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name, amount, tickers, force: true }),
          });
          const data2 = await res2.json();
          if (!res2.ok) throw new Error(data2.detail || `Server error ${res2.status}`);
          pfStatusEl.textContent = `Bought "${name}" for $${data2.total_invested.toFixed(2)}.`;
          await loadPortfolios();
          return;
        }
        pfStatusEl.textContent = "Cancelled.";
        return;
      }
      throw new Error(data.detail || `Server error ${res.status}`);
    }
    pfStatusEl.textContent = `Bought "${name}" for $${data.total_invested.toFixed(2)}.`;
    if (data.skipped_symbols && data.skipped_symbols.length) {
      pfStatusEl.textContent += ` Couldn't price: ${data.skipped_symbols.join(", ")}.`;
    }
    await loadPortfolios();
  } catch (err) {
    pfStatusEl.textContent = `Failed to buy: ${err.message}`;
  } finally {
    buyBtn.disabled = false;
  }
}

buyBtn.addEventListener("click", buyPortfolio);

function pct(v) {
  return v === null || v === undefined ? "-" : `${v > 0 ? "+" : ""}${v}%`;
}

function money(v) {
  return `$${v.toFixed(2)}`;
}

async function loadPortfolios() {
  portfolioListEl.innerHTML = `<p style="color: var(--muted);">Loading portfolios&hellip;</p>`;
  const res = await fetch("/api/portfolios");
  const data = await res.json();

  if (!data.portfolios.length) {
    portfolioListEl.innerHTML = `<p style="color: var(--muted);">No portfolios yet. Buy one above.</p>`;
    return;
  }

  portfolioListEl.innerHTML = "";
  for (const p of data.portfolios) {
    const card = document.createElement("div");
    card.className = "portfolio-card";
    card.innerHTML = `
      <div class="portfolio-card-header">
        <div>
          <strong>${p.name}</strong>
          <span style="color: var(--muted); font-size: 12px;">
            &middot; ${p.position_count} position(s) &middot; invested ${money(p.total_invested)} &middot; bought ${new Date(p.created_at).toLocaleDateString()}
          </span>
        </div>
        <div>
          <button type="button" class="check-btn">Check P/L</button>
          <button type="button" class="delete-btn">Delete</button>
        </div>
      </div>
      <div class="portfolio-card-body hidden"></div>
    `;
    const body = card.querySelector(".portfolio-card-body");

    card.querySelector(".check-btn").addEventListener("click", async () => {
      if (!body.classList.contains("hidden")) {
        body.classList.add("hidden");
        return;
      }
      body.classList.remove("hidden");
      body.innerHTML = `<p style="color: var(--muted);">Fetching current prices&hellip;</p>`;
      try {
        const statusRes = await fetch(`/api/portfolios/${encodeURIComponent(p.name)}`);
        const status = await statusRes.json();
        if (!statusRes.ok) throw new Error(status.detail || `Server error ${statusRes.status}`);
        body.innerHTML = renderStatus(status);
      } catch (err) {
        body.innerHTML = `<p style="color: var(--red);">Couldn't check status: ${err.message}</p>`;
      }
    });

    card.querySelector(".delete-btn").addEventListener("click", async () => {
      if (!confirm(`Delete portfolio "${p.name}"? This can't be undone.`)) return;
      await fetch(`/api/portfolios/${encodeURIComponent(p.name)}`, { method: "DELETE" });
      await loadPortfolios();
    });

    portfolioListEl.appendChild(card);
  }
}

function renderStatus(status) {
  const verdict = status.in_profit ? "PROFIT" : "LOSS";
  const verdictClass = status.in_profit ? "pos" : "neg";
  const rows = status.positions
    .map(
      (pos) => `
        <tr>
          <td class="symbol-cell">${pos.symbol}</td>
          <td>${pos.shares.toFixed(4)}</td>
          <td>${money(pos.purchase_price)}</td>
          <td>${money(pos.current_price)}</td>
          <td>${money(pos.current_value)}</td>
          <td class="${pos.pl >= 0 ? "pos" : "neg"}">${pos.pl >= 0 ? "+" : ""}${money(pos.pl)}</td>
          <td class="${pos.pl_pct >= 0 ? "pos" : "neg"}">${pct(pos.pl_pct)}</td>
        </tr>
      `
    )
    .join("");

  return `
    <p>
      <strong>${verdict}</strong>
      <span class="${verdictClass}">${status.total_pl >= 0 ? "+" : ""}${money(status.total_pl)} (${pct(status.total_pl_pct)})</span>
      &nbsp; <span style="color: var(--muted); font-size: 12px;">after ${status.days_held} day(s) &middot; now worth ${money(status.total_current_value)} of ${money(status.total_invested)} invested</span>
    </p>
    <table class="portfolio-positions">
      <thead>
        <tr><th>Symbol</th><th>Shares</th><th>Buy Price</th><th>Now</th><th>Value</th><th>P/L</th><th>P/L %</th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
    ${status.unavailable_symbols.length ? `<p style="color: var(--muted); font-size: 12px;">Couldn't fetch a current price for: ${status.unavailable_symbols.join(", ")}</p>` : ""}
    <p style="color: var(--muted); font-size: 12px;">${status.currency_note}</p>
  `;
}

addTickerRow();
addTickerRow();
loadPortfolios();
