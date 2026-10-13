// Shared by every page: the USD/EUR display switch and all money formatting.
//
// Every monetary value in the app is stored in its own native currency (US
// listings in USD, XETRA listings in EUR, portfolios in the currency they were
// bought in). Pages never convert by hand - they call Currency.format(value,
// nativeCurrency) and get the number in whichever currency is selected at the
// top. The choice is remembered across pages and reloads.
//
// Only USD and EUR can be converted (live EUR/USD rate from /api/fx). If the
// rate is unavailable, or a value is in some other currency, it is shown in its
// own currency with its own symbol rather than converted wrongly.
const Currency = (() => {
  const STORAGE_KEY = "displayCurrency";
  const SYMBOLS = { USD: "$", EUR: "€", GBP: "£", CHF: "CHF ", JPY: "¥" };
  const listeners = [];

  let display = "USD";
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "USD" || saved === "EUR") display = saved;
  } catch (_) {
    // localStorage can be unavailable (private windows); the choice just won't persist
  }

  let fx = null; // { rate: USD per 1 EUR, as_of, stale }

  const symbol = (code) => SYMBOLS[code] ?? `${code} `;

  function convert(value, from) {
    if (value === null || value === undefined) return { value, currency: from || display };
    if (!from || from === display) return { value, currency: display };
    const convertible = (from === "USD" || from === "EUR") && fx;
    if (!convertible) return { value, currency: from };
    return { value: from === "EUR" ? value * fx.rate : value / fx.rate, currency: display };
  }

  // Amount as a plain number in the display currency (for sorting/comparing).
  const amount = (value, from) => convert(value, from).value;

  function format(value, from, digits = 2) {
    if (value === null || value === undefined) return "-";
    const c = convert(value, from);
    const sign = c.value < 0 ? "-" : "";
    return `${sign}${symbol(c.currency)}${Math.abs(c.value).toFixed(digits)}`;
  }

  function compact(value, from) {
    if (value === null || value === undefined) return "-";
    const c = convert(value, from);
    for (const [size, suffix] of [[1e12, "T"], [1e9, "B"], [1e6, "M"]]) {
      if (c.value >= size) return `${symbol(c.currency)}${(c.value / size).toFixed(1)}${suffix}`;
    }
    return `${symbol(c.currency)}${c.value.toFixed(0)}`;
  }

  function renderToggle() {
    const el = document.getElementById("ccyToggle");
    if (el) {
      let rateText = "";
      if (fx) {
        rateText = `1 EUR = ${fx.rate.toFixed(4)} USD &middot; ${fx.as_of}${fx.stale ? " (stale)" : ""}`;
      } else {
        rateText = display === "EUR"
          ? "EUR rate unavailable - showing native currencies"
          : "EUR rate unavailable";
      }
      el.innerHTML = `
        <span class="ccy-label">Show values in</span>
        <span class="ccy-buttons" role="group" aria-label="Display currency">
          <button type="button" data-ccy="USD" class="${display === "USD" ? "active" : ""}">USD</button>
          <button type="button" data-ccy="EUR" class="${display === "EUR" ? "active" : ""}">EUR</button>
        </span>
        <span class="ccy-rate">${rateText}</span>`;
      el.querySelectorAll("button").forEach((btn) => btn.addEventListener("click", () => setDisplay(btn.dataset.ccy)));
    }
    document.querySelectorAll(".ccy-symbol").forEach((node) => {
      node.textContent = symbol(display).trim();
    });
  }

  function setDisplay(code) {
    if (code === display) return;
    display = code;
    try {
      localStorage.setItem(STORAGE_KEY, code);
    } catch (_) {
      // not persisted - fine
    }
    renderToggle();
    listeners.forEach((fn) => fn(code));
  }

  const ready = fetch("/api/fx")
    .then((res) => (res.ok ? res.json() : null))
    .catch(() => null)
    .then((data) => {
      fx = data;
      renderToggle();
    });

  renderToggle();

  return {
    get display() { return display; },
    symbol,
    convert,
    amount,
    format,
    compact,
    ready,
    onChange: (fn) => listeners.push(fn),
  };
})();
