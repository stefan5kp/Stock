#!/usr/bin/env python3
"""
Stock Analyzer
==============
Fetches real data from Yahoo Finance and opens a full dashboard in your browser.

Usage:
    pip install yfinance
    python nvda_analyzer.py          # NVDA (default)
    python nvda_analyzer.py COST     # any Yahoo Finance ticker
"""

import json, math, webbrowser, os, sys
from datetime import datetime, timedelta
import numpy as np
from scipy.optimize import minimize

# ── 1. Install / import yfinance ─────────────────────────────────────────────
try:
    import yfinance as yf
except ImportError:
    print("Installing yfinance...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance", "-q"])
    import yfinance as yf

# ── 2. Fetch data ─────────────────────────────────────────────────────────────
SYMBOL = (sys.argv[1] if len(sys.argv) > 1 else "NVDA").upper()
print(f"Fetching {SYMBOL} data from Yahoo Finance...")
ticker = yf.Ticker(SYMBOL)
hist   = ticker.history(period="1y")
info   = ticker.fast_info

if hist.empty:
    sys.exit(f"No data returned for {SYMBOL}. Check the ticker symbol and your internet connection.")

dates  = [d.strftime("%Y-%m-%d") for d in hist.index]
closes = [round(float(v), 2) for v in hist["Close"]]
highs  = [round(float(v), 2) for v in hist["High"]]
lows   = [round(float(v), 2) for v in hist["Low"]]
vols   = [int(v) for v in hist["Volume"]]

price      = closes[-1]
prev       = closes[-2]
change     = round(price - prev, 2)
change_pct = round((change / prev) * 100, 2)
high52     = round(max(highs), 2)
low52      = round(min(lows), 2)

try:
    mkt_cap  = info.market_cap
    pe       = ticker.info.get("trailingPE")
    eps      = ticker.info.get("trailingEps")
    beta     = ticker.info.get("beta")
    avg_vol  = info.three_month_average_volume
except Exception:
    mkt_cap = pe = eps = beta = avg_vol = None

EXCHANGES = {"NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ", "NYQ": "NYSE",
             "ASE": "NYSE American", "PCX": "NYSE Arca", "BTS": "Cboe"}
try:
    company  = ticker.info.get("longName") or ticker.info.get("shortName") or SYMBOL
    exch     = ticker.info.get("exchange", "")
    exchange = EXCHANGES.get(exch, ticker.info.get("fullExchangeName") or exch)
except Exception:
    company, exchange = SYMBOL, ""

def fmt_cap(n):
    if not n: return "N/A"
    if n >= 1e12: return f"${n/1e12:.2f}T"
    if n >= 1e9:  return f"${n/1e9:.2f}B"
    return f"${n/1e6:.1f}M"

def fmt_vol(n):
    if not n: return "N/A"
    if n >= 1e9: return f"{n/1e9:.2f}B"
    if n >= 1e6: return f"{n/1e6:.1f}M"
    return f"{int(n):,}"

# ── 3. Technical indicators ───────────────────────────────────────────────────
def sma(arr, p):
    return [None if i < p-1 else sum(arr[i-p+1:i+1])/p for i in range(len(arr))]

def ema(arr, p):
    k, e, out = 2/(p+1), arr[0], []
    for i, v in enumerate(arr):
        e = v if i == 0 else v*k + e*(1-k)
        out.append(e)
    return out

def rsi(closes, p=14):
    if len(closes) < p+1: return None
    g = l = 0
    for i in range(1, p+1):
        d = closes[i] - closes[i-1]
        if d > 0: g += d
        else:     l -= d
    ag, al = g/p, l/p
    for i in range(p+1, len(closes)):
        d = closes[i] - closes[i-1]
        ag = (ag*(p-1) + (d if d > 0 else 0)) / p
        al = (al*(p-1) + (-d if d < 0 else 0)) / p
    return round(100 if al == 0 else 100 - 100/(1+ag/al), 2)

def macd(closes):
    e12, e26 = ema(closes, 12), ema(closes, 26)
    line = [a-b for a, b in zip(e12, e26)]
    sig  = ema(line, 9)
    return line, sig

def bollinger(closes, p=20):
    m = sma(closes, p)
    out = []
    for i in range(len(closes)):
        if i < p-1: out.append(None); continue
        sl   = closes[i-p+1:i+1]
        mean = m[i]
        std  = math.sqrt(sum((x-mean)**2 for x in sl)/p)
        out.append({"upper": mean+2*std, "lower": mean-2*std, "mean": mean})
    return out

n = len(closes)
ma50_arr  = sma(closes, min(50, n))
ma200_arr = sma(closes, min(200, n))
rsi_val   = rsi(closes) or 50.0
macd_line, macd_sig = macd(closes)
boll_arr  = bollinger(closes)

i        = n - 1
ma50_v   = ma50_arr[i]
ma200_v  = ma200_arr[i]
macd_l   = macd_line[i]
macd_s   = macd_sig[i]
boll_v   = boll_arr[i]

ma50_bull  = bool(ma50_v  and price > ma50_v)
ma200_bull = bool(ma200_v and price > ma200_v)
macd_bull  = macd_l > macd_s
rsi_sig    = "Overbought" if rsi_val > 70 else "Oversold" if rsi_val < 30 else "Neutral"
boll_pos   = None
if boll_v:
    boll_pos = "Upper" if price > boll_v["upper"] else "Lower" if price < boll_v["lower"] else "Middle"

bulls = bears = 0
for b in [ma50_bull, ma200_bull, macd_bull]:
    if b: bulls += 1
    else: bears += 1
if 35 < rsi_val < 65: bulls += 1
elif rsi_val >= 65:   bears += 1
else:                 bulls += 1
if boll_pos == "Lower":  bulls += 1
elif boll_pos == "Upper": bears += 1

if   bulls >= 4: overall = "Strong Buy"
elif bulls == 3: overall = "Buy"
elif bears >= 4: overall = "Strong Sell"
elif bears == 3: overall = "Sell"
else:            overall = "Hold"

daily_chg = [0] + [round((closes[i]-closes[i-1])/closes[i-1]*100, 2) for i in range(1, n)]

# ── 4. Probabilistic forecast: GARCH(1,1) + filtered historical simulation ────
# Volatility follows a GARCH(1,1) fit to ~5 years of daily log returns. Each
# simulated path resamples the model's standardized residuals (keeping the
# stock's fat tails) and scales them by the path's own evolving volatility.
# Drift is an assumption, not an estimate: past returns say little about it.
ANNUAL_DRIFT = 0.08      # assumed yearly growth of the median; 0.0 = "no view"
N_PATHS      = 10_000
HORIZON      = 90        # trading sessions
SEED         = 7         # fixed so re-runs on the same data match

try:
    long_close = ticker.history(period="5y")["Close"]
except Exception:
    long_close = hist["Close"]
rets = 100 * np.diff(np.log(long_close.to_numpy(dtype=float)))   # daily, in %
resid  = rets - rets.mean()

def garch_var(params, e):
    w, a, bb = params
    s2 = np.empty(len(e)); s2[0] = e.var()
    for t in range(1, len(e)):
        s2[t] = w + a*e[t-1]**2 + bb*s2[t-1]
    return s2

def garch_nll(params, e):
    if params[1] + params[2] >= 0.999: return 1e10   # keep it stationary
    s2 = garch_var(params, e)
    return 0.5 * np.sum(np.log(s2) + e**2 / s2)

fit = minimize(garch_nll, x0=[0.1*resid.var(), 0.08, 0.88], args=(resid,), method="L-BFGS-B",
               bounds=[(1e-6, None), (0, 0.5), (0, 0.999)])
g_w, g_a, g_b = fit.x
cond_var = garch_var(fit.x, resid)
z_resid  = resid / np.sqrt(cond_var)
lr_var   = g_w / (1 - g_a - g_b)                       # long-run daily variance
var_next = g_w + g_a*resid[-1]**2 + g_b*cond_var[-1]     # tomorrow's variance
vol_now  = math.sqrt(var_next * 252)                   # annualized, %
vol_lr   = math.sqrt(lr_var * 252)

rng   = np.random.default_rng(SEED)
mu    = 100 * ANNUAL_DRIFT / 252
logp  = np.zeros(N_PATHS)
var_t = np.full(N_PATHS, var_next)
paths = np.empty((HORIZON, N_PATHS))
for h in range(HORIZON):
    shock    = np.sqrt(var_t) * rng.choice(z_resid, N_PATHS)
    logp    += (mu + shock) / 100
    var_t    = g_w + g_a*shock**2 + g_b*var_t
    paths[h] = price * np.exp(logp)

PCTS  = [5, 25, 50, 75, 95]
bands = {str(p): [price] + [round(float(v), 2) for v in np.percentile(paths, p, axis=1)] for p in PCTS}

def outlook(h):
    end = paths[h-1]
    return {"median": float(np.median(end)),
            "lo": float(np.percentile(end, 5)), "hi": float(np.percentile(end, 95)),
            "p_up":   float((end > price).mean() * 100),
            "p_up10": float((end >= price * 1.1).mean() * 100),
            "p_dn10": float((end <= price * 0.9).mean() * 100),
            "p_high": float((paths[:h].max(axis=0) >= high52).mean() * 100)}

o30, o90 = outlook(30), outlook(90)
chg30 = (o30["median"] - price) / price * 100

def coverage(h=30, z90=1.645, window=750):
    """Share of past h-day moves inside the model's 90% band (in-sample, overlapping)."""
    k, persist, hits = np.arange(h), g_a + g_b, []
    for t in range(max(0, len(resid) - window - h), len(resid) - h):
        v1 = g_w + g_a*resid[t]**2 + g_b*cond_var[t]
        v  = np.sum(lr_var + persist**k * (v1 - lr_var))
        hits.append(abs(resid[t+1:t+1+h].sum()) <= z90 * math.sqrt(v))
    return float(np.mean(hits) * 100)

cover30 = coverage(30)

print(f"  {len(closes)} trading days  |  ${price:.2f}  {change:+.2f} ({change_pct:+.2f}%)")
print(f"  RSI {rsi_val:.1f}  |  MACD {'Bullish' if macd_bull else 'Bearish'}  |  Signal: {overall}")
print(f"  GARCH vol {vol_now:.0f}% now / {vol_lr:.0f}% long-run  |  backtest: {cover30:.0f}% of 30d moves inside 90% band")
for lbl, o in (("30d", o30), ("90d", o90)):
    print(f"  {lbl}: median ${o['median']:.2f}  90% range ${o['lo']:.0f}-${o['hi']:.0f}  P(up) {o['p_up']:.0f}%")

# ── 5. Generate HTML ──────────────────────────────────────────────────────────
def next_trading_days(last, count):
    out, d = [], last
    while len(out) < count:
        d += timedelta(days=1)
        if d.weekday() < 5: out.append(d.strftime("%Y-%m-%d"))
    return out

fore_dates = next_trading_days(hist.index[-1].to_pydatetime(), HORIZON)

up       = change >= 0
o_state  = "bull" if "Buy" in overall else "bear" if "Sell" in overall else "neut"
GLYPH    = {"bull": "▲", "bear": "▼", "neut": "●"}
def b(x): return "bull" if x else "bear"

rsi_state  = "bear" if rsi_sig == "Overbought" else "bull" if rsi_sig == "Oversold" else "neut"
boll_state = "bull" if boll_pos == "Lower" else "bear" if boll_pos == "Upper" else "neut"
ma50_txt   = f"${ma50_v:.0f}"  if ma50_v  else "N/A"
ma200_txt  = f"${ma200_v:.0f}" if ma200_v else "N/A"

def signal(name, state, value):
    return (f'<div class="sig-card"><span class="pip {state}">{GLYPH[state]}</span>'
            f'<div><div class="sig-name">{name}</div><div class="sig-val {state}">{value}</div></div></div>')

signals_html = "\n    ".join([
    signal("RSI (14)",          rsi_state,      f"{rsi_val:.1f} · {rsi_sig}"),
    signal("MACD vs Signal",    b(macd_bull),   f"{'Bullish' if macd_bull else 'Bearish'} ({macd_l-macd_s:+.2f})"),
    signal("Price vs MA50",     b(ma50_bull),   f"{'Above' if ma50_bull else 'Below'} {ma50_txt}"),
    signal("Price vs MA200",    b(ma200_bull),  f"{'Above' if ma200_bull else 'Below'} {ma200_txt}"),
    signal("Bollinger Band",    boll_state,     f"{boll_pos or '—'} Band"),
    signal("30-Day 90% Range",  "neut",         f"${o30['lo']:.0f} – ${o30['hi']:.0f}"),
])

def stat(label, value, cls=""):
    return f'<div class="stat-card"><div class="stat-lbl">{label}</div><div class="stat-val {cls}">{value}</div></div>'

stats_html = "\n  ".join([
    stat("Market Cap", fmt_cap(mkt_cap), "accent"),
    stat("P/E Ratio",  f"{pe:.1f}x" if pe else "N/A"),
    stat("EPS (TTM)",  f"${eps:.2f}" if eps else "N/A"),
    stat("Beta",       f"{beta:.2f}" if beta else "N/A"),
    stat("RSI (14)",   f"{rsi_val:.1f}", "bear" if rsi_val > 70 else "bull" if rsi_val < 30 else ""),
    stat("MA 50",      ma50_txt),
    stat("MA 200",     ma200_txt),
    stat("Avg Volume", fmt_vol(avg_vol)),
])

def target(label, tag, o):
    chg = (o["median"] - price) / price * 100
    return f"""<div class="pred-card">
        <div class="pred-lbl"><span>{label}</span><span class="tag">{tag}</span></div>
        <div class="pred-price">${o['median']:.2f}</div>
        <div class="pred-chg {b(chg >= 0)}">{chg:+.1f}% median</div>
        <div class="pred-range">90% range <b>${o['lo']:.0f} – ${o['hi']:.0f}</b></div>
        <div class="conf-lbl"><span>Chance of finishing higher</span><span>{o['p_up']:.0f}%</span></div>
        <div class="conf-track"><div class="conf-fill" style="width:{o['p_up']:.0f}%"></div></div>
      </div>"""

def prob_row(label, key):
    return f"<tr><td>{label}</td><td>{o30[key]:.0f}%</td><td>{o90[key]:.0f}%</td></tr>"

prob_rows = "\n          ".join([
    prob_row("Finish higher",              "p_up"),
    prob_row("Gain 10% or more",           "p_up10"),
    prob_row("Lose 10% or more",           "p_dn10"),
    prob_row(f"Touch 52w high (${high52:.0f})", "p_high"),
])

# Year to date: measured from the prior year's last close, as brokers quote it
ytd_year   = dates[-1][:4]
ytd_i      = next(k for k, d in enumerate(dates) if d.startswith(ytd_year))
ytd_from   = max(ytd_i - 1, 0)
ytd_dates  = dates[ytd_from:]
ytd_closes = closes[ytd_from:]
ytd_base   = ytd_closes[0]
ytd_ret    = (price / ytd_base - 1) * 100
ytd_hi_i   = max(range(len(ytd_closes)), key=ytd_closes.__getitem__)
ytd_lo_i   = min(range(len(ytd_closes)), key=ytd_closes.__getitem__)

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{SYMBOL} Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root{{--bg:#0a0e1a;--surface:#111827;--surface2:#162036;--border:#1f2a40;--grid:#1a2438;--accent:#76b900;--accent2:#00d4aa;
  --text:#e8edf5;--text2:#b4bfd3;--muted:#8b97b0;--red:#ef4444;--green:#22c55e;
  --t-bull:rgba(34,197,94,.14);--t-bear:rgba(239,68,68,.14);--t-neut:rgba(139,151,176,.14);}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--bg);color:var(--text);min-height:100vh;-webkit-font-smoothing:antialiased;}}
.bull{{color:var(--green);}} .bear{{color:var(--red);}} .neut{{color:var(--muted);}} .accent{{color:var(--accent);}}

header{{background:var(--surface);border-bottom:1px solid var(--border);padding:14px 24px;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;}}
.brand{{display:flex;align-items:center;gap:10px;}}
.dot{{width:9px;height:9px;border-radius:50%;background:var(--accent);box-shadow:0 0 8px var(--accent);}}
.brand-name{{font-size:15px;font-weight:700;}} .brand-sub{{font-size:11px;color:var(--muted);}}
.hdr-right{{display:flex;align-items:center;gap:12px;}}
.gen{{font-size:11px;color:var(--muted);}}
.badge{{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:700;padding:5px 12px;border-radius:20px;}}
.badge.bull{{background:var(--t-bull);}} .badge.bear{{background:var(--t-bear);}} .badge.neut{{background:var(--t-neut);color:var(--text2);}}
.badge small{{font-size:9px;}}

main{{max-width:1120px;margin:0 auto;padding:28px 20px 40px;}}
.hero{{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:24px;}}
.price-row{{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:8px;}}
.price-main{{font-size:52px;font-weight:800;letter-spacing:-.03em;line-height:1;}}
.price-chip{{font-size:16px;font-weight:600;padding:5px 10px;border-radius:6px;}}
.price-chip.bull{{background:var(--t-bull);}} .price-chip.bear{{background:var(--t-bear);}}
.price-meta{{font-size:13px;color:var(--muted);}} .price-meta b{{color:var(--text2);font-weight:600;}}
.src{{font-size:11px;color:var(--muted);text-align:right;line-height:1.7;}}

.stat-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:32px;}}
.stat-card{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px 16px;}}
.stat-lbl{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px;}}
.stat-val{{font-size:20px;font-weight:700;letter-spacing:-.02em;}}

.section{{margin-bottom:32px;}}
.sec-hd{{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:12px;flex-wrap:wrap;}}
.sec-title{{font-size:15px;font-weight:600;}}
.sec-badge{{font-size:11px;color:var(--muted);background:var(--surface2);padding:3px 9px;border-radius:12px;}}
.chart-card{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:18px 20px 14px;}}
.chart-wrap{{position:relative;height:320px;}} .chart-wrap.sm{{height:190px;}}
.legend{{display:flex;gap:18px;font-size:12px;color:var(--text2);margin-bottom:12px;flex-wrap:wrap;}}
.legend span{{display:inline-flex;align-items:center;gap:7px;}}
.legend i{{display:inline-block;width:18px;border-top:2px solid;}}
.legend i.dash{{border-top-style:dashed;}}
.legend i.box{{width:12px;height:10px;border:0;border-radius:2px;}}
.legend .meta{{margin-left:auto;color:var(--muted);}} .legend .meta b{{color:var(--text2);font-weight:600;}}
.card-cap{{font-size:12px;color:var(--text2);margin-bottom:10px;}}

.signals-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;}}
.sig-card{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px 16px;display:flex;align-items:center;gap:12px;}}
.pip{{width:30px;height:30px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:11px;flex-shrink:0;}}
.pip.bull{{background:var(--t-bull);}} .pip.bear{{background:var(--t-bear);}} .pip.neut{{background:var(--t-neut);}}
.sig-name{{font-size:11px;color:var(--muted);margin-bottom:2px;}}
.sig-val{{font-size:14px;font-weight:600;}} .sig-val.neut{{color:var(--text2);}}

.two-col{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:20px;align-items:start;}}
.pred-grid{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:10px;margin-bottom:12px;}}
.pred-card{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px;}}
.pred-lbl{{font-size:11px;color:var(--muted);margin-bottom:8px;display:flex;justify-content:space-between;gap:6px;}}
.tag{{color:var(--accent2);}}
.pred-price{{font-size:26px;font-weight:800;letter-spacing:-.02em;}}
.pred-chg{{font-size:13px;font-weight:600;margin:2px 0 12px;}}
.conf-lbl{{font-size:10px;color:var(--muted);display:flex;justify-content:space-between;margin-bottom:4px;}}
.conf-track{{height:4px;background:var(--border);border-radius:2px;overflow:hidden;}}
.conf-fill{{height:100%;border-radius:2px;background:var(--accent2);}}
.pred-range{{font-size:12px;color:var(--muted);margin-bottom:12px;}} .pred-range b{{color:var(--text2);font-weight:600;}}
.prob-card{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:6px 18px;margin-bottom:12px;}}
.prob{{width:100%;border-collapse:collapse;font-size:13px;}}
.prob th{{font-size:10px;font-weight:500;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;text-align:right;padding:10px 0 8px;}}
.prob th:first-child,.prob td:first-child{{text-align:left;}}
.prob td{{padding:9px 0;border-top:1px solid var(--border);text-align:right;color:var(--text2);font-variant-numeric:tabular-nums;}}
.prob td:not(:first-child){{color:var(--text);font-weight:600;width:22%;}}
.analysis-box{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:20px 22px;font-size:13.5px;line-height:1.75;color:var(--text2);}}
.analysis-box p{{margin-bottom:12px;}} .analysis-box p:last-child{{margin-bottom:0;}} .analysis-box strong{{color:var(--text);}}
.disclaimer{{margin-top:32px;padding:14px 16px;border:1px solid var(--border);border-radius:8px;font-size:11.5px;color:var(--muted);line-height:1.6;}}
.disclaimer strong{{color:var(--text2);}}

@media(max-width:860px){{.signals-grid{{grid-template-columns:repeat(2,minmax(0,1fr));}} .two-col{{grid-template-columns:1fr;}}}}
@media(max-width:640px){{
  main{{padding:20px 16px 32px;}} header{{padding:12px 16px;}}
  .stat-grid{{grid-template-columns:repeat(2,minmax(0,1fr));}} .signals-grid{{grid-template-columns:1fr;}}
  .price-main{{font-size:42px;}} .src{{text-align:left;}} .gen{{display:none;}}
}}
</style>
</head>
<body>
<header>
  <div class="brand"><div class="dot"></div>
    <div><div class="brand-name">{SYMBOL}{" · " + exchange if exchange else ""}</div><div class="brand-sub">{company}</div></div>
  </div>
  <div class="hdr-right">
    <span class="gen">Generated {datetime.now().strftime("%b %d, %Y %H:%M")}</span>
    <span class="badge {o_state}"><small>{GLYPH[o_state]}</small>{overall}</span>
  </div>
</header>

<main>
<div class="hero">
  <div>
    <div class="price-row">
      <div class="price-main">${price:.2f}</div>
      <div class="price-chip {b(up)}">{change:+.2f} ({change_pct:+.2f}%)</div>
    </div>
    <div class="price-meta">Prev close <b>${prev:.2f}</b> &nbsp;·&nbsp; 52w high <b>${high52:.2f}</b> &nbsp;·&nbsp; 52w low <b>${low52:.2f}</b></div>
  </div>
  <div class="src">Yahoo Finance via yfinance · {len(closes)} trading days<br>Re-run the script to refresh</div>
</div>

<div class="stat-grid">
  {stats_html}
</div>

<div class="section">
  <div class="sec-hd">
    <div class="sec-title">Price History &amp; 30-Day Forecast</div>
    <div class="sec-badge">Last 90 sessions + 30-session simulation</div>
  </div>
  <div class="chart-card">
    <div class="legend">
      <span><i style="border-color:var(--accent)"></i>Close</span>
      <span><i class="dash" style="border-color:var(--accent2)"></i>Median forecast</span>
      <span><i class="box" style="background:rgba(0,212,170,.30)"></i>50% range</span>
      <span><i class="box" style="background:rgba(0,212,170,.13)"></i>90% range</span>
    </div>
    <div class="chart-wrap"><canvas id="priceChart"></canvas></div>
  </div>
</div>

<div class="section">
  <div class="sec-hd">
    <div class="sec-title">Year to Date</div>
    <div class="sec-badge">{ytd_year} YTD <span class="{b(ytd_ret >= 0)}">{ytd_ret:+.1f}%</span></div>
  </div>
  <div class="chart-card">
    <div class="legend">
      <span><i style="border-color:var(--accent)"></i>Close</span>
      <span><i class="dash" style="border-color:var(--muted)"></i>Start of year ${ytd_base:.2f}</span>
      <span class="meta">High <b>${ytd_closes[ytd_hi_i]:.2f}</b> ({ytd_dates[ytd_hi_i][5:]}) &nbsp;·&nbsp; Low <b>${ytd_closes[ytd_lo_i]:.2f}</b> ({ytd_dates[ytd_lo_i][5:]})</span>
    </div>
    <div class="chart-wrap"><canvas id="ytdChart"></canvas></div>
  </div>
</div>

<div class="section">
  <div class="sec-hd">
    <div class="sec-title">Technical Indicators</div>
    <div class="sec-badge">Overall: <span class="{o_state}">{overall}</span></div>
  </div>
  <div class="signals-grid">
    {signals_html}
  </div>
</div>

<div class="two-col">
  <div>
    <div class="sec-hd"><div class="sec-title">Price Outlook</div><div class="sec-badge">GARCH(1,1) Monte Carlo · {N_PATHS:,} paths</div></div>
    <div class="pred-grid">
      {target("30-Day Outlook", "Short-term", o30)}
      {target("90-Day Outlook", "Mid-term", o90)}
    </div>
    <div class="prob-card">
      <table class="prob">
        <thead><tr><th>Probability</th><th>30 days</th><th>90 days</th></tr></thead>
        <tbody>
          {prob_rows}
        </tbody>
      </table>
    </div>
    <div class="chart-card">
      <div class="card-cap">Daily % change · last 60 sessions</div>
      <div class="chart-wrap sm"><canvas id="dailyChart"></canvas></div>
    </div>
  </div>
  <div>
    <div class="sec-hd"><div class="sec-title">Technical Analysis</div><div class="sec-badge">Computed from real data</div></div>
    <div class="analysis-box">
      <p>{SYMBOL} is trading at <strong>${price:.2f}</strong>, {'up' if up else 'down'} <strong>{abs(change_pct):.2f}%</strong> from the prior session. Based on {len(closes)} trading days of real data, the stock is {'above both its 50-day MA (<strong>$' + f"{ma50_v:.0f}" + '</strong>) and 200-day MA (<strong>$' + f"{ma200_v:.0f}" + '</strong>) — a bullish golden-cross structure' if ma50_bull and ma200_bull else 'above the 50-day MA but below the 200-day — recovery in progress' if ma50_bull else 'below both moving averages — bearish structure requiring caution'}.</p>
      <p>The <strong>RSI of {rsi_val:.1f}</strong> signals {'overbought conditions — a short-term pullback is possible' if rsi_sig=='Overbought' else 'oversold conditions — a bounce may be near' if rsi_sig=='Oversold' else 'neutral momentum'}. MACD is <strong>{'bullish' if macd_bull else 'bearish'}</strong> ({macd_l-macd_s:+.2f} vs signal). {f"Price is at the <strong>{boll_pos} Bollinger Band</strong>" + (" — extended." if boll_pos=="Upper" else " — potential support." if boll_pos=="Lower" else " — normal range.") if boll_pos else ""}</p>
      <p>A <strong>GARCH(1,1)</strong> model fit to {len(rets):,} daily returns puts current volatility at <strong>{vol_now:.0f}%</strong> annualized (long-run {vol_lr:.0f}%). Across {N_PATHS:,} simulated paths the 30-day median is <strong>${o30['median']:.2f}</strong> (90% range ${o30['lo']:.0f}–${o30['hi']:.0f}), with a <strong>{o30['p_up']:.0f}%</strong> chance of finishing higher. In an in-sample backtest, <strong>{cover30:.0f}%</strong> of past 30-day moves fell inside the model's 90% band.</p>
      <p>The stock is at <strong>{(price-low52)/(high52-low52)*100:.0f}%</strong> of its 52-week range (${low52:.0f}–${high52:.0f}). Overall technical signal: <strong class="{o_state}">{overall}</strong>.</p>
    </div>
  </div>
</div>

<div class="disclaimer"><strong>Disclaimer:</strong> Data sourced from Yahoo Finance via yfinance. All indicators and forecasts are computed locally from historical prices. The simulation assumes {ANNUAL_DRIFT:.0%} annual drift; its probabilities describe the model, not the market. For educational purposes only — not financial advice. Consult a licensed financial advisor before investing.</div>
</main>

<script>
const DATES  = {json.dumps(dates)};
const CLOSES = {json.dumps(closes)};
const BANDS  = {json.dumps(bands)};
const FDATES = {json.dumps(fore_dates)};
const DAILY  = {json.dumps(daily_chg)};
const YTD_DATES  = {json.dumps(ytd_dates)};
const YTD_CLOSES = {json.dumps(ytd_closes)};

const C = {{text:'#e8edf5', text2:'#b4bfd3', muted:'#8b97b0', grid:'#1a2438', surface:'#111827',
           border:'#2a3854', accent:'#76b900', accent2:'#00d4aa', green:'#22c55e', red:'#ef4444'}};
const MON  = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const fmtD = s => {{ const [y, m, d] = s.split('-'); return MON[+m-1] + ' ' + (+d); }};
Chart.defaults.font.family = 'system-ui,-apple-system,"Segoe UI",sans-serif';
Chart.defaults.color = C.muted;
const TIP = {{backgroundColor:C.surface, borderColor:C.border, borderWidth:1, titleColor:C.text,
             bodyColor:C.text2, padding:10, cornerRadius:8, displayColors:false}};
const dateTicks = {{maxRotation:0, autoSkip:true, font:{{size:11}},
                   callback: function(v) {{ return fmtD(this.getLabelForValue(v)); }}}};
// Vertical gradient sized to the plot area, not a fixed pixel height
const hover = col => ({{pointRadius:0, pointHoverRadius:5, pointHoverBackgroundColor:col,
                        pointHoverBorderColor:C.surface, pointHoverBorderWidth:2}});
const fade = (hex, a) => c => {{
  const {{ctx, chartArea}} = c.chart;
  if (!chartArea) return 'transparent';
  const g = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
  g.addColorStop(0, hex + a); g.addColorStop(1, hex + '00');
  return g;
}};

(function() {{
  const d90 = DATES.slice(-90), c90 = CLOSES.slice(-90), last = c90.length - 1;
  const H = 30;   // chart shows the first 30 sessions; 90-day bands would flatten the history
  // Bands start at the last close so they fan out from today
  const band = p => [...new Array(last).fill(null), ...BANDS[p].slice(0, H + 1)];
  const area = (label, p, fill, color) => ({{label, data:band(p), fill, backgroundColor:color,
    borderWidth:0, pointRadius:0, pointHoverRadius:0, tension:0.2}});
  const todayLine = {{id:'today', beforeDatasetsDraw(ch) {{
    const x = ch.scales.x.getPixelForValue(last), {{top, bottom}} = ch.chartArea, g = ch.ctx;
    g.save(); g.strokeStyle = C.border; g.lineWidth = 1; g.setLineDash([2, 3]);
    g.beginPath(); g.moveTo(x, top); g.lineTo(x, bottom); g.stroke(); g.restore();
  }}}};
  new Chart(document.getElementById('priceChart'), {{
    type: 'line',
    plugins: [todayLine],
    data: {{
      labels: [...d90, ...FDATES.slice(0, H)],
      datasets: [
        {{label:'Close', data:c90, borderColor:C.accent, backgroundColor:fade(C.accent, '33'),
          borderWidth:2, fill:'start', tension:0.25, ...hover(C.accent)}},
        area('p5',  '5',  false, 'transparent'),
        area('p95', '95', '-1',  C.accent2 + '21'),
        area('p25', '25', false, 'transparent'),
        area('p75', '75', '-1',  C.accent2 + '3d'),
        {{label:'Median', data:band('50'), borderColor:C.accent2, borderWidth:2, borderDash:[6, 4],
          fill:false, tension:0.2, ...hover(C.accent2)}}
      ]
    }},
    options: {{
      responsive:true, maintainAspectRatio:false,
      interaction:{{mode:'index', intersect:false}},
      plugins: {{
        legend:{{display:false}},
        tooltip:{{...TIP,
          filter: i => i.raw != null && (i.datasetIndex === 0 || (i.datasetIndex === 5 && i.dataIndex > last)),
          callbacks:{{title: i => fmtD(i[0].label), label: c => {{
            if (c.datasetIndex === 0) return `Close: $${{c.raw.toFixed(2)}}`;
            const k = c.dataIndex - last, r = (lo, hi) => `$${{BANDS[lo][k].toFixed(0)}} – $${{BANDS[hi][k].toFixed(0)}}`;
            return [`Median: $${{c.raw.toFixed(2)}}`, `50% range: ${{r('25', '75')}}`, `90% range: ${{r('5', '95')}}`];
          }}}}}}
      }},
      scales: {{
        x:{{grid:{{display:false}}, border:{{color:C.border}}, ticks:{{...dateTicks, maxTicksLimit:8}}}},
        y:{{grid:{{color:C.grid}}, border:{{display:false}}, ticks:{{font:{{size:11}}, callback: v => '$' + v}}}}
      }}
    }}
  }});
}})();

(function() {{
  const base = YTD_CLOSES[0];
  // Dashed reference line at the start-of-year price
  const baseline = {{id:'baseline', beforeDatasetsDraw(ch) {{
    const y = ch.scales.y.getPixelForValue(base), {{left, right}} = ch.chartArea, g = ch.ctx;
    g.save(); g.strokeStyle = C.muted; g.globalAlpha = 0.6; g.lineWidth = 1; g.setLineDash([4, 4]);
    g.beginPath(); g.moveTo(left, y); g.lineTo(right, y); g.stroke(); g.restore();
  }}}};
  new Chart(document.getElementById('ytdChart'), {{
    type: 'line',
    plugins: [baseline],
    data: {{
      labels: YTD_DATES,
      datasets: [{{label:'Close', data:YTD_CLOSES, borderColor:C.accent, borderWidth:2, tension:0.25,
                   fill:{{target:{{value:base}}, above:C.green + '24', below:C.red + '24'}}, ...hover(C.accent)}}]
    }},
    options: {{
      responsive:true, maintainAspectRatio:false,
      interaction:{{mode:'index', intersect:false}},
      plugins: {{
        legend:{{display:false}},
        tooltip:{{...TIP, callbacks:{{title: i => fmtD(i[0].label), label: c => {{
          const pct = (c.raw / base - 1) * 100;
          return [`Close: $${{c.raw.toFixed(2)}}`, `YTD: ${{pct >= 0 ? '+' : ''}}${{pct.toFixed(1)}}%`];
        }}}}}}
      }},
      scales: {{
        x:{{grid:{{display:false}}, border:{{color:C.border}}, ticks:{{...dateTicks, maxTicksLimit:10}}}},
        y:{{grid:{{color:C.grid}}, border:{{display:false}}, ticks:{{font:{{size:11}}, callback: v => '$' + v}}}}
      }}
    }}
  }});
}})();

(function() {{
  const d60 = DATES.slice(-60), chg60 = DAILY.slice(-60);
  new Chart(document.getElementById('dailyChart'), {{
    type: 'bar',
    data: {{
      labels: d60,
      datasets: [{{data:chg60, backgroundColor: chg60.map(v => v >= 0 ? C.green + 'cc' : C.red + 'cc'),
                   borderRadius:2, borderSkipped:false, barPercentage:0.75, categoryPercentage:0.9}}]
    }},
    options: {{
      responsive:true, maintainAspectRatio:false,
      plugins: {{
        legend:{{display:false}},
        tooltip:{{...TIP, callbacks:{{title: i => fmtD(i[0].label),
                                     label: c => (c.raw >= 0 ? '+' : '') + c.raw.toFixed(2) + '%'}}}}
      }},
      scales: {{
        x:{{grid:{{display:false}}, border:{{color:C.border}}, ticks:{{...dateTicks, maxTicksLimit:6}}}},
        y:{{grid:{{color:C.grid}}, border:{{display:false}}, ticks:{{font:{{size:11}}, callback: v => v + '%'}}}}
      }}
    }}
  }});
}})();
</script>
</body>
</html>"""

out = f"{SYMBOL.lower()}_dashboard.html"
with open(out, "w", encoding="utf-8") as f:
    f.write(html)

def pct(v): return round((v - price) / price * 100, 2)
def horizon(o): return {"median": round(o["median"], 2), "chg": pct(o["median"]),
                        "lo": round(o["lo"], 2), "hi": round(o["hi"], 2),
                        **{k: round(o[k], 1) for k in ("p_up", "p_up10", "p_dn10", "p_high")}}
summary = {
    "symbol": SYMBOL, "company": company, "as_of": dates[-1],
    "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
    "price": price, "change_pct": change_pct, "ytd": round(ytd_ret, 2),
    "high52": high52, "low52": low52,
    "signal": overall, "bulls": bulls, "bears": bears,
    "rsi": rsi_val, "rsi_sig": rsi_sig, "macd_bull": bool(macd_bull),
    "ma50_bull": ma50_bull, "ma200_bull": ma200_bull, "boll_pos": boll_pos,
    "vol_now": round(vol_now, 1), "vol_lr": round(vol_lr, 1), "cover30": round(cover30, 1),
    "o30": horizon(o30), "o90": horizon(o90),
}
with open(f"{SYMBOL.lower()}_summary.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=1)

print(f"\n✓ Saved: {os.path.abspath(out)}")
if not os.environ.get("ANALYZER_NO_BROWSER"):   # set by server.py (web tool)
    print("  Opening in browser...")
    webbrowser.open(f"file://{os.path.abspath(out)}")
