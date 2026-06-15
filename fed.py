"""
fed.py
------
FED interest-rate context + a market-implied expectation of the next move.

We avoid paid APIs. Data comes from two free, key-less sources:

1. FRED (Federal Reserve Bank of St. Louis) public CSV download endpoint
   `fredgraph.csv` — used for the current Fed Funds target band and the
   effective rate. No API key required.

2. Yahoo Finance Treasury yields (^IRX 13-week, ^FVX 5y, ^TNX 10y, ^TYX 30y)
   as a fallback and to build the market-implied signal.

Market-implied direction heuristic
-----------------------------------
The 3-month T-bill yield (^IRX) tracks where the market thinks the *average*
policy rate will sit over the next quarter. Comparing it to the midpoint of the
current Fed Funds target band gives a simple, transparent read:

    spread = 3M_bill_yield - fed_funds_midpoint

    spread < -0.15%  -> market is pricing CUTS
    spread >  0.15%  -> market is pricing HIKES
    otherwise        -> market expects the Fed ON HOLD

This is a heuristic proxy for CME FedWatch, not a probability model.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"


@dataclass
class FedView:
    target_upper: float | None = None
    target_lower: float | None = None
    effective: float | None = None
    bill_3m: float | None = None
    y2: float | None = None
    y10: float | None = None
    last_update: str = ""
    signal: str = "Unknown"          # CUTS / HIKES / ON HOLD / Unknown
    spread_bps: float | None = None
    detail: str = ""

    @property
    def target_mid(self) -> float | None:
        if self.target_upper is not None and self.target_lower is not None:
            return (self.target_upper + self.target_lower) / 2
        return None


def _fred_latest(series: str) -> float | None:
    try:
        r = requests.get(FRED_CSV.format(series=series), timeout=10)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = ["date", "value"]
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna()
        if df.empty:
            return None
        return float(df["value"].iloc[-1])
    except Exception:
        return None


def _yahoo_yield(symbol: str) -> float | None:
    try:
        h = yf.Ticker(symbol).history(period="5d")
        if h is None or h.empty:
            return None
        # These ^ indices quote yield * 10 historically; Yahoo returns the yield directly now.
        return float(h["Close"].dropna().iloc[-1])
    except Exception:
        return None


@st.cache_data(ttl=1800, show_spinner=False)
def get_fed_view() -> FedView:
    """Build the Fed snapshot. Cached for 30 minutes."""
    fv = FedView()

    # 1) Fed funds target band + effective rate from FRED.
    fv.target_upper = _fred_latest("DFEDTARU")   # upper limit
    fv.target_lower = _fred_latest("DFEDTARL")   # lower limit
    fv.effective = _fred_latest("DFF")           # daily effective fed funds rate

    # 2) Treasury yields (Yahoo) for the market-implied read.
    fv.bill_3m = _yahoo_yield("^IRX")            # 13-week T-bill yield
    fv.y2 = _fred_latest("DGS2")                 # 2y from FRED (more stable)
    fv.y10 = _fred_latest("DGS10")               # 10y

    fv.last_update = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # 3) Compute the signal.
    mid = fv.target_mid
    bill = fv.bill_3m if fv.bill_3m is not None else fv.effective
    if mid is not None and bill is not None:
        spread = bill - mid          # in percentage points
        fv.spread_bps = spread * 100
        if spread < -0.15:
            fv.signal = "CUTS"
            fv.detail = ("Short-term market rates sit below the Fed's current "
                         "target band — the market is leaning toward rate CUTS.")
        elif spread > 0.15:
            fv.signal = "HIKES"
            fv.detail = ("Short-term market rates sit above the Fed's current "
                         "target band — the market is leaning toward rate HIKES.")
        else:
            fv.signal = "ON HOLD"
            fv.detail = ("Short-term market rates are roughly in line with the "
                         "Fed's target band — the market expects the Fed to stay "
                         "ON HOLD near term.")
    else:
        fv.detail = "Live Fed data unavailable (no network). Showing what we could fetch."

    # 4) Yield-curve flag (recession proxy) for extra colour.
    if fv.y2 is not None and fv.y10 is not None:
        curve = fv.y10 - fv.y2
        if curve < 0:
            fv.detail += (f"  Yield curve is INVERTED (10y−2y = {curve:+.2f}%), "
                          f"often a market signal of expected easing ahead.")
        else:
            fv.detail += f"  Yield curve (10y−2y) = {curve:+.2f}%."

    return fv
