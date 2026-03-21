# Tesis: Escasez y Resiliencia
## *Un Marco Matemático para Invertir en la Era de la Autorreplicación Artificial*

**Autor:** Jose Antonio Vilar  
**Versión:** 1.2  
**Última actualización:** 2026-03-21  
**Estado:** Working Paper publicado en SSRN (marzo 2026)

---

## Modelo central

$$V(t) = Capital \times (1+r_{IA})^t \times \frac{\Phi_L(t)}{\Phi_L(0)}$$

$$\Phi_L(t) = 1 + \frac{K}{1 + e^{-\gamma(t - t_0)}}$$

La normalización por $\Phi_L(0)$ garantiza $V(0) = Capital$ para cualquier combinación de parámetros.

| Parámetro | Descripción | Calibración |
|-----------|-------------|-------------|
| `r_IA` | Crecimiento ecosistema IA | SOX trailing 12M / 100 |
| `K` | Multiplicador máximo de autorreplicación | Escenario (2–6×) |
| `γ` | Velocidad de adopción | `ln(2) / años_entre_releases_LLM` |
| `t₀` | Año de inflexión (máxima aceleración) | Señal Divergencia SOX↑/Cobre↓ |

**Referencia:** Verhulst, P.-F. (1838). *Correspondance Mathématique et Physique*, 10, 113–121.

---

## Estructura del proyecto

```
tesis/
├── README.md                          ← Este fichero
├── paper/
│   ├── Vilar_2026_Escasez_Resiliencia_SSRN_v2.docx  ← Paper final (SSRN)
│   ├── Autofabricacion_Olas_Tecnologicas_v2.docx     ← Paper II (companion)
│   ├── SSRN_submission_guide.md                      ← Metadatos y guía de envío
│   └── paper_ssrn_v2.py                              ← Script generador del paper
├── laboratorio/
│   ├── Laboratorio_Modelo_Escasez_Resiliencia.ipynb  ← Notebook principal
│   ├── backtest.py                                   ← Backtesting con datos reales
│   └── plot_curves.py                                ← Visualización de curvas
├── figuras/
│   └── modelo_curvas_comparativa.png                 ← Proyección 3 escenarios
└── datos/
    └── (datos empíricos — vinculados a ../historico/)
```

---

## Los cinco pilares

| Pilar | Activos | Rol en el modelo |
|-------|---------|-----------------|
| Escasez Digital | Bitcoin (BTC) | Escasez monetaria programada (21M fijo) |
| Autorreplicación IA | Semiconductores, Robótica, Cuántica | Exposición directa a K y γ |
| Energía / Grid | Uranio, Utilities, Smart Grid | Combustible físico de la tesis |
| Escasez Física | Cobre, Oro | Demanda estructural de electrificación |
| Resiliencia | MSCI World, S&P 500, Vanguard | Protección si la tesis falla |

---

## Detector SOX/Cobre — estados del paradigma

| Estado | Condición | Acción |
|--------|-----------|--------|
| 🟢 Era de Construcción | SOX ↑ y Cobre ↑ | Mantener todos los pilares |
| 🔴 Divergencia · Alerta | SOX ↑ / Cobre ↓ | Rotar metales → IA pura — marca t₀ empírico |
| 🟡 Escasez Física | SOX ↓ / Cobre ↑ | Mantener metales, esperar rebote SOX |
| 🔴 Contracción | SOX ↓ y Cobre ↓ | Modo defensivo |

---

## Cómo trabajar con este proyecto

### Abrir el laboratorio
```bash
jupyter notebook tesis/laboratorio/Laboratorio_Modelo_Escasez_Resiliencia.ipynb
```

### Ejecutar backtesting
```bash
python3 tesis/laboratorio/backtest.py
```

### Regenerar visualización de curvas
```bash
python3 tesis/laboratorio/plot_curves.py
```

---

## Hoja de ruta

- [x] v1.0 — Modelo logístico + paper SSRN
- [x] v1.1 — Laboratorio notebook + análisis de sensibilidad
- [x] v1.2 — Paper publicado en SSRN (marzo 2026) · Paper II: Autofabricación
- [ ] v1.3 — Backtesting formal 2018–2025 con datos reales
- [ ] v1.4 — Estimación de K y t₀ con optimización (gradient descent)
- [ ] v1.5 — Test de falsificabilidad: Φ_L→1 como hipótesis nula

---

## Clasificación JEL

`G11` Selección de cartera · `G12` Valoración de activos  
`O33` Cambio tecnológico · `Q02` Economía de recursos no renovables

---

*Jose Antonio Vilar · javsprivate@gmail.com*
