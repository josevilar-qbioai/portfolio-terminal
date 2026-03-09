#!/usr/bin/env python3
"""
fx_convert_historical.py — Convierte históricos USD→EUR en los CSVs del portfolio.
════════════════════════════════════════════════════════════════════════════════════

Para cada activo con divisa USD que tenga un CSV histórico, descarga el histórico
del tipo de cambio EURUSD=X desde Yahoo Finance y convierte cada precio diario
de USD a EUR usando la tasa del mismo día (fallback ±5 días hábiles).

Los precios originales en USD se preservan en la columna `notas` como `usd=XXXX`.
La columna `fuente` cambia a `usd_to_eur` para que las filas ya convertidas no se
procesen de nuevo en ejecuciones futuras.

Uso:
  python3 scripts/fx_convert_historical.py -f portfolio.yaml -d historico
  python3 scripts/fx_convert_historical.py -f portfolio.yaml -d historico --dry-run
  python3 scripts/fx_convert_historical.py -f portfolio.yaml -d historico --ticker JE00B1VS3W29
"""

import argparse
import csv
import sys
from pathlib import Path
from datetime import datetime, timedelta, date

import yaml

# ── Helpers yfinance ───────────────────────────────────────────────────────────

def load_eurusd_history() -> dict:
    """Descarga el histórico completo de EURUSD=X con yfinance.
    Devuelve dict {date_str: usd_to_eur_rate} (p.ej. "2024-03-15" → 0.9236).
    """
    try:
        import yfinance as yf
    except ImportError:
        print("ERROR: yfinance no está instalado.")
        print("       pip install yfinance")
        sys.exit(1)

    print("Descargando histórico EURUSD=X desde Yahoo Finance…")
    ticker = yf.Ticker("EURUSD=X")
    df = ticker.history(period="max", auto_adjust=True)

    if df.empty:
        print("ERROR: No se pudo obtener el histórico de EURUSD=X.")
        sys.exit(1)

    fx = {}
    for ts, row in df.iterrows():
        day = ts.strftime("%Y-%m-%d")
        eur_usd = float(row["Close"])
        if eur_usd and eur_usd > 0:
            fx[day] = round(1.0 / eur_usd, 8)   # USDEUR = 1 / EURUSD

    first = min(fx.keys())
    last  = max(fx.keys())
    print(f"  {len(fx):,} días descargados  ({first} → {last})")
    return fx


def get_fx_rate(fx_dict: dict, date_str: str, max_days: int = 5) -> float | None:
    """Devuelve la tasa USDEUR para date_str.
    Si no existe (finde, festivo), busca en ±max_days días, priorizando antes que después.
    """
    if date_str in fx_dict:
        return fx_dict[date_str]

    dt = datetime.strptime(date_str, "%Y-%m-%d")
    for delta in range(1, max_days + 1):
        for sign in (-1, 1):
            candidate = (dt + timedelta(days=delta * sign)).strftime("%Y-%m-%d")
            if candidate in fx_dict:
                return fx_dict[candidate]
    return None


# ── Conversión CSV ─────────────────────────────────────────────────────────────

HEADERS = ["fecha", "precio_cierre", "fuente", "notas"]


def convert_csv(csv_path: Path, fx_dict: dict, dry_run: bool = False) -> dict:
    """Convierte los precios USD→EUR en un CSV histórico.

    Omite filas ya convertidas (fuente == 'usd_to_eur').
    Preserva el USD original en notas como `usd=XXXX`.

    Devuelve un dict con estadísticas: converted, skipped, missing_fx, errors.
    """
    stats = {"converted": 0, "skipped": 0, "missing_fx": 0, "errors": 0}

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        return stats

    new_rows = []
    for row in rows:
        fuente = row.get("fuente", "")

        # Ya convertida → no tocar
        if fuente == "usd_to_eur":
            new_rows.append(row)
            stats["skipped"] += 1
            continue

        date_str = row.get("fecha", "").strip()
        raw      = row.get("precio_cierre", "").strip()

        if not date_str or not raw:
            new_rows.append(row)
            stats["errors"] += 1
            continue

        try:
            precio_usd = float(raw)
        except ValueError:
            new_rows.append(row)
            stats["errors"] += 1
            continue

        fx_rate = get_fx_rate(fx_dict, date_str)
        if fx_rate is None:
            # Sin FX: dejar intacta y avisar
            new_rows.append(row)
            stats["missing_fx"] += 1
            print(f"  WARN {date_str}: sin tasa FX, fila no convertida")
            continue

        precio_eur = round(precio_usd * fx_rate, 6)
        notas_orig = row.get("notas", "").strip()
        notas_new  = f"usd={precio_usd:.4f}" + (f" | {notas_orig}" if notas_orig else "")

        new_rows.append({
            "fecha":         date_str,
            "precio_cierre": f"{precio_eur:.6f}",
            "fuente":        "usd_to_eur",
            "notas":         notas_new,
        })
        stats["converted"] += 1

    if not dry_run:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=HEADERS)
            w.writeheader()
            for r in new_rows:
                w.writerow({k: r.get(k, "") for k in HEADERS})

    return stats


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Convierte históricos USD→EUR en los CSVs del portfolio."
    )
    parser.add_argument("-f", "--file",   default="portfolio.yaml",
                        help="Ruta al portfolio.yaml (default: portfolio.yaml)")
    parser.add_argument("-d", "--dir",    default="historico",
                        help="Directorio con los CSVs (default: historico/)")
    parser.add_argument("--dry-run",      action="store_true",
                        help="Simula la conversión sin modificar ficheros")
    parser.add_argument("--ticker",       default=None,
                        help="Convertir solo este ticker/ISIN (ej. JE00B1VS3W29)")
    args = parser.parse_args()

    yaml_path = Path(args.file)
    hist_dir  = Path(args.dir)

    # Hacer los paths relativos al directorio del YAML si no son absolutos
    if not yaml_path.is_absolute():
        yaml_path = Path.cwd() / yaml_path
    if not hist_dir.is_absolute():
        hist_dir = yaml_path.parent / args.dir

    if not yaml_path.exists():
        print(f"ERROR: No se encuentra {yaml_path}")
        sys.exit(1)

    with open(yaml_path, encoding="utf-8") as f:
        portfolio = yaml.safe_load(f)

    activos = portfolio.get("activos") or []

    # ── Identificar activos USD con CSV propio ──
    usd_assets = []
    seen_csvs  = set()
    for a in activos:
        if a.get("divisa", "EUR") != "USD":
            continue
        ticker           = a["ticker"]
        historico_ticker = a.get("historico_ticker", ticker)

        # Filtrar por --ticker si se especificó
        if args.ticker and args.ticker not in (ticker, historico_ticker):
            continue

        csv_path = hist_dir / f"{historico_ticker}.csv"
        if str(csv_path) in seen_csvs:
            continue
        seen_csvs.add(str(csv_path))

        if not csv_path.exists():
            print(f"  ⚠  {ticker}: {csv_path.name} no existe, omitido")
            continue

        usd_assets.append((ticker, historico_ticker, csv_path))

    if not usd_assets:
        print("No se encontraron activos USD con CSV histórico para convertir.")
        return

    print(f"\nActivos USD a convertir: {[t for t,_,_ in usd_assets]}")
    if args.dry_run:
        print("MODO DRY-RUN — no se modificará ningún fichero\n")
    else:
        print()

    # ── Descargar histórico de tipos de cambio ──
    fx_dict = load_eurusd_history()
    print()

    # ── Convertir cada CSV ──
    total_conv  = 0
    total_skip  = 0
    total_miss  = 0
    total_errs  = 0

    for ticker, hist_ticker, csv_path in usd_assets:
        print(f"Procesando {ticker}  ({csv_path.name})…")
        s = convert_csv(csv_path, fx_dict, dry_run=args.dry_run)
        print(f"  → convertidas: {s['converted']}  ya-EUR: {s['skipped']}  "
              f"sin-FX: {s['missing_fx']}  errores: {s['errors']}")

        # Mostrar primera y última fila convertida para verificación
        if not args.dry_run and s["converted"] > 0:
            with open(csv_path, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            converted_rows = [r for r in rows if r.get("fuente") == "usd_to_eur"]
            if converted_rows:
                r0 = converted_rows[0]
                r1 = converted_rows[-1]
                print(f"     primera: {r0['fecha']}  {r0['notas'].split('|')[0].strip()}  → €{r0['precio_cierre']}")
                print(f"     última:  {r1['fecha']}  {r1['notas'].split('|')[0].strip()}  → €{r1['precio_cierre']}")
        print()

        total_conv += s["converted"]
        total_skip += s["skipped"]
        total_miss += s["missing_fx"]
        total_errs += s["errors"]

    # ── Resumen final ──
    print("═" * 56)
    print(f"  TOTAL  convertidas: {total_conv}  ya-EUR: {total_skip}  "
          f"sin-FX: {total_miss}  errores: {total_errs}")
    if args.dry_run:
        print("  DRY-RUN — ejecuta sin --dry-run para aplicar los cambios.")
    else:
        print("  Conversión completada. Los CSVs ahora almacenan precios en EUR.")
        print("  El precio USD original queda en la columna 'notas' (usd=XXXX).")
    print("═" * 56)


if __name__ == "__main__":
    main()
