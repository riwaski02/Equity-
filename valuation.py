"""
valuation.py
------------
The dashboard's own, transparent fair-value engine.

Three independent lenses are blended into a single fair value:

1. DCF on Free Cash Flow to the Firm (FCFF)
   - Project FCFF for N years at a fading growth rate.
   - Discount at WACC.
   - Terminal value via Gordon growth.
   - Subtract net debt -> equity value -> per-share value.

2. FCFE / Equity DCF
   - Project Free Cash Flow to Equity and discount at cost of equity (CAPM).

3. Relative valuation
   - Apply a "fair" P/E (here: a sensible default / sector-agnostic anchor)
     to forward EPS, and average with an EV/EBITDA cross-check.

The blend is the simple average of whichever lenses produced a value.
Every assumption is exposed in the UI so the user can tune it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from data import StockData, _safe, _row


# --------------------------------------------------------------------------- #
# Assumptions the user can tweak in the sidebar
# --------------------------------------------------------------------------- #
@dataclass
class ValuationInputs:
    years: int = 5
    growth_rate: float = 0.08          # initial FCF growth
    terminal_growth: float = 0.025     # perpetual growth
    discount_rate: float = 0.09        # WACC for FCFF DCF
    cost_of_equity: float = 0.10       # for FCFE DCF
    fair_pe: float = 18.0              # anchor multiple for relative valuation
    risk_free: float = 0.043           # used if we derive cost of equity via CAPM
    equity_risk_premium: float = 0.05


@dataclass
class ValuationResult:
    dcf_fcff: float | None = None
    dcf_fcfe: float | None = None
    relative_pe: float | None = None
    relative_ev_ebitda: float | None = None
    fair_value: float | None = None
    current_price: float | None = None
    upside: float | None = None
    verdict: str = ""
    notes: list[str] = field(default_factory=list)
    breakdown: dict = field(default_factory=dict)


def _capm_cost_of_equity(beta: float | None, inp: ValuationInputs) -> float:
    if beta is None:
        return inp.cost_of_equity
    return inp.risk_free + beta * inp.equity_risk_premium


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def market_consensus_inputs(sd: StockData, fed=None,
                            base: ValuationInputs | None = None):
    """
    Build a ValuationInputs object from analyst/market consensus rather than
    from the user's sliders.

    Derivations (all transparent, shown in the sidebar):
      - Risk-free      : live 10Y Treasury yield (FRED, via the Fed panel)
      - Cost of equity : CAPM  = risk_free + beta * equity_risk_premium
      - WACC / discount: market-weighted blend of cost of equity and
                         after-tax cost of debt
      - Fair P/E       : analyst forward P/E (falls back to trailing P/E)
      - FCF growth     : analyst earnings-growth estimate (falls back to
                         revenue growth)
      - Terminal growth: long-run nominal anchor (~risk-free, capped 2–3%)

    Returns
    -------
    (ValuationInputs, dict[str, str])
        The inputs plus a {label: human-readable value} map of what was used,
        so the UI can display the consensus assumptions.
    """
    base = base or ValuationInputs()
    info = sd.info
    sources: dict[str, str] = {}

    # ---- Risk-free from the live 10Y (Fed panel) ----------------------- #
    risk_free = base.risk_free
    if fed is not None and getattr(fed, "y10", None):
        risk_free = fed.y10 / 100.0
    sources["Risk-free (10Y)"] = f"{risk_free * 100:.2f}%"

    erp = base.equity_risk_premium
    beta = _safe(info, "beta")
    beta_used = beta if beta is not None else 1.0

    # ---- Cost of equity (CAPM) ----------------------------------------- #
    coe = risk_free + beta_used * erp
    coe = _clamp(coe, 0.05, 0.20)
    sources["Cost of equity (CAPM)"] = f"{coe * 100:.2f}%  (β={beta_used:.2f})"

    # ---- WACC: weight cost of equity & after-tax cost of debt ---------- #
    mkt_cap = _safe(info, "marketCap") or 0.0
    total_debt = _safe(info, "totalDebt") or 0.0
    cost_of_debt = risk_free + 0.015            # risk-free + a generic spread
    tax_rate = 0.21
    after_tax_kd = cost_of_debt * (1 - tax_rate)
    cap = mkt_cap + total_debt
    if cap > 0:
        wacc = (mkt_cap / cap) * coe + (total_debt / cap) * after_tax_kd
    else:
        wacc = coe
    wacc = _clamp(wacc, 0.05, 0.18)
    sources["WACC"] = f"{wacc * 100:.2f}%"

    # ---- Fair P/E from analyst forward estimate ------------------------ #
    fair_pe = _safe(info, "forwardPE") or _safe(info, "trailingPE") or base.fair_pe
    fair_pe = _clamp(float(fair_pe), 5.0, 45.0)
    sources["Fair P/E (forward)"] = f"{fair_pe:.1f}x"

    # ---- FCF growth from analyst earnings growth ----------------------- #
    growth = _safe(info, "earningsGrowth", "earningsQuarterlyGrowth",
                   "revenueGrowth")
    growth = _clamp(float(growth), 0.0, 0.30) if growth is not None else base.growth_rate
    sources["FCF growth (analyst)"] = f"{growth * 100:.1f}%"

    # ---- Terminal growth: long-run nominal anchor ---------------------- #
    terminal = _clamp(risk_free * 0.6, 0.02, 0.03)
    sources["Terminal growth"] = f"{terminal * 100:.1f}%"

    inp = ValuationInputs(
        years=base.years,
        growth_rate=growth,
        terminal_growth=terminal,
        discount_rate=wacc,
        cost_of_equity=coe,
        fair_pe=fair_pe,
        risk_free=risk_free,
        equity_risk_premium=erp,
    )
    return inp, sources


def _project_and_discount(base_cf: float, growth: float, terminal_growth: float,
                          rate: float, years: int) -> float | None:
    """Standard multi-stage DCF -> present value of explicit period + terminal."""
    if base_cf is None or base_cf <= 0 or rate <= terminal_growth:
        return None
    pv = 0.0
    cf = base_cf
    # Fade growth linearly from `growth` to `terminal_growth` across the horizon.
    for yr in range(1, years + 1):
        g = growth + (terminal_growth - growth) * (yr - 1) / max(years - 1, 1)
        cf = cf * (1 + g)
        pv += cf / (1 + rate) ** yr
    # Terminal value (Gordon growth) on the final-year cash flow.
    terminal = cf * (1 + terminal_growth) / (rate - terminal_growth)
    pv += terminal / (1 + rate) ** years
    return pv


def run_valuation(sd: StockData, inp: ValuationInputs,
                  cashflow_metrics: dict) -> ValuationResult:
    res = ValuationResult()
    info = sd.info
    res.current_price = sd.price

    shares = _safe(info, "sharesOutstanding")
    total_debt = _safe(info, "totalDebt") or 0.0
    total_cash = _safe(info, "totalCash") or 0.0
    net_debt = total_debt - total_cash
    beta = _safe(info, "beta")

    fcff = cashflow_metrics.get("Free Cash Flow (FCFF)")
    fcfe = cashflow_metrics.get("Free Cash Flow to Equity (FCFE)")

    # ---- 1) FCFF DCF -> equity per share ------------------------------- #
    if fcff and shares:
        ev = _project_and_discount(fcff, inp.growth_rate, inp.terminal_growth,
                                   inp.discount_rate, inp.years)
        if ev:
            equity_value = ev - net_debt
            res.dcf_fcff = max(equity_value / shares, 0.0)
            res.breakdown["FCFF DCF enterprise value"] = ev
            res.breakdown["Net debt"] = net_debt
    else:
        res.notes.append("FCFF DCF skipped: missing free cash flow or share count.")

    # ---- 2) FCFE DCF --------------------------------------------------- #
    if fcfe and shares:
        coe = _capm_cost_of_equity(beta, inp)
        res.breakdown["Cost of equity (CAPM)"] = coe
        eq = _project_and_discount(fcfe, inp.growth_rate, inp.terminal_growth,
                                   coe, inp.years)
        if eq:
            res.dcf_fcfe = max(eq / shares, 0.0)
    else:
        res.notes.append("FCFE DCF skipped: missing FCFE or share count.")

    # ---- 3) Relative valuation ----------------------------------------- #
    fwd_eps = _safe(info, "forwardEps") or _safe(info, "trailingEps")
    if fwd_eps and fwd_eps > 0:
        res.relative_pe = fwd_eps * inp.fair_pe
        res.breakdown["Fair P/E x EPS"] = f"{inp.fair_pe:.1f} x {fwd_eps:.2f}"
    else:
        res.notes.append("Relative P/E skipped: no positive EPS.")

    ebitda = _safe(info, "ebitda")
    if ebitda and shares and ebitda > 0:
        # Use the stock's own current EV/EBITDA as a mean-reversion-free anchor,
        # falling back to a market-typical 11x if missing.
        anchor = _safe(info, "enterpriseToEbitda") or 11.0
        implied_ev = ebitda * anchor
        eq = implied_ev - net_debt
        res.relative_ev_ebitda = max(eq / shares, 0.0)

    # ---- Blend --------------------------------------------------------- #
    components = [v for v in (res.dcf_fcff, res.dcf_fcfe, res.relative_pe,
                              res.relative_ev_ebitda) if v and v > 0]
    if components:
        res.fair_value = sum(components) / len(components)
        if res.current_price:
            res.upside = (res.fair_value / res.current_price) - 1.0
            if res.upside > 0.20:
                res.verdict = "Significantly UNDERVALUED"
            elif res.upside > 0.05:
                res.verdict = "Moderately UNDERVALUED"
            elif res.upside > -0.05:
                res.verdict = "Roughly FAIRLY VALUED"
            elif res.upside > -0.20:
                res.verdict = "Moderately OVERVALUED"
            else:
                res.verdict = "Significantly OVERVALUED"
    else:
        res.verdict = "Not enough data to compute a fair value."

    return res
