"""Fetches a stock's recent news headlines and tags each one with a rough
positive/negative keyword count.

IMPORTANT: this is NOT real sentiment analysis, NLP, or an LLM reading the
articles - it's a plain keyword count over headlines/summaries. It exists to
give a quick pointer for further reading, not a verdict. A headline can
trip the wrong keyword (e.g. "beats" about a competitor, "warns" about an
unrelated risk), so always open the linked article and judge for yourself
before acting on it.
"""
from __future__ import annotations

import time

import yfinance as yf

NEWS_CACHE_TTL_SECONDS = 20 * 60
MAX_HEADLINES = 8

POSITIVE_WORDS = [
    "beat", "beats", "beating", "surge", "surges", "soar", "soars",
    "record high", "upgrade", "upgraded", "outperform", "rally", "rallies",
    "raises guidance", "raises forecast", "raised guidance", "strong demand",
    "profit rises", "profit jumps", "expands", "expansion", "breakthrough",
    "partnership", "approval", "approved", "wins contract", "buyback",
    "dividend increase", "bullish", "growth", "gains", "jumps", "climbs",
    "tops estimates", "exceeds", "best buy", "strong buy",
]

NEGATIVE_WORDS = [
    "miss", "misses", "missed", "plunge", "plunges", "slump", "slumps",
    "downgrade", "downgraded", "underperform", "lawsuit", "investigation",
    "probe", "recall", "layoff", "layoffs", "cuts guidance", "cuts forecast",
    "cut guidance", "weak demand", "profit falls", "profit drops", "decline",
    "declines", "bearish", "fraud", "scandal", "ban", "banned", "tariff",
    "tariffs", "sanction", "sanctions", "fine", "fined", "bankruptcy",
    "warns", "warning", "delisted", "resigns", "antitrust", "sued", "sues",
    "sell-off", "selloff", "crash", "crashes",
]

_news_cache: dict[str, tuple[float, dict]] = {}


def _score_text(text: str) -> int:
    text_l = text.lower()
    positive = sum(text_l.count(w) for w in POSITIVE_WORDS)
    negative = sum(text_l.count(w) for w in NEGATIVE_WORDS)
    return positive - negative


def _fetch_news_signal(symbol: str) -> dict:
    try:
        raw_news = yf.Ticker(symbol).news or []
    except Exception:
        raw_news = []

    headlines = []
    total_score = 0
    for item in raw_news[:MAX_HEADLINES]:
        content = item.get("content") or item
        title = (content.get("title") or "").strip()
        if not title:
            continue
        summary = content.get("summary") or content.get("description") or ""
        provider = (content.get("provider") or {}).get("displayName")
        url = (content.get("canonicalUrl") or content.get("clickThroughUrl") or {}).get("url")
        published_at = content.get("pubDate") or content.get("displayTime")

        item_score = _score_text(f"{title} {summary}")
        total_score += item_score

        headlines.append({
            "title": title,
            "publisher": provider,
            "published_at": published_at,
            "url": url,
            "sentiment": "positive" if item_score > 0 else "negative" if item_score < 0 else "neutral",
        })

    if not headlines:
        label = "No Recent News"
    elif total_score >= 2:
        label = "Positive"
    elif total_score <= -2:
        label = "Negative"
    elif total_score == 0:
        label = "Neutral"
    else:
        label = "Mixed"

    return {
        "symbol": symbol,
        "headlines": headlines,
        "sentiment_score": total_score,
        "sentiment_label": label,
    }


def get_news_signal(symbol: str) -> dict:
    """Cached wrapper - news is fetched on demand (not during a full scan)
    since it's a per-symbol call that would otherwise slow every screen
    down; a short TTL keeps it reasonably fresh across repeat clicks.
    """
    now = time.time()
    cached = _news_cache.get(symbol)
    if cached and now - cached[0] < NEWS_CACHE_TTL_SECONDS:
        return cached[1]
    result = _fetch_news_signal(symbol)
    _news_cache[symbol] = (now, result)
    return result
