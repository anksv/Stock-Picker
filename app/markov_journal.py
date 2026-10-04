"""Persistent prediction journal for the Markov Outlook model.

Every week the model's next-week call for each tracked asset is written to
disk. Once that week has completed, the call is scored against what the real
price actually did, and the running track record feeds back into the model:

  1. Scoreboard - direction accuracy vs. an "always guess up" baseline, a
     Brier skill score vs. the asset's usual odds, calibration buckets, and
     the accuracy of the Favorable/Unfavorable labels specifically.
  2. Learning weight - the model's deviation from an asset's usual odds is
     only worth keeping if live results show it carries information. The
     weight (0..1) is the pooled slope of "what actually happened" against
     "what the model said, relative to usual", and the displayed odds are
     shrunk toward the usual odds by that weight. If the model's calls turn
     out to be noise, the weight heads to 0 and the page says so.
  3. Lessons - plain-language notes generated from the record (what it got
     wrong, whether it is calibrated, what to distrust), alongside notes you
     add yourself.

Honest limits: one prediction per asset per week, so per-asset records grow
slowly; the pooled view across the whole universe is what accumulates
quickly - but all assets move together with the market in any given week,
so learning is only switched on after several distinct weeks of data.

CLI (suitable for a daily cron job):
    python -m app.markov_journal update    # log new calls, score finished ones
    python -m app.markov_journal report    # print scoreboard and lessons
"""
from __future__ import annotations

import argparse
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yfinance as yf

from app.markov import compute_markov
from app.storage import atomic_write_json

JOURNAL_PATH = Path(__file__).resolve().parent.parent / "markov_journal" / "journal.json"

# A week's call is only logged if the model is run within this many days of
# that week ending (i.e. by Monday). Logging later would let part of the
# "future" week leak into a call that is supposed to be made beforehand.
MAX_LAG_DAYS = 3

MIN_RESOLVED_FOR_LEARNING = 200
MIN_WEEKS_FOR_LEARNING = 3
STATE_NAMES = ["Down", "Flat", "Up"]

_LOCK = threading.RLock()


def _empty_journal() -> dict:
    return {"version": 1, "last_updated": None, "tracked_extra": [], "predictions": [], "notes": []}


def load_journal() -> dict:
    """Read-only access; safe without the lock because saves are atomic."""
    if not JOURNAL_PATH.exists():
        return _empty_journal()
    import json

    try:
        return {**_empty_journal(), **json.loads(JOURNAL_PATH.read_text())}
    except (json.JSONDecodeError, OSError):
        return _empty_journal()


def _save(journal: dict) -> None:
    atomic_write_json(JOURNAL_PATH, journal)


# ---------------------------------------------------------------- tracking

def track_symbol(symbol: str) -> None:
    """Remember a searched ticker so it keeps being logged and scored."""
    with _LOCK:
        journal = load_journal()
        if symbol not in journal["tracked_extra"]:
            journal["tracked_extra"].append(symbol)
            _save(journal)


def tracked_symbols(universe_symbols: list[str]) -> list[str]:
    extra = [s for s in load_journal()["tracked_extra"] if s not in universe_symbols]
    return list(universe_symbols) + extra


# ---------------------------------------------------------------- recording

def _record(journal: dict, results: list[dict], today: date) -> dict:
    existing = {p["id"] for p in journal["predictions"]}
    recorded = skipped_late = already = 0

    for r in results:
        if not r or r.get("outlook_label") == "Insufficient History" or "as_of_week_ending" not in r:
            continue
        as_of = date.fromisoformat(r["as_of_week_ending"])
        target = as_of + timedelta(days=7)
        pid = f"{r['symbol']}|{target.isoformat()}"
        if pid in existing:
            already += 1
            continue
        if (today - as_of).days > MAX_LAG_DAYS or target <= today:
            skipped_late += 1
            continue

        probs = [r["p_down_next"], r["p_flat_next"], r["p_up_next"]]
        journal["predictions"].append({
            "id": pid,
            "symbol": r["symbol"],
            "made_at": datetime.now(timezone.utc).isoformat(),
            "as_of_week_ending": as_of.isoformat(),
            "target_week_ending": target.isoformat(),
            "current_state": r["current_state"],
            "p_down": probs[0],
            "p_flat": probs[1],
            "p_up": probs[2],
            "base_down": r["base_down"],
            "base_up": r["base_up"],
            "threshold_pct": r["state_threshold_pct"],
            "predicted_state": STATE_NAMES[probs.index(max(probs))],
            "predicted_direction": "Up" if probs[2] >= probs[0] else "Down",
            "outlook_label": r["outlook_label"],
            "resolved": False,
        })
        existing.add(pid)
        recorded += 1

    return {"recorded": recorded, "skipped_late": skipped_late, "already_logged": already}


# --------------------------------------------------------------- resolving

def _fetch_closes(symbol: str, start: date):
    try:
        history = yf.Ticker(symbol).history(start=start.isoformat(), interval="1d", auto_adjust=True)
        closes = history["Close"].dropna()
        return symbol, closes
    except Exception:
        return symbol, None


def _resolve_one(pred: dict, closes) -> bool:
    as_of = date.fromisoformat(pred["as_of_week_ending"])
    target = date.fromisoformat(pred["target_week_ending"])
    dates = closes.index.date
    before_as_of = closes[dates <= as_of]
    in_target = closes[dates <= target]
    if before_as_of.empty or in_target.empty:
        return False
    target_date = in_target.index[-1].date()
    # The target week must actually have trading data, not just stale prices.
    if target_date <= as_of or (target - target_date).days > 4:
        return False

    # Both closes come from the same fetch so dividend/split adjustments
    # can't leak into the measured return.
    as_of_close = float(before_as_of.iloc[-1])
    target_close = float(in_target.iloc[-1])
    ret = target_close / as_of_close - 1
    threshold = pred["threshold_pct"] / 100
    actual_state = "Up" if ret > threshold else "Down" if ret < -threshold else "Flat"

    pred.update({
        "resolved": True,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "actual_return_pct": round(ret * 100, 2),
        "actual_state": actual_state,
        "direction_correct": (ret > 0) == (pred["predicted_direction"] == "Up"),
        "state_correct": actual_state == pred["predicted_state"],
    })
    return True


def _resolve_due(journal: dict, today: date) -> int:
    due = [p for p in journal["predictions"] if not p["resolved"] and date.fromisoformat(p["target_week_ending"]) < today]
    if not due:
        return 0
    earliest = min(date.fromisoformat(p["as_of_week_ending"]) for p in due) - timedelta(days=10)
    symbols = sorted({p["symbol"] for p in due})
    with ThreadPoolExecutor(max_workers=10) as pool:
        closes_by_symbol = dict(pool.map(lambda s: _fetch_closes(s, earliest), symbols))

    resolved = 0
    for pred in due:
        closes = closes_by_symbol.get(pred["symbol"])
        if closes is not None and _resolve_one(pred, closes):
            resolved += 1
    return resolved


def update_journal(symbols: list[str], today: date | None = None) -> dict:
    """Scores every finished prediction against real prices, then logs the
    model's fresh call for each symbol. Safe to run as often as you like.
    """
    today = today or date.today()
    with _LOCK:
        journal = load_journal()
        resolved_now = _resolve_due(journal, today)

        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(compute_markov, symbols))
        summary = _record(journal, results, today)

        journal["last_updated"] = datetime.now(timezone.utc).isoformat()
        _save(journal)

    pending = sum(1 for p in journal["predictions"] if not p["resolved"])
    return {**summary, "resolved_now": resolved_now, "pending": pending, "symbols": len(symbols)}


def maybe_update(symbols: list[str], min_hours: float = 6) -> dict | None:
    last = load_journal()["last_updated"]
    if last and datetime.now(timezone.utc) - datetime.fromisoformat(last) < timedelta(hours=min_hours):
        return None
    return update_journal(symbols)


# ----------------------------------------------------------------- scoring

def _resolved(journal: dict) -> list[dict]:
    return [p for p in journal["predictions"] if p["resolved"]]


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _pct(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value * 100, digits)


def _calibration(resolved: list[dict], prob_key: str, base_key: str, state: str) -> list[dict]:
    bins = [(0, 25), (25, 30), (30, 35), (35, 40), (40, 101)]
    rows = []
    for lo, hi in bins:
        group = [p for p in resolved if lo <= p[prob_key] < hi]
        if not group:
            continue
        rows.append({
            "range": f"{lo}-{hi if hi <= 100 else 100}%",
            "n": len(group),
            "predicted_pct": round(_mean([p[prob_key] for p in group]), 1),
            "actual_pct": _pct(_mean([1.0 if p["actual_state"] == state else 0.0 for p in group])),
        })
    return rows


def learning_state(journal: dict) -> dict:
    """Weight in 0..1 saying how much of the model's deviation from usual
    odds live results support. Stays at 1 (no adjustment) until there is
    enough data across enough distinct weeks to say anything.
    """
    resolved = _resolved(journal)
    weeks = len({p["target_week_ending"] for p in resolved})
    state = {"status": "collecting", "weight": 1.0, "resolved": len(resolved), "weeks": weeks,
             "needed_resolved": MIN_RESOLVED_FOR_LEARNING, "needed_weeks": MIN_WEEKS_FOR_LEARNING}
    if len(resolved) < MIN_RESOLVED_FOR_LEARNING or weeks < MIN_WEEKS_FOR_LEARNING:
        return state

    sxy = sxx = 0.0
    for p in resolved:
        for prob, base, hit in ((p["p_up"], p["base_up"], p["actual_state"] == "Up"),
                                (p["p_down"], p["base_down"], p["actual_state"] == "Down")):
            x = (prob - base) / 100
            y = (1.0 if hit else 0.0) - base / 100
            sxy += x * y
            sxx += x * x
    weight = max(0.0, min(1.0, sxy / sxx)) if sxx > 0 else 1.0
    return {**state, "status": "active", "weight": round(weight, 2)}


def apply_learning(result: dict, learning: dict) -> dict:
    """Adds odds shrunk toward the asset's usual odds by the learned weight."""
    if "p_up_next" not in result:
        return result
    w = learning["weight"]

    def adj(prob: float, base: float) -> float:
        return round(base + w * (prob - base), 1)

    return {
        **result,
        "learning_status": learning["status"],
        "learning_weight": w,
        "p_up_adjusted": adj(result["p_up_next"], result["base_up"]),
        "p_down_adjusted": adj(result["p_down_next"], result["base_down"]),
    }


def scoreboard(journal: dict) -> dict:
    resolved = _resolved(journal)
    n = len(resolved)
    out = {"resolved": n, "pending": len(journal["predictions"]) - n,
           "weeks": len({p["target_week_ending"] for p in resolved}), "tracked_assets": len({p["symbol"] for p in journal["predictions"]})}
    if not n:
        return {**out, "direction_accuracy_pct": None, "baseline_accuracy_pct": None, "brier_skill": None,
                "labels": [], "calibration_up": [], "calibration_down": [], "weekly": []}

    up_weeks = [p for p in resolved if p["actual_return_pct"] > 0]
    brier = base_brier = 0.0
    for p in resolved:
        for prob, base, state in ((p["p_up"], p["base_up"], "Up"), (p["p_down"], p["base_down"], "Down")):
            o = 1.0 if p["actual_state"] == state else 0.0
            brier += (prob / 100 - o) ** 2
            base_brier += (base / 100 - o) ** 2

    labels = []
    for label in ("Favorable", "Unfavorable", "No Clear Edge"):
        group = [p for p in resolved if p["outlook_label"] == label]
        if not group:
            continue
        row = {"label": label, "n": len(group), "direction_accuracy_pct": _pct(_mean([1.0 if p["direction_correct"] else 0.0 for p in group]))}
        if label == "Favorable":
            row["hit_rate_pct"] = _pct(_mean([1.0 if p["actual_state"] == "Up" else 0.0 for p in group]))
            row["usual_rate_pct"] = round(_mean([p["base_up"] for p in group]), 1)
        elif label == "Unfavorable":
            row["hit_rate_pct"] = _pct(_mean([1.0 if p["actual_state"] == "Down" else 0.0 for p in group]))
            row["usual_rate_pct"] = round(_mean([p["base_down"] for p in group]), 1)
        labels.append(row)

    weekly = []
    for week in sorted({p["target_week_ending"] for p in resolved}):
        group = [p for p in resolved if p["target_week_ending"] == week]
        weekly.append({
            "week": week, "n": len(group),
            "accuracy_pct": _pct(_mean([1.0 if p["direction_correct"] else 0.0 for p in group])),
            "baseline_pct": _pct(_mean([1.0 if p["actual_return_pct"] > 0 else 0.0 for p in group])),
            "avg_return_pct": round(_mean([p["actual_return_pct"] for p in group]), 2),
        })

    return {
        **out,
        "direction_accuracy_pct": _pct(_mean([1.0 if p["direction_correct"] else 0.0 for p in resolved])),
        "baseline_accuracy_pct": _pct(len(up_weeks) / n),
        "brier_skill": round(1 - brier / base_brier, 3) if base_brier else None,
        "labels": labels,
        "calibration_up": _calibration(resolved, "p_up", "base_up", "Up"),
        "calibration_down": _calibration(resolved, "p_down", "base_down", "Down"),
        "weekly": weekly,
    }


def recent_misses(journal: dict, limit: int = 8) -> list[dict]:
    """Worst calls: the model leaned Up and the asset fell (or vice versa),
    ranked by how large the move against the call was.
    """
    wrong = [p for p in _resolved(journal) if not p["direction_correct"]]
    wrong.sort(key=lambda p: abs(p["actual_return_pct"]), reverse=True)
    return wrong[:limit]


def lessons(journal: dict, board: dict, learning: dict) -> list[dict]:
    notes: list[dict] = []
    n = board["resolved"]
    if not n:
        pending = board["pending"]
        notes.append({"kind": "info", "text": f"No finished predictions yet - {pending} logged and waiting for their week to complete. Lessons appear once real prices have been compared against them."})
        return notes

    notes.append({"kind": "info", "text": f"{n} predictions scored across {board['weeks']} week(s) and {board['tracked_assets']} asset(s)."})

    acc, base = board["direction_accuracy_pct"], board["baseline_accuracy_pct"]
    if acc > base + 1:
        notes.append({"kind": "good", "text": f"Direction calls were right {acc}% of the time vs. {base}% for always guessing up - ahead of the baseline so far."})
    elif acc < base - 1:
        notes.append({"kind": "warn", "text": f"Direction calls were right {acc}% of the time vs. {base}% for always guessing up - the model is doing worse than a coin that always says Up. Don't lean on its direction."})
    else:
        notes.append({"kind": "warn", "text": f"Direction calls were right {acc}% of the time, level with {base}% for always guessing up - no added value from direction yet."})

    skill = board["brier_skill"]
    if skill is not None:
        if skill > 0.01:
            notes.append({"kind": "good", "text": f"Probability skill is positive ({skill}): its Up/Down odds beat simply using each asset's usual odds."})
        else:
            notes.append({"kind": "warn", "text": f"Probability skill is {skill}: its Up/Down odds are no better than each asset's usual odds, so the conditional part of the model isn't adding information yet."})

    top = [r for r in board["calibration_up"] if r["n"] >= 10][-1:] or []
    for row in top:
        gap = row["predicted_pct"] - row["actual_pct"]
        if abs(gap) >= 5:
            word = "over-confident" if gap > 0 else "under-confident"
            notes.append({"kind": "warn", "text": f"Calibration: when it gave Up a {row['range']} chance (avg {row['predicted_pct']}%), Up actually happened {row['actual_pct']}% of the time ({row['n']} cases) - {word} on its most bullish calls."})

    for row in board["labels"]:
        if row["label"] in ("Favorable", "Unfavorable") and row["n"] >= 5:
            beat = row["hit_rate_pct"] > row["usual_rate_pct"]
            small = row["n"] < 30
            side = "Up" if row["label"] == "Favorable" else "Down"
            text = f"{row['label']} flags: {side} happened {row['hit_rate_pct']}% of the time vs. {row['usual_rate_pct']}% usual ({row['n']} flags) - {'beat' if beat else 'did not beat'} the usual odds"
            text += ", but that's a small sample and could be luck." if small else "."
            notes.append({"kind": "info" if small else ("good" if beat else "warn"), "text": text})

    misses = recent_misses(journal, 3)
    for p in misses:
        notes.append({"kind": "miss", "text": f"Miss: {p['symbol']} - called {p['predicted_direction']} (Up {p['p_up']}% / Down {p['p_down']}%) for the week ending {p['target_week_ending']}, but it moved {p['actual_return_pct']:+.2f}%."})

    if learning["status"] == "active":
        w = learning["weight"]
        if w < 0.3:
            notes.append({"kind": "warn", "text": f"Learning: live results support only {int(w * 100)}% of the model's deviation from usual odds, so displayed odds are now pulled almost all the way back to each asset's usual odds."})
        else:
            notes.append({"kind": "info", "text": f"Learning: live results support {int(w * 100)}% of the model's deviation from usual odds; displayed odds are blended accordingly."})
    else:
        notes.append({"kind": "info", "text": f"Learning is not applied yet - needs {learning['needed_resolved']} scored predictions across {learning['needed_weeks']} distinct weeks (has {learning['resolved']} across {learning['weeks']}). Until then odds are shown unadjusted."})
    return notes


def asset_record(journal: dict, symbol: str, limit: int = 8) -> dict:
    mine = [p for p in journal["predictions"] if p["symbol"] == symbol]
    resolved = [p for p in mine if p["resolved"]]
    recent = sorted(mine, key=lambda p: p["target_week_ending"], reverse=True)[:limit]
    return {
        "symbol": symbol,
        "logged": len(mine),
        "resolved": len(resolved),
        "direction_accuracy_pct": _pct(_mean([1.0 if p["direction_correct"] else 0.0 for p in resolved])),
        "baseline_accuracy_pct": _pct(_mean([1.0 if p["actual_return_pct"] > 0 else 0.0 for p in resolved])),
        "recent": recent,
    }


# ------------------------------------------------------------------- notes

def add_note(text: str) -> dict:
    with _LOCK:
        journal = load_journal()
        note = {"id": uuid.uuid4().hex[:8], "created_at": datetime.now(timezone.utc).isoformat(), "text": text.strip()[:2000]}
        journal["notes"].append(note)
        _save(journal)
        return note


def delete_note(note_id: str) -> bool:
    with _LOCK:
        journal = load_journal()
        kept = [n for n in journal["notes"] if n["id"] != note_id]
        if len(kept) == len(journal["notes"]):
            return False
        journal["notes"] = kept
        _save(journal)
        return True


def summary() -> dict:
    """Everything the Learning log page needs, in one read."""
    journal = load_journal()
    board = scoreboard(journal)
    learning = learning_state(journal)
    return {
        "last_updated": journal["last_updated"],
        "tracked_extra": journal["tracked_extra"],
        "scoreboard": board,
        "learning": learning,
        "lessons": lessons(journal, board, learning),
        "misses": recent_misses(journal),
        "notes": journal["notes"],
    }


# --------------------------------------------------------------------- CLI

def main() -> None:
    from app.universe import tickers_for_filters

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["update", "report"])
    args = parser.parse_args()

    if args.command == "update":
        symbols = tracked_symbols(tickers_for_filters("All", "All", "All"))
        print(update_journal(symbols))

    data = summary()
    board, learning = data["scoreboard"], data["learning"]
    print(f"\nLast updated: {data['last_updated']}")
    print(f"Scored: {board['resolved']}  Pending: {board['pending']}  Weeks: {board['weeks']}  Learning: {learning['status']} (weight {learning['weight']})")
    for note in data["lessons"]:
        print(f"  [{note['kind']}] {note['text']}")


if __name__ == "__main__":
    main()
