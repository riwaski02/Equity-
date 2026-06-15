"""
app.py
------
Equity Dashboard — an interactive, single-page stock research terminal.

Run it with:
    streamlit run app.py

Sections (top to bottom):
    1. FED rate-expectation banner  (always visible)
    2. Header: price + key snapshot
    3. Price chart
    4. Valuation multiples (EV/EBITDA, P/E trailing & forward, P/S, P/B, EV ...)
    5. Profitability & balance sheet
    6. Dividends
    7. Free Cash Flow (FCFF) & Free Cash Flow to Equity (FCFE)
    8. Analyst consensus
    9. Latest news
   10. Our own valuation (DCF + FCFE + relative) -> fair value & verdict
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data as D
from fed import get_fed_view
from valuation import ValuationInputs, run_valuation

st.set_page_config(page_title="Equity Dashboard", page_icon="📈", layout="wide")


# --------------------------------------------------------------------------- #
# Helpers for layout
# --------------------------------------------------------------------------- #
def metric_grid(items: dict, columns: int = 4, formatter=None):
    """Render a dict of label->value as a grid of st.metric cards."""
    keys = list(items.keys())
    for i in range(0, len(keys), columns):
        cols = st.columns(columns)
        for col, key in zip(cols, keys[i:i + columns]):
            val = items[key]
            col.metric(key, formatter(key, val) if formatter else D.fmt_number(val))


def value_fmt(key: str, val) -> str:
    pct_keys = ("Margin", "ROE", "ROA", "Growth", "Yield", "Payout", "Upside")
    money_keys = ("Cap", "Value", "Revenue", "EBITDA", "Income", "Cash", "Debt",
                  "Flow", "FCFE", "Borrowing", "CapEx", "Capital", "Expenditure")
    if val is None:
        return "—"
    if any(p in key for p in pct_keys):
        return D.fmt_number(val, pct=True)
    if any(p in key for p in money_keys):
        return D.fmt_number(val, prefix="$")
    return D.fmt_number(val)


# --------------------------------------------------------------------------- #
# Sidebar — ticker + valuation assumptions
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.title("📈 Equity Dashboard")
    ticker = st.text_input("Ticker symbol", value="AAPL",
                           help="e.g. AAPL, MSFT, NVDA, GOOGL, BMW.DE, SAN.MC").strip().upper()
    st.caption("Data: Yahoo Finance · FRED. For research/education only.")

    st.divider()
    st.subheader("Valuation assumptions")
    inp = ValuationInputs(
        years=st.slider("Projection years", 3, 10, 5),
        growth_rate=st.slider("Initial FCF growth", 0.0, 0.30, 0.08, 0.01),
        terminal_growth=st.slider("Terminal growth", 0.0, 0.05, 0.025, 0.005),
        discount_rate=st.slider("Discount rate / WACC", 0.04, 0.18, 0.09, 0.005),
        fair_pe=st.slider("Fair P/E (relative)", 5.0, 40.0, 18.0, 0.5),
    )
    st.divider()
    if st.button("🔄 Refresh data (clear cache)"):
        st.cache_data.clear()
        st.rerun()


# --------------------------------------------------------------------------- #
# 1) FED rate-expectations banner — ALWAYS visible
# --------------------------------------------------------------------------- #
fed = get_fed_view()
signal_color = {"CUTS": "🟢", "HIKES": "🔴", "ON HOLD": "🟡"}.get(fed.signal, "⚪")

st.markdown(
    f"### {signal_color} FED Watch — Market is pricing: **{fed.signal}**"
)
fc = st.columns(5)
band = (f"{D.fmt_number(fed.target_lower)}–{D.fmt_number(fed.target_upper)}%"
        if fed.target_upper is not None else "—")
fc[0].metric("Fed Funds Target", band)
fc[1].metric("Effective Rate", D.fmt_number(fed.effective, suffix="%"))
fc[2].metric("3M T-Bill", D.fmt_number(fed.bill_3m, suffix="%"))
fc[3].metric("2Y Yield", D.fmt_number(fed.y2, suffix="%"))
fc[4].metric("10Y Yield", D.fmt_number(fed.y10, suffix="%"))
st.caption(f"🏦 {fed.detail}  ·  _Updated {fed.last_update}_")
st.divider()


# --------------------------------------------------------------------------- #
# Load the stock
# --------------------------------------------------------------------------- #
sd = D.load_stock(ticker)
if not sd.valid:
    st.error(sd.error or "Could not load this ticker.")
    st.stop()

price = sd.price
val_metrics = D.get_valuation_metrics(sd)
div_metrics = D.get_dividend_metrics(sd)
cf_metrics = D.get_cashflow_metrics(sd)
analyst = D.get_analyst_consensus(sd)


# --------------------------------------------------------------------------- #
# 2) Header
# --------------------------------------------------------------------------- #
sector = D._safe(sd.info, "sector", default="")
industry = D._safe(sd.info, "industry", default="")
st.title(f"{sd.name} ({sd.ticker})")
st.caption(f"{sector} · {industry} · {sd.currency}")

h = st.columns(4)
chg = None
if not sd.history.empty and len(sd.history) > 1 and price:
    prev = float(sd.history["Close"].iloc[-2])
    chg = (price / prev - 1.0) if prev else None
h[0].metric("Price", D.fmt_number(price, prefix="$"),
            D.fmt_number(chg, pct=True) if chg is not None else None)
h[1].metric("Market Cap", D.fmt_number(val_metrics["Market Cap"], prefix="$"))
h[2].metric("Enterprise Value", D.fmt_number(val_metrics["Enterprise Value (EV)"], prefix="$"))
h[3].metric("52W Range",
            f"{D.fmt_number(val_metrics['52W Low'], prefix='$')} – "
            f"{D.fmt_number(val_metrics['52W High'], prefix='$')}")


# --------------------------------------------------------------------------- #
# 3) Price chart
# --------------------------------------------------------------------------- #
if not sd.history.empty:
    st.subheader("Price history (5Y, adjusted)")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=sd.history.index, y=sd.history["Close"],
                             mode="lines", name="Close",
                             line=dict(color="#2E86DE", width=2)))
    fig.update_layout(height=350, margin=dict(l=0, r=0, t=10, b=0),
                      xaxis_title=None, yaxis_title=f"Price ({sd.currency})",
                      template="plotly_white")
    st.plotly_chart(fig, use_container_width=True)


# --------------------------------------------------------------------------- #
# 4) Valuation multiples
# --------------------------------------------------------------------------- #
st.subheader("💰 Valuation multiples")
multiples = {
    "P/E (Trailing)": val_metrics["P/E (Trailing)"],
    "P/E (Forward)": val_metrics["P/E (Forward)"],
    "P/S (Trailing)": val_metrics["P/S (Trailing)"],
    "P/B": val_metrics["P/B"],
    "EV/EBITDA": val_metrics["EV/EBITDA"],
    "EV/Revenue": val_metrics["EV/Revenue"],
    "PEG Ratio": val_metrics["PEG Ratio"],
    "Beta": val_metrics["Beta"],
}
metric_grid(multiples, columns=4, formatter=value_fmt)

with st.expander("Per-share & size figures"):
    metric_grid({
        "Enterprise Value (EV)": val_metrics["Enterprise Value (EV)"],
        "Market Cap": val_metrics["Market Cap"],
        "Revenue (TTM)": val_metrics["Revenue (TTM)"],
        "EBITDA": val_metrics["EBITDA"],
        "Net Income (TTM)": val_metrics["Net Income (TTM)"],
        "Trailing EPS": val_metrics["Trailing EPS"],
        "Forward EPS": val_metrics["Forward EPS"],
        "Book Value / Share": val_metrics["Book Value / Share"],
    }, columns=4, formatter=value_fmt)


# --------------------------------------------------------------------------- #
# 5) Profitability & balance sheet
# --------------------------------------------------------------------------- #
st.subheader("📊 Profitability & balance sheet")
metric_grid({
    "Gross Margin": val_metrics["Gross Margin"],
    "Operating Margin": val_metrics["Operating Margin"],
    "Profit Margin": val_metrics["Profit Margin"],
    "ROE": val_metrics["ROE"],
    "ROA": val_metrics["ROA"],
    "Revenue Growth (YoY)": val_metrics["Revenue Growth (YoY)"],
    "Earnings Growth (YoY)": val_metrics["Earnings Growth (YoY)"],
    "Debt / Equity": val_metrics["Debt / Equity"],
    "Current Ratio": val_metrics["Current Ratio"],
    "Quick Ratio": val_metrics["Quick Ratio"],
    "Total Cash": val_metrics["Total Cash"],
    "Total Debt": val_metrics["Total Debt"],
}, columns=4, formatter=value_fmt)


# --------------------------------------------------------------------------- #
# 6) Dividends
# --------------------------------------------------------------------------- #
st.subheader("💵 Dividends")
if div_metrics.get("Dividend Rate (annual)") or div_metrics.get("Dividend Yield"):
    metric_grid({
        "Dividend Rate (annual)": div_metrics["Dividend Rate (annual)"],
        "Dividend Yield": div_metrics["Dividend Yield"],
        "Payout Ratio": div_metrics["Payout Ratio"],
        "5Y Avg Yield": div_metrics["5Y Avg Yield"],
    }, columns=4, formatter=lambda k, v: (
        D.fmt_number(v, pct=True) if "Yield" in k or "Payout" in k
        else D.fmt_number(v, prefix="$")))
else:
    st.info("This company does not currently pay a dividend.")


# --------------------------------------------------------------------------- #
# 7) Free Cash Flow & FCFE
# --------------------------------------------------------------------------- #
st.subheader("🌊 Free Cash Flow & FCFE")
st.caption("FCFF = Operating Cash Flow − CapEx · FCFE = FCFF + Net Borrowing")
metric_grid({
    "Operating Cash Flow": cf_metrics["Operating Cash Flow"],
    "Capital Expenditure": cf_metrics["Capital Expenditure"],
    "Free Cash Flow (FCFF)": cf_metrics["Free Cash Flow (FCFF)"],
    "Net Borrowing": cf_metrics["Net Borrowing"],
    "Free Cash Flow to Equity (FCFE)": cf_metrics["Free Cash Flow to Equity (FCFE)"],
    "FCF / Share": cf_metrics["FCF / Share"],
    "FCFE / Share": cf_metrics["FCFE / Share"],
    "FCF Yield": cf_metrics["FCF Yield"],
}, columns=4, formatter=value_fmt)


# --------------------------------------------------------------------------- #
# 8) Analyst consensus
# --------------------------------------------------------------------------- #
st.subheader("🎯 Analyst consensus")
ac = st.columns(4)
ac[0].metric("Recommendation", str(analyst["Recommendation"]).replace("_", " ").title())
ac[1].metric("Mean Target", D.fmt_number(analyst["Target Mean"], prefix="$"))
ac[2].metric("Upside to Target",
             D.fmt_number(analyst.get("Upside to Mean Target"), pct=True))
ac[3].metric("# Analysts", D.fmt_number(analyst["Number of Analysts"], decimals=0))

rec_df = D.get_recommendation_breakdown(sd)
cc = st.columns([1, 1])
with cc[0]:
    if rec_df is not None and rec_df["Analysts"].sum() > 0:
        fig = go.Figure(go.Bar(x=rec_df["Rating"], y=rec_df["Analysts"],
                               marker_color=["#1e8e3e", "#34a853", "#fbbc04",
                                             "#ea8600", "#d93025"]))
        fig.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0),
                          template="plotly_white", yaxis_title="Analysts")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No analyst rating distribution available.")
with cc[1]:
    st.write("**Price targets**")
    st.write(pd.DataFrame({
        "Metric": ["Low", "Median", "Mean", "High", "Current"],
        "Price": [analyst["Target Low"], analyst["Target Median"],
                  analyst["Target Mean"], analyst["Target High"], price],
    }).set_index("Metric"))


# --------------------------------------------------------------------------- #
# 9) Latest news
# --------------------------------------------------------------------------- #
st.subheader("📰 Latest news")
news = D.get_news(sd, limit=8)
if news:
    for n in news:
        title = f"[{n['title']}]({n['url']})" if n["url"] else n["title"]
        st.markdown(f"- {title}  \n  _{n['publisher']} · {n['when']}_")
else:
    st.info("No recent news returned for this ticker.")


# --------------------------------------------------------------------------- #
# 10) Our own valuation
# --------------------------------------------------------------------------- #
st.divider()
st.header("🧮 Our own valuation")
res = run_valuation(sd, inp, cf_metrics)

if res.fair_value:
    v = st.columns(3)
    v[0].metric("Estimated Fair Value", D.fmt_number(res.fair_value, prefix="$"))
    v[1].metric("Current Price", D.fmt_number(res.current_price, prefix="$"))
    v[2].metric("Upside / Downside", D.fmt_number(res.upside, pct=True))

    verdict_color = "🟢" if (res.upside or 0) > 0.05 else (
        "🔴" if (res.upside or 0) < -0.05 else "🟡")
    st.markdown(f"## {verdict_color} Verdict: **{res.verdict}**")

    st.write("**Fair value by method (blended into the estimate above):**")
    method_df = pd.DataFrame({
        "Method": ["DCF — Free Cash Flow to Firm",
                   "DCF — Free Cash Flow to Equity",
                   "Relative — Fair P/E × EPS",
                   "Relative — EV/EBITDA"],
        "Fair value / share": [res.dcf_fcff, res.dcf_fcfe,
                               res.relative_pe, res.relative_ev_ebitda],
    })
    method_df["Fair value / share"] = method_df["Fair value / share"].apply(
        lambda x: D.fmt_number(x, prefix="$") if x else "—")
    st.table(method_df.set_index("Method"))
else:
    st.warning(res.verdict)

if res.notes:
    with st.expander("Valuation notes & skipped methods"):
        for note in res.notes:
            st.write("•", note)

st.divider()
st.caption(
    "⚠️ **Disclaimer:** This dashboard is for educational and research purposes "
    "only and is **not** investment advice. Data may be delayed or incomplete. "
    "Always do your own due diligence."
)
