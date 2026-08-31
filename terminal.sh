#!/bin/bash
# ══════════════════════════════════════════════════════════════
#  PORTFOLIO TERMINAL · Jose Vilar
#  Uso: ./terminal.sh              → actualiza precios + abre dashboard
#       ./terminal.sh --no-prices  → abre dashboard sin actualizar precios
# ══════════════════════════════════════════════════════════════

# ── Activar entorno conda ──────────────────────────────────────
CONDA_ENV="cartera"
if command -v conda &>/dev/null; then
    source "$(conda info --base)/etc/profile.d/conda.sh" 2>/dev/null
    if conda env list 2>/dev/null | grep -q "^${CONDA_ENV}"; then
        conda activate "$CONDA_ENV" 2>/dev/null
    else
        echo "⚠️  Entorno conda '$CONDA_ENV' no encontrado — usando Python del sistema"
        echo "    Créalo con: conda create -n cartera python=3.11 && conda activate cartera && pip install pyyaml yfinance textual requests"
    fi
fi

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
