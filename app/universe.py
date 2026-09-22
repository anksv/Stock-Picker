"""Curated ticker universe, each tagged with a GICS-style sector, the
continent of the company's primary listing/headquarters, and an asset type
(Stock, ETF, or Bitcoin).

This is a static seed list of well-known, liquid stocks, ETFs, and Bitcoin
used as the screening universe. Non-US names are mostly USD-denominated ADRs
so prices stay comparable across the whole universe. Sector-focused ETFs
reuse the same sector names as stocks so they can be screened and compared
side by side; broad-market/bond/commodity ETFs get their own pseudo-sectors
since GICS sectors don't apply to them. Bitcoin trades 24/7 with no single
listing venue, so it's tagged continent="Global" and sector="Cryptocurrency"
rather than forced into a geography/GICS bucket that doesn't fit. Edit
STOCKS to add/remove tickers, sectors, continents, or asset types.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Stock:
    symbol: str
    sector: str
    continent: str
    asset_type: str = "Stock"


STOCKS: list[Stock] = [
    # --- North America (US) ---
    Stock("AAPL", "Technology", "North America"),
    Stock("MSFT", "Technology", "North America"),
    Stock("NVDA", "Technology", "North America"),
    Stock("GOOGL", "Technology", "North America"),
    Stock("AVGO", "Technology", "North America"),
    Stock("CRM", "Technology", "North America"),
    Stock("ADBE", "Technology", "North America"),
    Stock("ORCL", "Technology", "North America"),
    Stock("AMD", "Technology", "North America"),
    Stock("INTC", "Technology", "North America"),
    Stock("CSCO", "Technology", "North America"),
    Stock("IBM", "Technology", "North America"),
    Stock("QCOM", "Technology", "North America"),
    Stock("TXN", "Technology", "North America"),
    Stock("NOW", "Technology", "North America"),
    Stock("META", "Communication Services", "North America"),
    Stock("NFLX", "Communication Services", "North America"),
    Stock("DIS", "Communication Services", "North America"),
    Stock("TMUS", "Communication Services", "North America"),
    Stock("CMCSA", "Communication Services", "North America"),
    Stock("VZ", "Communication Services", "North America"),
    Stock("T", "Communication Services", "North America"),
    Stock("EA", "Communication Services", "North America"),
    Stock("WBD", "Communication Services", "North America"),
    Stock("AMZN", "Consumer Discretionary", "North America"),
    Stock("TSLA", "Consumer Discretionary", "North America"),
    Stock("HD", "Consumer Discretionary", "North America"),
    Stock("MCD", "Consumer Discretionary", "North America"),
    Stock("NKE", "Consumer Discretionary", "North America"),
    Stock("SBUX", "Consumer Discretionary", "North America"),
    Stock("LOW", "Consumer Discretionary", "North America"),
    Stock("BKNG", "Consumer Discretionary", "North America"),
    Stock("TJX", "Consumer Discretionary", "North America"),
    Stock("PG", "Consumer Staples", "North America"),
    Stock("KO", "Consumer Staples", "North America"),
    Stock("PEP", "Consumer Staples", "North America"),
    Stock("WMT", "Consumer Staples", "North America"),
    Stock("COST", "Consumer Staples", "North America"),
    Stock("PM", "Consumer Staples", "North America"),
    Stock("MDLZ", "Consumer Staples", "North America"),
    Stock("CL", "Consumer Staples", "North America"),
    Stock("MO", "Consumer Staples", "North America"),
    Stock("BRK-B", "Financials", "North America"),
    Stock("JPM", "Financials", "North America"),
    Stock("V", "Financials", "North America"),
    Stock("MA", "Financials", "North America"),
    Stock("BAC", "Financials", "North America"),
    Stock("WFC", "Financials", "North America"),
    Stock("GS", "Financials", "North America"),
    Stock("MS", "Financials", "North America"),
    Stock("AXP", "Financials", "North America"),
    Stock("SCHW", "Financials", "North America"),
    Stock("UNH", "Healthcare", "North America"),
    Stock("JNJ", "Healthcare", "North America"),
    Stock("LLY", "Healthcare", "North America"),
    Stock("ABBV", "Healthcare", "North America"),
    Stock("MRK", "Healthcare", "North America"),
    Stock("PFE", "Healthcare", "North America"),
    Stock("TMO", "Healthcare", "North America"),
    Stock("ABT", "Healthcare", "North America"),
    Stock("DHR", "Healthcare", "North America"),
    Stock("BMY", "Healthcare", "North America"),
    Stock("GE", "Industrials", "North America"),
    Stock("CAT", "Industrials", "North America"),
    Stock("UNP", "Industrials", "North America"),
    Stock("RTX", "Industrials", "North America"),
    Stock("HON", "Industrials", "North America"),
    Stock("BA", "Industrials", "North America"),
    Stock("UPS", "Industrials", "North America"),
    Stock("DE", "Industrials", "North America"),
    Stock("LMT", "Industrials", "North America"),
    Stock("XOM", "Energy", "North America"),
    Stock("CVX", "Energy", "North America"),
    Stock("COP", "Energy", "North America"),
    Stock("SLB", "Energy", "North America"),
    Stock("EOG", "Energy", "North America"),
    Stock("MPC", "Energy", "North America"),
    Stock("PSX", "Energy", "North America"),
    Stock("OXY", "Energy", "North America"),
    Stock("NEE", "Utilities", "North America"),
    Stock("DUK", "Utilities", "North America"),
    Stock("SO", "Utilities", "North America"),
    Stock("D", "Utilities", "North America"),
    Stock("AEP", "Utilities", "North America"),
    Stock("EXC", "Utilities", "North America"),
    Stock("SRE", "Utilities", "North America"),
    Stock("PLD", "Real Estate", "North America"),
    Stock("AMT", "Real Estate", "North America"),
    Stock("EQIX", "Real Estate", "North America"),
    Stock("SPG", "Real Estate", "North America"),
    Stock("O", "Real Estate", "North America"),
    Stock("PSA", "Real Estate", "North America"),
    Stock("WELL", "Real Estate", "North America"),
    Stock("LIN", "Materials", "North America"),
    Stock("SHW", "Materials", "North America"),
    Stock("APD", "Materials", "North America"),
    Stock("ECL", "Materials", "North America"),
    Stock("FCX", "Materials", "North America"),
    Stock("NEM", "Materials", "North America"),

    # --- Europe (USD ADRs / US-listed) ---
    Stock("ASML", "Technology", "Europe"),
    Stock("SAP", "Technology", "Europe"),
    Stock("NVO", "Healthcare", "Europe"),
    Stock("AZN", "Healthcare", "Europe"),
    Stock("SNY", "Healthcare", "Europe"),
    Stock("SHEL", "Energy", "Europe"),
    Stock("BP", "Energy", "Europe"),
    Stock("TTE", "Energy", "Europe"),
    Stock("UL", "Consumer Staples", "Europe"),
    Stock("NSRGY", "Consumer Staples", "Europe"),
    Stock("DEO", "Consumer Staples", "Europe"),

    # --- Asia (USD ADRs / US-listed) ---
    Stock("TSM", "Technology", "Asia"),
    Stock("SONY", "Technology", "Asia"),
    Stock("INFY", "Technology", "Asia"),
    Stock("WIT", "Technology", "Asia"),
    Stock("BABA", "Consumer Discretionary", "Asia"),
    Stock("JD", "Consumer Discretionary", "Asia"),
    Stock("PDD", "Consumer Discretionary", "Asia"),
    Stock("NIO", "Consumer Discretionary", "Asia"),
    Stock("TM", "Consumer Discretionary", "Asia"),
    Stock("IBN", "Financials", "Asia"),
    Stock("HDB", "Financials", "Asia"),

    # --- Oceania (USD ADRs / US-listed) ---
    Stock("BHP", "Materials", "Oceania"),
    Stock("RIO", "Materials", "Oceania"),
    Stock("AMCR", "Materials", "Oceania"),
    Stock("MQBKY", "Financials", "Oceania"),
    Stock("NWSA", "Communication Services", "Oceania"),

    # --- South America (USD ADRs) ---
    Stock("VALE", "Materials", "South America"),
    Stock("PBR", "Energy", "South America"),
    Stock("ITUB", "Financials", "South America"),
    Stock("MELI", "Consumer Discretionary", "South America"),

    # --- Africa (USD ADRs) ---
    Stock("SSL", "Energy", "Africa"),
    Stock("GFI", "Materials", "Africa"),

    # --- ETFs (US-listed) ---
    Stock("SPY", "Broad Market", "North America", "ETF"),
    Stock("VTI", "Broad Market", "North America", "ETF"),
    Stock("QQQ", "Broad Market", "North America", "ETF"),
    Stock("DIA", "Broad Market", "North America", "ETF"),
    Stock("IWM", "Broad Market", "North America", "ETF"),
    Stock("XLK", "Technology", "North America", "ETF"),
    Stock("XLF", "Financials", "North America", "ETF"),
    Stock("XLV", "Healthcare", "North America", "ETF"),
    Stock("XLE", "Energy", "North America", "ETF"),
    Stock("XLY", "Consumer Discretionary", "North America", "ETF"),
    Stock("XLP", "Consumer Staples", "North America", "ETF"),
    Stock("XLI", "Industrials", "North America", "ETF"),
    Stock("XLU", "Utilities", "North America", "ETF"),
    Stock("XLB", "Materials", "North America", "ETF"),
    Stock("XLRE", "Real Estate", "North America", "ETF"),
    Stock("XLC", "Communication Services", "North America", "ETF"),
    Stock("AGG", "Fixed Income", "North America", "ETF"),
    Stock("BND", "Fixed Income", "North America", "ETF"),
    Stock("TLT", "Fixed Income", "North America", "ETF"),
    Stock("GLD", "Commodities", "North America", "ETF"),
    Stock("SLV", "Commodities", "North America", "ETF"),
    Stock("USO", "Commodities", "North America", "ETF"),

    # --- Crypto (trades 24/7, no single listing venue/continent) ---
    Stock("BTC-USD", "Cryptocurrency", "Global", "Bitcoin"),
]

_BY_SYMBOL: dict[str, Stock] = {s.symbol: s for s in STOCKS}


def all_sectors() -> list[str]:
    return sorted({s.sector for s in STOCKS})


def all_continents() -> list[str]:
    return sorted({s.continent for s in STOCKS})


def all_asset_types() -> list[str]:
    return sorted({s.asset_type for s in STOCKS})


def tickers_for_filters(sector: str | None, continent: str | None, asset_type: str | None = None) -> list[str]:
    sector_l = sector.lower() if sector else "all"
    continent_l = continent.lower() if continent else "all"
    asset_type_l = asset_type.lower() if asset_type else "all"
    return [
        s.symbol
        for s in STOCKS
        if (sector_l == "all" or s.sector.lower() == sector_l)
        and (continent_l == "all" or s.continent.lower() == continent_l)
        and (asset_type_l == "all" or s.asset_type.lower() == asset_type_l)
    ]


def sector_for_ticker(ticker: str) -> str | None:
    stock = _BY_SYMBOL.get(ticker)
    return stock.sector if stock else None


def continent_for_ticker(ticker: str) -> str | None:
    stock = _BY_SYMBOL.get(ticker)
    return stock.continent if stock else None


def asset_type_for_ticker(ticker: str) -> str | None:
    stock = _BY_SYMBOL.get(ticker)
    return stock.asset_type if stock else None
