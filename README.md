# 📈 Equity Dashboard

An interactive, single-page **stock research terminal** built with Python +
[Streamlit](https://streamlit.io). Type a ticker and instantly see every
important characteristic of the stock — valuation multiples, profitability,
cash flow, dividends, analyst consensus, the latest news, an always-on **FED
interest-rate expectation panel**, and finally **our own fair-value
estimate**.

> ⚠️ For education and research only. **Not** investment advice.

---

## ✨ What you get

| Section | What it shows |
|---|---|
| 🏦 **FED Watch (always on top)** | Current Fed Funds target band, effective rate, 3M/2Y/10Y Treasury yields, and a **market-implied read of the next move: CUTS / HIKES / ON HOLD** |
| 📊 **Header & price chart** | Live price, market cap, EV, 52-week range, 5-year chart |
| 💰 **Valuation multiples** | **EV/EBITDA, P/E (trailing & forward), P/S, P/B, EV, EV/Revenue, PEG, Beta** |
| 📈 **Profitability & balance sheet** | Margins, ROE, ROA, growth, debt/equity, current & quick ratios, cash, debt |
| 💵 **Dividends** | Rate, yield, payout ratio, 5-year average yield |
| 🌊 **Cash flow** | Operating CF, CapEx, **Free Cash Flow (FCFF)** and **Free Cash Flow to Equity (FCFE)**, per-share & FCF yield |
| 🎯 **Analyst consensus** | Recommendation, mean/median/high/low price targets, upside, rating distribution |
| 📰 **Latest news** | Most recent headlines for the ticker, with links |
| 🧮 **Our own valuation** | A blended **DCF (FCFF) + DCF (FCFE) + relative (P/E & EV/EBITDA)** fair value, upside/downside, and a verdict |

Data comes from **Yahoo Finance** (via `yfinance`) and the **Federal Reserve (FRED)** —
both free, no API key required.

---

## 🚀 Quick start (run it locally)

You need **Python 3.9+** installed.

```bash
# 1. Clone the repository
git clone https://github.com/riwaski02/Equity-.git
cd Equity-

# 2. (Recommended) create a virtual environment
python -m venv .venv
source .venv/bin/activate        # on Windows: .venv\Scripts\activate

# 3. Install the dependencies
pip install -r requirements.txt

# 4. Launch the dashboard
streamlit run app.py
```

Streamlit opens the dashboard in your browser at `http://localhost:8501`.
Type any ticker in the sidebar (e.g. `AAPL`, `MSFT`, `NVDA`, `GOOGL`, or
international symbols like `BMW.DE`, `SAN.MC`) and explore.

Use the sidebar sliders to tune the valuation assumptions (projection years,
growth, discount rate / WACC, terminal growth, fair P/E) and watch the
fair-value estimate update in real time.

### Assumption source: Automatic vs. Market Consensus

In the sidebar's **Valuation assumptions** section there is a switch:

- **Automatic Mode** — uses the sliders, driven by Yahoo Finance historical
  financials (the default behaviour).
- **Market Consensus Mode** — **disables all five sliders** (they stay visible,
  pre-filled with the consensus values) and **derives the assumptions from
  analyst consensus / live market data**, tuned to realistic ranges so the fair
  value lands closer to the market price:
  - **Projection years** = 7 (default within the typical 5–10y range)
  - **Risk-free** = live 10Y Treasury yield (from the FED panel)
  - **Cost of equity** = CAPM (`risk-free + β × equity-risk-premium`), 7–16%
  - **WACC** = market-weighted blend of cost of equity and after-tax cost of
    debt, 7–14%
  - **Fair P/E** = analyst forward P/E (5–40×)
  - **Initial FCF growth** = analyst earnings-growth estimate (capped at 20%)
  - **Terminal growth** = long-run nominal anchor (~risk-free, capped 2–3%)

  The exact values used — and how they were derived — are shown in the sidebar
  so nothing is hidden.

---

## 🧮 How the "own valuation" works

The fair value is the **average of every method that has enough data**:

1. **DCF on Free Cash Flow to the Firm (FCFF)** — projects FCFF for *N* years
   with growth fading toward the terminal rate, discounts at your WACC, adds a
   Gordon-growth terminal value, subtracts net debt → equity value → per share.
2. **DCF on Free Cash Flow to Equity (FCFE)** — projects FCFE and discounts at
   the cost of equity (CAPM: `risk-free + β × equity-risk-premium`).
3. **Relative — Fair P/E × forward EPS**.
4. **Relative — EV/EBITDA** cross-check.

Every assumption is exposed in the sidebar, and skipped methods are listed
under *Valuation notes* so nothing is hidden.

### FED expectation logic

We compare the 3-month T-bill yield to the midpoint of the current Fed Funds
target band:

```
spread = 3M_bill_yield − fed_funds_midpoint
spread < −0.15%  →  market is pricing CUTS
spread >  0.15%  →  market is pricing HIKES
otherwise        →  market expects ON HOLD
```

This is a transparent proxy for CME FedWatch (not a probability model), plus a
10y−2y yield-curve flag for extra context.

---

## 📂 Project structure

```
Equity-/
├── app.py            # Streamlit UI — the dashboard itself
├── data.py           # Yahoo Finance data fetching + metric extraction
├── fed.py            # FED rate context + market-implied expectation
├── valuation.py      # DCF / FCFE / relative fair-value engine
├── requirements.txt  # Python dependencies
├── .streamlit/       # Theme configuration
└── README.md         # You are here
```

---

## 🐙 Step-by-step GitHub tutorial

Everything below is in English, from zero to a live repository.

### A. One-time setup

1. **Create a GitHub account** at <https://github.com> (skip if you have one).
2. **Install Git**: <https://git-scm.com/downloads>. Verify with:
   ```bash
   git --version
   ```
3. **Tell Git who you are** (only needed once per machine):
   ```bash
   git config --global user.name  "Your Name"
   git config --global user.email "you@example.com"
   ```

### B. Get this project onto your computer

If the repository already exists on GitHub (`riwaski02/Equity-`):

```bash
git clone https://github.com/riwaski02/Equity-.git
cd Equity-
```

> 💡 The code for this dashboard lives on the branch
> **`claude/wonderful-curie-as17m4`**. To check it out:
> ```bash
> git fetch origin claude/wonderful-curie-as17m4
> git checkout claude/wonderful-curie-as17m4
> ```

### C. Run it

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Your browser opens the dashboard. 🎉

### D. Make a change and save it to GitHub

```bash
# 1. See what changed
git status

# 2. Stage your changes
git add .

# 3. Commit with a clear message
git commit -m "Describe what you changed"

# 4. Push to GitHub
git push origin claude/wonderful-curie-as17m4
```

### E. Open a Pull Request (to merge into main)

1. Go to your repository on GitHub.com.
2. You'll see a yellow banner: **"Compare & pull request"** — click it.
   (Or open the **Pull requests** tab → **New pull request**.)
3. Set **base = `main`** and **compare = `claude/wonderful-curie-as17m4`**.
4. Add a title and description, then click **Create pull request**.
5. Review the changes and click **Merge pull request** when ready.

### F. Starting your own repository from scratch (optional)

If you ever want to publish this as a **brand-new** repo:

```bash
# Inside the project folder
git init
git add .
git commit -m "Initial commit: Equity Dashboard"

# Create an empty repo on github.com first, then:
git remote add origin https://github.com/<your-username>/<your-repo>.git
git branch -M main
git push -u origin main
```

### G. Deploy it for free (optional, share a public link)

1. Push your code to GitHub (steps above).
2. Go to <https://share.streamlit.io> and sign in with GitHub.
3. Click **New app**, pick your repository, branch, and `app.py`.
4. Click **Deploy** — Streamlit Community Cloud gives you a public URL.

---

## 🛠️ Troubleshooting

| Problem | Fix |
|---|---|
| `command not found: streamlit` | Re-run `pip install -r requirements.txt` inside your activated venv |
| A metric shows `—` | Yahoo doesn't report that field for this ticker (common for non-US or small caps) |
| FED panel shows `Unknown` | No internet access to FRED/Yahoo at that moment — try the **Refresh** button |
| Data looks stale | Click **🔄 Refresh data** in the sidebar (data is cached for 15–30 min) |

---

## ⚠️ Disclaimer

This software is provided for **educational and informational purposes only**.
It is **not** financial, investment, legal, or tax advice. Market data may be
delayed, incomplete, or inaccurate. Always do your own research and consult a
licensed professional before making any investment decision.
