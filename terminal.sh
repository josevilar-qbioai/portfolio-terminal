#!/bin/bash
# ══════════════════════════════════════════════════════════════
#  PORTFOLIO TERMINAL · Jose Vilar
#  Uso: ./terminal.sh              → actualiza precios + abre dashboard
#       ./terminal.sh --no-prices  → abre dashboard sin actualizar precios
# ══════════════════════════════════════════════════════════════

CONFIG="portfolio.yaml"
HIST="historico"
SKIP_PRICES=0
SKIP_MACRO=0

# ── Parsear argumentos ─────────────────────────────────────────
for arg in "$@"; do
    case $arg in
        --no-prices) SKIP_PRICES=1 ;;
        --no-macro)  SKIP_MACRO=1  ;;
    esac
done

# ── Verificar portfolio.yaml ───────────────────────────────────
if [ ! -f "$CONFIG" ]; then
    echo "❌  No se encuentra $CONFIG en este directorio."
    echo "    Ejecuta el script desde la carpeta Cartera-Inversion/"
    exit 1
fi

# ── Actualizar precios ─────────────────────────────────────────
if [ "$SKIP_PRICES" -eq 0 ]; then
    echo ""
    echo "📡  Actualizando precios históricos..."
    python3 scripts/price_recorder.py -f "$CONFIG" -d "$HIST"
fi

# ── Actualizar indicadores macro ───────────────────────────────
if [ "$SKIP_MACRO" -eq 0 ]; then
    echo ""
    echo "🌍  Actualizando indicadores macroeconómicos..."
    python3 scripts/macro_recorder.py -d "$HIST" 2>/dev/null || \
        echo "    (macro_recorder omitido — instala yfinance para activarlo)"
fi

# ── Lanzar dashboard ───────────────────────────────────────────
echo "🚀  Iniciando dashboard..."
python3 scripts/portfolio_dash.py -f "$CONFIG" -d "$HIST"
