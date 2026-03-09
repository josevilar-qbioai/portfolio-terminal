#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════╗
║   PORTFOLIO DASH  ·  Bloomberg Terminal Style  v4.0   ║
║   python3 portfolio_dash.py -f portfolio.yaml         ║
╚═══════════════════════════════════════════════════════╝
Requiere : pyyaml textual
  pip install textual pyyaml
Opcional : yfinance (precios reales)
  pip install yfinance
"""

import argparse, csv, json, subprocess, sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml
from textual.app        import App, ComposeResult
from textual.binding    import Binding
from textual.containers import ScrollableContainer, Horizontal, Container
from textual.screen     import ModalScreen
from textual.widgets    import (Header, Footer, TabbedContent, TabPane,
                                 Static, Input, Button, Label)

from rich.table  import Table
from rich.text   import Text
from rich        import box as rbox
from rich.console import Group

# Rangos de tiempo disponibles para el histórico (tecla T)
HIST_RANGES = ["TODO", "3A", "1A", "6M", "3M", "1M"]

# ══════════════════════════════════════════════════════════════════════════════
# XIRR
# ══════════════════════════════════════════════════════════════════════════════
def xirr(cashflows):
    if len(cashflows) < 2: return None
    try:
        t0   = cashflows[0][0]
        yrs  = [(cf[0]-t0).days/365.25 for cf in cashflows]
        r    = 0.1
        for _ in range(200):
            if r <= -1: return None
            npv  = sum(cf[1]/(1+r)**t for cf,t in zip(cashflows,yrs))
            dnpv = sum(-t*cf[1]/(1+r)**(t+1) for cf,t in zip(cashflows,yrs))
            if abs(dnpv) < 1e-12: break
            nr = r - npv/dnpv
            if abs(nr-r) < 1e-8:
                return float(nr) if isinstance(nr, (int, float)) else None
            r = nr
        return float(r) if isinstance(r, (int, float)) else None
    except: return None

# ══════════════════════════════════════════════════════════════════════════════
# DATOS
# ══════════════════════════════════════════════════════════════════════════════
def load_macro_snapshot(hist_dir) -> dict:
    """Carga historico/macro_snapshot.json; devuelve {} si no existe."""
    path = Path(hist_dir) / "macro_snapshot.json"
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def load_history(ticker, hist_dir):
    path = Path(hist_dir) / f"{ticker.replace('/','-')}.csv"
    if not path.exists(): return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try: rows.append((r["fecha"], float(r["precio_cierre"])))
            except: pass
    return sorted(rows, key=lambda x: x[0])

def history_stats(hist):
    if not hist: return {}
    dates  = [h[0] for h in hist]
    prices = [h[1] for h in hist]
    p0, p1 = prices[0], prices[-1]
    def pct_since(days):
        cutoff = (date.today()-timedelta(days=days)).isoformat()
        sub = [p for d,p in hist if d >= cutoff]
        return (sub[-1]-sub[0])/sub[0]*100 if len(sub) >= 2 else None
    return {
        "prices": prices, "dates": dates,
        "p_first": p0, "p_last": p1,
        "p_min": min(prices), "p_max": max(prices),
        "total_pct": (p1-p0)/p0*100 if p0 else 0,
        "1M": pct_since(30),   "3M": pct_since(90),
        "6M": pct_since(180),  "1A": pct_since(365),
        "3A": pct_since(1095), "5A": pct_since(1825),
        "10A": pct_since(3650),
    }

def daily_returns(prices):
    """Retornos diarios como lista de floats."""
    if len(prices) < 2: return []
    return [(prices[i]-prices[i-1])/prices[i-1] for i in range(1,len(prices))]

def max_drawdown(prices):
    """Máxima caída desde un pico anterior (0.0 – 1.0)."""
    if len(prices) < 2: return None
    peak, dd = prices[0], 0.0
    for p in prices:
        if p > peak: peak = p
        if peak > 0: dd = max(dd, (peak-p)/peak)
    return dd

def sharpe_ratio(prices, risk_free=0.03):
    """Sharpe Ratio anualizado. Requiere ≥30 observaciones."""
    if len(prices) < 30: return None
    rets = daily_returns(prices)
    if not rets: return None
    n    = len(rets)
    mean = sum(rets)/n
    var  = sum((r-mean)**2 for r in rets)/(n-1) if n > 1 else 0
    std  = var**0.5
    if std == 0: return None
    daily_rf = risk_free/252
    return (mean-daily_rf)/std*(252**0.5)

def volatility_annual(prices):
    """Volatilidad anualizada (desv. típica de retornos diarios × √252)."""
    if len(prices) < 10: return None
    rets = daily_returns(prices)
    if len(rets) < 2: return None
    n    = len(rets)
    mean = sum(rets)/n
    var  = sum((r-mean)**2 for r in rets)/(n-1)
    return var**0.5 * (252**0.5)

def pearson_corr(px, py):
    """Correlación de Pearson entre dos series de precios (retornos)."""
    n = min(len(px), len(py))
    if n < 30: return None
    ra = daily_returns(px[-n:])
    rb = daily_returns(py[-n:])
    m  = min(len(ra), len(rb))
    if m < 2: return None
    ra, rb  = ra[:m], rb[:m]
    ma = sum(ra)/m;  mb = sum(rb)/m
    num  = sum((a-ma)*(b-mb) for a,b in zip(ra,rb))
    da   = sum((a-ma)**2 for a in ra)**0.5
    db   = sum((b-mb)**2 for b in rb)**0.5
    return num/(da*db) if da*db > 0 else None

def sortino_ratio(prices, risk_free=0.03):
    """Sortino Ratio anualizado. Solo penaliza volatilidad a la baja (retornos < rf diario).
    Más justo que Sharpe para activos asimétricos como Bitcoin o materias primas."""
    if len(prices) < 30: return None
    rets     = daily_returns(prices)
    if not rets: return None
    n        = len(rets)
    daily_rf = risk_free / 252
    mean     = sum(rets) / n
    # Downside deviation: penaliza solo retornos por debajo del objetivo (rf)
    neg_sq   = [(r - daily_rf)**2 for r in rets if r < daily_rf]
    if not neg_sq: return None
    downside_std = (sum(neg_sq) / n) ** 0.5   # denominador = n total, no solo negativos
    if downside_std == 0: return None
    return (mean - daily_rf) / downside_std * (252 ** 0.5)

def var_95_daily(prices):
    """VaR histórico al 95% de confianza (pérdida máxima esperada en el 5% peor de días).
    Devuelve la pérdida como número positivo. Ej: 0.032 = perder hasta 3.2% en un mal día."""
    if len(prices) < 30: return None
    rets = daily_returns(prices)
    if not rets: return None
    sorted_rets = sorted(rets)
    idx = max(0, int(len(sorted_rets) * 0.05) - 1)
    return -sorted_rets[idx]   # positivo = pérdida

def current_drawdown(prices):
    """Drawdown actual: caída desde el máximo histórico hasta el precio más reciente.
    0.0 = en máximos históricos. 0.30 = 30% por debajo del pico."""
    if len(prices) < 2: return None
    peak = max(prices)
    if peak == 0: return None
    return (peak - prices[-1]) / peak

def pct_positive_days(prices):
    """Porcentaje de días con retorno diario positivo (win rate).
    Un activo puede tener gran rentabilidad con solo un 52% de días en verde."""
    if len(prices) < 10: return None
    rets = daily_returns(prices)
    if not rets: return None
    return sum(1 for r in rets if r > 0) / len(rets) * 100

def beta_vs_hist(hist_a, hist_b):
    """Beta de A respecto a B alineando por fecha. Requiere ≥30 días comunes.
    Beta >1 = más volátil que benchmark. Beta <1 = defensivo. Beta <0 = inversamente correlado."""
    if not hist_a or not hist_b: return None
    lookup_b = {d: p for d, p in hist_b}
    aligned_a, aligned_b = [], []
    for d, p in hist_a:
        if d in lookup_b:
            aligned_a.append(p)
            aligned_b.append(lookup_b[d])
    if len(aligned_a) < 30: return None
    rets_a = daily_returns(aligned_a)
    rets_b = daily_returns(aligned_b)
    n = min(len(rets_a), len(rets_b))
    if n < 30: return None
    rets_a, rets_b = rets_a[:n], rets_b[:n]
    ma = sum(rets_a)/n;  mb = sum(rets_b)/n
    cov   = sum((rets_a[i]-ma)*(rets_b[i]-mb) for i in range(n)) / (n-1)
    var_b = sum((r-mb)**2 for r in rets_b) / (n-1)
    return round(cov/var_b, 2) if var_b > 0 else None

def load_yaml(path):
    with open(path, encoding="utf-8") as f: return yaml.safe_load(f)

def load_fx_rates(hist_dir) -> dict:
    """Carga los tipos de cambio CCY→EUR desde historico/USDEUR.csv, GBPEUR.csv, etc.
    Devuelve dict como {"USD": 0.9524, "GBP": 1.1905}.
    """
    fx = {}
    for ccy in ["USD", "GBP", "CHF", "JPY", "SEK", "NOK"]:
        h = load_history(f"{ccy}EUR", hist_dir)
        if h:
            fx[ccy] = h[-1][1]
    return fx

def process(data, hist_dir, use_live=False):
    prices_yaml = {k:float(v) for k,v in (data.get("precios_actuales") or {}).items() if v is not None}

    # Tipos de cambio CCY→EUR (1 USD = X EUR). Se acumulan en historico/USDEUR.csv etc.
    fx_eur = load_fx_rates(hist_dir)

    assets = []
    for a in (data.get("activos") or []):
        ticker           = a["ticker"]
        yahoo_ticker     = a.get("yahoo_ticker", ticker)
        historico_ticker = a.get("historico_ticker", ticker)
        divisa           = a.get("divisa", "EUR")
        fx_rate          = fx_eur.get(divisa, 1.0)  # 1.0 para EUR; e.g. 0.9524 para USD
        txs       = a.get("transacciones") or []
        buys      = [t for t in txs if t.get("tipo")=="compra"]
        sells     = [t for t in txs if t.get("tipo")=="venta"]
        # total_inv y proceeds ya están en EUR (el broker convirtió al operar)
        total_inv = sum(t["participaciones"]*t["precio"]+float(t.get("comision",0)) for t in buys)
        shares    = sum(t["participaciones"] for t in buys) - sum(t["participaciones"] for t in sells)
        proceeds  = sum(t["participaciones"]*t["precio"]-float(t.get("comision",0)) for t in sells)
        avg_cost  = (total_inv-proceeds)/shares if shares > 0 else 0
        hist = load_history(historico_ticker, hist_dir)
        hst  = history_stats(hist)
        # cur_price ya está en EUR desde el CSV (price_recorder convierte antes de guardar)
        # Si el CSV no existe o no tiene datos, intentamos precios_actuales (también EUR)
        cur_price_eur = hst.get("p_last") \
                        or prices_yaml.get(yahoo_ticker) \
                        or prices_yaml.get(historico_ticker) \
                        or prices_yaml.get(ticker, 0)
        cur_val       = shares * cur_price_eur
        # Precio nativo (USD) = precio_eur / fx_rate — solo para display informativo
        if divisa != "EUR" and fx_rate > 0:
            cur_price_native = round(cur_price_eur / fx_rate, 6)
        else:
            cur_price_native = cur_price_eur
        ter           = float(a.get("ter", 0) or 0)
        annual_fee_eur = cur_val * ter
        gain      = cur_val + proceeds - total_inv
        gain_pct  = gain/total_inv*100 if total_inv else 0
        cfs = sorted(
            [(-t["participaciones"]*t["precio"]-float(t.get("comision",0)),
              datetime.strptime(str(t["fecha"]),"%Y-%m-%d").date()) for t in buys] +
            [(t["participaciones"]*t["precio"]-float(t.get("comision",0)),
              datetime.strptime(str(t["fecha"]),"%Y-%m-%d").date()) for t in sells] +
            [(cur_val, date.today())],
            key=lambda x: x[1]
        )
        tir  = xirr([(d,v) for v,d in cfs])
        prices_h        = [h[1] for h in hist]
        last_price_date = hst["dates"][-1] if hst.get("dates") else None
        assets.append({
            "ticker":ticker, "nombre":a.get("nombre",""), "tipo":a.get("tipo","—"),
            "isin":a.get("isin",""), "taxonomia":a.get("taxonomia",""),
            "divisa":divisa, "fx_rate":fx_rate, "txs":txs,
            "shares":shares, "total_inv":total_inv, "proceeds":proceeds,
            "avg_cost":avg_cost,
            "cur_price":cur_price_eur,           # en EUR para cálculos y display
            "cur_price_native":cur_price_native, # en divisa original (para info)
            "cur_val":cur_val,
            "gain":gain, "gain_pct":gain_pct, "tir":tir,
            "hist":hist, "hst":hst,
            "last_price_date": last_price_date,
            "sharpe":   sharpe_ratio(prices_h),
            "sortino":  sortino_ratio(prices_h),
            "max_dd":   max_drawdown(prices_h),
            "cur_dd":   current_drawdown(prices_h),
            "vol":      volatility_annual(prices_h),
            "var95":    var_95_daily(prices_h),
            "pct_pos":  pct_positive_days(prices_h),
            "beta":     None,   # se calcula tras el loop vs benchmark
            "ter":      ter,
            "annual_fee_eur": annual_fee_eur,
        })
    # Beta vs benchmark (Vanguard Global Stock)
    bench_hist = next((a["hist"] for a in assets
                       if a["ticker"] in ("0IE00B03HCZ61","IE00B03HCZ61")), None)
    for a in assets:
        a["beta"] = beta_vs_hist(a["hist"], bench_hist) if bench_hist else None

    total_val        = sum(a["cur_val"]        for a in assets)
    total_inv2       = sum(a["total_inv"]      for a in assets)
    total_gain       = sum(a["gain"]           for a in assets)
    total_pct        = total_gain/total_inv2*100 if total_inv2 else 0
    total_annual_fee = sum(a["annual_fee_eur"] for a in assets)
    return {
        "meta":data.get("meta",{}), "assets":assets,
        "fx_eur": fx_eur,
        "total_val":total_val, "total_inv":total_inv2,
        "total_gain":total_gain, "total_pct":total_pct,
        "total_annual_fee": total_annual_fee,
    }

# ══════════════════════════════════════════════════════════════════════════════
# RENDER HELPERS
# ══════════════════════════════════════════════════════════════════════════════
SPARK = " ▁▂▃▄▅▆▇█"
MASK  = "████████"

def spark(prices, width=50):
    if len(prices) < 2: return "─" * width
    mn, mx = min(prices), max(prices)
    rng    = mx - mn or 1
    sample = (prices if len(prices) <= width
              else [prices[int(i*len(prices)/width)] for i in range(width)])
    return "".join(SPARK[min(8, int((p-mn)/rng*8))] for p in sample)

def fp(n):
    if n is None: return "—"
    return f"{'+'if n>=0 else ''}{n:.2f}%"

def fe(n):
    s = f"€{abs(n):,.2f}".replace(",","X").replace(".",",").replace("X",".")
    return ("-" if n < 0 else "+") + s

def gc(n):
    return "bright_green" if (n or 0) >= 0 else "bright_red"

def price_date_text(last_date_str):
    """Devuelve un Text con la fecha del último precio, coloreado por antigüedad."""
    if not last_date_str:
        return Text("sin datos", style="bright_red")
    try:
        last = date.fromisoformat(last_date_str)
        diff = (date.today() - last).days
    except Exception:
        return Text(last_date_str, style="grey50")
    if diff == 0:
        return Text("hoy", style="bright_green")
    elif diff == 1:
        return Text("ayer", style="green")
    elif diff <= 4:
        return Text("{:+d}d  {}".format(-diff, last_date_str[5:]), style="yellow")
    else:
        return Text("⚠ {}".format(last_date_str[5:]), style="bright_red")

def build_portfolio_history(assets, days=None):
    """Construye la serie temporal del valor total del portfolio.
    Devuelve (fechas_iso, valores_€). Solo usa activos con histórico y transacciones."""
    cutoff = (date.today() - timedelta(days=days)).isoformat() if days else "2000-01-01"

    # Recopilar fechas únicas de todos los activos
    all_dates_set = set()
    for a in assets:
        for d, _ in a["hist"]:
            if d >= cutoff:
                all_dates_set.add(d)
    if len(all_dates_set) < 2:
        return [], []
    all_dates = sorted(all_dates_set)

    # Pre-calcular precio disponible en cada fecha (last-known-price)
    def price_at(hist_sorted, d):
        last = None
        for hd, hp in hist_sorted:
            if hd <= d:
                last = hp
            else:
                break
        return last

    # Pre-ordenar históricos
    sorted_hists = {a["ticker"]: sorted(a["hist"], key=lambda x: x[0]) for a in assets}

    def shares_at(txs, d):
        s = 0.0
        for tx in txs:
            if str(tx.get("fecha","9999")) <= d:
                if tx.get("tipo") == "compra":
                    s += float(tx.get("participaciones", 0))
                elif tx.get("tipo") == "venta":
                    s -= float(tx.get("participaciones", 0))
        return max(0.0, s)

    port_dates, port_vals = [], []
    for d in all_dates:
        total = 0.0
        has_any = False
        for a in assets:
            sh = shares_at(a["txs"], d)
            if sh <= 0:
                continue
            p = price_at(sorted_hists[a["ticker"]], d)
            if p is None:
                continue
            total += sh * p
            has_any = True
        if has_any and total > 0:
            port_dates.append(d)
            port_vals.append(total)
    return port_dates, port_vals

def render_chart(prices, width=65, height=10, mask_axis=False):
    """Devuelve lista de objetos Text para el gráfico ASCII."""
    if not prices or len(prices) < 2:
        return [Text("Sin datos suficientes", style="grey50")]
    mn, mx = min(prices), max(prices)
    rng    = mx - mn or 1
    n      = width
    sample = ([prices[int(i*(len(prices)-1)/(n-1))] for i in range(n)]
              if len(prices) > n else prices + [prices[-1]]*(n-len(prices)))
    col    = "bright_green" if prices[-1] >= prices[0] else "bright_red"
    lines  = []
    for r in range(height):
        t = Text()
        upper = mx - rng*(r/(height-1)) if height > 1 else mx
        label = MASK[:9] if mask_axis else f"{upper:9.3f}"
        t.append(f"{label} │", style="grey50")
        for p in sample:
            norm     = (p-mn)/rng
            char_row = height-1-int(norm*(height-1))
            ch = "━" if char_row==r else ("░" if char_row<r else " ")
            t.append(ch, style=col)
        lines.append(t)
    sep = Text()
    sep.append("          └", style="grey50")
    sep.append("─"*width,     style="grey50")
    lines.append(sep)
    return lines

# ══════════════════════════════════════════════════════════════════════════════
# MODAL: AÑADIR TRANSACCIÓN
# ══════════════════════════════════════════════════════════════════════════════
def _macro_context(ind: dict) -> list:
    """Genera líneas Rich con interpretación macro para inversor a largo plazo."""
    lines = []

    def bullet(text, style="white"):
        t = Text()
        t.append("  ● ", style="#00ff41")
        t.append(text, style=style)
        lines.append(t)

    def note(text, style="grey50"):
        lines.append(Text("    " + text, style=style))

    vix      = (ind.get("VIX")     or {}).get("valor")
    spread   = (ind.get("SPREAD")  or {}).get("valor")
    usdidx   = (ind.get("USDIDX")  or {}).get("valor")
    gold1m   = (ind.get("GOLD")    or {}).get("chg_1mes")
    sp1m     = (ind.get("SP500")   or {}).get("chg_1mes")
    btc1m    = (ind.get("BTC")     or {}).get("chg_1mes")
    us10y    = (ind.get("US10Y")   or {}).get("valor")
    eurusd   = (ind.get("EURUSD")  or {}).get("valor")
    sox1m    = (ind.get("SOX")     or {}).get("chg_1mes")
    xlu1m    = (ind.get("XLU")     or {}).get("chg_1mes")
    gas1m    = (ind.get("GAS")     or {}).get("chg_1mes")
    uranium  = (ind.get("URANIUM") or {}).get("valor")
    copper1m = (ind.get("COPPER")  or {}).get("chg_1mes")

    # VIX
    if vix is not None:
        if vix < 15:
            bullet(f"Volatilidad MUY BAJA (VIX {vix:.1f}) — complacencia extrema.",
                   style="yellow")
            note("Los mercados están muy tranquilos, históricamente precede correcciones.")
        elif vix < 20:
            bullet(f"Volatilidad BAJA (VIX {vix:.1f}) — mercado tranquilo.", style="#00ff41")
            note("Sin señales de pánico. Buen contexto para continuar el DCA periódico.")
        elif vix < 30:
            bullet(f"Volatilidad MEDIA (VIX {vix:.1f}) — incertidumbre moderada.", style="yellow")
            note("Correcciones posibles a corto plazo. Para LP, mantener sin cambios.")
        else:
            bullet(f"Volatilidad ALTA (VIX {vix:.1f}) — miedo en el mercado.", style="#ff5555")
            note("Correcciones severas en marcha. Históricamente son OPORTUNIDADES de")
            note("compra para inversores a 10+ años. No vender por pánico.")

    # Curva de tipos
    if spread is not None:
        if spread > 0.5:
            bullet(f"Curva de tipos NORMAL (spread {spread:+.2f}%) — señal de crecimiento.",
                   style="#00ff41")
            note("La curva inclinada positivamente indica expectativas de crecimiento económico.")
        elif spread > -0.5:
            bullet(f"Curva de tipos PLANA (spread {spread:+.2f}%) — señal de transición.",
                   style="yellow")
            note("Curva plana: el mercado anticipa ralentización económica. Sin señal de")
            note("recesión inmediata. Impacto irrelevante para horizonte de 10+ años.")
        else:
            bullet(f"Curva INVERTIDA (spread {spread:+.2f}%) — señal histórica de recesión.",
                   style="#ff5555")
            note("La inversión de la curva ha precedido recesiones 12–18 meses después en el")
            note("pasado. Para un inversor indexado a LP, esto NO cambia la estrategia:")
            note("el mercado ha subido significativamente en períodos de 5–10 años incluso")
            note("iniciando con curvas invertidas.")

    # USD Index (impacto en EUR)
    if usdidx is not None:
        if usdidx > 106:
            bullet(f"USD FUERTE (DXY {usdidx:.1f}) — impacto negativo en activos USD→EUR.",
                   style="#ff5555")
            note("Los activos en USD pierden valor al convertir a EUR.")
            note("Los CSVs ya almacenan precios en EUR con la tasa de cambio diaria.")
        elif usdidx > 100:
            bullet(f"USD MODERADAMENTE FUERTE (DXY {usdidx:.1f}).", style="yellow")
            note("Ligero efecto divisa en activos USD. Diversificación geográfica protege.")
        else:
            bullet(f"USD DÉBIL (DXY {usdidx:.1f}) — favorable para activos USD en EUR.", style="#00ff41")
            note("La debilidad del USD añade rentabilidad al convertir posiciones USD a EUR.")

    # Tipos de interés largo plazo
    if us10y is not None:
        if us10y > 5.0:
            bullet(f"Tipos a LP ALTOS (10Y {us10y:.2f}%) — renta fija compite con bolsa.",
                   style="#ff5555")
            note("Con tipos altos, los bonos ofrecen rentabilidad atractiva. Sin embargo,")
            note("históricamente la bolsa supera a bonos en horizontes de 10+ años.")
        elif us10y > 3.5:
            bullet(f"Tipos a LP ELEVADOS (10Y {us10y:.2f}%) — entorno restrictivo.", style="yellow")
            note("Los tipos altos encarecen el crédito empresarial y pueden frenar el crecimiento.")
        else:
            bullet(f"Tipos a LP BAJOS (10Y {us10y:.2f}%) — favorable para renta variable.",
                   style="#00ff41")
            note("Entorno de tipos bajos impulsa la valoración de activos de riesgo.")

    # Oro
    if gold1m is not None and abs(gold1m) > 3:
        if gold1m > 3:
            bullet(f"Oro subiendo fuerte (+{gold1m:.1f}% 1M) — búsqueda de refugio activa.",
                   style="yellow")
            note("El oro como refugio indica incertidumbre institucional. No cambia la")
            note("estrategia indexada, pero puede indicar mayor volatilidad próxima.")
        else:
            bullet(f"Oro cayendo ({gold1m:.1f}% 1M) — apetito por activos de riesgo.", style="#00ff41")

    # S&P 500 tendencia
    if sp1m is not None:
        if sp1m < -10:
            bullet(f"S&P 500 en corrección fuerte ({sp1m:+.1f}% 1M).", style="#ff5555")
            note("Las correcciones >10% son OPORTUNIDADES históricas. El mercado ha")
            note("recuperado el 100% de las correcciones en un horizonte de 5–7 años.")
        elif sp1m < -5:
            bullet(f"S&P 500 con corrección moderada ({sp1m:+.1f}% 1M).", style="yellow")
            note("Corrección dentro de la normalidad histórica (~5 al año). DCA útil.")

    # EUR/USD
    if eurusd is not None:
        eurusd_note = None
        if eurusd < 1.03:
            eurusd_note = (f"EUR/USD muy bajo ({eurusd:.4f}) — el EUR débil amplifica retornos USD.",
                           "#00ff41")
        elif eurusd > 1.15:
            eurusd_note = (f"EUR fuerte ({eurusd:.4f}) — penaliza conversión activos USD→EUR.",
                           "yellow")
        if eurusd_note:
            bullet(eurusd_note[0], style=eurusd_note[1])

    # ── Bloque IA / Data Centers / Energía digital ─────────────────────────────
    ia_signals = [x for x in [sox1m, xlu1m, gas1m] if x is not None]
    if ia_signals:
        lines.append(Text(""))
        lines.append(Text("  ── TESIS IA · DATA CENTERS · ENERGÍA ──", style="cyan bold"))

        # SOX — indicador adelantado del ciclo de capex en IA
        if sox1m is not None:
            if sox1m > 5:
                bullet(f"Semiconductores (SOX) subiendo fuerte (+{sox1m:.1f}% 1M) — "
                       "ciclo de capex IA activo.", style="#00ff41")
                note("Las grandes tecnológicas están invirtiendo en infraestructura de IA.")
                note("En 12–24 meses esto se traduce en mayor demanda eléctrica. Favorable")
                note("para uranio y nuclear como fuente de energía base 24/7.")
            elif sox1m > 0:
                bullet(f"Semiconductores (SOX) +{sox1m:.1f}% 1M — capex IA en marcha.",
                       style="#00ff41")
            elif sox1m > -10:
                bullet(f"Semiconductores (SOX) {sox1m:.1f}% 1M — corrección técnica.",
                       style="yellow")
                note("Pausa en el ciclo IA, no cambio de tendencia estructural. La demanda")
                note("energética a 10+ años no depende de correcciones trimestrales.")
            else:
                bullet(f"Semiconductores (SOX) {sox1m:.1f}% 1M — contracción del sector.",
                       style="#ff5555")
                note("Reducción del capex en chips. Podría ralentizar el crecimiento de")
                note("data centers a corto plazo. Tesis energética intacta a largo plazo.")

        # XLU — utilities firmando PPAs con hyperscalers
        if xlu1m is not None:
            if xlu1m > 3:
                bullet(f"Utilities EEUU (XLU) +{xlu1m:.1f}% 1M — el mercado descuenta "
                       "contratos con data centers.", style="#00ff41")
                note("Las eléctricas suben cuando firman PPAs (Power Purchase Agreements)")
                note("con Microsoft, Google o Amazon. Señal de que la demanda energética")
                note("de IA se está materializando en contratos reales.")
            elif xlu1m < -5:
                bullet(f"Utilities EEUU (XLU) {xlu1m:.1f}% 1M — presión por tipos altos.",
                       style="yellow")
                note("Las utilities caen cuando los tipos de interés suben (compiten con")
                note("la renta fija). No implica menor demanda de data centers.")

        # Gas natural — presión eléctrica a corto plazo
        if gas1m is not None:
            if gas1m > 10:
                bullet(f"Gas Natural +{gas1m:.1f}% 1M — presión en la generación eléctrica.",
                       style="yellow")
                note("El gas sube cuando la demanda eléctrica supera la capacidad base.")
                note("Refuerza la tesis nuclear: se necesita energía base sin emisiones y")
                note("sin volatilidad de precio. Favorece activos relacionados con energía nuclear.")
            elif gas1m < -10:
                bullet(f"Gas Natural {gas1m:.1f}% 1M — alivio en costes de generación.",
                       style="#00ff41")
                note("Gas barato reduce el coste marginal de la electricidad para data")
                note("centers a corto plazo. No altera la tesis estructural nuclear.")

        # Uranio vía Cameco (proxy del precio spot; UX=F no disponible en Yahoo)
        if uranium is not None:
            if uranium > 55:
                bullet(f"Cameco (CCJ) ${uranium:.1f} — proxy uranio en zona alta.",
                       style="#00ff41")
                note("Cameco es el mayor productor mundial de uranio. Su cotización")
                note("refleja expectativas de nuevos contratos con utilities nucleares.")
            elif uranium > 35:
                bullet(f"Cameco (CCJ) ${uranium:.1f} — proxy uranio en rango medio.",
                       style="#00ff41")
            else:
                bullet(f"Cameco (CCJ) ${uranium:.1f} — proxy uranio deprimido.",
                       style="yellow")
                note("Valoraciones bajas de productores suelen preceder ciclos alcistas.")
                note("El ciclo del uranio tarda 3–5 años en materializarse en precio.")

        # Cobre como proxy de electrificación global
        if copper1m is not None and abs(copper1m) > 4:
            if copper1m > 4:
                bullet(f"Cobre +{copper1m:.1f}% 1M — electrificación global acelerada.",
                       style="#00ff41")
                note("El cobre es el metal de la electrificación: cables, transformadores,")
                note("centros de datos, vehículos eléctricos. Subidas fuertes indican")
                note("que la demanda industrial de infraestructura eléctrica es real.")
            else:
                bullet(f"Cobre {copper1m:.1f}% 1M — ralentización industrial.",
                       style="yellow")

    # Mensaje final invariable para inversor LP
    lines.append(Text(""))
    conclusion = Text()
    conclusion.append("  ✓  ESTRATEGIA RECOMENDADA A 10+ AÑOS: ", style="#00ff41 bold")
    conclusion.append(
        "MANTENER posiciones y DCA periódico.", style="bright_white bold")
    lines.append(conclusion)
    lines.append(Text(
        "     Los indicadores macro a corto plazo NO deben modificar una estrategia de",
        style="grey70"))
    lines.append(Text(
        "     inversión indexada a largo plazo. El crecimiento económico secular premia",
        style="grey70"))
    lines.append(Text(
        "     la paciencia. Sigue el plan de inversión y aprovecha cada corrección.",
        style="grey70"))
    lines.append(Text(""))

    return lines


class AddTransactionScreen(ModalScreen):
    """Formulario modal para añadir una transacción al portfolio."""

    CSS = """
    AddTransactionScreen {
        align: center middle;
    }
    #atx-dialog {
        width: 72;
        height: auto;
        background: #001a00;
        border: solid #00ff41;
        padding: 1 2;
    }
    #atx-dialog Label {
        color: #007a1f;
        margin-top: 1;
    }
    #atx-dialog Input {
        background: #002800;
        border: solid #005e17;
        color: #00ff41;
        width: 100%;
    }
    #atx-dialog Input:focus {
        border: solid #00ff41;
    }
    #atx-btns {
        margin-top: 1;
        height: 3;
        align: right middle;
    }
    #atx-btns Button {
        margin-left: 1;
    }
    #atx-error {
        color: #ff5555;
        height: 1;
    }
    """

    def __init__(self, tickers: list, prefill: dict = None):
        super().__init__()
        self.tickers = tickers
        self.prefill = prefill or {}

    def compose(self) -> ComposeResult:
        pf        = self.prefill
        today_str = str(date.today())
        is_edit   = bool(pf)
        title_lbl = "EDITAR TRANSACCIÓN" if is_edit else "AÑADIR TRANSACCIÓN"
        nombre_line = f"[grey50]  {pf['nombre']}[/]" if pf.get("nombre") else ""
        with Container(id="atx-dialog"):
            yield Static(f"[bright_green bold]▸ {title_lbl}[/]  [grey50](Esc para cancelar)[/]")
            if nombre_line:
                yield Static(nombre_line)
            yield Static("", id="atx-error")
            yield Label("Ticker (ISIN o código):")
            yield Input(value=pf.get("ticker",""), placeholder="ej: GB00B15KXQ89", id="atx-ticker")
            yield Label("Tipo:")
            yield Input(value=pf.get("tipo","compra"), placeholder="compra  /  venta", id="atx-tipo")
            yield Label("Participaciones:")
            yield Input(value=str(pf["participaciones"]) if "participaciones" in pf else "",
                        placeholder="0.000000", id="atx-partic")
            yield Label("Precio unitario (divisa del activo):")
            yield Input(value=str(pf["precio"]) if "precio" in pf else "",
                        placeholder="0.0000", id="atx-precio")
            yield Label("Comisión (€):")
            yield Input(value=str(pf.get("comision","0.00")), placeholder="0.00", id="atx-comis")
            yield Label("Fecha (YYYY-MM-DD):")
            yield Input(value=pf.get("fecha", today_str), id="atx-fecha")
            yield Label("Nota (opcional):")
            yield Input(value=pf.get("nota",""), placeholder="", id="atx-nota")
            with Horizontal(id="atx-btns"):
                yield Button("✓ Guardar", variant="success",  id="atx-save")
                yield Button("✗ Cancelar", variant="error",   id="atx-cancel")

    def _show_error(self, msg: str):
        try:
            self.query_one("#atx-error", Static).update(f"[bright_red]⚠ {msg}[/]")
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "atx-cancel":
            self.dismiss(None)
            return
        if event.button.id != "atx-save":
            return

        ticker   = self.query_one("#atx-ticker", Input).value.strip().upper()
        tipo     = self.query_one("#atx-tipo",   Input).value.strip().lower()
        partic_s = self.query_one("#atx-partic", Input).value.strip().replace(",",".")
        precio_s = self.query_one("#atx-precio", Input).value.strip().replace(",",".")
        comis_s  = self.query_one("#atx-comis",  Input).value.strip().replace(",",".")
        fecha    = self.query_one("#atx-fecha",  Input).value.strip()
        nota     = self.query_one("#atx-nota",   Input).value.strip()

        if not ticker:
            self._show_error("El ticker no puede estar vacío."); return
        if tipo not in ("compra", "venta"):
            self._show_error("El tipo debe ser 'compra' o 'venta'."); return
        try:
            partic = float(partic_s)
            precio = float(precio_s)
            comis  = float(comis_s)
        except ValueError:
            self._show_error("Revisa los valores numéricos (usa punto como decimal)."); return
        if partic <= 0:
            self._show_error("Las participaciones deben ser > 0."); return
        if precio <= 0:
            self._show_error("El precio debe ser > 0."); return
        try:
            datetime.strptime(fecha, "%Y-%m-%d")
        except ValueError:
            self._show_error("Fecha inválida — usa el formato YYYY-MM-DD."); return

        if ticker not in self.tickers:
            self._show_error(f"'{ticker}' no encontrado en el portfolio."); return

        self.dismiss({
            "ticker": ticker, "tipo": tipo,
            "participaciones": partic, "precio": precio,
            "comision": comis, "fecha": fecha, "nota": nota,
        })

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)

# ══════════════════════════════════════════════════════════════════════════════
# MODAL: SELECCIONAR TRANSACCIÓN
# ══════════════════════════════════════════════════════════════════════════════
class SelectTransactionScreen(ModalScreen):
    """Buscador de transacciones con filtro en tiempo real y navegación ↑↓ + Enter."""

    CSS = """
    SelectTransactionScreen {
        align: center middle;
    }
    SelectTransactionScreen #atx-dialog {
        width: 92;
        height: auto;
        background: #001a00;
        border: solid #00ff41;
        padding: 1 2;
    }
    SelectTransactionScreen #atx-dialog Input {
        background: #002800;
        border: solid #005e17;
        color: #00ff41;
        width: 100%;
        margin-bottom: 1;
    }
    SelectTransactionScreen #atx-dialog Input:focus {
        border: solid #00ff41;
    }
    SelectTransactionScreen #atx-error {
        color: #ff5555;
        height: 1;
    }
    SelectTransactionScreen #sel-list {
        height: auto;
        margin-top: 0;
    }
    """

    _WINDOW = 12  # filas visibles máximas

    def __init__(self, assets: list, title: str = "SELECCIONAR TRANSACCIÓN"):
        super().__init__()
        self._title = title
        # Lista plana ordenada por fecha: (ticker, nombre, local_idx, tx_dict)
        self.txs: list = []
        for a in assets:
            nombre = (a.get("nombre") or a.get("ticker", ""))[:28]
            for i, tx in enumerate(a.get("txs") or []):
                self.txs.append((a["ticker"], nombre, i, dict(tx)))
        self.txs.sort(key=lambda x: str(x[3].get("fecha", "")))
        self._filtered: list = list(self.txs)
        self._cursor: int = 0

    def compose(self) -> ComposeResult:
        total = len(self.txs)
        hint = f"[grey50]{total} transacción(es) · ↑↓ navegar · Enter seleccionar · Esc cancelar[/]"
        with Container(id="atx-dialog"):
            yield Static(f"[bright_green bold]▸ {self._title}[/]")
            yield Static(hint)
            yield Input(placeholder="Buscar por ticker, nombre, fecha, tipo, nota…", id="sel-search")
            yield Static("", id="sel-list")
            yield Static("", id="atx-error")

    def on_mount(self) -> None:
        self._render_list()
        self.query_one("#sel-search", Input).focus()

    # ── Renderizado ───────────────────────────────────────────────────────────
    def _render_list(self) -> None:
        widget = self.query_one("#sel-list", Static)
        if not self._filtered:
            widget.update("[grey50]  Sin resultados.[/]")
            return

        total = len(self._filtered)
        cur   = self._cursor
        ws    = self._WINDOW
        half  = ws // 2
        start = max(0, cur - half)
        end   = min(total, start + ws)
        start = max(0, end - ws)   # reajusta si end fue recortado

        rows = []
        if start > 0:
            rows.append(f"[grey50]  ↑ {start} más arriba…[/]")

        for i in range(start, end):
            ticker, nombre, _li, tx = self._filtered[i]
            sel    = (i == cur)
            prefix = "[bright_white bold]▶[/] " if sel else "  "
            tc     = "[bright_green]C[/]" if tx.get("tipo") == "compra" else "[bright_red]V[/]"
            nota_s = f" [grey50]{tx['nota']}[/]" if tx.get("nota") else ""
            partes = float(tx.get("participaciones", 0))
            precio = float(tx.get("precio", 0))
            t_col  = "bright_white" if sel else "grey80"
            n_col  = "white"        if sel else "grey60"
            rows.append(
                f"{prefix}[{t_col}]{ticker:<14s}[/] [{n_col}]{nombre:<28s}[/] "
                f"[cyan]{tx.get('fecha','?')}[/] {tc} "
                f"[white]{partes:.4f}×{precio:.4f}[/]{nota_s}"
            )

        if end < total:
            rows.append(f"[grey50]  ↓ {total - end} más abajo…[/]")

        widget.update("\n".join(rows))

    # ── Filtro en tiempo real ─────────────────────────────────────────────────
    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "sel-search":
            return
        q = event.value.strip().lower()
        if not q:
            self._filtered = list(self.txs)
        else:
            self._filtered = [
                (ticker, nombre, li, tx)
                for ticker, nombre, li, tx in self.txs
                if q in ticker.lower()
                or q in nombre.lower()
                or q in str(tx.get("fecha", "")).lower()
                or q in str(tx.get("tipo", "")).lower()
                or q in str(tx.get("nota", "")).lower()
            ]
        self._cursor = 0
        self._render_list()
        try: self.query_one("#atx-error", Static).update("")
        except Exception: pass

    # ── Enter en el buscador → confirmar ─────────────────────────────────────
    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._confirm()

    # ── Navegación por teclado ────────────────────────────────────────────────
    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
        elif event.key == "up":
            if self._filtered:
                self._cursor = max(0, self._cursor - 1)
                self._render_list()
            event.prevent_default()
        elif event.key == "down":
            if self._filtered:
                self._cursor = min(len(self._filtered) - 1, self._cursor + 1)
                self._render_list()
            event.prevent_default()

    def _confirm(self) -> None:
        if not self._filtered:
            try: self.query_one("#atx-error", Static).update("[bright_red]⚠ Sin resultados que seleccionar.[/]")
            except Exception: pass
            return
        ticker, _nombre, local_idx, tx = self._filtered[self._cursor]
        self.dismiss((ticker, local_idx, tx))


# ══════════════════════════════════════════════════════════════════════════════
# MODAL: CONFIRMAR BORRADO
# ══════════════════════════════════════════════════════════════════════════════
class ConfirmDeleteScreen(ModalScreen):
    """Muestra los detalles de la transacción y pide confirmación de borrado."""

    def __init__(self, ticker: str, tx: dict, nombre: str = ""):
        super().__init__()
        self._ticker = ticker
        self._nombre = nombre
        self._tx     = tx

    def compose(self) -> ComposeResult:
        tx = self._tx
        partic = float(tx.get("participaciones", 0))
        precio = float(tx.get("precio", 0))
        comis  = float(tx.get("comision", 0))
        nota_s = tx.get("nota","") or "—"
        nombre_s = f"  [grey50]{self._nombre}[/]\n" if self._nombre else ""
        detail = (
            f"\n  Activo : [white]{self._ticker}[/]\n"
            f"{nombre_s}"
            f"  Fecha  : [cyan]{tx.get('fecha','?')}[/]   "
            f"Tipo: [{'bright_green' if tx.get('tipo')=='compra' else 'bright_red'}]"
            f"{tx.get('tipo','?')}[/]\n"
            f"  Partic.: [white]{partic:.6f}[/]   "
            f"Precio: [white]{precio:.4f}[/]   "
            f"Comis.: [white]{comis:.2f}[/]\n"
            f"  Nota   : [grey70]{nota_s}[/]\n"
        )
        with Container(id="atx-dialog"):
            yield Static("[bright_red bold]▸ CONFIRMAR BORRADO[/]  [grey50](Esc para cancelar)[/]")
            yield Static(detail)
            yield Static("[yellow]¿Borrar esta transacción? Esta acción no se puede deshacer.[/]")
            with Horizontal(id="atx-btns"):
                yield Button("✗ Sí, borrar",  variant="error",   id="del-yes")
                yield Button("← Cancelar",    variant="success", id="del-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "del-yes": self.dismiss(True)
        else: self.dismiss(False)

    def on_key(self, event) -> None:
        if event.key == "escape": self.dismiss(False)


# ══════════════════════════════════════════════════════════════════════════════
# CSS
# ══════════════════════════════════════════════════════════════════════════════
APP_CSS = """
Screen               { background: #001200; }
Header               { background: #001a00; color: #00ff41; }
Footer               { background: #001a00; color: #00ff41; }
TabbedContent        { background: #001200; height: 1fr; }
TabPane              { padding: 1 2; background: #001200; }
Tabs                 { background: #001a00; border-bottom: solid #005e17; }
Tab                  { color: #007a1f; padding: 0 2; }
Tab.-active          { color: #00ff41; text-style: bold; background: #001200; }
Static               { background: #001200; }
ScrollableContainer  { background: #001200; }
"""

# ══════════════════════════════════════════════════════════════════════════════
# APP
# ══════════════════════════════════════════════════════════════════════════════
class PortfolioApp(App):
    CSS                    = APP_CSS
    TITLE                  = "PORTFOLIO DASHBOARD"
    ENABLE_COMMAND_PALETTE = False   # temas built-in no funcionan con CSS personalizado
    BINDINGS = [
        Binding("q", "quit",                   "Salir"),
        Binding("r", "reload",                 "Recargar"),
        Binding("p", "toggle_privacy",         "🔒 Privado"),
        Binding("a", "add_transaction",        "+ Transac."),
        Binding("e", "edit_transaction",       "✎ Editar tx"),
        Binding("d", "delete_transaction",     "✗ Borrar tx"),
        Binding("t", "toggle_hist_range",      "Rango hist.",  show=False),
        Binding("f", "toggle_pos_filter",      "Filtro",       show=False),
        Binding("1", "goto('resumen')",        "Resumen",      show=False),
        Binding("2", "goto('posiciones')",     "Posiciones",   show=False),
        Binding("3", "goto('historico')",      "Histórico",    show=False),
        Binding("4", "goto('transacciones')",  "Transacciones",show=False),
        Binding("5", "goto('tir')",            "TIR",          show=False),
        Binding("6", "goto('metricas')",       "Métricas",     show=False),
        Binding("7", "goto('costes')",         "Costes",       show=False),
        Binding("8", "goto('benchmark')",      "Benchmark",    show=False),
        Binding("9", "goto('macro')",          "Macro",        show=False),
    ]

    def __init__(self, yaml_path, hist_dir, use_live):
        super().__init__()
        self.yaml_path   = yaml_path
        self.hist_dir    = hist_dir
        self.use_live    = use_live
        self.p           = None
        self.err         = None
        self.privacy     = False      # ← modo presentación / ofuscación
        self._hist_range = "TODO"     # ← rango activo en ③ HISTÓRICO (tecla T)
        self._pos_filter = None       # ← filtro activo en ② POSICIONES (tecla F)
        self._load()

    # ── helper de ofuscación ─────────────────────────────────────────────────
    def _m(self, text):
        """Devuelve MASK si el modo privado está activo, o el texto original."""
        return MASK if self.privacy else text

    def _load(self):
        try:
            self.p   = process(load_yaml(self.yaml_path), self.hist_dir, self.use_live)
            self.err = None
        except Exception as e:
            self.err = str(e)

    def _refresh_subtitle(self):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.sub_title = (ts + "  🔒 MODO PRIVADO") if self.privacy else ts

    def on_mount(self):
        if self.p:
            self.title = self.p["meta"].get("nombre","PORTFOLIO").upper()
            self._refresh_subtitle()

    # ── COMPOSE ──────────────────────────────────────────────────────────────
    def compose(self) -> ComposeResult:
        yield Header()
        if self.err:
            yield Static(f"[red bold]ERROR:[/] [white]{self.err}[/]\n\n"
                         f"[grey50]Revisa el YAML y pulsa [bright_yellow]R[/] para reintentar.[/]")
        else:
            with TabbedContent(initial="resumen"):
                with TabPane("① RESUMEN",       id="resumen"):
                    with ScrollableContainer():
                        yield Static(self._render_resumen(),       id="w-resumen")
                with TabPane("② POSICIONES",    id="posiciones"):
                    with ScrollableContainer():
                        yield Static(self._render_posiciones(),    id="w-posiciones")
                with TabPane("③ HISTÓRICO",     id="historico"):
                    with ScrollableContainer():
                        yield Static(self._render_historico(),     id="w-historico")
                with TabPane("④ TRANSACCIONES", id="transacciones"):
                    with ScrollableContainer():
                        yield Static(self._render_transacciones(), id="w-transacciones")
                with TabPane("⑤ TIR / XIRR",   id="tir"):
                    with ScrollableContainer():
                        yield Static(self._render_tir(),           id="w-tir")
                with TabPane("⑥ MÉTRICAS",      id="metricas"):
                    with ScrollableContainer():
                        yield Static(self._render_metricas(),      id="w-metricas")
                with TabPane("⑦ COSTES",        id="costes"):
                    with ScrollableContainer():
                        yield Static(self._render_costes(),        id="w-costes")
                with TabPane("⑧ BENCHMARK",     id="benchmark"):
                    with ScrollableContainer():
                        yield Static(self._render_benchmark(),     id="w-benchmark")
                with TabPane("⑨ MACRO",         id="macro"):
                    with ScrollableContainer():
                        yield Static(self._render_macro(),         id="w-macro")
        yield Footer()

    # ── VISTA 1: RESUMEN ─────────────────────────────────────────────────────
    def _render_resumen(self):
        p   = self.p
        col = gc(p["total_gain"])

        # ── KPIs ──
        kpi = Table(box=rbox.SIMPLE, show_header=False, expand=True,
                    border_style="#005e17", style="on #001200", padding=(0,3))
        kpi.add_column("lbl",  style="grey62",  width=18)
        kpi.add_column("val",  justify="right", width=18)
        kpi.add_column("lbl2", style="grey62",  width=18)
        kpi.add_column("val2", justify="right", width=18)
        kpi.add_column("lbl3", style="grey62",  width=18)
        kpi.add_column("val3", justify="right", width=18)
        kpi.add_column("lbl4", style="grey62",  width=14)
        kpi.add_column("val4", justify="right", width=12)

        total_val_str  = self._m("€{:>12,.2f}".format(p["total_val"]))
        total_inv_str  = self._m("€{:>12,.2f}".format(p["total_inv"]))
        total_gain_str = self._m(fe(p["total_gain"]))

        fee_str      = self._m("€{:,.2f}".format(p["total_annual_fee"]))
        fee_pct      = p["total_annual_fee"] / p["total_val"] * 100 if p["total_val"] else 0
        fee_pct_str  = "{:.3f}%".format(fee_pct)

        # FX row: mostrar tipos de cambio activos
        fx_parts = []
        for ccy, rate in sorted((p.get("fx_eur") or {}).items()):
            fx_parts.append("1 {} = {:.4f} €".format(ccy, rate))
        fx_str = "   ".join(fx_parts) if fx_parts else "solo EUR"

        kpi.add_row(
            "VALOR TOTAL",    Text(total_val_str,         style="bright_green bold"),
            "INVERTIDO",      Text(total_inv_str,         style="grey70"),
            "GANANCIA/PÉRD.", Text(total_gain_str,        style="{} bold".format(col)),
            "RENTABILIDAD",   Text(fp(p["total_pct"]),    style="{} bold".format(col)),
        )
        kpi.add_row(
            "GASTOS TER/AÑO", Text(fee_str,               style="yellow"),
            "TER MEDIO",      Text(fee_pct_str,           style="yellow"),
            "TIPO DE CAMBIO", Text(fx_str,                style="grey62"),
            "",               Text(""),
        )

        # ── Posiciones ──
        COLORS = ["bright_green","cyan","green","bright_cyan","white","grey70"]
        pos = Table(box=rbox.SIMPLE_HEAD, expand=True,
                    border_style="#003300", style="on #001200",
                    header_style="bright_green bold")
        for h,j in [("NOMBRE","left"),("TIPO","left"),("ISIN","left"),("DIV","left"),
                    ("PRECIO","right"),("ACTUALIZ.","left"),("PARTICIPAC.","right"),
                    ("COSTE Ø","right"),("INVERTIDO","right"),("VALOR ACT.","right"),
                    ("G/P €","right"),("G/P %","right"),("TIR","right")]:
            pos.add_column(h, justify=j, no_wrap=True)

        for i, a in enumerate(p["assets"]):
            gc_      = gc(a["gain"])
            tir_str  = fp(a["tir"]*100) if a["tir"] is not None else "—"
            precio_s = self._m("€{:,.3f}".format(a["cur_price"]))
            cost_s   = self._m("€{:,.3f}".format(a["avg_cost"]))
            inv_s    = self._m("€{:,.2f}".format(a["total_inv"]))
            val_s    = self._m("€{:,.2f}".format(a["cur_val"]))
            gain_s   = self._m(fe(a["gain"]))
            nombre_s = a["nombre"][:34] if len(a["nombre"]) > 34 else a["nombre"]
            pos.add_row(
                Text(nombre_s,      style="{} bold".format(COLORS[i%len(COLORS)])),
                Text(a["tipo"],     style="grey62"),
                Text(a["isin"],     style="grey50"),
                Text(a["divisa"],   style="grey50"),
                precio_s,
                price_date_text(a.get("last_price_date")),
                "{:,.4f}".format(a["shares"]),
                cost_s,
                Text(inv_s,         style="grey70"),
                Text(val_s,         style="white bold"),
                Text(gain_s,        style=gc_),
                Text(fp(a["gain_pct"]), style=gc_),
                Text(tir_str,       style="{}".format(gc(a["tir"] or 0))),
            )

        # ── Barras de distribución ──
        alloc = Table(box=None, show_header=False, padding=(0,1), expand=False)
        alloc.add_column("ticker",   width=14)
        alloc.add_column("nombre",   width=24)
        alloc.add_column("taxon",    width=20)
        alloc.add_column("bar",      width=37)
        alloc.add_column("pct",      width=7,  justify="right")
        alloc.add_column("val",      width=14, justify="right")
        BAR_W = 35
        for i, a in enumerate(p["assets"]):
            pct    = a["cur_val"]/p["total_val"]*100 if p["total_val"] > 0 else 0
            c      = COLORS[i % len(COLORS)]
            filled = round(pct/100*BAR_W)
            bar    = Text("█"*filled, style=c) + Text("░"*(BAR_W-filled), style="grey23")
            val_s  = self._m("€{:,.2f}".format(a["cur_val"]))
            nom_s  = a["nombre"][:23] if len(a["nombre"]) > 23 else a["nombre"]
            tax_s  = a.get("taxonomia","")[:19] if len(a.get("taxonomia","")) > 19 else a.get("taxonomia","")
            alloc.add_row(
                Text(a["ticker"],   style="{} bold".format(c)),
                Text(nom_s,         style="grey62"),
                Text(tax_s,         style="grey50"),
                bar,
                Text("{:.1f}%".format(pct), style=c),
                Text(val_s,         style="white"),
            )

        return Group(
            Text("▸ KPIs GLOBALES", style="bright_green bold"),
            kpi,
            Text(""),
            Text("▸ POSICIONES", style="bright_green bold"),
            pos,
            Text(""),
            Text("▸ DISTRIBUCIÓN", style="bright_green bold"),
            alloc,
        )

    # ── VISTA 2: POSICIONES ──────────────────────────────────────────────────
    def _render_posiciones(self):
        items     = []
        all_assets = self.p["assets"]
        filt      = getattr(self, "_pos_filter", None)

        # Obtener taxonomías únicas (orden de aparición)
        taxonomies = []
        for a in all_assets:
            t = a.get("taxonomia") or ""
            if t and t not in taxonomies:
                taxonomies.append(t)

        # ── Barra de filtro ──
        flt_bar = Text("  Filtro: ", style="grey50")
        flt_bar.append(" TODOS " if filt is None else " TODOS ",
                       style="#4da6ff bold reverse" if filt is None else "grey42")
        for tax in taxonomies:
            active = (filt == tax)
            flt_bar.append("  {}  ".format(tax),
                           style="#4da6ff bold reverse" if active else "grey42")
        flt_bar.append("   [F] para cambiar", style="#7ec8e3 italic")
        items.append(flt_bar)

        # KPIs del subconjunto filtrado
        visible = [a for a in all_assets if filt is None or a.get("taxonomia") == filt]
        if filt is not None and visible:
            sub_val  = sum(a["cur_val"]   for a in visible)
            sub_inv  = sum(a["total_inv"] for a in visible)
            sub_gain = sum(a["gain"]      for a in visible)
            sub_pct  = sub_gain / sub_inv * 100 if sub_inv else 0
            pct_total = sub_val / self.p["total_val"] * 100 if self.p["total_val"] else 0
            kpi_line = Text("  ")
            kpi_line.append("{} activo{}".format(len(visible), "s" if len(visible) != 1 else ""),
                            style="#4da6ff")
            kpi_line.append("   Valor: ", style="grey50")
            kpi_line.append(self._m("€{:,.2f}".format(sub_val)), style="white bold")
            kpi_line.append("  ({:.1f}% del portfolio)".format(pct_total), style="grey50")
            kpi_line.append("   G/P: ", style="grey50")
            kpi_line.append("{} {}".format(self._m(fe(sub_gain)), fp(sub_pct)),
                            style="{} bold".format(gc(sub_gain)))
            items.append(kpi_line)

        items.append(Text(""))

        if not visible:
            items.append(Text("  Sin activos para la taxonomía «{}».".format(filt),
                               style="grey50"))
            return Group(*items)

        for a in visible:
            gc_   = gc(a["gain"])
            hst   = a.get("hst", {})
            tir_  = fp(a["tir"]*100) if a["tir"] is not None else "—"

            precio_s  = self._m("€{:,.4f}".format(a["cur_price"]))
            cost_s    = self._m("€{:,.4f}".format(a["avg_cost"]))
            inv_s     = self._m("€{:,.2f}".format(a["total_inv"]))
            val_s     = self._m("€{:,.2f}".format(a["cur_val"]))
            gain_fe   = self._m(fe(a["gain"]))
            gain_str  = "{} {}".format(gain_fe, fp(a["gain_pct"])) if not self.privacy else fp(a["gain_pct"])

            # ── Columna izquierda: métricas ──
            left = Table(box=rbox.SIMPLE, expand=False, show_header=False,
                         style="on #001200", border_style="#003300", padding=(0,1))
            left.add_column("campo", style="grey62",     width=17)
            left.add_column("valor", justify="right",    width=22, no_wrap=True)
            ter_pct = a.get("ter", 0) or 0
            ter_eur = a.get("annual_fee_eur", 0) or 0
            ter_str = ("{:.2f}%  →  {}/año".format(ter_pct * 100,
                        self._m("€{:,.0f}".format(ter_eur))) if ter_pct > 0 else "—")

            left.add_row("Precio actual",   Text(precio_s,                          style="white bold"))
            # Precio nativo (si la divisa no es EUR, mostrar el USD original + tipo de cambio)
            divisa    = a.get("divisa", "EUR")
            fx_rate   = a.get("fx_rate", 1.0)
            if divisa != "EUR" and fx_rate != 1.0:
                native = a.get("cur_price_native", 0)
                fx_info = "{:.4f} {}  ×  {:.4f} $/€".format(native, divisa, fx_rate)
                left.add_row("  precio origen", Text(fx_info,                       style="grey50"))
            left.add_row("Coste medio",     Text(cost_s,                            style="grey70"))
            left.add_row("Participaciones", Text("{:,.6f}".format(a["shares"]),     style="white"))
            left.add_row("Invertido",       Text(inv_s,                             style="grey70"))
            left.add_row("Valor actual",    Text(val_s,                             style="white bold"))
            left.add_row("Ganancia/Pérd.",  Text(gain_str,                          style=gc_))
            left.add_row("TIR (XIRR)",      Text(tir_, style="{} bold".format(gc(a["tir"] or 0))))
            left.add_row("TER anual",       Text(ter_str, style="yellow" if ter_pct > 0 else "grey50"))

            # ── Columna derecha: gráfico ASCII ──
            if hst.get("prices"):
                chart_lines = render_chart(hst["prices"], width=52, height=8,
                                           mask_axis=self.privacy)
                per1 = Text("")
                for lbl in ["1M","3M","6M","1A"]:
                    v = hst.get(lbl)
                    per1.append(" {}: ".format(lbl), style="grey50")
                    per1.append("{}".format(fp(v)), style="{} bold".format(gc(v or 0)))
                per2 = Text("")
                for lbl in ["3A","5A","10A"]:
                    v = hst.get(lbl)
                    if v is not None:
                        per2.append(" {}: ".format(lbl), style="grey50")
                        per2.append("{}".format(fp(v)), style="{} bold".format(gc(v or 0)))
                right = Group(*chart_lines, per1, per2)
            else:
                right = Text("  Sin datos históricos.", style="grey50")

            # ── Layout 2 columnas ──
            row = Table(box=rbox.SIMPLE, expand=True, style="on #001200",
                        border_style="#003300",
                        title="[bright_cyan bold]{}[/]  [grey50]{}[/]  [bright_yellow][{}][/]  "
                              "[grey42]ISIN: {}  Taxonomía: {}  Divisa: {}[/]".format(
                                  a["ticker"], a["nombre"], a["tipo"],
                                  a["isin"], a.get("taxonomia","—"), a["divisa"]),
                        title_justify="left")
            row.add_column("métricas", ratio=2)
            row.add_column("gráfico",  ratio=3)
            row.add_row(left, right)

            items.append(row)
            items.append(Text(""))

        return Group(*items)

    # ── VISTA 3: HISTÓRICO ───────────────────────────────────────────────────
    def _render_historico(self):
        items     = []
        today_iso = date.today().isoformat()
        rng       = getattr(self, "_hist_range", "TODO")

        # Cabecera con rango activo y ayuda
        rng_bar = Text("  Rango: ", style="grey50")
        for r in HIST_RANGES:
            if r == rng:
                rng_bar.append(f" {r} ", style="#4da6ff bold reverse")
            else:
                rng_bar.append(f" {r} ", style="grey42")
        rng_bar.append("   [T] para cambiar", style="#7ec8e3 italic")
        items.append(rng_bar)
        items.append(Text(""))

        for a in self.p["assets"]:
            hst = a.get("hst", {})
            hdr = Text("▸ {}  ".format(a["ticker"]), style="bright_green bold")
            hdr.append(a["nombre"], style="bright_green")
            items.append(hdr)

            if not hst.get("prices"):
                items.append(Text("  Sin datos históricos.", style="grey50"))
                items.append(Text(""))
                continue

            # Copia para no mutar el original; añade punto sintético si cur_price es más reciente
            prices = list(hst["prices"])
            dates  = list(hst["dates"])
            cur_price = a.get("cur_price", 0)
            synth = False
            if cur_price and cur_price > 0 and today_iso > dates[-1]:
                prices.append(cur_price)
                dates.append(today_iso)
                synth = True

            # Aplicar filtro de rango
            if rng != "TODO":
                _days_map = {"1M":30,"3M":90,"6M":180,"1A":365,"3A":1095}
                cutoff = (date.today()-timedelta(days=_days_map[rng])).isoformat()
                pairs  = [(d,p) for d,p in zip(dates, prices) if d >= cutoff]
                if len(pairs) >= 2:
                    dates  = [x[0] for x in pairs]
                    prices = [x[1] for x in pairs]
                else:
                    items.append(Text("  Sin datos suficientes para el rango {}.".format(rng),
                                      style="grey50"))
                    items.append(Text(""))
                    continue

            for line in render_chart(prices, width=65, height=10, mask_axis=self.privacy):
                items.append(line)

            # Etiquetas eje X — siempre incluir la fecha final
            if len(dates) > 1:
                d_line = Text("           ", style="grey50")
                n      = len(dates)
                step   = max(1, n // 6)
                idxs   = list(range(0, n, step))
                idxs[-1] = n - 1          # forzar última etiqueta = última fecha
                prev = 0
                for i in idxs:
                    pos = int(i * 65 / (n - 1))
                    gap = pos - prev
                    if gap > 0:
                        d_line.append(" " * gap)
                    d_line.append(dates[i][:7], style="grey50")
                    prev = pos + 7
                items.append(d_line)

            items.append(Text(""))

            per = Text("  ")
            for lbl in ["1M","3M","6M","1A"]:
                v = hst.get(lbl)
                per.append("{}: ".format(lbl), style="grey50")
                per.append("{}   ".format(fp(v)), style="{} bold".format(gc(v or 0)))
            items.append(per)

            per2 = Text("  ")
            for lbl in ["3A","5A","10A"]:
                v = hst.get(lbl)
                if v is not None:
                    per2.append("{}: ".format(lbl), style="grey50")
                    per2.append("{}   ".format(fp(v)), style="{} bold".format(gc(v or 0)))
            if per2.plain.strip():
                items.append(per2)

            p_min_s = self._m("{:.3f}".format(min(prices)))
            p_max_s = self._m("{:.3f}".format(max(prices)))
            synth_tag = "  ★ precio actual" if synth else ""
            items.append(Text(
                "  Min: {}   Max: {}   Registros: {}   Desde: {}   Hasta: {}{}".format(
                    p_min_s, p_max_s, len(prices), dates[0], dates[-1], synth_tag),
                style="grey50"
            ))
            items.append(Text(""))

        return Group(*items)

    # ── VISTA 4: TRANSACCIONES ───────────────────────────────────────────────
    def _render_transacciones(self):
        items = []
        for a in self.p["assets"]:
            txs = sorted(a["txs"], key=lambda t: str(t.get("fecha","")), reverse=True)
            hdr = Text("▸ {}  ".format(a["ticker"]), style="bright_green bold")
            hdr.append(a["nombre"], style="bright_green")
            items.append(hdr)

            if not txs:
                items.append(Text("  Sin transacciones.", style="grey50"))
                items.append(Text(""))
                continue

            t = Table(box=rbox.SIMPLE_HEAD, expand=False,
                      border_style="#003300", style="on #001200",
                      header_style="bright_green bold")
            t.add_column("FECHA",       width=13)
            t.add_column("TIPO",        width=11)
            t.add_column("PARTICIPAC.", justify="right", width=16)
            t.add_column("PRECIO",      justify="right", width=13)
            t.add_column("COMISIÓN",    justify="right", width=11)
            t.add_column("TOTAL",       justify="right", width=14)

            total_inv = 0.0
            for tx in txs:
                tipo   = tx.get("tipo","?")
                c      = "bright_green" if tipo=="compra" else "bright_red"
                sym    = "▲" if tipo=="compra" else "▼"
                partic = float(tx.get("participaciones",0))
                precio = float(tx.get("precio",0))
                comis  = float(tx.get("comision",0))
                total  = partic * precio
                if tipo == "compra": total_inv += total + comis
                t.add_row(
                    str(tx.get("fecha","")),
                    Text("{} {}".format(sym, tipo),        style=c),
                    Text("{:,.6f}".format(partic),          style="white"),
                    Text(self._m("€{:,.3f}".format(precio)),style="white"),
                    Text(self._m("€{:,.2f}".format(comis)), style="grey50"),
                    Text(self._m("€{:,.2f}".format(total)), style=c),
                )

            items.append(t)
            inv_s  = self._m("€{:,.2f}".format(total_inv))
            cost_s = self._m("€{:,.4f}".format(a["avg_cost"]))
            items.append(Text(
                "  Total compras: {}   Participaciones netas: {:,.6f}   Coste medio: {}".format(
                    inv_s, a["shares"], cost_s),
                style="grey70"
            ))
            items.append(Text(""))

        return Group(*items)

    # ── VISTA 5: TIR ─────────────────────────────────────────────────────────
    def _render_tir(self):
        p     = self.p
        BAR_W = 30
        COLORS = ["bright_green","cyan","green","bright_cyan","white","grey70"]

        tbl = Table(box=rbox.SIMPLE_HEAD, expand=False,
                    border_style="#003300", style="on #001200",
                    header_style="bright_green bold")
        tbl.add_column("ACTIVO",        width=16)
        tbl.add_column("NOMBRE",        width=28)
        tbl.add_column("TIR ANUAL",     justify="right", width=12)
        tbl.add_column("BARRA VISUAL",  width=BAR_W+2)
        tbl.add_column("CLASIFICACIÓN", width=26)

        for i, a in enumerate(p["assets"]):
            tir    = a["tir"]
            col    = COLORS[i % len(COLORS)]
            nom_s  = a["nombre"][:27] if len(a["nombre"]) > 27 else a["nombre"]

            if tir is None:
                # Fallback: retorno simple acumulado + días cuando XIRR no converge
                txs  = [tx for tx in a["txs"] if tx.get("tipo") == "compra"]
                if txs and a["total_inv"] > 0:
                    first_date = min(datetime.strptime(str(tx["fecha"]), "%Y-%m-%d").date()
                                     for tx in txs)
                    days = (date.today() - first_date).days or 1
                    ret  = (a["cur_val"] + a["proceeds"] - a["total_inv"]) / a["total_inv"] * 100
                    ret_s   = self._m("{:+.1f}%".format(ret))
                    clasif  = Text("⚠ ret. simple {ret} ({d}d) — período corto".format(
                                   ret=ret_s, d=days), style="yellow")
                    bar     = Text("░" * BAR_W, style="grey23")
                    tir_txt = Text("—", style="grey50")
                else:
                    clasif  = Text("Sin transacciones", style="grey50")
                    bar     = Text("░" * BAR_W, style="grey23")
                    tir_txt = Text("—", style="grey50")
                tbl.add_row(
                    Text(a["ticker"][:15], style="{} bold".format(col)),
                    Text(nom_s,            style="grey62"),
                    tir_txt, bar, clasif,
                )
            else:
                pct    = tir * 100
                c      = "bright_green" if pct >= 0 else "bright_red"
                filled = min(BAR_W, abs(int(pct/20*BAR_W)))
                bar    = Text("▓"*filled, style=c) + Text("░"*(BAR_W-filled), style="grey23")
                clasif = ("🔴 Pérdida"       if pct < 0  else
                          "🟡 Bajo inflación" if pct < 3  else
                          "🟢 Moderado"       if pct < 7  else
                          "🟢 Bueno"          if pct < 15 else "⭐ Excelente")
                tbl.add_row(
                    Text(a["ticker"][:15], style="{} bold".format(col)),
                    Text(nom_s,            style="grey62"),
                    Text(fp(pct),          style="{} bold".format(c)),
                    bar,
                    Text(clasif,           style=c),
                )

        guide = Table(box=None, show_header=False, padding=(0,2))
        guide.add_column("rng",  width=10)
        guide.add_column("desc", style="grey70")
        guide.add_row(Text("< 0%",    style="bright_red bold"),   "Pérdida real")
        guide.add_row(Text("0 – 3%",  style="grey70"),            "Por debajo de la inflación")
        guide.add_row(Text("3 – 7%",  style="white"),             "Rentabilidad moderada")
        guide.add_row(Text("7 – 15%", style="bright_green"),      "Buena rentabilidad")
        guide.add_row(Text("> 15%",   style="bright_green bold"), "Rentabilidad excelente")

        return Group(
            Text("▸ TASA INTERNA DE RETORNO ANUALIZADA (XIRR)", style="bright_green bold"),
            Text("  Anualiza el rendimiento ponderando el momento exacto de cada flujo de caja.",
                 style="grey50"),
            Text("  ⚠ indica retorno simple cuando el período es muy corto o la caída > 100% anual.",
                 style="grey50"),
            Text(""),
            tbl,
            Text(""),
            Text("▸ GUÍA DE INTERPRETACIÓN", style="bright_green bold"),
            guide,
        )

    # ── VISTA 6: MÉTRICAS ────────────────────────────────────────────────────
    def _render_metricas(self):
        p      = self.p
        assets = p["assets"]
        COLORS = ["bright_green","cyan","green","bright_cyan","white","grey70"]

        # ── Tabla 1: Rendimiento ajustado por riesgo ──
        t1 = Table(box=rbox.SIMPLE_HEAD, expand=False,
                   border_style="#003300", style="on #001200",
                   header_style="bright_green bold")
        t1.add_column("ACTIVO",   width=16)
        t1.add_column("NOMBRE",   width=24)
        t1.add_column("SHARPE",   justify="right", width=9)
        t1.add_column("SORTINO",  justify="right", width=9)
        t1.add_column("BETA",     justify="right", width=8)
        t1.add_column("DÍAS+",    justify="right", width=8)
        t1.add_column("RIESGO",   width=16)

        # ── Tabla 2: Exposición al riesgo ──
        t2 = Table(box=rbox.SIMPLE_HEAD, expand=False,
                   border_style="#003300", style="on #001200",
                   header_style="bright_green bold")
        t2.add_column("ACTIVO",     width=16)
        t2.add_column("NOMBRE",     width=24)
        t2.add_column("MAX DD",     justify="right", width=9)
        t2.add_column("DD ACTUAL",  justify="right", width=11)
        t2.add_column("VaR 95%",    justify="right", width=9)
        t2.add_column("VOLATILIDAD",justify="right", width=13)

        for i, a in enumerate(assets):
            sh    = a.get("sharpe")
            so    = a.get("sortino")
            dd    = a.get("max_dd")
            cdd   = a.get("cur_dd")
            vol   = a.get("vol")
            var95 = a.get("var95")
            ppos  = a.get("pct_pos")
            beta  = a.get("beta")
            c     = COLORS[i % len(COLORS)]
            nom_s = a["nombre"][:23]

            sh_s   = "{:+.2f}".format(sh)     if sh    is not None else "—"
            so_s   = "{:+.2f}".format(so)     if so    is not None else "—"
            dd_s   = "{:.1f}%".format(dd*100) if dd    is not None else "—"
            cdd_s  = "{:.1f}%".format(cdd*100)if cdd   is not None else "—"
            vol_s  = "{:.1f}%".format(vol*100)if vol   is not None else "—"
            var_s  = "{:.1f}%".format(var95*100) if var95 is not None else "—"
            pos_s  = "{:.0f}%".format(ppos)   if ppos  is not None else "—"
            beta_s = "{:+.2f}".format(beta)   if beta  is not None else "—"

            sh_col = ("bright_green" if (sh or 0)>=1 else
                      "white"        if (sh or 0)>=0 else "bright_red")
            so_col = ("bright_green" if (so or 0)>=1 else
                      "white"        if (so or 0)>=0 else "bright_red")
            beta_col = ("grey50"      if beta is None else
                        "bright_red"  if (beta or 0)>1.5 else
                        "yellow"      if (beta or 0)>1.0 else
                        "bright_green"if (beta or 0)<0.5 else "white")
            cdd_col = ("bright_red"  if (cdd or 0)>0.20 else
                       "yellow"      if (cdd or 0)>0.10 else
                       "bright_green"if (cdd or 0)<0.03 else "white")
            pos_col = ("bright_green" if (ppos or 0)>=55 else
                       "white"        if (ppos or 0)>=50 else "yellow")

            if vol is None:
                riesgo, riesgo_col = "—",          "grey50"
            elif vol < 0.10: riesgo, riesgo_col = "🟢 Bajo",    "bright_green"
            elif vol < 0.20: riesgo, riesgo_col = "🟡 Moderado","white"
            elif vol < 0.35: riesgo, riesgo_col = "🟠 Alto",    "yellow"
            else:            riesgo, riesgo_col = "🔴 Muy alto","bright_red"

            t1.add_row(
                Text(a["ticker"][:15], style="{} bold".format(c)),
                Text(nom_s,            style="grey62"),
                Text(sh_s,             style=sh_col),
                Text(so_s,             style=so_col),
                Text(beta_s,           style=beta_col),
                Text(pos_s,            style=pos_col),
                Text(riesgo,           style=riesgo_col),
            )
            t2.add_row(
                Text(a["ticker"][:15], style="{} bold".format(c)),
                Text(nom_s,            style="grey62"),
                Text(dd_s,   style="bright_red" if (dd or 0)>0.3 else "white"),
                Text(cdd_s,            style=cdd_col),
                Text(var_s,  style="bright_red" if (var95 or 0)>0.04 else "white"),
                Text(vol_s,            style="white"),
            )

        # ── Matriz de correlación ──
        with_hist = [(a["ticker"], [h[1] for h in a["hist"]])
                     for a in assets if len(a["hist"]) >= 30]

        corr_items = [
            Text(""),
            Text("▸ MATRIZ DE CORRELACIÓN  (retornos diarios)", style="bright_green bold"),
            Text("  +1.00 movimiento idéntico  ·  0.00 independientes  ·  -1.00 opuesto",
                 style="grey50"),
            Text(""),
        ]
        if len(with_hist) >= 2:
            col_w  = 8
            header = Text("  {:22s}".format(""), style="grey50")
            for tk,_ in with_hist:
                header.append("{:>{w}s}".format(tk[:col_w-1], w=col_w), style="grey62")
            corr_items.append(header)
            for i, (ta, pa_) in enumerate(with_hist):
                row = Text("  {:22s}".format(ta[:22]),
                           style="{} bold".format(COLORS[i%len(COLORS)]))
                for j, (tb, pb_) in enumerate(with_hist):
                    if i == j:
                        row.append("{:>{w}.2f}".format(1.0, w=col_w), style="grey50")
                    else:
                        c_ = pearson_corr(pa_, pb_)
                        if c_ is None:
                            row.append("{:>{w}s}".format("—", w=col_w), style="grey50")
                        else:
                            col_ = ("bright_green" if c_>=0.7 else "green" if c_>=0.3
                                    else "bright_red" if c_<=-0.7 else "red" if c_<=-0.3
                                    else "grey62")
                            row.append("{:>{w}.2f}".format(c_, w=col_w), style=col_)
                corr_items.append(row)
        else:
            corr_items.append(Text("  Se necesitan al menos 2 activos con historial ≥ 30 días.",
                                   style="grey50"))

        # ── Guía de interpretación (todos los indicadores) ──
        guia = Table(box=None, show_header=False, padding=(0,2))
        guia.add_column("ind",  width=18, style="grey62")
        guia.add_column("val",  width=14)
        guia.add_column("desc", style="grey70")

        guia.add_row("Sharpe",   Text("> 1",   style="bright_green bold"), "Rentabilidad buena ajustada por riesgo total")
        guia.add_row("",         Text("0 – 1", style="white"),             "Aceptable, compensa el riesgo")
        guia.add_row("",         Text("< 0",   style="bright_red"),        "No compensa el riesgo asumido")
        guia.add_row("Sortino",  Text("> 1",   style="bright_green bold"), "Bueno ajustando solo por caídas (mejor para crypto)")
        guia.add_row("",         Text("< Sharpe","white"),                 "Muchas caídas asimétricas (más bajadas que subidas)")
        guia.add_row("Beta",     Text("< 0.5", style="bright_green"),      "Activo defensivo, poco correlado con el mercado")
        guia.add_row("",         Text("≈ 1.0", style="white"),             "Se mueve igual que el benchmark (MSCI World)")
        guia.add_row("",         Text("> 1.5", style="bright_red"),        "Amplifica los movimientos del mercado")
        guia.add_row("Max DD",   Text("> 30%", style="bright_red"),        "Caída severa en algún período histórico")
        guia.add_row("DD Actual",Text("> 20%", style="bright_red"),        "Caída activa significativa desde el pico reciente")
        guia.add_row("",         Text("< 3%",  style="bright_green"),      "En o cerca de máximos históricos")
        guia.add_row("VaR 95%",  Text("> 4%",  style="bright_red"),        "En un mal día puedes perder más del 4%")
        guia.add_row("",         Text("< 2%",  style="bright_green"),      "Riesgo diario controlado")
        guia.add_row("Días+",    Text("> 55%", style="bright_green"),      "Más de la mitad de días cierran en positivo")
        guia.add_row("",         Text("< 50%", style="yellow"),            "Pocos días positivos (pero puede ser rentable si las subidas son grandes)")
        guia.add_row("Volatil.", Text("< 10%", style="bright_green"),      "Baja volatilidad (fondos indexados conservadores)")
        guia.add_row("",         Text("> 35%", style="bright_red"),        "Alta volatilidad (Bitcoin, materias primas)")

        return Group(
            Text("▸ RENDIMIENTO AJUSTADO POR RIESGO", style="bright_green bold"),
            Text("  Calculado sobre el histórico completo. Beta vs Vanguard Global Stock Index.",
                 style="grey50"),
            Text(""),
            t1,
            Text(""),
            Text("▸ EXPOSICIÓN AL RIESGO", style="bright_green bold"),
            Text("  DD Actual = caída desde el máximo histórico hasta hoy. VaR 95% = pérdida máxima en un mal día.",
                 style="grey50"),
            Text(""),
            t2,
            *corr_items,
            Text(""),
            Text("▸ GUÍA DE INDICADORES", style="bright_green bold"),
            guia,
        )

    # ── VISTA 7: COSTES TER ──────────────────────────────────────────────────
    def _render_costes(self):
        p      = self.p
        assets = p["assets"]
        COLORS = ["bright_green","cyan","green","bright_cyan","white","grey70"]
        BAR_W  = 26

        tbl = Table(box=rbox.SIMPLE_HEAD, expand=False,
                    border_style="#003300", style="on #001200",
                    header_style="bright_green bold")
        tbl.add_column("ACTIVO",       width=16)
        tbl.add_column("NOMBRE",       width=30)
        tbl.add_column("VALOR €",      justify="right", width=13)
        tbl.add_column("TER",          justify="right", width=8)
        tbl.add_column("€/AÑO",        justify="right", width=12)
        tbl.add_column("€/5 AÑOS",     justify="right", width=12)
        tbl.add_column("€/10 AÑOS",    justify="right", width=12)
        tbl.add_column("% COSTE",      width=BAR_W+4)

        total_fee_5y  = 0.0
        total_fee_10y = 0.0
        total_val     = p["total_val"] or 1

        for i, a in enumerate(assets):
            c       = COLORS[i % len(COLORS)]
            ter     = a.get("ter", 0) or 0
            val     = a["cur_val"]
            fee_y   = a["annual_fee_eur"]
            nom_s   = a["nombre"][:29] if len(a["nombre"]) > 29 else a["nombre"]
            val_s   = self._m("€{:,.0f}".format(val))

            # Proyección compuesta: coste acumulado asumiendo crecimiento 0
            # (fee compuesta sería complejo; usamos estimación lineal conservadora)
            fee_5y  = fee_y * 5
            fee_10y = fee_y * 10
            total_fee_5y  += fee_5y
            total_fee_10y += fee_10y

            fee_y_s  = self._m("€{:,.0f}".format(fee_y))  if ter > 0 else "—"
            fee_5s   = self._m("€{:,.0f}".format(fee_5y)) if ter > 0 else "—"
            fee_10s  = self._m("€{:,.0f}".format(fee_10y)) if ter > 0 else "—"
            ter_s    = "{:.2f}%".format(ter*100) if ter > 0 else "—"
            ter_col  = ("bright_red"   if ter > 0.01
                        else "yellow"  if ter > 0.005
                        else "bright_green" if ter > 0
                        else "grey50")

            # Barra proporcional al TER
            max_ter = 0.02  # 2% como máximo visual
            filled  = min(BAR_W, int(ter/max_ter*BAR_W)) if ter > 0 else 0
            bar     = Text("▓"*filled, style=ter_col) + Text("░"*(BAR_W-filled), style="grey23")

            tbl.add_row(
                Text(a["ticker"][:15], style="{} bold".format(c)),
                Text(nom_s,            style="grey62"),
                Text(val_s,            style="white"),
                Text(ter_s,            style=ter_col),
                Text(fee_y_s,          style=ter_col),
                Text(fee_5s,           style="grey70"),
                Text(fee_10s,          style="grey50"),
                bar,
            )

        # Totales
        fee_pct  = p["total_annual_fee"] / total_val * 100 if total_val else 0
        fee_tot_s  = self._m("€{:,.0f}".format(p["total_annual_fee"]))
        fee_5_s    = self._m("€{:,.0f}".format(total_fee_5y))
        fee_10_s   = self._m("€{:,.0f}".format(total_fee_10y))
        total_val_s = self._m("€{:,.0f}".format(total_val))

        # Tabla de totales
        tot = Table(box=rbox.SIMPLE, show_header=False, expand=False,
                    border_style="#005e17", style="on #001200", padding=(0,2))
        tot.add_column("lbl", style="grey62", width=20)
        tot.add_column("val", justify="right", width=14)
        tot.add_column("lbl2", style="grey62", width=18)
        tot.add_column("val2", justify="right", width=14)
        tot.add_row("COSTE TOTAL / AÑO",  Text(fee_tot_s, style="yellow bold"),
                    "TER MEDIO PONDERADO", Text("{:.3f}%".format(fee_pct), style="yellow bold"))
        tot.add_row("COSTE TOTAL 5 AÑOS", Text(fee_5_s,   style="yellow"),
                    "COSTE TOTAL 10 AÑOS", Text(fee_10_s,  style="yellow"))
        tot.add_row("VALOR ACTUAL PORTFOLIO", Text(total_val_s, style="bright_green"),
                    "", Text(""))

        # Tabla comparativa top-cheapest
        sorted_ter = sorted([a for a in assets if (a.get("ter") or 0) > 0],
                            key=lambda x: x.get("ter", 0))
        cmp_items = []
        if sorted_ter:
            cheapest = sorted_ter[0]
            dearest  = sorted_ter[-1]
            diff_ter = (dearest.get("ter", 0) - cheapest.get("ter", 0)) * 100
            diff_eur = (dearest["annual_fee_eur"] - cheapest["annual_fee_eur"])
            cmp = Text("  Más barato: ")
            cmp.append("{} ({:.2f}%)".format(cheapest["ticker"], cheapest.get("ter",0)*100),
                       style="bright_green bold")
            cmp.append("    Más caro: ")
            cmp.append("{} ({:.2f}%)".format(dearest["ticker"], dearest.get("ter",0)*100),
                       style="bright_red bold")
            cmp.append("    Diferencia: {:.2f}% → {}".format(
                diff_ter, self._m("€{:,.0f}/año".format(diff_eur))), style="yellow")
            cmp_items.append(cmp)

        # Nota sobre proyección
        nota = Text(
            "  ★ Proyección lineal (fee × años). No incluye el impacto del interés compuesto.\n"
            "  Con reinversión, el coste real a 10 años puede ser un 5-10% superior.",
            style="#7ec8e3 italic")

        return Group(
            Text("▸ GASTOS DE GESTIÓN ANUALIZADOS (TER)", style="bright_green bold"),
            Text("  TER = Total Expense Ratio. Se descuenta diariamente del valor liquidativo.",
                 style="grey50"),
            Text(""),
            tbl,
            Text(""),
            Text("▸ RESUMEN DE COSTES", style="bright_green bold"),
            tot,
            Text(""),
            *cmp_items,
            Text(""),
            nota,
        )

    # ── VISTA 8: BENCHMARK ───────────────────────────────────────────────────
    def _render_benchmark(self):
        p      = self.p
        assets = p["assets"]

        # Identificar activo benchmark (Vanguard Global Stock Index preferido)
        BENCH_TICKERS = ["0IE00B03HCZ61", "IE00B03HCZ61", "LU0996182563", "IE00B42W4L06"]
        bench_asset = None
        for bt in BENCH_TICKERS:
            bench_asset = next((a for a in assets if a["ticker"] == bt), None)
            if bench_asset and bench_asset.get("hist"):
                break

        # Construir serie del portfolio (últimos 2 años)
        port_dates, port_vals = build_portfolio_history(assets, days=730)

        items = [
            Text("▸ PORTFOLIO vs BENCHMARK (MSCI WORLD)", style="bright_green bold"),
        ]

        if bench_asset:
            items.append(Text(
                "  Benchmark: {}  [{}]".format(bench_asset["nombre"], bench_asset["ticker"]),
                style="grey50"))
        else:
            items.append(Text(
                "  ⚠ Sin activo de referencia disponible. "
                "Añade un fondo global indexado para activar esta vista.",
                style="yellow"))

        items.append(Text(""))

        # ── Tabla comparativa de rentabilidades ──
        bench_hst = bench_asset["hst"] if bench_asset else {}
        periods   = [("1M",30), ("3M",90), ("6M",180), ("1A",365), ("TODO",None)]

        cmp_tbl = Table(box=rbox.SIMPLE_HEAD, expand=False,
                        border_style="#003300", style="on #001200",
                        header_style="bright_green bold")
        cmp_tbl.add_column("PERÍODO",        width=10)
        cmp_tbl.add_column("MI PORTFOLIO",   justify="right", width=16)
        cmp_tbl.add_column("BENCHMARK",      justify="right", width=16)
        cmp_tbl.add_column("ALPHA  (P–B)",   justify="right", width=16)
        cmp_tbl.add_column("",               width=20)

        def port_pct_since(days):
            if len(port_vals) < 2: return None
            cutoff = (date.today()-timedelta(days=days)).isoformat()
            sub = [(d,v) for d,v in zip(port_dates, port_vals) if d >= cutoff]
            if len(sub) < 2: return None
            return (sub[-1][1]-sub[0][1])/sub[0][1]*100

        for lbl, d in periods:
            if d is None:
                # Rentabilidad total del portfolio
                p_pct = (port_vals[-1]-port_vals[0])/port_vals[0]*100 if len(port_vals) >= 2 else None
                b_pct = bench_hst.get("total_pct")
            else:
                p_pct = port_pct_since(d)
                b_pct = bench_hst.get(lbl)

            alpha  = (p_pct - b_pct) if (p_pct is not None and b_pct is not None) else None
            p_s    = fp(p_pct)
            b_s    = fp(b_pct)
            a_s    = fp(alpha)
            p_col  = gc(p_pct or 0)
            b_col  = gc(b_pct or 0)
            a_col  = gc(alpha or 0)

            verdict = ""
            if alpha is not None:
                verdict = ("⭐ Bate al índice" if alpha > 2
                           else "✓ En línea"    if alpha > -2
                           else "⚠ Por debajo")
                v_col = ("bright_green" if alpha > 2 else
                         "white"        if alpha > -2 else "yellow")
            else:
                v_col = "grey50"

            cmp_tbl.add_row(
                Text(lbl,  style="bright_green bold"),
                Text(p_s,  style="{} bold".format(p_col)),
                Text(b_s,  style=b_col),
                Text(a_s,  style="{} bold".format(a_col)),
                Text(verdict, style=v_col),
            )

        items.append(Text("▸ RENTABILIDAD COMPARATIVA", style="bright_green bold"))
        items.append(cmp_tbl)
        items.append(Text(""))

        # ── Gráfico portfolio normalizado ──
        if len(port_vals) >= 10:
            p0_norm = port_vals[0]
            norm_port = [v/p0_norm*100 for v in port_vals]
            items.append(Text("▸ EVOLUCIÓN PORTFOLIO (base 100 en inicio)", style="bright_green bold"))
            for line in render_chart(norm_port, width=65, height=8, mask_axis=False):
                items.append(line)
            if len(port_dates) > 1:
                d_line = Text("           ", style="grey50")
                n = len(port_dates)
                step = max(1, n // 6)
                idxs = list(range(0, n, step)); idxs[-1] = n-1
                prev = 0
                for i in idxs:
                    pos = int(i*65/(n-1)); gap = pos-prev
                    if gap > 0: d_line.append(" "*gap)
                    d_line.append(port_dates[i][:7], style="grey50"); prev = pos+7
                items.append(d_line)
            items.append(Text(""))

        # ── Gráfico benchmark normalizado ──
        if bench_asset and bench_hst.get("prices") and len(bench_hst["prices"]) >= 10:
            b_prices = bench_hst["prices"]
            b_dates  = bench_hst["dates"]
            # Recortar a los últimos 2 años
            cutoff = (date.today()-timedelta(days=730)).isoformat()
            pairs = [(d,p_) for d,p_ in zip(b_dates, b_prices) if d >= cutoff]
            if len(pairs) >= 10:
                b_d = [x[0] for x in pairs]; b_p = [x[1] for x in pairs]
                b0  = b_p[0]
                norm_b = [v/b0*100 for v in b_p]
                items.append(Text("▸ BENCHMARK {} (base 100 en inicio)".format(
                    bench_asset["ticker"]), style="bright_green bold"))
                for line in render_chart(norm_b, width=65, height=8, mask_axis=False):
                    items.append(line)
                if len(b_d) > 1:
                    d_line = Text("           ", style="grey50")
                    n = len(b_d)
                    step = max(1, n // 6)
                    idxs = list(range(0, n, step)); idxs[-1] = n-1
                    prev = 0
                    for i in idxs:
                        pos = int(i*65/(n-1)); gap = pos-prev
                        if gap > 0: d_line.append(" "*gap)
                        d_line.append(b_d[i][:7], style="grey50"); prev = pos+7
                    items.append(d_line)
                items.append(Text(""))

        if len(port_vals) < 10:
            items.append(Text(
                "  ⚠ Se necesitan más datos históricos para mostrar los gráficos.",
                style="grey50"))

        items.append(Text(
            "  Alpha positivo = portfolio supera al índice  |  "
            "Alpha negativo = el índice lo hace mejor",
            style="#7ec8e3 italic"))

        return Group(*items)

    # ── VISTA 9: MACRO ────────────────────────────────────────────────────────
    def _render_macro(self):
        """⑨ MACROECONOMÍA — indicadores macro para inversor a largo plazo."""
        snap = load_macro_snapshot(self.hist_dir)
        items = []

        # Cabecera
        hdr = Text()
        hdr.append("  ⑨ MACROECONOMÍA", style="#00ff41 bold")
        hdr.append("  —  Indicadores para inversor a largo plazo  (10+ años)", style="grey70")
        items.append(hdr)
        items.append(Text(""))

        if not snap:
            items.append(Text(
                "  Sin datos. Ejecuta:  python3 scripts/macro_recorder.py -d historico",
                style="yellow"))
            items.append(Text(
                "  (o activa la opción en terminal.sh para que se actualice automáticamente)",
                style="grey50"))
            return Group(*items)

        updated = snap.get("updated", "—")
        ind     = snap.get("indicadores", {})

        # Fecha de actualización
        upd_line = Text()
        upd_line.append("  Actualizado: ", style="grey50")
        upd_line.append(updated, style="white")
        upd_line.append("   ·  Fuente: Yahoo Finance", style="grey50")
        items.append(upd_line)
        items.append(Text(""))

        # ── Helpers ────────────────────────────────────────────────────────────
        def fmt_val(v, decimales, unidad):
            if v is None: return "   —"
            fmt = f"{v:,.{decimales}f}" if decimales > 0 else f"{v:,.0f}"
            return fmt + unidad

        def fmt_chg(v, unit, decimales=1):
            if v is None: return "       "
            sign = "+" if v >= 0 else ""
            col  = "#00ff41" if v >= 0 else "#ff5555"
            return (f"{sign}{v:.{decimales}f}{unit}", col)

        def semaforo_vix(val):
            if val is None: return ("─", "grey50")
            if val < 20:  return ("🟢", "#00ff41")
            if val < 30:  return ("🟡", "yellow")
            return ("🔴", "#ff5555")

        def semaforo_spread(val):
            if val is None: return ("─", "grey50")
            if val > 0.5:   return ("🟢", "#00ff41")
            if val > -0.5:  return ("🟡", "yellow")
            return ("🔴", "#ff5555")

        def semaforo_usdidx(val):
            if val is None: return ("─", "grey50")
            if val < 100:   return ("🟢", "#00ff41")
            if val < 106:   return ("🟡", "yellow")
            return ("🔴", "#ff5555")

        def semaforo_pct1m(val):
            if val is None: return ("─", "grey50")
            if val > 2:     return ("🟢", "#00ff41")
            if val > -5:    return ("🟡", "yellow")
            return ("🔴", "#ff5555")

        # ── Tabla mercados ──────────────────────────────────────────────────────
        items.append(Text("  INDICADORES DE MERCADO", style="#00ff41 bold"))
        items.append(Text("  " + "─" * 78, style="grey35"))

        t_mkt = Table(box=rbox.SIMPLE, show_header=True, padding=(0,1),
                      header_style="grey50", style="#001200")
        t_mkt.add_column("INDICADOR",   style="grey50",      width=28)
        t_mkt.add_column("VALOR",       style="white",       width=14, justify="right")
        t_mkt.add_column("1 DÍA",       style="white",       width=11, justify="right")
        t_mkt.add_column("1 SEMANA",    style="white",       width=11, justify="right")
        t_mkt.add_column("1 MES",       style="white",       width=11, justify="right")
        t_mkt.add_column("SEÑAL",       style="white",       width=7,  justify="center")

        MKT_KEYS = [
            ("VIX",    semaforo_vix),
            ("SP500",  semaforo_pct1m),
            ("NASDAQ", semaforo_pct1m),
            ("STOXX50",semaforo_pct1m),
        ]
        for k, sem_fn in MKT_KEYS:
            v = ind.get(k)
            if not v: continue
            dec   = v["decimales"]; u = v["unidad"]; cu = v["chg_unit"]
            val_s = fmt_val(v["valor"], dec, u)
            sem_icon, _ = sem_fn(v.get("valor") if k == "VIX" else v.get("chg_1mes"))
            d1  = fmt_chg(v.get("chg_1d"),   cu)
            d1w = fmt_chg(v.get("chg_1sem"),  cu)
            d1m = fmt_chg(v.get("chg_1mes"),  cu)
            row_vals = [
                Text(v["nombre"],           style="white"),
                Text(val_s,                 style="bright_white"),
                Text(d1[0],                 style=d1[1]),
                Text(d1w[0],                style=d1w[1]),
                Text(d1m[0],                style=d1m[1]),
                Text(sem_icon,              style="white"),
            ]
            t_mkt.add_row(*row_vals)
        items.append(t_mkt)

        # ── Tabla tipos de interés ──────────────────────────────────────────────
        items.append(Text("  TIPOS DE INTERÉS (EEUU)", style="#00ff41 bold"))
        items.append(Text("  " + "─" * 78, style="grey35"))

        t_rates = Table(box=rbox.SIMPLE, show_header=True, padding=(0,1),
                        header_style="grey50", style="#001200")
        t_rates.add_column("INDICADOR",  style="grey50",   width=28)
        t_rates.add_column("VALOR",      style="white",    width=14, justify="right")
        t_rates.add_column("CAMBIO 1D",  style="white",    width=14, justify="right")
        t_rates.add_column("SEÑAL",      style="white",    width=7,  justify="center")
        t_rates.add_column("NOTA",       style="grey50",   width=30)

        for k, sem_fn, nota in [
            ("US13W",  None,              "Tipo a corto (referencia BCE/FED)"),
            ("US10Y",  None,              "Tipo a largo — coste deuda global"),
            ("SPREAD", semaforo_spread,   "Spread 10Y−13W  (>0 = curva normal)"),
        ]:
            v = ind.get(k)
            if not v: continue
            dec = v["decimales"]; u = v["unidad"]; cu = v["chg_unit"]
            val_s = fmt_val(v["valor"], dec, u)
            if k == "SPREAD":
                sem_icon, _ = semaforo_spread(v.get("valor"))
            else:
                sem_icon = "─"
            d1 = fmt_chg(v.get("chg_1d"), cu)
            row_name = Text(v["nombre"], style="cyan" if k == "SPREAD" else "white")
            row_vals = [
                row_name,
                Text(val_s, style="bright_white"),
                Text(d1[0], style=d1[1]),
                Text(sem_icon),
                Text(nota, style="grey50"),
            ]
            t_rates.add_row(*row_vals)
        items.append(t_rates)

        # ── Tabla divisas y materias primas ─────────────────────────────────────
        items.append(Text("  DIVISAS · MATERIAS PRIMAS · ENERGÍA · CRIPTO", style="#00ff41 bold"))
        items.append(Text("  " + "─" * 78, style="grey35"))

        t_comm = Table(box=rbox.SIMPLE, show_header=True, padding=(0,1),
                       header_style="grey50", style="#001200")
        t_comm.add_column("INDICADOR",  style="grey50",      width=28)
        t_comm.add_column("VALOR",      style="white",       width=14, justify="right")
        t_comm.add_column("1 DÍA",      style="white",       width=11, justify="right")
        t_comm.add_column("1 SEMANA",   style="white",       width=11, justify="right")
        t_comm.add_column("1 MES",      style="white",       width=11, justify="right")
        t_comm.add_column("SEÑAL",      style="white",       width=7,  justify="center")

        COMM_KEYS = [
            ("EURUSD",  None),
            ("USDIDX",  semaforo_usdidx),
            ("GOLD",    semaforo_pct1m),
            ("OIL",     None),
            ("COPPER",  None),
            ("URANIUM", None),
            ("BTC",     semaforo_pct1m),
        ]
        for k, sem_fn in COMM_KEYS:
            v = ind.get(k)
            if not v: continue
            dec   = v["decimales"]; u = v["unidad"]; cu = v["chg_unit"]
            val_s = fmt_val(v["valor"], dec, u)
            if sem_fn is not None:
                arg = v.get("valor") if k == "USDIDX" else v.get("chg_1mes")
                sem_icon, _ = sem_fn(arg)
            else:
                sem_icon = "─"
            d1  = fmt_chg(v.get("chg_1d"),  cu)
            d1w = fmt_chg(v.get("chg_1sem"), cu)
            d1m = fmt_chg(v.get("chg_1mes"), cu)
            t_comm.add_row(
                Text(v["nombre"], style="white"),
                Text(val_s, style="bright_white"),
                Text(d1[0],  style=d1[1]),
                Text(d1w[0], style=d1w[1]),
                Text(d1m[0], style=d1m[1]),
                Text(sem_icon),
            )
        items.append(t_comm)

        # ── Tabla IA · Data Centers · Energía digital ───────────────────────────
        items.append(Text("  IA · DATA CENTERS · ENERGÍA DIGITAL", style="#00ff41 bold"))
        items.append(Text("  " + "─" * 78, style="grey35"))

        t_ai = Table(box=rbox.SIMPLE, show_header=True, padding=(0,1),
                     header_style="grey50", style="#001200")
        t_ai.add_column("INDICADOR",  style="grey50",   width=28)
        t_ai.add_column("VALOR",      style="white",    width=14, justify="right")
        t_ai.add_column("1 DÍA",      style="white",    width=11, justify="right")
        t_ai.add_column("1 SEMANA",   style="white",    width=11, justify="right")
        t_ai.add_column("1 MES",      style="white",    width=11, justify="right")
        t_ai.add_column("SEÑAL",      style="white",    width=7,  justify="center")

        AI_KEYS = [
            ("GAS",  None,           semaforo_pct1m),
            ("XLU",  semaforo_pct1m, semaforo_pct1m),
            ("SOX",  semaforo_pct1m, semaforo_pct1m),
        ]
        for k, _, sem_fn in AI_KEYS:
            v = ind.get(k)
            if not v: continue
            dec   = v["decimales"]; u = v["unidad"]; cu = v["chg_unit"]
            val_s = fmt_val(v["valor"], dec, u)
            sem_icon, _ = sem_fn(v.get("chg_1mes")) if sem_fn else ("─", "grey50")
            d1  = fmt_chg(v.get("chg_1d"),   cu)
            d1w = fmt_chg(v.get("chg_1sem"),  cu)
            d1m = fmt_chg(v.get("chg_1mes"),  cu)
            t_ai.add_row(
                Text(v["nombre"], style="white"),
                Text(val_s,       style="bright_white"),
                Text(d1[0],       style=d1[1]),
                Text(d1w[0],      style=d1w[1]),
                Text(d1m[0],      style=d1m[1]),
                Text(sem_icon),
            )
        # Nota explicativa compacta bajo la tabla
        nota_ai = Text()
        nota_ai.append("  SOX", style="cyan"); nota_ai.append(" = indicador adelantado de capex IA → demanda energética futura  ", style="grey50")
        nota_ai.append("XLU", style="cyan");   nota_ai.append(" = utilities firman PPAs con hyperscalers  ", style="grey50")
        nota_ai.append("Gas", style="cyan");   nota_ai.append(" = presión eléctrica a corto plazo", style="grey50")
        items.append(t_ai)
        items.append(nota_ai)

        # ── Bloque contexto inversor ────────────────────────────────────────────
        items.append(Text(""))
        items.append(Text("  CONTEXTO PARA INVERSOR A LARGO PLAZO  (10+ años)", style="#00ff41 bold"))
        items.append(Text("  " + "─" * 78, style="grey35"))

        ctx_lines = _macro_context(ind)
        for line in ctx_lines:
            items.append(line)

        items.append(Text("  " + "─" * 78, style="grey35"))
        items.append(Text(
            "  Usa [R] para recargar precios · [9] para volver a esta pestaña",
            style="#7ec8e3 italic"))
        items.append(Text(
            "  Actualiza macro:  python3 scripts/macro_recorder.py -d historico",
            style="grey50 italic"))

        return Group(*items)

    # ── ACCIONES ─────────────────────────────────────────────────────────────
    def _refresh_all_widgets(self):
        if not self.err and self.p:
            IDS = ["resumen","posiciones","historico","transacciones",
                   "tir","metricas","costes","benchmark","macro"]
            FNS = [self._render_resumen, self._render_posiciones,
                   self._render_historico, self._render_transacciones,
                   self._render_tir, self._render_metricas,
                   self._render_costes, self._render_benchmark,
                   self._render_macro]
            for wid, fn in zip(IDS, FNS):
                try: self.query_one("#w-{}".format(wid), Static).update(fn())
                except Exception: pass

    def action_reload(self):
        self.notify("Actualizando precios… ⏳", severity="information", timeout=15)
        self.run_worker(self._fetch_prices_thread, thread=True, exclusive=True)

    def _fetch_prices_thread(self) -> None:
        """Corre en un hilo de fondo: ejecuta price_recorder y luego actualiza la UI.
        Usa --force para sobreescribir el precio de hoy con valores frescos de Yahoo/EODHD."""
        script = Path(__file__).parent / "price_recorder.py"
        if script.exists():
            subprocess.run(
                [sys.executable, str(script),
                 "-f", str(self.yaml_path),
                 "-d", str(self.hist_dir),
                 "--force"],
                capture_output=True,
            )
        self.call_from_thread(self._apply_reload)

    def _apply_reload(self) -> None:
        """Corre en el hilo principal: recarga datos y refresca toda la UI."""
        self._load()
        self._refresh_subtitle()
        self._refresh_all_widgets()
        self.notify("Portfolio recargado ✓", severity="information", timeout=3)

    def action_toggle_privacy(self):
        self.privacy = not self.privacy
        self._refresh_subtitle()
        self._refresh_all_widgets()
        if self.privacy:
            self.notify("🔒 Modo privado ACTIVADO — valores ocultados",
                        severity="warning", timeout=3)
        else:
            self.notify("🔓 Modo privado DESACTIVADO",
                        severity="information", timeout=2)

    def action_toggle_pos_filter(self):
        """Cicla entre taxonomías en ② POSICIONES."""
        if not self.p:
            return
        taxonomies = []
        for a in self.p["assets"]:
            t = a.get("taxonomia") or ""
            if t and t not in taxonomies:
                taxonomies.append(t)
        # Ciclo: None → tax[0] → tax[1] → … → None
        options = [None] + taxonomies
        cur = getattr(self, "_pos_filter", None)
        idx = options.index(cur) if cur in options else 0
        self._pos_filter = options[(idx + 1) % len(options)]
        label = self._pos_filter or "TODOS"
        self.notify("Posiciones: {}".format(label), severity="information", timeout=2)
        try:
            self.query_one("#w-posiciones", Static).update(self._render_posiciones())
        except Exception:
            pass

    def action_toggle_hist_range(self):
        """Cicla entre rangos de tiempo en ③ HISTÓRICO."""
        idx = HIST_RANGES.index(self._hist_range)
        self._hist_range = HIST_RANGES[(idx + 1) % len(HIST_RANGES)]
        self.notify("Histórico: {}".format(self._hist_range),
                    severity="information", timeout=2)
        try:
            self.query_one("#w-historico", Static).update(self._render_historico())
        except Exception:
            pass

    def action_add_transaction(self):
        """Abre el formulario modal para añadir una transacción."""
        if not self.p:
            self.notify("Sin datos cargados.", severity="warning"); return
        tickers = [a["ticker"] for a in self.p["assets"]]

        def handle_result(tx_data):
            if tx_data is None:
                return
            self._save_transaction_to_yaml(tx_data)

        self.push_screen(AddTransactionScreen(tickers), handle_result)

    def _save_transaction_to_yaml(self, tx_data):
        """Inserta la transacción en portfolio.yaml preservando el formato original."""
        try:
            with open(self.yaml_path, encoding="utf-8") as f:
                lines = f.readlines()

            ticker = tx_data["ticker"]

            # Encontrar la línea del activo: "  - ticker: XXXX"
            asset_idx = None
            for i, line in enumerate(lines):
                if line.rstrip() in (f"  - ticker: {ticker}",
                                     f"  - ticker: '{ticker}'",
                                     f'  - ticker: "{ticker}"'):
                    asset_idx = i
                    break

            if asset_idx is None:
                self.notify(f"Ticker '{ticker}' no encontrado en el YAML.",
                            severity="error", timeout=5)
                return

            # Encontrar el inicio del siguiente activo (para delimitar el bloque)
            next_asset_idx = len(lines)
            for i in range(asset_idx + 1, len(lines)):
                if lines[i].startswith("  - ticker:"):
                    next_asset_idx = i
                    break

            # Dentro del bloque del activo, encontrar "    transacciones:"
            asset_block = lines[asset_idx:next_asset_idx]
            tx_header_rel = None
            for j, l in enumerate(asset_block):
                if l.rstrip() == "    transacciones:":
                    tx_header_rel = j
                    break

            if tx_header_rel is None:
                self.notify("No se encontró el bloque 'transacciones:' para este ticker.",
                            severity="error", timeout=5)
                return

            # Encontrar la última línea del último bloque de transacciones
            last_tx_line_rel = tx_header_rel
            for j in range(tx_header_rel + 1, len(asset_block)):
                l = asset_block[j]
                if l.startswith("      ") and l.strip():
                    last_tx_line_rel = j
                elif l.strip() == "":
                    pass   # líneas vacías no interrumpen
                else:
                    break  # línea con menos indentación → fin del bloque tx

            insert_abs = asset_idx + last_tx_line_rel + 1

            nota_val = str(tx_data.get("nota") or "")
            new_lines = [
                f'      - fecha: "{tx_data["fecha"]}"\n',
                f'        tipo: {tx_data["tipo"]}\n',
                f'        participaciones: {tx_data["participaciones"]:.6f}\n',
                f'        precio: {tx_data["precio"]:.4f}\n',
                f'        comision: {tx_data["comision"]:.2f}\n',
                f'        nota: {nota_val}\n',
            ]

            for j, nl in enumerate(new_lines):
                lines.insert(insert_abs + j, nl)

            with open(self.yaml_path, "w", encoding="utf-8") as f:
                f.writelines(lines)

            self._load()
            self._refresh_all_widgets()
            self.notify(
                "✓ {} de {} guardada · {:.6f} × {:.4f}".format(
                    tx_data["tipo"].capitalize(), ticker,
                    tx_data["participaciones"], tx_data["precio"]),
                severity="information", timeout=5)

        except Exception as e:
            self.notify(f"Error al guardar: {e}", severity="error", timeout=8)

    # ── EDITAR TRANSACCIÓN ────────────────────────────────────────────────────
    def action_edit_transaction(self):
        """E — selecciona una transacción y abre el formulario pre-relleno para editarla."""
        if not self.p: self.notify("Sin datos.", severity="warning"); return
        assets = self.p["assets"]
        if not any(a.get("txs") for a in assets):
            self.notify("No hay transacciones registradas.", severity="warning"); return

        def on_selected(result):
            if result is None: return
            ticker, local_idx, tx = result
            tickers = [a["ticker"] for a in assets]
            nombre = next((a.get("nombre", "") for a in assets if a["ticker"] == ticker), "")
            prefill = dict(tx); prefill["ticker"] = ticker; prefill["nombre"] = nombre

            def on_saved(new_tx):
                if new_tx is None: return
                if not self._delete_transaction_from_yaml(ticker, local_idx):
                    self.notify("Error al eliminar la transacción original.", severity="error"); return
                if self._save_transaction_to_yaml(new_tx):
                    self._load(); self._refresh_all_widgets()
                    self.notify("Transacción actualizada ✓", severity="information", timeout=3)
                else:
                    self.notify("Error al guardar la transacción editada.", severity="error")

            self.push_screen(AddTransactionScreen(tickers, prefill=prefill), on_saved)

        self.push_screen(SelectTransactionScreen(assets, "EDITAR TRANSACCIÓN"), on_selected)

    # ── BORRAR TRANSACCIÓN ────────────────────────────────────────────────────
    def action_delete_transaction(self):
        """D — selecciona una transacción y la borra tras confirmación."""
        if not self.p: self.notify("Sin datos.", severity="warning"); return
        assets = self.p["assets"]
        if not any(a.get("txs") for a in assets):
            self.notify("No hay transacciones registradas.", severity="warning"); return

        def on_selected(result):
            if result is None: return
            ticker, local_idx, tx = result
            nombre = next((a.get("nombre", "") for a in assets if a["ticker"] == ticker), "")

            def on_confirmed(confirmed):
                if not confirmed: return
                if self._delete_transaction_from_yaml(ticker, local_idx):
                    self._load(); self._refresh_all_widgets()
                    self.notify("Transacción eliminada ✓", severity="warning", timeout=3)
                else:
                    self.notify("Error al eliminar la transacción.", severity="error")

            self.push_screen(ConfirmDeleteScreen(ticker, tx, nombre), on_confirmed)

        self.push_screen(SelectTransactionScreen(assets, "BORRAR TRANSACCIÓN"), on_selected)

    # ── HELPER: BORRAR DEL YAML ───────────────────────────────────────────────
    def _delete_transaction_from_yaml(self, ticker: str, local_idx: int) -> bool:
        """Elimina la transacción local_idx del activo ticker en portfolio.yaml."""
        try:
            import re as _re
            with open(self.yaml_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # Localizar el activo por ticker
            asset_line = None
            for i, l in enumerate(lines):
                if _re.match(r'^  - ticker:\s+{}$'.format(_re.escape(ticker)), l.rstrip()):
                    asset_line = i; break
            if asset_line is None: return False

            # Localizar su bloque transacciones:
            txs_line = None
            for i in range(asset_line, len(lines)):
                if lines[i].rstrip() == "    transacciones:":
                    txs_line = i; break
                if i > asset_line and _re.match(r'^  - ticker:', lines[i]):
                    break
            if txs_line is None: return False

            # Encontrar los inicios de cada transacción (líneas "      - fecha:")
            tx_starts = []
            for i in range(txs_line + 1, len(lines)):
                if lines[i].startswith("      - fecha:"):
                    tx_starts.append(i)
                elif lines[i].startswith("  - ") and i > txs_line + 1:
                    break
                elif (not lines[i].startswith("      ") and lines[i].strip()
                      and i > txs_line + 1):
                    break

            if local_idx >= len(tx_starts): return False

            # Delimitar el bloque a eliminar
            start = tx_starts[local_idx]
            if local_idx + 1 < len(tx_starts):
                end = tx_starts[local_idx + 1]
            else:
                end = start + 1
                while end < len(lines) and lines[end].startswith("        "):
                    end += 1

            del lines[start:end]
            with open(self.yaml_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            return True
        except Exception:
            return False

    def action_goto(self, tab_id: str):
        try: self.query_one(TabbedContent).active = tab_id
        except Exception: pass


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Portfolio Dashboard v4.0 (Textual)")
    ap.add_argument("-f","--file", default="portfolio.yaml",  help="Ruta al portfolio.yaml")
    ap.add_argument("-d","--hist", default="historico",        help="Directorio histórico")
    args = ap.parse_args()

    if not Path(args.file).exists():
        print(f"\n  ✗ No se encuentra: {args.file}\n")
        sys.exit(1)

    PortfolioApp(args.file, args.hist, False).run()
    print("\n  ✓ Dashboard cerrado.\n")
