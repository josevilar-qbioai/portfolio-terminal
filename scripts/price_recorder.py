#!/usr/bin/env python3
"""
price_recorder.py — Grabador de precios históricos
════════════════════════════════════════════════════
Guarda el precio de cierre de cada activo en un CSV individual.

Estructura de ficheros generada:
  historico/
    GB00B15KXQ89.csv
    BTC-EUR.csv
    IE00BGV5VN51.csv
    ...

Campos opcionales en portfolio.yaml que este script respeta:
  yahoo_ticker     — ticker para Yahoo Finance (si difiere del ticker principal)
  historico_ticker — nombre del CSV en historico/ (si difiere del ticker principal)
                     Activos con el mismo historico_ticker (ej. BTC wallets)
                     solo se graban una vez.
  isin             — ISIN del activo, usado por Morningstar como fallback para
                     fondos españoles (ES), irlandeses (IE) y luxemburgueses (LU)
  eodhd_ticker     — ticker EODHD (ej. BTIC.XETRA, IE00B03HCZ61.ETFEU)

Uso:
  python3 price_recorder.py                    # Lee portfolio.yaml del directorio actual
  python3 price_recorder.py -f mi.yaml         # Fichero YAML concreto
  python3 price_recorder.py -f mi.yaml --show  # Muestra resumen tras grabar
  python3 price_recorder.py -f mi.yaml --force # Sobreescribe el precio de hoy

Integración con cron (cierre europeo 18:00):
  0 18 * * 1-5 /usr/bin/python3 /ruta/price_recorder.py -f /ruta/portfolio.yaml

Integración con terminal.sh:
  El script terminal.sh ejecuta este grabador automáticamente al arrancar.
"""

import csv
import sys
import yaml
import argparse
from datetime import date
from pathlib import Path

# ── Fetch precio real (Yahoo Finance) ─────────────────────────────────────────
def fetch_price_yfinance(ticker):
    """Intenta obtener precio real con yfinance. Devuelve None si no está instalado.
    Método 1: fast_info (rápido)
    Método 2: history(period='5d') — fallback para ETFs europeos donde fast_info falla
    """
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        # Método 1: fast_info
        info  = t.fast_info
        price = getattr(info, "last_price", None) or getattr(info, "regularMarketPrice", None)
        if price:
            return float(price)
        # Método 2: history — más robusto para bolsas europeas (Xetra, etc.)
        hist = t.history(period="5d", auto_adjust=True)
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
        return None
    except Exception:
        return None

def fetch_price_eodhd(ticker, api_key):
    """Obtiene precio de EODHD (EOD Historical Data).
    Cubre ETFs europeos, fondos UCITS y activos no disponibles en Yahoo.
    Prueba el ticker tal cual y variantes con el exchange correcto:
      Yahoo .DE → EODHD .XETRA  |  Yahoo .L → EODHD .LSE  |  etc.
    """
    if not api_key:
        return None
    try:
        import urllib.request, json
        EXCHANGE_MAP = {
            ".DE": ".XETRA", ".F": ".F", ".SG": ".XETRA",
            ".L": ".LSE",    ".SW": ".SW",
            ".MI": ".MI",    ".PA": ".PA", ".AS": ".AS",
        }
        tickers_to_try = [ticker]
        for yext, eext in EXCHANGE_MAP.items():
            if ticker.upper().endswith(yext.upper()):
                alt = ticker[:-len(yext)] + eext
                if alt != ticker:
                    tickers_to_try.append(alt)
        for t in tickers_to_try:
            url = "https://eodhd.com/api/real-time/{}?api_token={}&fmt=json".format(t, api_key)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode("utf-8"))
            price = data.get("close") or data.get("adjusted_close")
            if price and str(price) not in ("NA", "None", "") and float(price) > 0:
                return float(price)
        return None
    except Exception:
        return None

def fetch_price_stooq(ticker):
    """Fallback gratuito: obtiene precio de Stooq (sin API key).
    Cubre ETFs europeos (Xetra, LSE, Euronext) que fallan en yfinance.
    URL: https://stooq.com/q/l/?s=btic.de&f=sd2t2ohlcv&h&e=csv
    """
    try:
        import urllib.request, io
        url = "https://stooq.com/q/l/?s={}&f=sd2t2ohlcv&h&e=csv".format(ticker.lower())
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            content = r.read().decode("utf-8")
        import csv as csv_mod, io as io_mod
        rows = list(csv_mod.DictReader(io_mod.StringIO(content)))
        if not rows:
            return None
        close = rows[0].get("Close") or rows[0].get("close")
        if close and close.strip() not in ("N/D", "", "N/A"):
            return float(close)
        return None
    except Exception:
        return None

def fetch_price_morningstar(isin):
    """Obtiene precio de Morningstar por ISIN.
    Cubre fondos de inversión europeos (ES, IE, LU) no disponibles en yfinance/EODHD.
    Prueba primero el universo español, luego fondos europeos de IE/LU.
    """
    if not isin:
        return None
    try:
        import urllib.request, json
        # Universos por prefijo ISIN: España, Irlanda, Luxemburgo, RU
        isin_upper = isin.upper()
        if isin_upper.startswith("ES"):
            universes = ["FOESP%24%24ALL", "ETFES%24%24ALL"]
        elif isin_upper.startswith("IE"):
            universes = ["FOEIE%24%24ALL", "ETFIE%24%24ALL", "ETFEUR%24%24ALL"]
        elif isin_upper.startswith("LU"):
            universes = ["FOELU%24%24ALL"]
        elif isin_upper.startswith("GB") or isin_upper.startswith("JE"):
            universes = ["FOEUK%24%24ALL", "ETFEUR%24%24ALL"]
        else:
            universes = ["ETFEUR%24%24ALL", "FOEIE%24%24ALL", "FOELU%24%24ALL"]
        for universe in universes:
            url = (
                "https://lt.morningstar.com/api/rest.svc/klr5zyak8x/security/screener"
                "?page=1&pageSize=5&outputType=json&version=1&languageId=es-ES&currencyId=EUR"
                f"&universeIds={universe}"
                "&securityDataPoints=SecId%7CLegalName%7CClosePrice%7CISIN"
                f"&filters=ISIN%3AIN%3A{isin}"
            )
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode("utf-8"))
            rows = data.get("rows", [])
            for row in rows:
                price = row.get("ClosePrice")
                if price and str(price) not in ("None", "N/A", "", "nan") and float(price) > 0:
                    return float(price)
        return None
    except Exception:
        return None

def get_price(yahoo_ticker, historico_ticker, ticker, yaml_prices,
              eodhd_ticker=None, eodhd_api_key=None, isin=None):
    """
    Prioridad de precio:
      1. yfinance      — rápido, gratuito
      2. EODHD         — de pago, excelente cobertura europea y fondos UCITS
      3. Stooq         — gratuito, fallback ETFs europeos
      4. Morningstar   — gratuito por ISIN, cubre fondos ES/IE/LU no en Yahoo
      5. precios_actuales[yahoo_ticker / historico_ticker / ticker]  — YAML manual
    """
    real = fetch_price_yfinance(yahoo_ticker)
    if real:
        return real, "yfinance"
    eodhd_p = fetch_price_eodhd(eodhd_ticker or yahoo_ticker, eodhd_api_key)
    if eodhd_p:
        return eodhd_p, "eodhd"
    stooq = fetch_price_stooq(yahoo_ticker)
    if stooq:
        return stooq, "stooq"
    ms = fetch_price_morningstar(isin or ticker)
    if ms:
        return ms, "morningstar"
    for key in (yahoo_ticker, historico_ticker, ticker):
        if key and key in yaml_prices:
            return float(yaml_prices[key]), "yaml"
    return None, "none"

# ── CSV helpers ────────────────────────────────────────────────────────────────
HEADERS = ["fecha", "precio_cierre", "fuente", "notas"]

def ensure_csv(path: Path):
    """Crea el CSV con cabecera si no existe."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(HEADERS)
        print(f"  ✦ Creado {path}")

def already_recorded(path: Path, today: str) -> bool:
    """Devuelve True si ya hay registro para la fecha de hoy."""
    if not path.exists():
        return False
    with open(path, "r", encoding="utf-8") as f:
        return any(row.get("fecha") == today for row in csv.DictReader(f))

def ensure_trailing_newline(path: Path):
    """
    Fix: garantiza que el fichero termina en \\n antes de un append.
    Sin esto, la nueva fila CSV se concatena a la última línea existente.
    """
    if not path.exists() or path.stat().st_size == 0:
        return
    with open(path, "rb") as f:
        f.seek(-1, 2)
        last_byte = f.read(1)
    if last_byte not in (b"\n", b"\r"):
        with open(path, "ab") as f:
            f.write(b"\n")

def append_price(path: Path, fecha: str, precio: float, fuente: str,
                 notas: str = "", force: bool = False):
    """Añade una fila al CSV. Si force=True borra primero la entrada de esa fecha."""
    if force and path.exists():
        rows = read_history(path)
        rows = [r for r in rows if r.get("fecha") != fecha]
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(HEADERS)
            for r in rows:
                w.writerow([r["fecha"], r["precio_cierre"],
                            r.get("fuente", ""), r.get("notas", "")])

    ensure_trailing_newline(path)   # ← Fix del bug de newline
    with open(path, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([fecha, f"{precio:.6f}", fuente, notas])

def read_history(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))

# ── Tipos de cambio ────────────────────────────────────────────────────────────
def fetch_fx_to_eur(ccy: str) -> float | None:
    """Devuelve cuántos EUR vale 1 unidad de `ccy`.
    Intenta primero {CCY}EUR=X directamente; si falla, invierte EUR{CCY}=X.
    """
    # Intento directo: USDEUR=X
    rate = fetch_price_yfinance(f"{ccy}EUR=X")
    if rate and rate > 0:
        return rate
    # Fallback: EURUSD=X invertido
    inv = fetch_price_yfinance(f"EUR{ccy}=X")
    if inv and inv > 0:
        return round(1.0 / inv, 6)
    return None

def record_fx_rates(activos: list, hist_dir: Path,
                    today: str, force: bool = False):
    """Graba el tipo de cambio CCY→EUR para cada divisa extranjera del portfolio.
    Los ficheros se guardan como historico/USDEUR.csv, GBPEUR.csv, etc.
    """
    foreign_ccys = sorted({a.get("divisa", "EUR")
                            for a in activos
                            if a.get("divisa", "EUR") != "EUR"})
    if not foreign_ccys:
        return

    print(f"\n  ── Tipos de cambio ──────────────────────────────────")
    for ccy in foreign_ccys:
        csv_path = hist_dir / f"{ccy}EUR.csv"
        ensure_csv(csv_path)

        if already_recorded(csv_path, today) and not force:
            print(f"  ⏭  FX {ccy}/EUR        ya registrado hoy")
            continue

        rate = fetch_fx_to_eur(ccy)
        if rate and rate > 0:
            append_price(csv_path, today, rate, "yfinance", force=force)
            print(f"  ✓  FX {ccy}/EUR  {rate:.6f}  → {csv_path.name}")
        else:
            print(f"  ✗  FX {ccy}/EUR  sin precio disponible")

# ── Main recorder ──────────────────────────────────────────────────────────────
def record_prices(yaml_path: str, hist_dir: str = "historico",
                  force: bool = False, show: bool = False):
    yaml_path = Path(yaml_path)
    hist_dir  = Path(hist_dir)
    today     = date.today().isoformat()

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    activos        = data.get("activos") or []
    yaml_prices    = {k: float(v) for k, v in (data.get("precios_actuales") or {}).items()
                      if v is not None}
    eodhd_api_key  = (data.get("configuracion") or {}).get("eodhd_api_key")

    print(f"\n{'═'*60}")
    print(f"  PORTFOLIO PRICE RECORDER · {today}")
    print(f"  Fuente YAML: {yaml_path}")
    print(f"  Directorio : {hist_dir}/")
    if eodhd_api_key:
        print(f"  EODHD      : activo ✓")
    print(f"{'═'*60}")

    results       = []
    recorded_csvs = set()   # evita grabar dos veces el mismo fichero (ej. BTC wallets)
    fx_cache      = {}      # {ccy: rate} — tipos de cambio ya descargados este run

    for a in activos:
        ticker           = a["ticker"]
        yahoo_ticker     = a.get("yahoo_ticker",     ticker)
        historico_ticker = a.get("historico_ticker", ticker)
        eodhd_ticker     = a.get("eodhd_ticker")
        isin             = a.get("isin", ticker)
        divisa           = a.get("divisa", "EUR")
        csv_path         = hist_dir / f"{historico_ticker.replace('/', '-')}.csv"

        # Activos con historico compartido (ej. BTCW1/2/3 → BTC-EUR.csv)
        if str(csv_path) in recorded_csvs:
            print(f"  ⤷  {ticker:<16} comparte histórico con {historico_ticker} (ya grabado)")
            results.append({"ticker": ticker, "status": "shared"})
            continue

        ensure_csv(csv_path)

        if already_recorded(csv_path, today) and not force:
            print(f"  ⏭  {ticker:<16} ya registrado hoy  (--force para sobreescribir)")
            results.append({"ticker": ticker, "status": "skip"})
            recorded_csvs.add(str(csv_path))
            continue

        precio, fuente = get_price(yahoo_ticker, historico_ticker, ticker, yaml_prices,
                                   eodhd_ticker=eodhd_ticker, eodhd_api_key=eodhd_api_key,
                                   isin=isin)

        if precio is None:
            print(f"  ✗  {ticker:<16} sin precio disponible")
            results.append({"ticker": ticker, "status": "error"})
            continue

        # ── Conversión USD→EUR (y otras divisas) ────────────────────────────
        notas_extra = ""
        precio_guardado = precio
        if divisa != "EUR":
            if divisa not in fx_cache:
                fx_cache[divisa] = fetch_fx_to_eur(divisa)
            fx_rate = fx_cache.get(divisa)
            if fx_rate and fx_rate > 0:
                precio_guardado = round(precio * fx_rate, 6)
                notas_extra = f"nativo={precio:.4f}{divisa}"
            else:
                notas_extra = f"SIN_FX_{divisa}"
                print(f"  ⚠  {ticker:<16} sin FX {divisa}/EUR, guardando precio nativo")

        append_price(csv_path, today, precio_guardado, fuente, notas=notas_extra, force=force)
        label = f"yahoo={yahoo_ticker}" if yahoo_ticker != ticker else ticker
        if divisa != "EUR" and notas_extra.startswith("nativo="):
            print(f"  ✓  {ticker:<16} {precio:>10.4f} {divisa} → €{precio_guardado:>10.4f}  [{fuente}]  → {csv_path.name}")
        else:
            print(f"  ✓  {ticker:<16} {precio_guardado:>14.4f}  [{fuente}]  → {csv_path.name}  ({label})")
        results.append({"ticker": ticker, "precio": precio_guardado, "fuente": fuente, "status": "ok"})
        recorded_csvs.add(str(csv_path))

    ok    = sum(1 for r in results if r["status"] == "ok")
    skip  = sum(1 for r in results if r["status"] in ("skip", "shared"))
    error = sum(1 for r in results if r["status"] == "error")

    print(f"\n  Grabados: {ok}  Omitidos/compartidos: {skip}  Errores: {error}")

    # ── Tipos de cambio para divisas extranjeras ──
    record_fx_rates(activos, hist_dir, today, force=force)

    print(f"\n{'═'*60}\n")

    if show:
        show_summary(hist_dir, activos)

    return results

# ── Show summary ───────────────────────────────────────────────────────────────
def show_summary(hist_dir, activos):
    hist_dir = Path(hist_dir)
    seen     = set()
    print(f"\n{'─'*60}")
    print(f"  RESUMEN HISTÓRICO")
    print(f"{'─'*60}")

    for a in activos:
        ticker           = a["ticker"]
        historico_ticker = a.get("historico_ticker", ticker)
        csv_path         = hist_dir / f"{historico_ticker.replace('/', '-')}.csv"

        if str(csv_path) in seen:
            continue
        seen.add(str(csv_path))

        rows = read_history(csv_path)
        if not rows:
            print(f"  {ticker:<16} sin datos")
            continue

        precios = [float(r["precio_cierre"]) for r in rows if r.get("precio_cierre")]
        fechas  = [r["fecha"] for r in rows]
        if not precios:
            continue

        p_last  = precios[-1]
        p_first = precios[0]
        p_min   = min(precios)
        p_max   = max(precios)
        pct     = (p_last - p_first) / p_first * 100 if p_first else 0
        sign    = "+" if pct >= 0 else ""
        n       = len(precios)
        hoy     = date.today().isoformat()
        age     = (date.fromisoformat(hoy) - date.fromisoformat(fechas[-1])).days
        age_s   = ("hoy" if age == 0 else "ayer" if age == 1 else f"+{age}d")

        print(f"\n  {ticker}  [{csv_path.name}]")
        print(f"    Registros : {n} días ({fechas[0]} → {fechas[-1]})  actualiz: {age_s}")
        print(f"    Último    : {p_last:.4f}")
        print(f"    Variación : {sign}{pct:.2f}% desde inicio")
        print(f"    Min/Max   : {p_min:.4f} / {p_max:.4f}")

        if len(precios) >= 2:
            mn, mx  = min(precios), max(precios)
            rng     = mx - mn or 1
            bars    = "▁▂▃▄▅▆▇█"
            spark   = "".join(bars[min(7, int((p - mn) / rng * 7))] for p in precios[-30:])
            print(f"    Tendencia : {spark}")

    print(f"\n{'─'*60}\n")

# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Portfolio Price Recorder v2.0")
    parser.add_argument("-f", "--file",   default="portfolio.yaml", help="Ruta al portfolio.yaml")
    parser.add_argument("-d", "--dir",    default="historico",       help="Directorio CSV (default: historico/)")
    parser.add_argument("--force",        action="store_true",       help="Sobreescribir registro de hoy")
    parser.add_argument("--show",         action="store_true",       help="Mostrar resumen tras grabar")
    parser.add_argument("--summary-only", action="store_true",       help="Solo mostrar resumen, no grabar")
    args = parser.parse_args()

    if not Path(args.file).exists():
        print(f"\n  ✗ No se encuentra: {args.file}")
        print(f"    Uso: python3 price_recorder.py -f /ruta/portfolio.yaml\n")
        sys.exit(1)

    if args.summary_only:
        with open(args.file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        show_summary(Path(args.dir), data.get("activos") or [])
    else:
        record_prices(args.file, args.dir, force=args.force, show=args.show)
