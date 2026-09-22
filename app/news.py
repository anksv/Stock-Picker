"""Fetches a stock's recent news headlines from two free sources and tags
each one with a rough positive/negative keyword count.

Sources:
  - Yahoo Finance's own per-ticker news feed (via yfinance).
  - Google News RSS, searched by company name - this is what actually
    surfaces real newspaper/wire-service coverage (Reuters, Bloomberg, WSJ,
    AP, etc. headlines when they cover the ticker), since there's no free
    public API for any single one of those outlets. Google's own feed
    license restricts this to "a personal feed reader for personal,
    non-commercial use" - this app is exactly that (local, single-user,
    not redistributed or run as a service), so stay within that use if you
    adapt this code.

IMPORTANT: the positive/negative tag is NOT real sentiment analysis, NLP,
or an LLM reading the articles - it's a plain keyword count over
headlines/summaries. It exists to give a quick pointer for further
reading, not a verdict. A headline can trip the wrong keyword (e.g.
"beats" about a competitor, "warns" about an unrelated risk), so always
open the linked article and judge for yourself before acting on it.
"""
from __future__ import annotations

import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import yfinance as yf

NEWS_CACHE_TTL_SECONDS = 20 * 60
MAX_HEADLINES = 10
REQUEST_TIMEOUT_SECONDS = 8
GOOGLE_NEWS_MAX_ITEMS = 6

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


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def _fetch_yahoo_headlines(symbol: str) -> list[dict]:
    try:
        raw_news = yf.Ticker(symbol).news or []
    except Exception:
        raw_news = []

    headlines = []
    for item in raw_news:
        content = item.get("content") or item
        title = (content.get("title") or "").strip()
        if not title:
            continue
        summary = content.get("summary") or content.get("description") or ""
        provider = (content.get("provider") or {}).get("displayName")
        url = (content.get("canonicalUrl") or content.get("clickThroughUrl") or {}).get("url")
        published_at = content.get("pubDate") or content.get("displayTime")

        headlines.append({
            "title": title,
            "summary": summary,
            "publisher": provider,
            "url": url,
            "published_at": published_at,
            "source_channel": "Yahoo Finance",
        })
    return headlines


def _fetch_google_news_headlines(query: str) -> list[dict]:
    """Real newspaper/wire-service coverage via Google News RSS, searched by
    company name. No API key - see module docstring for the usage terms
    Google's feed license attaches to this.
    """
    if not query:
        return []

    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
        "q": f"{query} stock",
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    })

    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            raw = response.read()
        root = ET.fromstring(raw)
    except Exception:
        return []

    headlines = []
    for item in root.findall("./channel/item")[:GOOGLE_NEWS_MAX_ITEMS]:
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        # Google News titles are usually "Headline - Publisher"; the <source>
        # element (when present) gives the publisher name more reliably.
        source_el = item.find("source")
        publisher = source_el.text if source_el is not None and source_el.text else None
        if publisher and title.endswith(f" - {publisher}"):
            title = title[: -(len(publisher) + 3)].strip()

        headlines.append({
            "title": title,
            "summary": "",
            "publisher": publisher,
            "url": item.findtext("link"),
            "published_at": item.findtext("pubDate"),
            "source_channel": "Google News",
        })
    return headlines


def _fetch_news_signal(symbol: str, name: str | None) -> dict:
    combined = _fetch_yahoo_headlines(symbol) + _fetch_google_news_headlines(name or symbol)

    # Sort newest first (undated items sink to the bottom rather than being dropped).
    # Mixed tz-aware/naive datetimes across sources would raise on comparison,
    # so every parsed value and the fallback are forced to be tz-aware.
    def _sort_key(h: dict) -> datetime:
        dt = _parse_datetime(h["published_at"])
        if dt is None:
            return datetime.min.replace(tzinfo=timezone.utc)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    combined.sort(key=_sort_key, reverse=True)

    headlines = []
    total_score = 0
    seen_titles: set[str] = set()
    for item in combined:
        title_key = item["title"].lower()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        if len(headlines) >= MAX_HEADLINES:
            break

        item_score = _score_text(f"{item['title']} {item.get('summary', '')}")
        total_score += item_score

        parsed = _parse_datetime(item["published_at"])
        headlines.append({
            "title": item["title"],
            "publisher": item["publisher"],
            "published_at": parsed.isoformat() if parsed else item["published_at"],
            "url": item["url"],
            "source_channel": item["source_channel"],
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


def get_news_signal(symbol: str, name: str | None = None) -> dict:
    """Cached wrapper - news is fetched on demand (not during a full scan)
    since it's a per-symbol call that would otherwise slow every screen
    down; a short TTL keeps it reasonably fresh across repeat clicks.
    """
    now = time.time()
    cached = _news_cache.get(symbol)
    if cached and now - cached[0] < NEWS_CACHE_TTL_SECONDS:
        return cached[1]
    result = _fetch_news_signal(symbol, name)
    _news_cache[symbol] = (now, result)
    return result
