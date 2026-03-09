# 📊 Portfolio Terminal

Dashboard interactivo de inversiones para terminal, construido con [Textual](https://textual.textualize.io/).

Gestiona ETFs, fondos indexados y criptomonedas con histórico de precios en CSV, métricas avanzadas y un panel de indicadores macroeconómicos en tiempo real.

---

## ✨ Características

- **9 pestañas interactivas**: resumen, posiciones, gráficos históricos, transacciones, TIR/XIRR, métricas de riesgo, costes TER, benchmark y macro
- **Grabado automático de precios** desde Yahoo Finance, EODHD, Stooq y Morningstar
- **Métricas financieras**: Sharpe, Sortino, Beta, VaR 95%, drawdown, volatilidad, correlación
- **TIR anualizada (XIRR)** ponderada por flujos de caja reales
- **Análisis de costes TER** con proyección a 5 y 10 años
- **Benchmark** vs cualquier fondo indexado global de tu cartera
- **Panel macro** con 17 indicadores: VIX, curva de tipos, USD, oro, petróleo, cobre, uranio, gas, semiconductores, utilities y Bitcoin
- **Modo privado** (`P`) para ocultar cifras en pantalla
- **Sin servidor** — todo corre en local, tus datos no salen de tu ordenador

---

## 🚀 Instalación

### Requisitos

- Python 3.9 o superior

### 1. Clona el repositorio

```bash
git clone https://github.com/TU_USUARIO/portfolio-terminal.git
cd portfolio-terminal
```

### 2. Instala las dependencias

```bash
pip install textual yfinance pyyaml requests rich
```

Opcionalmente, para exportar a Excel:

```bash
pip install openpyxl
```

### 3. Crea tu fichero de cartera

```bash
cp portfolio.example.yaml portfolio.yaml
```

Edita `portfolio.yaml` con tus activos y transacciones. El fichero de ejemplo incluye comentarios detallados en cada campo.

### 4. Crea las carpetas necesarias

```bash
mkdir -p historico exports
```

### 5. Lanza el dashboard

```bash
./terminal.sh
```

O directamente:

```bash
python3 scripts/portfolio_dash.py -f portfolio.yaml -d historico
```

---

## 📁 Estructura del proyecto

```
portfolio-terminal/
├── portfolio.example.yaml   ← Plantilla de cartera (copia a portfolio.yaml)
├── portfolio.yaml           ← Tu cartera personal (ignorada por .gitignore)
├── terminal.sh              ← Lanzador: graba precios + macro + abre dashboard
├── historico/               ← CSVs de precios diarios (ignorados por .gitignore)
├── exports/                 ← Informes Excel generados (ignorados por .gitignore)
└── scripts/
    ├── portfolio_dash.py         ← Dashboard interactivo (Textual)
    ├── price_recorder.py         ← Grabador de precios al cierre de mercado
    ├── macro_recorder.py         ← Grabador de indicadores macroeconómicos
    ├── fx_convert_historical.py  ← Conversión USD→EUR en CSVs existentes
    └── export_historico.py       ← Exportador a Excel + Markdown
```

---

## ⌨️ Controles del dashboard

| Tecla | Acción |
|-------|--------|
| `1`–`9` | Cambiar entre pestañas |
| `R` | Recargar datos |
| `P` | Modo privado (oculta cifras) |
| `A` | Añadir transacción |
| `E` | Editar transacción (buscador con filtro en tiempo real) |
| `D` | Borrar transacción (buscador + confirmación) |
| `T` | Cambiar rango del gráfico histórico |
| `F` | Filtrar posiciones por taxonomía |
| `Q` | Salir |

---

## 📋 Configurar tus activos

Edita `portfolio.yaml` con tus activos. Ejemplo mínimo:

```yaml
meta:
  nombre: "Mi Portafolio"
  divisa_base: EUR

activos:
  - ticker: IE00B03HCZ61
    nombre: "Vanguard Global Stock Index EUR Acc"
    tipo: Fondo
    taxonomia: Renta Variable
    divisa: EUR
    ter: 0.0012
    transacciones:
      - fecha: "2024-01-15"
        tipo: compra
        participaciones: 10.000000
        precio: 42.50
        comision: 0.00
        nota: "Primera aportación"
```

### Tipos de activo soportados

| `tipo` | Descripción |
|--------|-------------|
| `ETF` | ETF cotizado en bolsa |
| `Fondo` | Fondo de inversión no cotizado |
| `Crypto` | Criptomoneda |

### Taxonomías incluidas por defecto

`Renta Variable` · `Metal Precioso` · `Metal` · `Tecnología / AI` · `Energía / Nuclear` · `Computación Cuántica` · `Bitcoin`

Puedes usar cualquier texto como taxonomía — el filtro de posiciones (`F`) las agrupa automáticamente.

---

## 📈 Grabar precios

```bash
# Grabar precio de cierre de hoy
python3 scripts/price_recorder.py -f portfolio.yaml -d historico --show

# Actualizar indicadores macroeconómicos
python3 scripts/macro_recorder.py -d historico --show

# Todo a la vez (lo hace terminal.sh automáticamente)
./terminal.sh
```

---

## 🔧 Opciones avanzadas de activos

### Activos en divisa extranjera (USD, GBP…)

Los precios se almacenan siempre en EUR. El grabador descarga el tipo de cambio diario y convierte automáticamente. El precio original queda en la columna `notas` del CSV.

```yaml
  - ticker: IVV
    nombre: "iShares Core S&P 500 ETF"
    divisa: USD   # el grabador convierte a EUR usando USDEUR diario
```

### Múltiples activos compartiendo el mismo histórico

Útil para varias wallets de Bitcoin o cuentas del mismo activo:

```yaml
  - ticker: BTC-WALLET-1
    yahoo_ticker: BTC-EUR
    historico_ticker: BTC-EUR   # comparte CSV con BTC-WALLET-2

  - ticker: BTC-WALLET-2
    yahoo_ticker: BTC-EUR
    historico_ticker: BTC-EUR
```

### Fondos no disponibles en Yahoo Finance

Usa el campo `isin` para que el grabador los busque vía Morningstar (fondos IE, LU, ES):

```yaml
  - ticker: LU0996182563
    isin: LU0996182563
    nombre: "Amundi IS MSCI World AE-C"
    tipo: Fondo
    divisa: EUR
```

### API key EODHD (opcional)

Para ETFs europeos con cobertura limitada en Yahoo, obtén una clave gratuita en [eodhd.com](https://eodhd.com) (20 peticiones/día gratuitas) y añádela a `portfolio.yaml`:

```yaml
configuracion:
  eodhd_api_key: "TU_API_KEY"
```

---

## 📊 Exportar a Excel

```bash
python3 scripts/export_historico.py -f portfolio.yaml -d historico -o exports
```

Genera un fichero `.xlsx` con histórico completo, resumen de posiciones y métricas.

---

## 🤝 Contribuir

Las contribuciones son bienvenidas. Por favor:

1. Haz fork del repositorio
2. Crea una rama para tu mejora (`git checkout -b feature/mi-mejora`)
3. Abre un Pull Request describiendo los cambios

Ideas de mejora: soporte para nuevas fuentes de precio, nuevas métricas, internacionalización, tema de colores configurable.

---

## 📄 Licencia

MIT — úsalo, modifícalo y distribúyelo libremente.

---

## ⚠️ Aviso legal

Este software es una herramienta de seguimiento personal. No constituye asesoramiento financiero. Las métricas son informativas y se basan en datos históricos. Las rentabilidades pasadas no garantizan resultados futuros.
