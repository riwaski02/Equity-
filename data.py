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


# --------------------------------------------------------------------------- #
# Historical analysis ("Full Analysis & Metrics" section)
# --------------------------------------------------------------------------- #
def _row_series(df: pd.DataFrame, *names) -> Optional[pd.Series]:
    """Return the full (date-indexed) series of the first matching row."""
    if df is None or df.empty:
        return None
    for n in names:
        if n in df.index:
            s = df.loc[n].dropna()
            if not s.empty:
                return s
    return None


def _by_year(series: Optional[pd.Series]) -> dict:
    """Collapse a date-indexed series into {year: value}."""
    out: dict[int, float] = {}
    if series is None:
        return out
    for idx, val in series.items():
        try:
            year = idx.year
        except AttributeError:
            try:
                year = pd.to_datetime(idx).year
            except Exception:
                continue
        try:
            out[year] = float(val)
        except (TypeError, ValueError):
            continue
    return out


def get_financial_history(sd: StockData) -> pd.DataFrame:
    """
    Build a year-indexed DataFrame of core fundamentals from the annual
    statements. Columns: Sales, Gross Profit, Gross Margin %, EBITDA,
    Net Income, FCF, EPS. Rows are years (ascending).
    """
    fin, cf = sd.financials, sd.cashflow
    if (fin is None or fin.empty) and (cf is None or cf.empty):
        return pd.DataFrame()

    sales = _by_year(_row_series(fin, "Total Revenue", "Operating Revenue"))
    gross = _by_year(_row_series(fin, "Gross Profit"))
    net_income = _by_year(_row_series(
        fin, "Net Income", "Net Income Common Stockholders",
        "Net Income Continuous Operations"))
    eps = _by_year(_row_series(fin, "Diluted EPS", "Basic EPS"))

    # EBITDA: prefer the reported row, else Operating Income + D&A.
    ebitda = _by_year(_row_series(fin, "EBITDA", "Normalized EBITDA"))
    if not ebitda:
        op = _by_year(_row_series(fin, "Operating Income",
                                  "Total Operating Income As Reported"))
        da = _by_year(_row_series(cf, "Depreciation And Amortization",
                                  "Depreciation Amortization Depletion",
                                  "Depreciation"))
        ebitda = {y: op[y] + da.get(y, 0.0) for y in op} if op else {}

    # FCF: reported row, else Operating Cash Flow + CapEx (capex is negative).
    fcf = _by_year(_row_series(cf, "Free Cash Flow"))
    if not fcf:
        ocf = _by_year(_row_series(cf, "Operating Cash Flow",
                                   "Total Cash From Operating Activities"))
        capex = _by_year(_row_series(cf, "Capital Expenditure",
                                     "Capital Expenditures"))
        if ocf:
            fcf = {y: ocf[y] + capex.get(y, 0.0) for y in ocf}

    years = sorted(set(sales) | set(net_income) | set(ebitda) | set(fcf) | set(eps))
    if not years:
        return pd.DataFrame()

    rows = []
    for y in years:
        rev = sales.get(y)
        gp = gross.get(y)
        gm = (gp / rev * 100) if (gp is not None and rev) else None
        rows.append({
            "Sales": rev,
            "Gross Profit": gp,
            "Gross Margin %": gm,
            "EBITDA": ebitda.get(y),
            "Net Income": net_income.get(y),
            "FCF": fcf.get(y),
            "EPS": eps.get(y),
        })
    df = pd.DataFrame(rows, index=years)
    df.index.name = "Year"
    return df.tail(5)


def get_price_ranges_by_year(sd: StockData) -> pd.DataFrame:
    """High / Low / Close per calendar year for the last 5 years."""
    h = sd.history
    if h is None or h.empty:
        return pd.DataFrame()
    g = h.groupby(h.index.year)
    df = pd.DataFrame({
        "High": g["High"].max(),
        "Low": g["Low"].min(),
        "Close": g["Close"].last(),
    })
    df["Range %"] = (df["High"] - df["Low"]) / df["Low"] * 100
    df.index.name = "Year"
    return df.tail(5)


def get_multiples_history(sd: StockData, fin_hist: pd.DataFrame) -> pd.DataFrame:
    """
    Approximate the historical evolution of P/E and EV/EBITDA.

    P/E       = year-end close / EPS that fiscal year
    EV/EBITDA = (year-end market cap + net debt) / EBITDA

    Note: market cap uses *current* shares outstanding as an approximation
    (Yahoo does not expose a reliable per-year share count), so older years
    are indicative rather than exact.
    """
    if fin_hist is None or fin_hist.empty or sd.history is None or sd.history.empty:
        return pd.DataFrame()

    h = sd.history
    year_close = h.groupby(h.index.year)["Close"].last()
    shares = _safe(sd.info, "sharesOutstanding")
    bs = sd.balance_sheet
    debt = _by_year(_row_series(bs, "Total Debt", "Long Term Debt And Capital Lease Obligation"))
    cash = _by_year(_row_series(
        bs, "Cash And Cash Equivalents",
        "Cash Cash Equivalents And Short Term Investments"))

    rows = []
    for y in fin_hist.index:
        price = year_close.get(y)
        eps = fin_hist.loc[y, "EPS"]
        ebitda = fin_hist.loc[y, "EBITDA"]
        pe = (price / eps) if (price and eps and eps > 0) else None
        ev_ebitda = None
        if price and shares and ebitda and ebitda > 0:
            mcap = price * shares
            net_debt = (debt.get(y, 0.0) or 0.0) - (cash.get(y, 0.0) or 0.0)
            ev_ebitda = (mcap + net_debt) / ebitda
        rows.append({"P/E": pe, "EV/EBITDA": ev_ebitda})
    df = pd.DataFrame(rows, index=fin_hist.index)
    df.index.name = "Year"
    return df
