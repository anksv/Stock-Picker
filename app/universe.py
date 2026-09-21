"""Curated ticker universe grouped by GICS-style sector.

This is a static seed list of well-known, liquid US-listed stocks used as the
screening universe. Edit this list to add/remove tickers or sectors.
"""

UNIVERSE = {
    "Technology": [
        "AAPL", "MSFT", "NVDA", "GOOGL", "AVGO", "CRM", "ADBE", "ORCL",
        "AMD", "INTC", "CSCO", "IBM", "QCOM", "TXN", "NOW",
    ],
    "Communication Services": [
        "META", "NFLX", "DIS", "TMUS", "CMCSA", "VZ", "T", "EA", "WBD",
    ],
    "Consumer Discretionary": [
        "AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "LOW", "BKNG", "TJX",
    ],
    "Consumer Staples": [
        "PG", "KO", "PEP", "WMT", "COST", "PM", "MDLZ", "CL", "MO",
    ],
    "Financials": [
        "BRK-B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "AXP", "SCHW",
    ],
    "Healthcare": [
        "UNH", "JNJ", "LLY", "ABBV", "MRK", "PFE", "TMO", "ABT", "DHR", "BMY",
    ],
    "Industrials": [
        "GE", "CAT", "UNP", "RTX", "HON", "BA", "UPS", "DE", "LMT",
    ],
    "Energy": [
        "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "OXY",
    ],
    "Utilities": [
        "NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE",
    ],
    "Real Estate": [
        "PLD", "AMT", "EQIX", "SPG", "O", "PSA", "WELL",
    ],
    "Materials": [
        "LIN", "SHW", "APD", "ECL", "FCX", "NEM",
    ],
}


def all_sectors() -> list[str]:
    return sorted(UNIVERSE.keys())


def tickers_for_sector(sector: str | None) -> list[str]:
    if not sector or sector.lower() == "all":
        return [t for tickers in UNIVERSE.values() for t in tickers]
    for name, tickers in UNIVERSE.items():
        if name.lower() == sector.lower():
            return tickers
    return []


def sector_for_ticker(ticker: str) -> str | None:
    for name, tickers in UNIVERSE.items():
        if ticker in tickers:
            return name
    return None
