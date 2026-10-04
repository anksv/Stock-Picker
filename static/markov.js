const mkSector = document.getElementById("mkSector");
const mkContinent = document.getElementById("mkContinent");
const mkAssetType = document.getElementById("mkAssetType");
const mkOnlyEdge = document.getElementById("mkOnlyEdge");
const mkLoadBtn = document.getElementById("mkLoadBtn");
const mkStatus = document.getElementById("mkStatus");
const mkBody = document.getElementById("mkBody");
const mkSymbol = document.getElementById("mkSymbol");
const mkSearchBtn = document.getElementById("mkSearchBtn");
const mkSearchStatus = document.getElementById("mkSearchStatus");
const mkSearchResult = document.getElementById("mkSearchResult");
const mkDetailPanel = document.getElementById("mkDetailPanel");
const mkDetailBody = document.getElementById("mkDetailBody");

const STATES = ["Down", "Flat", "Up"];
const ASSET_TYPE_LABELS = { ETF: "ETFs only", Stock: "Stocks only", Crypto: "Crypto only" };
const ASSET_TYPE_CLASSES = { ETF: "etf-type", Crypto: "crypto-type" };

let universeResults = [];
let sortKey = "net_edge_pct";
let sortDir = -1;

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function pct(v, digits = 1) {
  return v === null || v === undefined ? "-" : `${v > 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

function plain(v) {
  return v === null || v === undefined ? "-" : `${v.toFixed(1)}%`;
}

function slug(label) {
  return label.toLowerCase().replace(/\s+/g, "-");
}

function outlookBadge(label) {
  return `<span class="badge markov-${slug(label)}">${esc(label)}</span>`;
}

function stateBadge(state) {
  return state ? `<span class="badge state-${state.toLowerCase()}">${esc(state)}</span>` : "-";
}

async function fillSelect(url, key, select, labelFor) {
  const res = await fetch(url);
  const data = await res.json();
  for (const value of data[key]) {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = labelFor ? labelFor(value) : value;
    select.appendChild(opt);
  }
}

// ---- tabs ----
let journalLoaded = false;
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === tab));
    for (const name of ["universe", "search", "learning"]) {
      document.getElementById(`tab-${name}`).classList.toggle("hidden", tab.dataset.tab !== name);
    }
    if (tab.dataset.tab === "learning" && !journalLoaded) loadJournal();
  });
});

// ---- detail view (shared by the universe modal and the search result) ----
function probBar(label, value, base, cls) {
  return `
    <div class="prob-row">
      <span class="prob-label">${label}</span>
      <div class="prob-track">
        <div class="prob-fill ${cls}" style="width:${Math.min(value, 100)}%"></div>
        <div class="prob-base" style="left:${Math.min(base, 100)}%" title="Usual: ${base.toFixed(1)}%"></div>
      </div>
      <span class="prob-value">${value.toFixed(1)}% <span class="prob-usual">(usual ${base.toFixed(1)}%)</span></span>
    </div>`;
}

let liveCounter = 0;

function renderDetail(r) {
  const title = r.name ? `${esc(r.name)} (${esc(r.symbol)})` : esc(r.symbol);
  const meta = [r.asset_type, r.sector, r.continent].filter(Boolean).map(esc).join(" &middot; ");

  if (r.outlook_label === "Insufficient History") {
    return `
      <h2>${title}</h2>
      ${meta ? `<p class="muted">${meta}</p>` : ""}
      <p>${outlookBadge(r.outlook_label)}</p>
      <p>Only ${r.weeks_of_history} completed weeks of price history - a Markov chain needs at least 104 (about 2 years) to estimate anything meaningful.</p>`;
  }

  const current = STATES.indexOf(r.current_state);
  const liveId = `mkLive${++liveCounter}`;
  setTimeout(() => loadLive(r.symbol, liveId), 0);
  const matrixRows = r.transition_matrix_pct
    .map((row, i) => {
      const cells = row
        .map((v, j) => `<td class="${i === current ? "matrix-current" : ""}" style="--heat:${(v / 100).toFixed(2)}" title="${r.transition_counts[i][j]} observed transitions">${v.toFixed(1)}%</td>`)
        .join("");
      return `<tr><th>${STATES[i]}${i === current ? " (now)" : ""}</th>${cells}<td class="muted">n=${r.transition_counts[i].reduce((a, b) => a + b, 0)}</td></tr>`;
    })
    .join("");

  const backtest = r.backtest
    ? `<p><strong>Walk-forward test:</strong> fitted on the first 60% of the history only, then predicted the direction of each of the next ${r.backtest.weeks} weeks:
        <strong>${r.backtest.accuracy_pct}%</strong> correct vs. <strong>${r.backtest.baseline_accuracy_pct}%</strong> for simply always guessing "up".
        ${r.backtest.accuracy_pct > r.backtest.baseline_accuracy_pct ? "The chain beat the baseline on this history." : r.backtest.accuracy_pct === r.backtest.baseline_accuracy_pct ? "A tie usually means the chain predicted \"up\" every week - i.e. it added nothing beyond the baseline." : "The chain did worse than the baseline on this history."}</p>`
    : `<p class="muted">Not enough history for a walk-forward backtest.</p>`;

  return `
    <h2>${title}</h2>
    ${meta ? `<p class="muted" style="margin-top:-8px">${meta}</p>` : ""}
    <p>
      ${outlookBadge(r.outlook_label)}
      &nbsp; <strong>Current state:</strong> ${stateBadge(r.current_state)}
      <span class="muted">(last completed week ending ${esc(r.as_of_week_ending)}: ${pct(r.last_week_return_pct, 2)}; Up/Down means beyond &plusmn;${r.state_threshold_pct}%)</span>
    </p>

    <h3>Next week, given the current state</h3>
    ${probBar("Up", r.p_up_next, r.base_up, "fill-up")}
    ${probBar("Flat", r.p_flat_next, r.base_flat, "fill-flat")}
    ${probBar("Down", r.p_down_next, r.base_down, "fill-down")}
    ${r.learning_status === "active" ? `<p><strong>After learning from live results</strong> (weight ${r.learning_weight}): Up ${r.p_up_adjusted}%, Down ${r.p_down_adjusted}% <span class="muted">- the odds above, pulled toward usual by how much live results have supported them</span></p>` : ""}
    <p>
      <strong>Net edge vs. usual:</strong> ${pct(r.net_edge_pct)} points
      &nbsp; <strong>Significance:</strong> ${r.significant ? "yes (|z| &ge; 1.96)" : "no"}
      <span class="muted">(z-up ${r.z_up}, z-down ${r.z_down}, based on ${r.sample_size} past weeks in this state)</span>
    </p>
    <p>
      <strong>Average return the week after this state:</strong> ${pct(r.expected_next_week_return_pct, 2)}
      <span class="muted">(overall average week: ${pct(r.avg_weekly_return_pct, 2)})</span>
    </p>
    <p><strong>Odds of being in the Up state 4 weeks out:</strong> ${plain(r.p_up_4w)}
      <span class="muted">(long-run share of weeks in Up: ${plain(r.stationary_up)} - the chain forgets today's state quickly)</span></p>

    <h3>Transition matrix <span class="muted" style="font-size:12px; font-weight:400">(row = this week's state, column = next week's state)</span></h3>
    <table class="matrix">
      <thead><tr><th></th>${STATES.map((s) => `<th>&rarr; ${s}</th>`).join("")}<th></th></tr></thead>
      <tbody>${matrixRows}</tbody>
    </table>

    <h3>Does it actually work?</h3>
    ${backtest}
    <h3>Live track record <span class="muted" style="font-size:12px; font-weight:400">(real weeks, scored after they finished)</span></h3>
    <div class="live-record" id="${liveId}"><span class="muted">Loading...</span></div>
    <p class="muted" style="font-size:12px">
      Built from ${r.weeks_of_history} completed weekly returns. Past transition frequencies don't guarantee future ones, and markets adapt.
      Not financial advice.
    </p>`;
}

// ---- universe table ----
function sortValue(row, key) {
  const v = row[key];
  return v === null || v === undefined ? -Infinity : v;
}

function renderTable() {
  let rows = universeResults;
  if (mkOnlyEdge.checked) rows = rows.filter((r) => r.outlook_label === "Favorable" || r.outlook_label === "Unfavorable");

  rows = [...rows].sort((a, b) => {
    const av = sortValue(a, sortKey), bv = sortValue(b, sortKey);
    if (typeof av === "string" || typeof bv === "string") return sortDir * String(av).localeCompare(String(bv));
    return sortDir * (av - bv);
  });

  mkBody.innerHTML = "";
  for (const r of rows) {
    const tr = document.createElement("tr");
    const insufficient = r.outlook_label === "Insufficient History";
    const edgeClass = r.net_edge_pct === undefined ? "" : r.net_edge_pct >= 0 ? "pos" : "neg";
    tr.innerHTML = `
      <td class="symbol-cell">${esc(r.symbol)}</td>
      <td><span class="badge ${ASSET_TYPE_CLASSES[r.asset_type] || "stock-type"}">${esc(r.asset_type)}</span></td>
      <td>${esc(r.sector)}</td>
      <td>${insufficient ? "-" : stateBadge(r.current_state)}</td>
      <td class="${r.last_week_return_pct >= 0 ? "pos" : "neg"}">${insufficient ? "-" : pct(r.last_week_return_pct, 2)}</td>
      <td>${insufficient ? "-" : plain(r.p_up_next)}</td>
      <td>${insufficient ? "-" : plain(r.p_down_next)}</td>
      <td>${insufficient ? "-" : plain(r.base_up)}</td>
      <td class="${edgeClass}">${insufficient ? "-" : pct(r.net_edge_pct)}</td>
      <td>${outlookBadge(r.outlook_label)}</td>
      <td>${insufficient ? r.weeks_of_history + " wks" : r.sample_size}</td>
    `;
    tr.addEventListener("click", () => {
      mkDetailBody.innerHTML = renderDetail(r);
      mkDetailPanel.classList.remove("hidden");
    });
    mkBody.appendChild(tr);
  }

  const edgeCount = universeResults.filter((r) => r.outlook_label === "Favorable" || r.outlook_label === "Unfavorable").length;
  mkStatus.textContent = `${universeResults.length} assets analyzed, ${edgeCount} with a statistically clear edge (expect a few by pure chance). Showing ${rows.length}. Click a row for details.`;
}

async function loadUniverse() {
  mkLoadBtn.disabled = true;
  mkStatus.textContent = "Computing Markov outlooks for the universe... the first load takes about 15-30 seconds, later loads are cached.";
  mkBody.innerHTML = "";
  try {
    const params = new URLSearchParams({ sector: mkSector.value, continent: mkContinent.value, asset_type: mkAssetType.value });
    const res = await fetch(`/api/markov/universe?${params}`);
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    universeResults = (await res.json()).results;
    renderTable();
  } catch (err) {
    mkStatus.textContent = `Failed to load: ${err.message}`;
  } finally {
    mkLoadBtn.disabled = false;
  }
}

mkLoadBtn.addEventListener("click", loadUniverse);
mkOnlyEdge.addEventListener("change", renderTable);

const sortableHeaders = document.querySelectorAll("#mkTable th[data-key]");
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
      sortDir = ["symbol", "asset_type", "sector", "current_state", "outlook_label"].includes(key) ? 1 : -1;
    }
    updateSortIndicators();
    renderTable();
  });
});
updateSortIndicators();

document.getElementById("mkCloseDetail").addEventListener("click", () => mkDetailPanel.classList.add("hidden"));
mkDetailPanel.addEventListener("click", (e) => {
  if (e.target === mkDetailPanel) mkDetailPanel.classList.add("hidden");
});

// ---- search ----
async function searchTicker() {
  const symbol = mkSymbol.value.trim();
  if (!symbol) {
    mkSearchStatus.textContent = "Enter a ticker symbol.";
    return;
  }
  mkSearchBtn.disabled = true;
  mkSearchStatus.textContent = `Analyzing ${symbol.toUpperCase()}...`;
  mkSearchResult.innerHTML = "";
  try {
    const res = await fetch(`/api/markov/search?${new URLSearchParams({ symbol })}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `Server error: ${res.status}`);
    mkSearchStatus.textContent = "";
    mkSearchResult.innerHTML = `<div class="portfolio-card">${renderDetail(data)}</div>`;
  } catch (err) {
    mkSearchStatus.textContent = err.message;
  } finally {
    mkSearchBtn.disabled = false;
  }
}

mkSearchBtn.addEventListener("click", searchTicker);
mkSymbol.addEventListener("keydown", (e) => {
  if (e.key === "Enter") searchTicker();
});

// ---- live record in the detail view ----
async function loadLive(symbol, elId) {
  const el = document.getElementById(elId);
  if (!el) return;
  try {
    const res = await fetch(`/api/markov/journal/asset?${new URLSearchParams({ symbol })}`);
    const rec = await res.json();
    if (!rec.logged) {
      el.innerHTML = `<span class="muted">Nothing logged for ${esc(symbol)} yet - it is added at the next daily check.</span>`;
      return;
    }
    const rows = rec.recent.map((p) => {
      const outcome = p.resolved
        ? `${pct(p.actual_return_pct, 2)} ${p.direction_correct ? "&#10003;" : "&#10007;"}`
        : `<span class="muted">pending (week ending ${esc(p.target_week_ending)})</span>`;
      return `<div class="live-row"><span>Week ending ${esc(p.target_week_ending)}: said ${esc(p.predicted_direction)} (Up ${p.p_up}% / Down ${p.p_down}%)</span><span class="${p.resolved ? (p.direction_correct ? "pos" : "neg") : ""}">${outcome}</span></div>`;
    }).join("");
    const summary = rec.resolved
      ? `<p class="muted" style="margin:0 0 6px">${rec.resolved} scored: direction right ${rec.direction_accuracy_pct}% vs. ${rec.baseline_accuracy_pct}% for always guessing up.</p>`
      : `<p class="muted" style="margin:0 0 6px">${rec.logged} logged, none finished yet.</p>`;
    el.innerHTML = summary + rows;
  } catch (err) {
    el.innerHTML = `<span class="muted">Couldn't load the live record: ${esc(err.message)}</span>`;
  }
}

// ---- learning log ----
const mkJournal = document.getElementById("mkJournal");
const mkJournalStatus = document.getElementById("mkJournalStatus");
const mkJournalMeta = document.getElementById("mkJournalMeta");
const mkUpdateBtn = document.getElementById("mkUpdateBtn");

function statCard(label, value, sub) {
  return `<div class="stat"><div class="label">${label}</div><div class="value">${value}</div><div class="sub">${sub}</div></div>`;
}

function simpleTable(headers, rows) {
  return `<table class="portfolio-positions"><thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

function renderJournal(d) {
  const b = d.scoreboard, l = d.learning;
  mkJournalMeta.textContent = d.last_updated
    ? `Last checked ${new Date(d.last_updated).toLocaleString()}. The server re-checks automatically every 12 hours while it runs; for a daily job without the server, run: python -m app.markov_journal update`
    : "Not checked yet - click the button, or it happens automatically ~20 seconds after the server starts.";

  const hasScores = b.resolved > 0;
  const accDiff = hasScores ? (b.direction_accuracy_pct - b.baseline_accuracy_pct).toFixed(1) : null;
  const cards = [
    statCard("Predictions scored", b.resolved, `${b.pending} waiting for their week to finish &middot; ${b.weeks} week(s) &middot; ${b.tracked_assets} assets`),
    statCard("Direction accuracy", hasScores ? `${b.direction_accuracy_pct}%` : "-", hasScores ? `vs. ${b.baseline_accuracy_pct}% always guessing up (${accDiff >= 0 ? "+" : ""}${accDiff} pts)` : "needs a finished week"),
    statCard("Probability skill", b.brier_skill === null || b.brier_skill === undefined ? "-" : b.brier_skill, "above 0 = beats each asset's usual odds"),
    statCard("Learning weight", l.status === "active" ? l.weight : "off", l.status === "active" ? "share of the model's deviation from usual that live results support" : `collecting: ${l.resolved}/${l.needed_resolved} scored, ${l.weeks}/${l.needed_weeks} weeks`),
  ].join("");

  const lessons = d.lessons.map((n) => `<li class="lesson ${n.kind}">${esc(n.text)}</li>`).join("");

  const labelTable = b.labels.length
    ? simpleTable(["Label", "Calls", "Direction right", "Hit rate", "Usual rate"], b.labels.map((x) => [esc(x.label), x.n, `${x.direction_accuracy_pct}%`, x.hit_rate_pct === undefined ? "-" : `${x.hit_rate_pct}%`, x.usual_rate_pct === undefined ? "-" : `${x.usual_rate_pct}%`]))
    : `<p class="muted">Nothing scored yet.</p>`;
  const calibTable = (rows) => rows.length
    ? simpleTable(["Model said", "Cases", "Avg said", "Actually happened"], rows.map((x) => [x.range, x.n, `${x.predicted_pct}%`, `${x.actual_pct}%`]))
    : `<p class="muted">Nothing scored yet.</p>`;
  const weeklyTable = b.weekly.length
    ? simpleTable(["Week ending", "Calls", "Direction right", "Always-up", "Avg asset move"], b.weekly.map((x) => [esc(x.week), x.n, `${x.accuracy_pct}%`, `${x.baseline_pct}%`, pct(x.avg_return_pct, 2)]))
    : `<p class="muted">Nothing scored yet.</p>`;
  const missTable = d.misses.length
    ? simpleTable(["Asset", "Week ending", "Model said", "What happened"], d.misses.map((p) => [`<strong>${esc(p.symbol)}</strong>`, esc(p.target_week_ending), `${esc(p.predicted_direction)} (Up ${p.p_up}% / Down ${p.p_down}%)`, `<span class="${p.actual_return_pct >= 0 ? "pos" : "neg"}">${pct(p.actual_return_pct, 2)}</span>`]))
    : `<p class="muted">No wrong calls scored yet.</p>`;

  const notes = d.notes.map((n) => `<div class="note-item"><div><div class="muted">${new Date(n.created_at).toLocaleString()}</div><div class="note-text">${esc(n.text)}</div></div><button type="button" data-note="${esc(n.id)}" title="Delete note">&times;</button></div>`).join("");

  mkJournal.innerHTML = `
    <div class="stat-grid">${cards}</div>
    <div class="journal-block"><h3>What the model has learned</h3><ul class="lessons">${lessons}</ul></div>
    <div class="journal-block"><h3>Biggest wrong calls</h3>${missTable}</div>
    <div class="journal-block"><h3>Do the Favorable / Unfavorable flags work?</h3>${labelTable}</div>
    <div class="journal-block"><h3>Calibration: when it said Up</h3>${calibTable(b.calibration_up)}</div>
    <div class="journal-block"><h3>Calibration: when it said Down</h3>${calibTable(b.calibration_down)}</div>
    <div class="journal-block"><h3>Week by week</h3>${weeklyTable}</div>
    <div class="journal-block">
      <h3>Your notes</h3>
      <div class="note-form"><textarea id="mkNoteText" placeholder="Anything you want to remember - e.g. 'ignore the model on crypto, it misses every big move'"></textarea><button id="mkNoteBtn" type="button">Add note</button></div>
      <div id="mkNotes">${notes || '<p class="muted">No notes yet.</p>'}</div>
    </div>`;

  document.getElementById("mkNoteBtn").addEventListener("click", addNote);
  mkJournal.querySelectorAll("[data-note]").forEach((btn) => btn.addEventListener("click", () => deleteNote(btn.dataset.note)));
}

async function loadJournal() {
  mkJournalStatus.textContent = "Loading the journal...";
  try {
    const res = await fetch("/api/markov/journal");
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    renderJournal(await res.json());
    journalLoaded = true;
    mkJournalStatus.textContent = "";
  } catch (err) {
    mkJournalStatus.textContent = `Failed to load: ${err.message}`;
  }
}

mkUpdateBtn.addEventListener("click", async () => {
  mkUpdateBtn.disabled = true;
  mkJournalStatus.textContent = "Scoring finished predictions against real prices and logging new ones... this can take 10-20 seconds.";
  try {
    const res = await fetch("/api/markov/journal/update", { method: "POST" });
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const s = await res.json();
    await loadJournal();
    mkJournalStatus.textContent = `Done: scored ${s.resolved_now} finished prediction(s), logged ${s.recorded} new, ${s.already_logged} already logged this week, ${s.skipped_late} skipped (too late in the week to be a fair forward call), ${s.pending} still pending.`;
  } catch (err) {
    mkJournalStatus.textContent = `Update failed: ${err.message}`;
  } finally {
    mkUpdateBtn.disabled = false;
  }
});

async function addNote() {
  const box = document.getElementById("mkNoteText");
  if (!box.value.trim()) return;
  await fetch("/api/markov/journal/notes", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: box.value }) });
  await loadJournal();
}

async function deleteNote(id) {
  await fetch(`/api/markov/journal/notes/${encodeURIComponent(id)}`, { method: "DELETE" });
  await loadJournal();
}

// ---- init ----
Promise.all([
  fillSelect("/api/sectors", "sectors", mkSector),
  fillSelect("/api/continents", "continents", mkContinent),
  fillSelect("/api/asset-types", "asset_types", mkAssetType, (t) => ASSET_TYPE_LABELS[t] || `${t} only`),
]).then(loadUniverse);
