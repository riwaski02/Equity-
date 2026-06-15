"""
data.py
-------
All data-fetching helpers for the Equity Dashboard.

Everything is sourced from Yahoo Finance through the `yfinance` library, with
defensive error handling so the dashboard never crashes when a field is
missing for a given ticker.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd
import streamlit as st
import yfinance as yf


# --------------------------------------------------------------------------- #
# Small utilities
# --------------------------------------------------------------------------- #
def _safe(d: dict, *keys, default=None):
    """Return the first key present in dict `d` (handles Yahoo's renamed keys)."""
    for k in keys:
        v = d.get(k)
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            return v
    return default


def fmt_number(value: Optional[float], suffix: str = "", prefix: str = "",
               decimals: int = 2, pct: bool = False) -> str:
    """Human-friendly formatting with B/M/K scaling."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "—"

    if pct:
        return f"{value * 100:.{decimals}f}%"

    abs_v = abs(value)
    if abs_v >= 1e12:
        return f"{prefix}{value / 1e12:.{decimals}f}T{suffix}"
    if abs_v >= 1e9:
        return f"{prefix}{value / 1e9:.{decimals}f}B{suffix}"
    if abs_v >= 1e6:
        return f"{prefix}{value / 1e6:.{decimals}f}M{suffix}"
    if abs_v >= 1e3:
        return f"{prefix}{value / 1e3:.{decimals}f}K{suffix}"
    return f"{prefix}{value:.{decimals}f}{suffix}"


# --------------------------------------------------------------------------- #
# Core container
# --------------------------------------------------------------------------- #
@dataclass
class StockData:
    ticker: str
    info: dict = field(default_factory=dict)
    fast_info: dict = field(default_factory=dict)
    history: pd.DataFrame = field(default_factory=pd.DataFrame)
    financials: pd.DataFrame = field(default_factory=pd.DataFrame)
    balance_sheet: pd.DataFrame = field(default_factory=pd.DataFrame)
    cashflow: pd.DataFrame = field(default_factory=pd.DataFrame)
    recommendations: pd.DataFrame = field(default_factory=pd.DataFrame)
    news: list = field(default_factory=list)
    valid: bool = True
    error: str = ""

    # ---- convenience getters -------------------------------------------- #
    @property
    def name(self) -> str:
        return _safe(self.info, "longName", "shortName", default=self.ticker)

    @property
    def price(self) -> Optional[float]:
        return _safe(self.fast_info, "lastPrice", default=None) or \
            _safe(self.info, "currentPrice", "regularMarketPrice")

    @property
    def currency(self) -> str:
        return _safe(self.fast_info, "currency", default="") or \
            _safe(self.info, "currency", default="USD")


# --------------------------------------------------------------------------- #
# Fetch
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=900, show_spinner=False)
def load_stock(ticker: str) -> StockData:
    """Download everything we need for one ticker. Cached for 15 minutes."""
    ticker = ticker.strip().upper()
    if not ticker:
        return StockData(ticker="", valid=False, error="Empty ticker.")

    try:
        tk = yf.Ticker(ticker)

        # .info can be flaky; wrap it.
        try:
            info = tk.info or {}
        except Exception:
            info = {}

        try:
            fast = dict(tk.fast_info) if tk.fast_info else {}
        except Exception:
            fast = {}

        if not info and not fast:
            return StockData(ticker=ticker, valid=False,
                             error=f"No data returned for '{ticker}'. "
                                   f"Check the symbol (e.g. AAPL, MSFT, BMW.DE).")

        hist = tk.history(period="5y", auto_adjust=True)

        try:
            fin = tk.financials
        except Exception:
            fin = pd.DataFrame()
        try:
            bs = tk.balance_sheet
        except Exception:
            bs = pd.DataFrame()
        try:
            cf = tk.cashflow
        except Exception:
            cf = pd.DataFrame()
        try:
            recs = tk.recommendations
        except Exception:
            recs = pd.DataFrame()

        try:
            news = tk.news or []
        except Exception:
            news = []

        return StockData(
            ticker=ticker, info=info, fast_info=fast, history=hist,
            financials=fin if fin is not None else pd.DataFrame(),
            balance_sheet=bs if bs is not None else pd.DataFrame(),
            cashflow=cf if cf is not None else pd.DataFrame(),
            recommendations=recs if recs is not None else pd.DataFrame(),
            news=news,
        )
    except Exception as exc:  # pragma: no cover
        return StockData(ticker=ticker, valid=False, error=str(exc))


# --------------------------------------------------------------------------- #
# Metric extraction
# --------------------------------------------------------------------------- #
def get_valuation_metrics(sd: StockData) -> dict:
    """Pull / derive the headline valuation multiples."""
    info = sd.info
    m: dict[str, Any] = {}

    m["Market Cap"] = _safe(info, "marketCap")
    m["Enterprise Value (EV)"] = _safe(info, "enterpriseValue")
    m["P/E (Trailing)"] = _safe(info, "trailingPE")
    m["P/E (Forward)"] = _safe(info, "forwardPE")
    m["PEG Ratio"] = _safe(info, "pegRatio", "trailingPegRatio")
    m["P/S (Trailing)"] = _safe(info, "priceToSalesTrailing12Months")
    m["P/B"] = _safe(info, "priceToBook")
    m["EV/EBITDA"] = _safe(info, "enterpriseToEbitda")
    m["EV/Revenue"] = _safe(info, "enterpriseToRevenue")
    m["Trailing EPS"] = _safe(info, "trailingEps")
    m["Forward EPS"] = _safe(info, "forwardEps")
    m["Book Value / Share"] = _safe(info, "bookValue")
    m["Profit Margin"] = _safe(info, "profitMargins")
    m["Operating Margin"] = _safe(info, "operatingMargins")
    m["Gross Margin"] = _safe(info, "grossMargins")
    m["ROE"] = _safe(info, "returnOnEquity")
    m["ROA"] = _safe(info, "returnOnAssets")
    m["Revenue (TTM)"] = _safe(info, "totalRevenue")
    m["EBITDA"] = _safe(info, "ebitda")
    m["Net Income (TTM)"] = _safe(info, "netIncomeToCommon")
    m["Revenue Growth (YoY)"] = _safe(info, "revenueGrowth")
    m["Earnings Growth (YoY)"] = _safe(info, "earningsGrowth")
    m["Debt / Equity"] = _safe(info, "debtToEquity")
    m["Current Ratio"] = _safe(info, "currentRatio")
    m["Quick Ratio"] = _safe(info, "quickRatio")
    m["Total Cash"] = _safe(info, "totalCash")
    m["Total Debt"] = _safe(info, "totalDebt")
    m["Beta"] = _safe(info, "beta")
    m["52W High"] = _safe(info, "fiftyTwoWeekHigh")
    m["52W Low"] = _safe(info, "fiftyTwoWeekLow")
    return m


def get_dividend_metrics(sd: StockData) -> dict:
    info = sd.info
    return {
        "Dividend Rate (annual)": _safe(info, "dividendRate"),
        "Dividend Yield": _safe(info, "dividendYield"),
        "Trailing Yield": _safe(info, "trailingAnnualDividendYield"),
        "Payout Ratio": _safe(info, "payoutRatio"),
        "5Y Avg Yield": _safe(info, "fiveYearAvgDividendYield"),
        "Ex-Dividend Date": _safe(info, "exDividendDate"),
    }


def _row(df: pd.DataFrame, *names) -> Optional[float]:
    """Get the most recent value of a row whose index matches one of `names`."""
    if df is None or df.empty:
        return None
    for n in names:
        if n in df.index:
            series = df.loc[n].dropna()
            if not series.empty:
                return float(series.iloc[0])
    return None


def get_cashflow_metrics(sd: StockData) -> dict:
    """
    Free Cash Flow (FCFF) and Free Cash Flow to Equity (FCFE).

    FCF (to firm) = Operating Cash Flow - Capital Expenditures
    FCFE          = FCF + Net Borrowing
                  = OCF - CapEx + (Debt Issued - Debt Repaid)
    """
    cf = sd.cashflow
    info = sd.info

    ocf = _row(cf, "Operating Cash Flow", "Total Cash From Operating Activities")
    capex = _row(cf, "Capital Expenditure", "Capital Expenditures")
    # Yahoo's "Free Cash Flow" row when present:
    fcf_reported = _row(cf, "Free Cash Flow") or _safe(info, "freeCashflow")

    debt_issued = _row(cf, "Issuance Of Debt", "Long Term Debt Issuance",
                       "Net Issuance Payments Of Debt")
    debt_repaid = _row(cf, "Repayment Of Debt", "Long Term Debt Payments")

    # Compute FCF (firm)
    if ocf is not None and capex is not None:
        fcf = ocf + capex  # capex is reported negative in Yahoo cashflow
    else:
        fcf = fcf_reported

    # Net borrowing
    net_borrow = None
    if debt_issued is not None or debt_repaid is not None:
        net_borrow = (debt_issued or 0.0) + (debt_repaid or 0.0)

    fcfe = None
    if fcf is not None:
        fcfe = fcf + (net_borrow or 0.0)

    shares = _safe(info, "sharesOutstanding")
    fcfe_ps = fcfe / shares if (fcfe and shares) else None
    fcf_ps = fcf / shares if (fcf and shares) else None

    return {
        "Operating Cash Flow": ocf,
        "Capital Expenditure": capex,
        "Free Cash Flow (FCFF)": fcf,
        "Net Borrowing": net_borrow,
        "Free Cash Flow to Equity (FCFE)": fcfe,
        "FCF / Share": fcf_ps,
        "FCFE / Share": fcfe_ps,
        "FCF Yield": (fcf / _safe(info, "marketCap")) if (fcf and _safe(info, "marketCap")) else None,
    }


def get_analyst_consensus(sd: StockData) -> dict:
    info = sd.info
    out = {
        "Recommendation": _safe(info, "recommendationKey", default="—"),
        "Recommendation Mean (1=Buy,5=Sell)": _safe(info, "recommendationMean"),
        "Number of Analysts": _safe(info, "numberOfAnalystOpinions"),
        "Target Mean": _safe(info, "targetMeanPrice"),
        "Target Median": _safe(info, "targetMedianPrice"),
        "Target High": _safe(info, "targetHighPrice"),
        "Target Low": _safe(info, "targetLowPrice"),
    }
    price = sd.price
    if price and out["Target Mean"]:
        out["Upside to Mean Target"] = (out["Target Mean"] / price) - 1.0
    return out


def get_recommendation_breakdown(sd: StockData) -> Optional[pd.DataFrame]:
    """Latest strongBuy/buy/hold/sell/strongSell distribution if available."""
    recs = sd.recommendations
    if recs is None or recs.empty:
        return None
    cols = ["strongBuy", "buy", "hold", "sell", "strongSell"]
    if all(c in recs.columns for c in cols):
        latest = recs.iloc[0]
        df = pd.DataFrame({
            "Rating": ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"],
            "Analysts": [int(latest[c]) for c in cols],
        })
        return df
    return None


def get_news(sd: StockData, limit: int = 8) -> list[dict]:
    """Normalise Yahoo's news payload (schema changes occasionally)."""
    out = []
    for item in (sd.news or [])[: limit * 2]:
        content = item.get("content", item)  # newer schema nests under 'content'
        title = content.get("title") or item.get("title")
        if not title:
            continue
        # URL
        url = (
            (content.get("canonicalUrl") or {}).get("url")
            or (content.get("clickThroughUrl") or {}).get("url")
            or item.get("link")
        )
        publisher = (
            (content.get("provider") or {}).get("displayName")
            or item.get("publisher")
            or "—"
        )
        # timestamp
        ts = content.get("pubDate") or item.get("providerPublishTime")
        when = ""
        if isinstance(ts, (int, float)):
            when = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        elif isinstance(ts, str):
            when = ts.replace("T", " ").replace("Z", " UTC")

        out.append({"title": title, "url": url, "publisher": publisher, "when": when})
        if len(out) >= limit:
            break
    return out
