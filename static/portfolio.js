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
      body: JSON.stringify({ name, amount, tickers, currency: Currency.display }),
    });
    const data = await res.json();
    if (!res.ok) {
      if (res.status === 409) {
        const overwrite = confirm(`Portfolio "${name}" already exists. Overwrite it with a new purchase?`);
        if (overwrite) {
          const res2 = await fetch("/api/portfolios", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name, amount, tickers, force: true, currency: Currency.display }),
          });
          const data2 = await res2.json();
          if (!res2.ok) throw new Error(data2.detail || `Server error ${res2.status}`);
          pfStatusEl.textContent = `Bought "${name}" for ${money(data2.total_invested, data2.currency)}.`;
          await loadPortfolios();
          return;
        }
        pfStatusEl.textContent = "Cancelled.";
        return;
      }
      throw new Error(data.detail || `Server error ${res.status}`);
    }
    pfStatusEl.textContent = `Bought "${name}" for ${money(data.total_invested, data.currency)}.`;
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

// Amounts (invested/value/P&L) are in the portfolio's own currency; asset
// prices are in each asset's own currency. Currency converts both to the
// currency selected at the top.
function money(v, currency) {
  return Currency.format(v, currency);
}

const expandedPortfolios = new Set();

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
            &middot; ${p.position_count} position(s) &middot; invested ${money(p.total_invested, p.currency || "USD")} &middot; bought ${new Date(p.created_at).toLocaleDateString()}
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
        expandedPortfolios.delete(p.name);
        return;
      }
      body.classList.remove("hidden");
      expandedPortfolios.add(p.name);
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
    if (expandedPortfolios.has(p.name)) card.querySelector(".check-btn").click();
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
          <td>${money(pos.purchase_price, pos.price_currency)}</td>
          <td>${money(pos.current_price, pos.price_currency)}</td>
          <td>${money(pos.current_value, status.currency)}</td>
          <td class="${pos.pl >= 0 ? "pos" : "neg"}">${pos.pl >= 0 ? "+" : ""}${money(pos.pl, status.currency)}</td>
          <td class="${pos.pl_pct >= 0 ? "pos" : "neg"}">${pct(pos.pl_pct)}</td>
        </tr>
      `
    )
    .join("");

  return `
    <p>
      <strong>${verdict}</strong>
      <span class="${verdictClass}">${status.total_pl >= 0 ? "+" : ""}${money(status.total_pl, status.currency)} (${pct(status.total_pl_pct)})</span>
      &nbsp; <span style="color: var(--muted); font-size: 12px;">after ${status.days_held} day(s) &middot; now worth ${money(status.total_current_value, status.currency)} of ${money(status.total_invested, status.currency)} invested</span>
    </p>
    <table class="portfolio-positions">
      <thead>
        <tr><th title="Ticker symbol of the holding.">Symbol</th><th title="Fractional shares bought: this holding's slice of the amount (converted into the asset's own currency if needed) divided by its price on the day of purchase.">Shares</th><th title="Price per share when the portfolio was bought, in the asset's own currency, then shown in the currency selected at the top.">Buy Price</th><th title="Latest closing price per share, in the asset's own currency, then shown in the currency selected at the top.">Now</th><th title="What the holding is worth now: shares times the current price, in the portfolio's currency, then shown in the currency selected at the top.">Value</th><th title="Profit or loss on this holding: its current Value minus the amount originally put into it. If the asset is priced in a different currency from the portfolio, currency movement since purchase is included.">P/L</th><th title="Profit or loss as a percentage of the amount originally put into this holding. It does not change with the display currency.">P/L %</th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
    ${status.unavailable_symbols.length ? `<p style="color: var(--muted); font-size: 12px;">Couldn't fetch a current price for: ${status.unavailable_symbols.join(", ")}</p>` : ""}
    <p style="color: var(--muted); font-size: 12px;">${status.currency_note}${Currency.display !== status.currency ? ` Recorded in ${status.currency} and shown in ${Currency.display} at today's rate; percentages are unaffected.` : ""}</p>
  `;
}

addTickerRow();
addTickerRow();
Currency.onChange(() => loadPortfolios());
Currency.ready.then(loadPortfolios);
