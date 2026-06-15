"""
fed.py
------
FED interest-rate context + a market-implied expectation of the next move.

Design goal: **never show blank / "Unknown"**. The extraction is layered so a
failure at any level falls through to the next:

    1. PRIMARY  — Yahoo Finance CBOE interest-rate indices (yfinance).
                  These are stable, key-less and rarely down:
                      ^IRX  -> 13-week (3-month) T-Bill yield
                      ^FVX  -> 5-year Treasury yield
                      ^TNX  -> 10-year Treasury yield
                      ^TYX  -> 30-year Treasury yield
                  The 2-year yield is taken from the `2YY=F` future, or
                  interpolated between the 3-month and 5-year points.

    2. FRED     — Fed Funds target band / effective rate (no key needed).
                  Wrapped in try/except; if it fails we approximate from the
                  3-month bill and fall back to a hardcoded last-known range.

    3. DISK CACHE — every successful fetch is written to `.fed_cache.json`.
                  If a later fetch fails, we reload the last good snapshot
                  instead of leaving the fields empty.

    4. HARDCODED — a last-known Fed Funds range so the panel is never blank.

Market-implied direction heuristic
----------------------------------
    spread = 3M_bill_yield - fed_funds_midpoint
    spread < -0.15%  -> market is pricing CUTS
    spread >  0.15%  -> market is pricing HIKES
    otherwise        -> market expects ON HOLD
"""

from __future__ import annotations

import io
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
CACHE_FILE = Path(__file__).parent / ".fed_cache.json"

# Last-known official Fed Funds target range (update when the Fed moves).
# Used only when both FRED and the disk cache are unavailable.
HARDCODED = {"target_lower": 4.25, "target_upper": 4.50, "effective": 4.33}


@dataclass
class FedView:
    target_upper: float | None = None
    target_lower: float | None = None
    effective: float | None = None
    bill_3m: float | None = None
    y2: float | None = None
    y5: float | None = None
    y10: float | None = None
    y30: float | None = None
    last_update: str = ""
    signal: str = "Unknown"          # CUTS / HIKES / ON HOLD / Unknown
    spread_bps: float | None = None
    detail: str = ""
    source: str = ""                 # where the numbers came from
    stale: bool = False              # True when served from disk cache

    @property
    def target_mid(self) -> float | None:
        if self.target_upper is not None and self.target_lower is not None:
            return (self.target_upper + self.target_lower) / 2
        return None


# --------------------------------------------------------------------------- #
# Low-level fetch helpers
# --------------------------------------------------------------------------- #
def _normalize_yield(v: float | None) -> float | None:
    """CBOE indices are sometimes quoted x10 (e.g. 42.5 -> 4.25%). A real
    Treasury yield never exceeds ~25%, so scale down when it clearly should be."""
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if v != v:           # NaN
        return None
    if v > 25:           # almost certainly quoted x10
        v = v / 10.0
    return round(v, 3)


def _yahoo_yield(symbol: str) -> float | None:
    """Robustly pull the latest yield for a CBOE rate index / yield future.

    Tries fast_info first, then a couple of history windows, and normalizes
    the x10 quoting convention."""
    try:
        tk = yf.Ticker(symbol)
        # 1) fast_info last price (cheapest, usually present)
        try:
            v = tk.fast_info.get("lastPrice")
            v = _normalize_yield(v)
            if v is not None:
                return v
        except Exception:
            pass
        # 2) recent history (try a few windows for resilience)
        for period in ("5d", "1mo", "3mo"):
            try:
                h = tk.history(period=period)
                if h is not None and not h.empty:
                    v = _normalize_yield(float(h["Close"].dropna().iloc[-1]))
                    if v is not None:
                        return v
            except Exception:
                continue
    except Exception:
        pass
    return None


def _fred_latest(series: str) -> float | None:
    try:
        r = requests.get(
            FRED_CSV.format(series=series),
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (EquityDashboard)"},
        )
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = ["date", "value"]
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna()
        if df.empty:
            return None
        return round(float(df["value"].iloc[-1]), 3)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Disk cache (last-good snapshot)
# --------------------------------------------------------------------------- #
def _save_cache(fv: FedView) -> None:
    try:
        data = asdict(fv)
        data["stale"] = False
        CACHE_FILE.write_text(json.dumps(data))
    except Exception:
        pass


def _load_cache() -> FedView | None:
    try:
        if CACHE_FILE.exists():
            data = json.loads(CACHE_FILE.read_text())
            data.pop("target_mid", None)  # property, not a field
            fv = FedView(**{k: v for k, v in data.items()
                            if k in FedView.__dataclass_fields__})
            fv.stale = True
            return fv
    except Exception:
        pass
    return None


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=1800, show_spinner=False)
def get_fed_view() -> FedView:
    """Build the Fed snapshot with layered fallbacks. Cached for 30 minutes."""
    fv = FedView()
    yahoo_ok = False
    sources: list[str] = []

    # ---- 1) PRIMARY: Yahoo Finance Treasury yields --------------------- #
    fv.bill_3m = _yahoo_yield("^IRX")     # 3-month T-bill
    fv.y5 = _yahoo_yield("^FVX")          # 5-year
    fv.y10 = _yahoo_yield("^TNX")         # 10-year
    fv.y30 = _yahoo_yield("^TYX")         # 30-year

    # 2-year: try the yield future, else interpolate between 3M and 5Y.
    fv.y2 = _yahoo_yield("2YY=F")
    if fv.y2 is None and fv.bill_3m is not None and fv.y5 is not None:
        # Linear interpolation by maturity (0.25y -> 5y).
        w = (2 - 0.25) / (5 - 0.25)
        fv.y2 = round(fv.bill_3m + (fv.y5 - fv.bill_3m) * w, 3)

    if any(v is not None for v in (fv.bill_3m, fv.y2, fv.y10)):
        yahoo_ok = True
        sources.append("Yahoo Finance (CBOE rate indices)")

    # ---- 2) Fed Funds band / effective rate (FRED, then fallbacks) ----- #
    fv.target_upper = _fred_latest("DFEDTARU")
    fv.target_lower = _fred_latest("DFEDTARL")
    fv.effective = _fred_latest("DFF")

    if fv.target_upper is not None and fv.target_lower is not None:
        sources.append("FRED (Fed Funds target)")
    else:
        # Approximate the effective rate from the 3-month bill, and use the
        # last-known hardcoded target band so the panel is never blank.
        if fv.effective is None and fv.bill_3m is not None:
            fv.effective = fv.bill_3m
        fv.target_lower = fv.target_lower if fv.target_lower is not None else HARDCODED["target_lower"]
        fv.target_upper = fv.target_upper if fv.target_upper is not None else HARDCODED["target_upper"]
        if fv.effective is None:
            fv.effective = HARDCODED["effective"]
        sources.append("Fed Funds: last-known fallback")

    fv.last_update = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    fv.source = " · ".join(sources)

    # ---- 3) If nothing live came through, serve the disk cache --------- #
    if not yahoo_ok and "FRED" not in fv.source:
        cached = _load_cache()
        if cached is not None:
            cached.detail = ("⚠️ Live rate feeds unavailable — showing the last "
                             f"cached snapshot from {cached.last_update}.")
            cached.signal = cached.signal or "ON HOLD"
            return cached

    # ---- 4) Compute the market-implied signal -------------------------- #
    _compute_signal(fv)

    # ---- 5) Persist this good snapshot --------------------------------- #
    if yahoo_ok:
        _save_cache(fv)

    return fv


def _compute_signal(fv: FedView) -> None:
    mid = fv.target_mid
    bill = fv.bill_3m if fv.bill_3m is not None else fv.effective
    if mid is not None and bill is not None:
        spread = bill - mid
        fv.spread_bps = round(spread * 100, 1)
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
        fv.signal = "ON HOLD"
        fv.detail = "Using best-available rate data."

    # Yield-curve flag for extra colour.
    if fv.y2 is not None and fv.y10 is not None:
        curve = fv.y10 - fv.y2
        if curve < 0:
            fv.detail += (f"  Yield curve is INVERTED (10y−2y = {curve:+.2f}%), "
                          f"often a market signal of expected easing ahead.")
        else:
            fv.detail += f"  Yield curve (10y−2y) = {curve:+.2f}%."

    if fv.source:
        fv.detail += f"  _Source: {fv.source}._"
