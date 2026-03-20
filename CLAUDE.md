# CLAUDE.md — Portafolio Inversiones · Jose Vilar

> Este fichero contiene las instrucciones permanentes para Claude Cowork.
> Cuando abras esta carpeta en Cowork, Claude leerá este fichero automáticamente
> y sabrá exactamente cómo gestionar tu portafolio.

---

## 🗂️ Contexto del proyecto

Soy Jose Vilar. Esta carpeta contiene mi sistema de seguimiento de inversiones personal.
Gestiona ETFs con precios históricos en CSV y un dashboard interactivo para terminal (Textual).

**Carpeta raíz del proyecto:** la carpeta donde está este fichero `CLAUDE.md`.
Todos los comandos deben ejecutarse desde esta raíz.

---

## 📁 Estructura de ficheros

```
Cartera-Inversion/
├── CLAUDE.md                   ← Este fichero (instrucciones para Cowork)
├── portfolio.yaml              ← Base de datos de activos y transacciones
├── historico/                  ← Un CSV por activo con precios diarios
│   ├── GB00B15KXQ89.csv        ← ETF Cobre (1.844 registros desde 2015-12-28)
│   ├── JE00B1VS3W29.csv        ← WisdomTree Precious Metal (2.563 registros desde 2015-12-29)
│   ├── IE00BGV5VN51.csv        ← Xtrackers AI & Big Data (1.791 registros desde 2019-02-05)
│   ├── IE00BYZK4552.csv        ← iShares Automation & Robotics (2.359 registros desde 2016-11-03)
│   ├── IE000M7V94E1.csv        ← Uranium And Nuclear Technologies (773 registros desde 2023-02-03)
│   ├── IE000W8WMSL2.csv        ← WisdomTree Quantum Computing (92 registros desde 2025-10-09)
│   ├── BTC-EUR.csv             ← Bitcoin precio EUR (2.242 registros desde 2020-01-03) — compartido por BTC-EUR, BTCW1, BTCW2, BTCW3
│   ├── IE00B03HCZ61.csv        ← Vanguard Global Stock Index (2.061 registros desde 2018-01-02)
│   ├── IE00B42W4L06.csv        ← Vanguard Global Small-Cap Index (2.061 registros desde 2018-01-02)
│   ├── LU0996182563.csv        ← Amundi IS MSCI World AE-C (958 registros desde 2022-03-07)
│   ├── XS2376095068.csv        ← Invesco Physical Bitcoin ETC (1.034 registros desde 2021-11-30)
│   ├── GB00BJYDH287.csv        ← WisdomTree Physical Bitcoin (2.243 registros desde 2020-01-03) — derivado de BTC-EUR × entitlement
│   ├── USDEUR.csv              ← Tipo de cambio USD→EUR (grabado automáticamente por price_recorder)
│   ├── GBPEUR.csv              ← Tipo de cambio GBP→EUR (grabado automáticamente por price_recorder)
│   ├── IE000J80JTL1.csv        ← Nasdaq Clean Edge Smart Grid Infrastructure (desde 2026-03-13)
│   └── macro_snapshot.json     ← Indicadores macroeconómicos (grabado por macro_recorder)
├── terminal.sh                 ← Lanzador: graba precios + macro + abre dashboard
├── exports/                    ← Excel e informes generados
└── scripts/
    ├── portfolio_dash.py       ← Dashboard interactivo (Textual) v4.8 — controles: 1-9 tabs, R recargar, P privado, A añadir tx, E editar tx, D borrar tx, F filtro, Q salir
    ├── price_recorder.py       ← Grabador de precios al cierre
    ├── macro_recorder.py       ← Grabador de indicadores macroeconómicos (Yahoo Finance → macro_snapshot.json)
    ├── fx_convert_historical.py← Conversión histórica USD→EUR en CSVs existentes
    └── export_historico.py     ← Exportador Excel + Markdown
```

---

## 🧠 Lo que debes saber siempre

### Mis activos actuales

| Ticker | ISIN | Nombre | Tipo | Taxonomía | Divisa |
|--------|------|--------|------|-----------|--------|
| GB00B15KXQ89 | GB00B15KXQ89 | ETF Cobre | ETF | Metal | EUR |
| JE00B1VS3W29 | JE00B1VS3W29 | WisdomTree Physical Precious Metal USD | ETF | Metal Precioso | USD |
| IE00BGV5VN51 | IE00BGV5VN51 | Xtrackers Artificial Intelligence & Big Data UCITS ETF | ETF | Tecnología / AI | EUR |
| IE00BYZK4552 | IE00BYZK4552 | iShares Automation & Robotics UCITS ETF USD (Acc) | ETF | Tecnología / AI | USD |
| IE000M7V94E1 | IE000M7V94E1 | Uranium And Nuclear Technologies USD (Acc) | ETF | Energía / Nuclear | USD |
| IE000W8WMSL2 | IE000W8WMSL2 | WisdomTree Quantum Computing USD | ETF | Computación Cuántica | USD |
| XS2376095068 | XS2376095068 | Invesco Physical Bitcoin ETC | ETF | Bitcoin | EUR |
| GB00BJYDH287 | GB00BJYDH287 | WisdomTree Physical Bitcoin | ETF | Bitcoin | EUR |
| BTCBP | BTCBP | Cuenta Bitpanda Bitcoin | Crypto | Bitcoin | EUR |
| BTC-EUR | BTC | Trade Republic Bitcoin | Crypto | Bitcoin | EUR |
| BTCW1 | BTCW1 | Monedero BTC #1 (Trezor) | Crypto | Bitcoin | EUR |
| BTCW2 | BTCW2 | Monedero BTC #2 (Trezor) | Crypto | Bitcoin | EUR |
| BTCW3 | BTCW3 | Monedero BTC #3 (Trezor) | Crypto | Bitcoin | EUR |
| 0IE00B03HCZ61 | IE00B03HCZ61 | Vanguard Global Stock Index Fund € Acc | Fondo | Renta Variable | EUR |
| LU0996182563 | LU0996182563 | Amundi IS MSCI World AE-C | Fondo | Renta Variable | EUR |
| IE00B42W4L06 | IE00B42W4L06 | Vanguard Global Small-Cap Index Fund EUR Acc | Fondo | Renta Variable | EUR |
| ES0152769032 | ES0152769032 | Fondo Naranja S&P 500 (ING) | Fondo | Renta Variable | EUR |
| IE000J80JTL1 | IE000J80JTL1 | Nasdaq Clean Edge Smart Grid Infrastructure UCITS ETF | ETF | Energía / Infraestructura | EUR |

### Configuración global (portfolio.yaml)

```yaml
configuracion:
  eodhd_api_key: "TU_TOKEN"   # EODHD — fallback para ETFs europeos y fondos UCITS
```

### Campos opcionales en activos (portfolio.yaml)

- `yahoo_ticker` — ticker de Yahoo Finance (si difiere del ticker principal)
- `historico_ticker` — nombre del CSV en `historico/` (si difiere del ticker principal)
- `eodhd_ticker` — ticker EODHD para activos que no funcionan en Yahoo (ej: `BTIC.XETRA`, `IE00B03HCZ61.ETFEU`)
- `isin` — ISIN del activo; usado por Morningstar como fuente de precios para fondos (ES, IE, LU) no disponibles en Yahoo ni EODHD
- `ter` — Total Expense Ratio anual (decimal, ej: 0.0035 = 0.35%). Se usa para calcular el coste de gestión en €/año.

**Cadena de fuentes de precio** (orden de prioridad en `price_recorder.py`):
1. **yfinance** — rápido, gratuito (ETFs en Yahoo Finance)
2. **EODHD** — de pago, cobertura europea amplia (`eodhd_ticker` o `yahoo_ticker`)
3. **Stooq** — gratuito, fallback para ETFs Xetra/LSE
4. **Morningstar** — gratuito por ISIN, cubre **fondos ES/IE/LU** no cotizados en bolsa
5. **precios_actuales** en YAML — actualización manual de emergencia

Ejemplo de uso (todos los monederos BTC comparten el mismo histórico y precio):
```yaml
  - ticker: BTCW1
    yahoo_ticker: BTC-EUR
    historico_ticker: BTC-EUR
```

Fondo Naranja ING — ticker Yahoo especial:
```yaml
  - ticker: ES0152769032
    yahoo_ticker: INGDIRECTFNS.BC
    historico_ticker: ES0152769032
```

### Formato de transacciones en portfolio.yaml

```yaml
transacciones:
  - fecha: "YYYY-MM-DD"
    tipo: compra          # compra | venta
    participaciones: 0.000000
    precio: 0.00          # precio unitario en la divisa del activo
    comision: 0.00
    nota:                 # campo opcional, dejar vacío o rellenar con texto
```

### Formato del histórico CSV

```
fecha,precio_cierre,fuente,notas
2026-02-20,43.334,csv_importado,
```

### Taxonomías en uso

- `Metal` — materias primas metálicas (cobre, etc.) · pilar Escasez física
- `Metal Precioso` — oro, plata, platino, paladio · pilar Escasez física
- `Tecnología / AI` — tecnología, inteligencia artificial, robótica · pilar Autoreplicación IA
- `Computación Cuántica` — computación cuántica · pilar Autoreplicación IA
- `Energía / Nuclear` — uranio, energía nuclear · pilar Energía / Grid
- `Energía / Infraestructura` — redes eléctricas inteligentes, smart grid · pilar Energía / Grid
- `Bitcoin` — criptomoneda Bitcoin · pilar Escasez digital
- `Renta Variable` — fondos indexados globales de renta variable · pilar Resiliencia

---

## ⚡ Comandos frecuentes

Cuando me pidas alguna de estas acciones, ejecuta exactamente estos comandos:

### "Graba los precios de hoy"
```bash
python3 scripts/price_recorder.py -f portfolio.yaml -d historico --show
```
Si `yfinance` no está instalado y no hay precio disponible, pregúntame el precio actual
antes de ejecutar y actualiza `precios_actuales:` en `portfolio.yaml`.

El grabador respeta `yahoo_ticker` (para fetch) y `historico_ticker` (para el CSV).
Activos con el mismo `historico_ticker` (ej. BTCW1/2/3 → BTC-EUR.csv) solo se graban una vez.

### "Actualiza los indicadores macro"
```bash
python3 scripts/macro_recorder.py -d historico --show
```
Descarga los siguientes indicadores desde Yahoo Finance y guarda `historico/macro_snapshot.json`.
El dashboard lee este fichero para la pestaña `⑧ MACRO`.

**Indicadores descargados por `macro_recorder.py`** (organizados por pilar de la tesis):

| Pilar | Clave | Ticker YF | Qué mide |
|-------|-------|-----------|----------|
| Autoreplicación IA | SOX | ^SOX | Semiconductores Philadelphia — proxy λ, capex IA adelantado |
| Autoreplicación IA | NASDAQ | ^IXIC | NASDAQ Composite — momentum tech global |
| Autoreplicación IA | ROBO | ROBO | Robo Global Robotics & Automation ETF — proxy Ola 2 (robótica) |
| Autoreplicación IA | QTUM | QTUM | Defiance Quantum ETF — proxy Ola 3/4 (computación cuántica) |
| Escasez digital | BTC | BTC-USD | Bitcoin (USD) — reserva de valor programada |
| Energía / Grid | URANIUM | CCJ | Cameco (USD) — proxy uranio, demanda nuclear 24/7 |
| Energía / Grid | XLU | XLU | Utilities EEUU — firman PPAs con hyperscalers |
| Escasez física | COPPER | HG=F | Cobre (USD/lb) — electrificación; cada robot necesita cobre |
| Escasez física | GOLD | GC=F | Oro (USD/oz) — refugio ante devaluación fiat |
| Resiliencia | VIX | ^VIX | Volatilidad implícita S&P 500 — < 20 entorno favorable |
| Resiliencia | SPREAD | calculado | Spread 10Y−13W — > 0.3% curva normal; < 0 señal recesión |
| Resiliencia | SP500 | ^GSPC | S&P 500 — benchmark salud del mercado amplio |
| (contexto) | US13W | ^IRX | T-Bill 13 semanas — usado para calcular SPREAD |
| (contexto) | US10Y | ^TNX | Bono 10 años EEUU — usado para calcular SPREAD |
| (contexto) | EURUSD | EURUSD=X | Tipo de cambio EUR/USD |
| (contexto) | USDIDX | DX-Y.NYB | Índice dólar DXY |
| (contexto) | OIL | CL=F | Petróleo WTI (USD/bbl) |
| (contexto) | GAS | NG=F | Gas Natural (USD/MMBtu) |
| (contexto) | STOXX50 | ^STOXX50E | Euro Stoxx 50 |

> Los indicadores de **contexto** se graban en `macro_snapshot.json` pero no se muestran en la pestaña ⑧ MACRO (no son relevantes para la tesis).

### "Abre el dashboard" / "Lanza el terminal"
```bash
# Recomendado: actualiza precios + macro y abre el dashboard
./terminal.sh

# Sin actualizar precios ni macro
./terminal.sh --no-prices --no-macro

# Solo sin actualizar macro
./terminal.sh --no-macro
```

O directamente el dashboard:
```bash
python3 scripts/portfolio_dash.py -f portfolio.yaml -d historico
```
Dashboard Textual interactivo. Controles: `1-9` cambiar tab, `R` recargar, `P` modo privado, `A` añadir transacción, `E` editar transacción, `D` borrar transacción, `F` filtro, `Q` salir.

**Header:** muestra fecha/hora + indicador `⚡ ESCASEZ [barra] score% · estado` con 10 señales macro alineadas a la tesis (ver abajo).

Pestañas disponibles:
- `① RESUMEN` — visión global del portfolio
- `② POSICIONES` — detalle por activo con gráfico y filtro por taxonomía (F); oculta activos con 0 participaciones. Columna TIR muestra `< 60d` si la posición tiene menos de 60 días
- `③ TRANSACCIONES` — registro histórico completo de compras/ventas (incluye activos vendidos)
- `④ TIR / XIRR` — rentabilidad interna por activo
- `⑤ MÉTRICAS` — Sharpe, Sortino, Beta, VaR 95%, drawdown, etc.
- `⑥ COSTES` — TER anual y coste de gestión en €
- `⑦ BENCHMARK` — comparativa vs Vanguard Global / MSCI World
- `⑧ MACRO` — señales organizadas por pilar de la tesis; encabezado por la **Correlación SOX/Cobre** (detector de cambio de paradigma) + 5 bloques: Autoreplicación IA · Escasez Digital · Energía/Grid · Escasez Física · Resiliencia
- `⑨ TESIS` — modelo Cartera Escasez y Resiliencia V(t)=Capital×(1+r)^t×e^(λ·t): curvas de 3 escenarios (Base, Acelerado, Óptimo) y proyección por categoría

### Indicador ⚡ ESCASEZ (header del terminal)

Score 0–100% calculado a partir de 12 señales macro agrupadas por pilar de la tesis:

| Pilar | Señal | Verde cuando… |
|-------|-------|---------------|
| Escasez digital | BTC momentum | BTC +5% en 1 mes |
| Escasez digital | BTC vs NASDAQ | BTC bate al NASDAQ en retorno mensual |
| Autoreplicación IA | SOX semiconductores | SOX +2% en 1 mes |
| Autoreplicación IA | NASDAQ tech | NASDAQ +2% en 1 mes |
| Autoreplicación IA | ROBO robótica | ROBO +2% en 1 mes |
| Autoreplicación IA | QTUM cuántica | QTUM +3% en 1 mes |
| Energía / Grid | Uranio (Cameco) | Uranio +2% en 1 mes |
| Energía / Grid | XLU utilities | Utilities +1% en 1 mes |
| Escasez física | Cobre | Cobre +2% en 1 mes |
| Escasez física | Oro | Oro +2% en 1 mes |
| Resiliencia | Spread curva tipos | Spread 10Y−13W > +0.3% |
| Resiliencia | VIX volatilidad | VIX < 20 |

- **≥ 65%** → `TESIS EN MARCHA`
- **40–64%** → `SEÑALES MIXTAS`
- **< 40%** → `TESIS DÉBIL`

### Correlación SOX / Cobre (pestaña ⑧ MACRO)

Señal compuesta calculada automáticamente desde `chg_1mes` de SOX y COPPER. Detector de cambio de paradigma:

| Estado | Condición | Acción |
|--------|-----------|--------|
| 🟢 ERA DE CONSTRUCCIÓN | SOX ↑ y Cobre ↑ | Mantener metales + IA — tesis completa en marcha |
| 🔴 DIVERGENCIA · ALERTA | SOX ↑ / Cobre ↓ | Vigilar rotación: reducir mineras, reforzar IA pura |
| 🟡 ESCASEZ FÍSICA | SOX ↓ / Cobre ↑ | Metales fuertes — esperar confirmación de rebote en SOX |
| 🔴 CONTRACCIÓN | SOX ↓ y Cobre ↓ | Modo defensivo — esperar estabilización |

La **DIVERGENCIA** es la señal más importante: indica que la IA ha empezado a miniaturizar o sustituir materiales físicos.

### Parámetros del modelo de tesis (`portfolio.yaml`)

Los parámetros `r` y `λ` del modelo `V(t) = Capital × (1+r)^t × e^(λ·t)` se editan en la sección `tesis:` de `portfolio.yaml`. Se revisan trimestralmente:

```yaml
tesis:
  ultima_revision: "YYYY-MM-DD"
  escenarios:
    base:
      r: 0.20        # proxy: SOX trailing 12M / 100
      lam: 0.05      # releases LLM cada ~6 meses
      nota: "descripción de la calibración"
    acelerado:
      r: 0.25
      lam: 0.15      # releases cada ~3 meses · coste token cayendo 10×/año
      nota: "..."
    optimo:
      r: 0.30
      lam: 0.30      # autorreplicación confirmada
      nota: "..."
```

**Guía de calibración:**
- `r` → SOX o NASDAQ `chg_1año / 100` (ej: SOX +22% → r=0.22)
- `λ_base` → releases LLM mayor cada ~6 meses = 0.05; cada ~3 meses = 0.15
- `λ_opt` → sube cuando la IA genera arquitecturas propias o el coste/token cae >5× en un año

### "Genera el informe" / "Exporta el histórico"
```bash
python3 scripts/export_historico.py -f portfolio.yaml -d historico -o exports
```
Tras ejecutar, dime el nombre exacto de los ficheros generados en `exports/`.

### "Actualiza los precios" / "Actualiza el portfolio"
1. Busca el precio actual de cada activo en internet (Yahoo Finance, Investing.com, etc.)
2. Muéstrame los precios encontrados y la fuente antes de guardar
3. Actualiza el campo `precios_actuales:` en `portfolio.yaml`
4. Graba en el histórico: `python3 scripts/price_recorder.py -f portfolio.yaml -d historico --force`

### "Añade una transacción"
1. Pregúntame: ticker, tipo (compra/venta), número de participaciones, precio unitario, comisión, fecha y nota (opcional)
2. Muéstrame el bloque YAML resultante para confirmar antes de guardar
3. Añade la transacción en el bloque correcto de `portfolio.yaml`

### "Edita una transacción" / tecla `E` en el dashboard
1. Muestra un buscador modal con todas las transacciones
2. Escribe para filtrar por ticker, nombre, fecha, tipo o nota — la lista se actualiza en tiempo real
3. Navega con ↑↓ y pulsa Enter para seleccionar
4. El formulario se abre pre-relleno con el nombre del fondo/ETF visible
5. Al guardar: elimina la entrada original y graba la versión editada

### "Borra una transacción" / tecla `D` en el dashboard
1. Muestra el mismo buscador modal para localizar la transacción
2. Selecciona con ↑↓ + Enter
3. Aparece pantalla de confirmación con el detalle completo (nombre del fondo, fecha, tipo, participaciones, precio, nota)
4. Confirma con `Sí` o cancela con `No` / Esc

### "¿Cómo va mi portfolio?" / "Resumen"
Calcula y muéstrame:
- Valor actual vs invertido y ganancia/pérdida en € y %
- Desglose por activo
- Rentabilidad por período si hay histórico disponible (1M, 3M, 6M, 1A)
- Advertencia si el precio en `precios_actuales` tiene más de 1 día de antigüedad

### "Informe mensual" / "Informe de [mes]"
1. Actualiza los precios
2. Ejecuta el exportador
3. Abre la carpeta `exports/` para que pueda ver los ficheros generados
4. Dame un resumen en texto del período: rentabilidad, máximos, mínimos, transacciones del mes

### "Añade cotizaciones" (cuando te paso un CSV)
Si me ves subir un fichero CSV con cotizaciones:
1. Detecta el formato (columnas, separador, formato de fecha y número)
2. Convierte al formato del sistema: `fecha,precio_cierre,fuente,notas`
   - Fechas: YYYY-MM-DD
   - Precios: punto decimal (no coma)
   - fuente: `csv_importado`
3. Guarda en `historico/ISIN.csv` — si ya existe, añade solo los registros nuevos (sin duplicar fechas)
4. Confirma cuántos registros nuevos se añadieron

---

## 📐 Cálculos importantes

### Precio medio de compra
```
precio_medio = sum(participaciones * precio + comision) / sum(participaciones)
```

### Ganancia/Pérdida
```
ganancia_€ = (participaciones_totales * precio_actual) - total_invertido
ganancia_% = ganancia_€ / total_invertido * 100
```

### TIR (XIRR)
- Solo es representativa con **más de 60 días** desde la primera compra
- Si el período es inferior, el dashboard muestra `< 60d` en la columna TIR (② POSICIONES) y en la pestaña ④ TIR muestra el retorno simple con nota `⚠ Xd — XIRR no representativo hasta 60d`
- Esta regla aplica **automáticamente** a todas las posiciones actuales y futuras — no requiere configuración manual
- El script `portfolio_dash.py` la calcula y filtra automáticamente

---

## ⚠️ Reglas importantes

1. **Nunca borres datos del histórico.** Si hay que corregir un precio, edita la línea existente, no la elimines.
2. **Antes de modificar `portfolio.yaml`**, muéstrame siempre el cambio propuesto y espera confirmación.
3. **Los precios en `precios_actuales:`** son de referencia manual. Indícame siempre la fecha del precio que estás usando.
4. **Si un ticker no tiene histórico CSV**, avísame y sugiere cómo descargarlo (Yahoo Finance, Investing.com).
5. **Formato de números en YAML:** usa punto como decimal (47.35, no 47,35) y sin separador de miles.
6. **Si hay un error en un script**, muéstrame el traceback completo antes de intentar corregirlo.
7. **El fichero de histórico se nombra con el ISIN** del activo (ej. `GB00B15KXQ89.csv`). Para activos con `historico_ticker`, el fichero se llama `<historico_ticker>.csv`.
8. **BTC-EUR compartido**: Los cuatro activos Bitcoin (BTC-EUR, BTCW1, BTCW2, BTCW3) usan `historico/BTC-EUR.csv` y el mismo precio. Si hay que grabar precio BTC, solo se graba una vez en ese fichero.
9. **Los CSV de activos USD se almacenan en EUR** (convertidos automáticamente por `price_recorder.py`). El precio nativo en USD queda en la columna `notas` como `nativo=XX.XXXXUSD`.

---

## 🤖 Cómo responderme

- Sé **conciso**: dame los números directamente, sin explicaciones largas.
- Cuando calcules rentabilidades, usa siempre el formato: `€ X.XXX,XX (+X,XX%)`.
- Si necesitas un dato que no tienes (precio actual, nueva transacción), **pregunta primero**, no inventes.
- Al terminar una tarea que modifica ficheros, confirma qué ficheros has cambiado y qué contienen.

---

## 📅 Rutina diaria sugerida

```
Cada vez que abras el terminal → ./terminal.sh
Fin de mes                     → "Genera el informe de [mes]"
Tras operar                    → "Añade una transacción"
```

---

*Última actualización: 2026-03-20 · Sistema v4.8*
