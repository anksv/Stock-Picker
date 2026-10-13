"""ETF-specific checks, built from a European investor's ETF checklist:
cost (TER), fund size, diversification, leveraged/inverse risk, domicile and
dividend-tax treatment, distribution policy, currency hedging, replication.

What this deliberately does NOT score, per that checklist: historical
returns, the fund's base currency, and dividend yield (a classic "dividend
trap" signal). Tracking error and tax registration are not exposed by the free
data source, so they are listed as manual checks rather than guessed.

Every field is "unknown" (None) when the data source doesn't state it - a
missing TER or fund size is reported as missing, never penalized or assumed.
Name-based inferences (swap, hedged, accumulating, active) rely on how fund
providers label their products, which is reliable when the label is present
and silent when it isn't.
"""
from __future__ import annotations

import re

import pandas as pd

# Fund-size thresholds are in the fund's reporting currency units; the
# checklist's "100 million minimum" is treated as 100M of whatever that is.
MIN_FUND_SIZE = 100_000_000

US_EXCHANGES = {"PCX", "NMS", "NGM", "NCM", "NYQ", "ASE", "BTS", "NYS"}
EU_EXCHANGES = {"GER", "STU", "FRA", "AMS", "PAR", "MIL", "VIE", "EBS", "MCE", "BRU"}
EU_DOMICILES = {"Ireland", "Luxembourg", "Germany", "France", "Netherlands", "Italy", "Spain", "Austria", "Belgium", "Finland", "Sweden"}

ISIN_DOMICILE = {
    "IE": "Ireland", "LU": "Luxembourg", "US": "United States", "DE": "Germany", "FR": "France", "GB": "United Kingdom",
    "JE": "Jersey", "CH": "Switzerland", "NL": "Netherlands", "AT": "Austria", "IT": "Italy", "ES": "Spain",
    "SE": "Sweden", "FI": "Finland", "BE": "Belgium", "CA": "Canada",
}

# Name-based detection is only a fallback for funds whose Yahoo category
# doesn't already say "Trading--Leveraged/Inverse". Generic words like "ultra"
# or "short" appear in harmless bond funds ("Ultra Short-Term Bond", "Short
# Duration"), so only unambiguous patterns are used: a Nx multiple, the
# explicit words, or ProShares' own Ultra/UltraPro/UltraShort branding.
_INVERSE = re.compile(
    r"\binverse\b|\bultrashort\b|\bproshares\s+ultrapro\s+short\b|\bproshares\s+short\b|\bdaily\s+short\b|\bbear\b|-\s?[123]x\b"
    r"|\bshort\s+(?:s&p|sp\s?500|nasdaq|qqq|dow|russell|msci|dax|stoxx|oil|gold|silver|vix)|\bshortdax\b",
    re.I,
)
_LEVERAGED = re.compile(r"\b[23]x\b|\bx[23]\b|\bleverag\w*\b(?!\s+(?:loan|buy-?out))|\bproshares\s+ultra(?:pro)?\b", re.I)
_ACCUMULATING = re.compile(r"\bacc\b|\baccumulating\b|\baccumulation\b|\(acc\)|\b[12]c\b|capitali[sz]ation", re.I)
_DISTRIBUTING = re.compile(r"\bdist\b|\bdistributing\b|\bdistribution\b|\(dist\)|\b[12]d\b", re.I)
_HEDGED = re.compile(r"\bhedged\b|\bhdg\b|\bchf hedged\b|\beur hedged\b", re.I)
_SWAP = re.compile(r"\bswap\b|\bsynthetic\b", re.I)
_ACTIVE = re.compile(r"\bactive(?:ly)?\b", re.I)


def classify_risk_type(name: str, category: str | None) -> str | None:
    """"Leveraged" / "Inverse" / "Volatility" for products that reset daily
    and decay over time (not for long-term holding), else None.
    """
    category = category or ""
    if category.startswith("Trading--Inverse"):
        return "Inverse"
    if category.startswith("Trading--Leveraged"):
        return "Leveraged"
    if category.startswith("Trading--Volatility"):
        return "Volatility"
    if _INVERSE.search(name):
        return "Inverse"
    if _LEVERAGED.search(name):
        return "Leveraged"
    return None


def _domicile(isin: str | None, family: str, name: str) -> tuple[str | None, str | None]:
    if isin and len(isin) >= 2 and isin[:2].isalpha() and isin[:2].upper() in ISIN_DOMICILE:
        return ISIN_DOMICILE[isin[:2].upper()], "ISIN"
    text = f"{family} {name}".lower()
    for word, country in (("ireland", "Ireland"), ("luxembourg", "Luxembourg"), ("jersey", "Jersey")):
        if word in text:
            return country, "fund manager's registered entity"
    return None, None


def _distribution(name: str, dividends: pd.Series | None, has_holdings: bool) -> tuple[str | None, str | None]:
    if _ACCUMULATING.search(name):
        return "Accumulating", "fund name"
    if _DISTRIBUTING.search(name):
        return "Distributing", "fund name"
    if dividends is not None and len(dividends):
        recent = dividends[dividends.index > dividends.index.max() - pd.Timedelta(days=400)]
        if len(recent):
            return "Distributing", "dividend history"
    if has_holdings and dividends is not None and len(dividends) == 0:
        return "Accumulating", "no payouts on record"
    return None, None


def _fetch_holdings(ticker) -> dict:
    out = {"top10_pct": None, "max_holding_pct": None, "max_sector": None, "asset_mix": None}
    try:
        funds = ticker.funds_data
    except Exception:
        return out
    try:
        holdings = funds.top_holdings
        if holdings is not None and len(holdings):
            weights = holdings["Holding Percent"].astype(float)
            out["top10_pct"] = round(float(weights.sum()) * 100, 1)
            out["max_holding_pct"] = round(float(weights.max()) * 100, 1)
    except Exception:
        pass
    try:
        sectors = funds.sector_weightings
        if sectors:
            name, weight = max(sectors.items(), key=lambda kv: kv[1] or 0)
            out["max_sector"] = {"name": name.replace("_", " "), "pct": round(float(weight) * 100, 1)}
    except Exception:
        pass
    try:
        mix = funds.asset_classes or {}
        stock, bond = mix.get("stockPosition") or 0, mix.get("bondPosition") or 0
        out["asset_mix"] = "Equity" if stock >= 0.7 else "Bond" if bond >= 0.7 else "Mixed" if stock + bond > 0.3 else None
    except Exception:
        pass
    return out


def build_etf_profile(ticker, info: dict, name: str) -> dict:
    category = info.get("category")
    family = info.get("fundFamily") or ""
    exchange = info.get("exchange")

    ter = info.get("netExpenseRatio")
    ter = round(float(ter), 3) if ter is not None else None
    size = info.get("totalAssets")
    size = float(size) if size else None

    holdings = _fetch_holdings(ticker)

    isin = None
    try:
        raw = ticker.isin
        isin = raw if raw and raw != "-" else None
    except Exception:
        pass
    try:
        dividends = ticker.dividends
    except Exception:
        dividends = None

    domicile, domicile_source = _domicile(isin, family, name)
    distribution, distribution_source = _distribution(name, dividends, holdings["top10_pct"] is not None)
    ucits = "ucits" in name.lower()
    if ucits or exchange in EU_EXCHANGES or domicile in EU_DOMICILES:
        eu_eligible = True
    elif domicile == "United States" or exchange in US_EXCHANGES:
        eu_eligible = False  # US-domiciled/US-listed funds generally lack the PRIIPs KID EU brokers require
    else:
        eu_eligible = None

    profile = {
        "risk_type": classify_risk_type(name, category),
        "category": category,
        "expense_ratio_pct": ter,
        "fund_size": size,
        "top10_pct": holdings["top10_pct"],
        "max_holding_pct": holdings["max_holding_pct"],
        "max_sector": holdings["max_sector"],
        "asset_mix": holdings["asset_mix"],
        "distribution": distribution,
        "distribution_source": distribution_source,
        "domicile": domicile,
        "domicile_source": domicile_source,
        "isin": isin,
        "ucits": ucits,
        "eu_retail_eligible": eu_eligible,
        "currency_hedged": bool(_HEDGED.search(name)),
        "replication": "Swap-based (synthetic)" if _SWAP.search(name) else None,
        "management_style": "Actively managed" if _ACTIVE.search(name) else None,
    }
    return {**profile, **_score(profile)}


def _score(p: dict) -> dict:
    score = 50
    flags: list[dict] = []
    unknown: list[str] = []

    def add(kind: str, text: str) -> None:
        flags.append({"kind": kind, "text": text})

    ter = p["expense_ratio_pct"]
    if ter is None:
        unknown.append("expense ratio (TER)")
    else:
        per_1000 = ter * 10
        if ter <= 0.10:
            score += 15; add("good", f"Very low cost: {ter}% TER (about {per_1000:.2f} per 1,000 invested per year).")
        elif ter <= 0.25:
            score += 12; add("good", f"Low cost: {ter}% TER (about {per_1000:.2f} per 1,000 per year).")
        elif ter <= 0.40:
            score += 6; add("info", f"Moderate cost: {ter}% TER (about {per_1000:.2f} per 1,000 per year).")
        elif ter <= 0.60:
            add("info", f"Above-average cost: {ter}% TER (about {per_1000:.2f} per 1,000 per year).")
        elif ter <= 0.80:
            score -= 6; add("warn", f"Expensive: {ter}% TER (about {per_1000:.2f} per 1,000 per year) - fees compound against you every year.")
        else:
            score -= 12; add("warn", f"Very expensive: {ter}% TER (about {per_1000:.2f} per 1,000 per year).")

    size = p["fund_size"]
    if size is None:
        unknown.append("fund size")
    elif size < MIN_FUND_SIZE:
        score -= 12; add("warn", f"Small fund (about {size / 1e6:.0f}M, under your 100M minimum): higher risk the provider closes it.")
    elif size < 500_000_000:
        add("info", f"Fund size about {size / 1e6:.0f}M - above the 100M minimum but still modest.")
    elif size < 1_000_000_000:
        score += 5; add("good", f"Established fund: about {size / 1e6:.0f}M in assets.")
    else:
        score += 10; add("good", f"Large fund: about {size / 1e9:.1f}B in assets - closure risk is remote.")

    top10 = p["top10_pct"]
    if top10 is None:
        unknown.append("holdings concentration")
    else:
        if top10 <= 30:
            score += 8; add("good", f"Well diversified: the top 10 holdings are only {top10}% of the fund.")
        elif top10 <= 45:
            score += 4; add("info", f"Reasonably diversified: top 10 holdings are {top10}% of the fund.")
        elif top10 <= 60:
            add("info", f"Fairly concentrated: top 10 holdings are {top10}% of the fund.")
        else:
            score -= 6; add("warn", f"Concentrated (thematic or sector fund): the top 10 holdings are {top10}% of the fund.")
        if p["max_holding_pct"] and p["max_holding_pct"] > 25:
            score -= 4; add("warn", f"One holding is {p['max_holding_pct']}% of the fund - a single-stock bet inside an ETF.")

    if p["risk_type"]:
        score -= 40
        text = {
            "Leveraged": "Leveraged ETF: resets daily, so losses compound and it decays in choppy markets - risky, not for long-term holding.",
            "Inverse": "Inverse ETF: bets against the market and resets daily - at most a short-term trade, not a long-term holding.",
            "Volatility": "Volatility product: decays over time by design - short-term trading only.",
        }[p["risk_type"]]
        add("risk", text)

    if p["asset_mix"] == "Equity" and p["domicile"] in ("Ireland", "Luxembourg"):
        if p["domicile"] == "Ireland":
            score += 3; add("good", "Domiciled in Ireland: 15% withholding tax on US dividends (30% for Luxembourg, per your notes) - matters for US-heavy funds.")
        else:
            score -= 3; add("warn", "Domiciled in Luxembourg: 30% withholding tax on US dividends (15% for Ireland, per your notes) - matters for US-heavy funds.")
    elif p["domicile"]:
        add("info", f"Domicile: {p['domicile']} (from {p['domicile_source']}).")
    else:
        unknown.append("domicile")

    if p["eu_retail_eligible"] is False:
        add("warn", "US-domiciled: usually can't be bought by EU retail investors (no PRIIPs KID) - check with your broker before relying on it.")

    if p["distribution"] == "Accumulating":
        add("info", f"Accumulating (from {p['distribution_source']}): payouts are reinvested, which per your notes is the better tax treatment in Germany.")
    elif p["distribution"] == "Distributing":
        add("info", f"Distributing (from {p['distribution_source']}): pays out dividends. Don't chase a high yield on its own - that is the 'dividend trap'.")
    else:
        unknown.append("distribution policy")

    if p["currency_hedged"]:
        add("info", "Currency-hedged: removes EUR/USD swings from your return, at the cost of hedging fees and giving up currency gains.")
    if p["replication"]:
        add("info", f"{p['replication']} per the fund name (often used for tax optimisation) - confirm in the KID.")
    if p["management_style"]:
        add("info", "Actively managed per the fund name: may outperform an index, but usually costs more.")

    measurable_known = sum(v is not None for v in (ter, size, top10))
    score = int(max(0, min(100, score)))
    if p["risk_type"]:
        label = "High-Risk Product"
    elif measurable_known < 2:
        label = "Limited Data"
    elif score >= 75:
        label = "Top-Tier ETF"
    elif score >= 60:
        label = "Solid ETF"
    elif score >= 45:
        label = "Fair ETF"
    else:
        label = "Weak ETF"

    return {
        "etf_score": score,
        "etf_label": label,
        "flags": flags,
        "unknown_checks": unknown,
        "checks_known": measurable_known,
        "manual_checks": MANUAL_CHECKS,
    }


MANUAL_CHECKS = [
    "Tracking error: take the ISIN, open the provider's official site, go to Performance and check the annualised tracking difference against the index.",
    "KID (Key Information Document): check the annual cost impact and the exit policy.",
    "Tax registration: confirm the fund is registered for sale/taxation in your country.",
    "Replication method (full replication, sampling, or swap): confirm in the KID if the fund name doesn't say.",
    "Exchange: confirm on the exchange section of your broker that you can buy it in EUR (the fund currency itself matters little).",
    "Country exposure: open the provider's Holdings section to see which countries your money goes to.",
]
