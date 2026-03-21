"""
Comparativa de curvas del factor de autorreplicación Φ(t)
para el modelo Escasez y Resiliencia.

Modelo Escasez y Resiliencia:
  V(t) = Capital × (1+r)^t × Φ_L(t)/Φ_L(0)
  Φ_L(t) = 1 + K / (1 + e^(−γ(t−t₀)))

Escenarios:
  1. BASE:               Φ(t) = 1 + K / (1 + e^(-γ(t - t0)))
  3. Gompertz:                          Φ(t) = e^((K/λ)(1 - e^(-λt)))
  4. Régimen dual (propuesta):          λ_alto para t < t0; λ_bajo para t >= t0
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import FancyArrowPatch
import warnings
warnings.filterwarnings('ignore')

# ── Parámetros comunes ─────────────────────────────────────────────────────────
C0     = 100_000        # capital inicial €
r      = 0.20           # tasa crecimiento ecosistema IA (calibrada SOX)
years  = np.linspace(0, 10, 200)
t_vals = years

# ── Parámetros por modelo ──────────────────────────────────────────────────────
K_log    = 4.0          # multiplicador máximo de la logística (5× sobre el base)
gamma    = 0.9          # velocidad de transición logística
t0_log   = 5.0          # inflexión logística (año 5 = ~2031)
K_gom    = np.log(5.0)  # Gompertz: K tal que Φ_max ≈ 5
lam_gom  = 0.50         # velocidad Gompertz
lam_hi   = 0.25         # λ alto antes de divergencia
lam_lo   = 0.02         # λ bajo después (miniaturización iniciada)
t0_reg   = 6.0          # año de la señal de Divergencia SOX/Cobre

# ── Funciones Φ(t) ────────────────────────────────────────────────────────────
def phi_logistic(t):
    return 1 + K_log / (1 + np.exp(-gamma * (t - t0_log)))

def phi_gompertz(t):
    return np.exp((K_gom / lam_gom) * (1 - np.exp(-lam_gom * t)))

def phi_dual(t):
    out = np.zeros_like(t)
    for i, ti in enumerate(t):
        if ti < t0_reg:
            out[i] = np.exp(lam_hi * ti)
        else:
            phi_at_t0 = np.exp(lam_hi * t0_reg)
            out[i]    = phi_at_t0 * np.exp(lam_lo * (ti - t0_reg))
    return out

# ── Valor de cartera V(t) = C0 × (1+r)^t × Φ(t) ──────────────────────────────
base_growth = C0 * (1 + r) ** t_vals
V_log  = base_growth * phi_logistic(t_vals)
V_gom  = base_growth * phi_gompertz(t_vals)
V_dual = base_growth * phi_dual(t_vals)
V_base = base_growth * 1  # solo (1+r)^t, sin λ — benchmark

# ── Colores y estilo ───────────────────────────────────────────────────────────
BG     = '#0d1117'
PANEL  = '#161b22'
GRID   = '#21262d'
WHITE  = '#e6edf3'
MUTED  = '#8b949e'

C_EXP  = '#ff7b72'   # rojo — actual (peligroso/especulativo)
C_LOG  = '#79c0ff'   # azul claro — logística (recomendado)
C_GOM  = '#d2a8ff'   # púrpura — Gompertz
C_DUAL = '#56d364'   # verde — régimen dual
C_BASE = '#e3b341'   # amarillo — solo crecimiento base

plt.rcParams.update({
    'figure.facecolor': BG,
    'axes.facecolor':   PANEL,
    'axes.edgecolor':   GRID,
    'axes.labelcolor':  WHITE,
    'xtick.color':      MUTED,
    'ytick.color':      MUTED,
    'text.color':       WHITE,
    'grid.color':       GRID,
    'grid.linewidth':   0.6,
    'font.family':      'DejaVu Sans',
    'legend.facecolor': '#1c2128',
    'legend.edgecolor': GRID,
})

fig = plt.figure(figsize=(16, 11), facecolor=BG)
fig.suptitle(
    'Escasez y Resiliencia — Comparativa de curvas del factor de autorreplicación Φ(t)\n'
    'V(t) = Capital × (1+r)^t × Φ(t)    |    r = 20%    |    Capital₀ = €100.000',
    fontsize=13, fontweight='bold', color=WHITE, y=0.97
)

gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.42, wspace=0.32,
                       left=0.07, right=0.97, top=0.91, bottom=0.07)

year_labels = [2026 + int(y) for y in range(0, 11, 2)]
xticks = list(range(0, 11, 2))

# ─────────────────────────────────────────────────────────────────────────────
# Panel 1: Factor Φ(t) comparado
# ─────────────────────────────────────────────────────────────────────────────
ax1 = fig.add_subplot(gs[0, 0])
ax1.set_title('① Factor Φ(t) — autorreplicación por modelo', fontsize=10.5, color=WHITE, pad=8)

ax1.plot(t_vals, phi_logistic(t_vals), color=C_LOG,  lw=2.5, label='Logística (S-curve)  1+K/(1+e^(-γ(t-t₀)))')
ax1.plot(t_vals, phi_gompertz(t_vals), color=C_GOM,  lw=2,   label='Gompertz  e^((K/λ)(1-e^(-λt)))')
ax1.plot(t_vals, phi_dual(t_vals),     color=C_DUAL, lw=2, ls='--', label=f'Régimen dual  (cambio en t={t0_reg:.0f})')
ax1.axhline(1, color=MUTED, lw=0.8, ls=':')
ax1.axvline(t0_reg, color=C_DUAL, lw=1, ls=':', alpha=0.5)
ax1.text(t0_reg + 0.15, 0.3, f'Divergencia\nt={t0_reg:.0f}', fontsize=7.5, color=C_DUAL, alpha=0.8)

ax1.set_xlabel('Años', fontsize=9)
ax1.set_ylabel('Φ(t)', fontsize=9)
ax1.set_xticks(xticks)
ax1.set_xticklabels(year_labels, fontsize=8)
ax1.legend(fontsize=7.5, loc='upper left')
ax1.grid(True, alpha=0.4)
ax1.set_xlim(0, 10)

# ─────────────────────────────────────────────────────────────────────────────
# Panel 2: Valor V(t) comparado (€)
# ─────────────────────────────────────────────────────────────────────────────
ax2 = fig.add_subplot(gs[0, 1])
ax2.set_title('② Valor de cartera V(t) en €', fontsize=10.5, color=WHITE, pad=8)

ax2.plot(t_vals, V_base / 1e6, color=C_BASE, lw=1.8, ls=':', label='Solo (1+r)^t — sin λ')
ax2.plot(t_vals, V_log  / 1e6, color=C_LOG,  lw=2.5, label='Logística (recomendado)')
ax2.plot(t_vals, V_gom  / 1e6, color=C_GOM,  lw=2,   label='Gompertz')
ax2.plot(t_vals, V_dual / 1e6, color=C_DUAL, lw=2, ls='--', label='Régimen dual')
ax2.plot(t_vals, V_exp  / 1e6, color=C_EXP,  lw=2,   label='Exponencial (actual)')

# Anotaciones finales
for V, c, label in [(V_log, C_LOG, f'€{V_log[-1]/1e6:.1f}M'),
                     (V_gom, C_GOM, f'€{V_gom[-1]/1e6:.1f}M'),
                     (V_dual, C_DUAL, f'€{V_dual[-1]/1e6:.1f}M'),
                     (V_exp, C_EXP, f'€{V_exp[-1]/1e6:.1f}M'),
                     (V_base, C_BASE, f'€{V_base[-1]/1e6:.1f}M')]:
    ax2.annotate(label, xy=(10, V[-1]/1e6), fontsize=7.5, color=c,
                 xytext=(9.65, V[-1]/1e6), va='center')

ax2.set_xlabel('Años', fontsize=9)
ax2.set_ylabel('Millones €', fontsize=9)
ax2.set_xticks(xticks)
ax2.set_xticklabels(year_labels, fontsize=8)
ax2.legend(fontsize=7.5, loc='upper left')
ax2.grid(True, alpha=0.4)
ax2.set_xlim(0, 10.3)

# ─────────────────────────────────────────────────────────────────────────────
# Panel 3: Logística detallada — anatomía del modelo recomendado
# ─────────────────────────────────────────────────────────────────────────────
ax3 = fig.add_subplot(gs[1, 0])
ax3.set_title('③ Anatomía del modelo logístico (recomendado)', fontsize=10.5, color=WHITE, pad=8)

gammas = [0.5, 0.9, 1.5]
cols3  = ['#a5d6ff', '#79c0ff', '#1f6feb']
for g, c in zip(gammas, cols3):
    phi_g = 1 + K_log / (1 + np.exp(-g * (t_vals - t0_log)))
    V_g   = base_growth * phi_g
    ax3.plot(t_vals, V_g / 1e6, color=c, lw=2,
             label=f'γ={g:.1f}  ({"lenta" if g<0.7 else "media" if g<1.2 else "rápida"})')

# Techo teórico
V_ceil = base_growth * (1 + K_log)
ax3.plot(t_vals, V_ceil / 1e6, color=MUTED, lw=1, ls='--', alpha=0.6, label=f'Techo K={K_log:.0f}× → €{V_ceil[-1]/1e6:.1f}M')

# Inflexión
phi_infl = phi_logistic(np.array([t0_log]))[0]
V_infl   = C0 * (1 + r)**t0_log * phi_infl
ax3.axvline(t0_log, color='#e3b341', lw=1, ls=':', alpha=0.7)
ax3.scatter([t0_log], [V_infl/1e6], color='#e3b341', zorder=5, s=60)
ax3.text(t0_log + 0.2, V_infl/1e6 * 1.05,
         f'Inflexión t₀={t0_log:.0f}\n(máxima aceleración)',
         fontsize=7.5, color='#e3b341')

ax3.set_xlabel('Años', fontsize=9)
ax3.set_ylabel('Millones €', fontsize=9)
ax3.set_xticks(xticks)
ax3.set_xticklabels(year_labels, fontsize=8)
ax3.legend(fontsize=7.5)
ax3.grid(True, alpha=0.4)
ax3.set_xlim(0, 10)
ax3.text(0.5, 0.06, f'Parámetros: r={r:.0%}, K={K_log:.0f}, t₀={t0_log:.0f}, Capital₀=€100k',
         transform=ax3.transAxes, fontsize=7.5, color=MUTED, ha='center')

# ─────────────────────────────────────────────────────────────────────────────
# Panel 4: Tabla comparativa cualitativa
# ─────────────────────────────────────────────────────────────────────────────
ax4 = fig.add_subplot(gs[1, 1])
ax4.set_title('④ Tabla comparativa — propiedades matemáticas', fontsize=10.5, color=WHITE, pad=8)
ax4.axis('off')

col_headers = ['Propiedad', 'Exponencial\n(actual)', 'Logística\n(S-curve)', 'Gompertz', 'Régimen\nDual']
rows = [
    ['Saturación (techo)',     '✗  Infinito',   '✓  K+1',        '✓  e^(K/λ)',   '~  Lento'],
    ['Inflexión observable',   '✗  Ninguna',    '✓  t₀',         '✓  implícita', '✓  t₀ SOX'],
    ['Paráms calibrables',     '1  (λ)',         '3  (K,γ,t₀)',   '2  (K,λ)',     '3  (λ₁,λ₂,t₀)'],
    ['Falsificable',           '✗  Difícil',    '✓  Sí',         '✓  Sí',        '✓  Sí'],
    ['Backtesting viable',     '✓  Sí',         '✓  Sí',         '✓  Sí',        '✓  Sí'],
    ['Conectado con tesis',    '~  Parcial',    '✓  Adopción',   '~  Parcial',   '✓✓ Directo'],
    ['Proyecc. a 10A (×Base)', f'{V_exp[-1]/V_base[-1]:.1f}×',
                                f'{V_log[-1]/V_base[-1]:.1f}×',
                                f'{V_gom[-1]/V_base[-1]:.1f}×',
                                f'{V_dual[-1]/V_base[-1]:.1f}×'],
    ['Recomendado para SSRN',  '✗',             '✓✓  Principal', '✓  Robusto',  '✓  Táctico'],
]

table = ax4.table(
    cellText=rows,
    colLabels=col_headers,
    cellLoc='center',
    loc='center',
    bbox=[0, 0, 1, 1]
)
table.auto_set_font_size(False)
table.set_fontsize(8)

# Estilo header
for j in range(len(col_headers)):
    table[(0, j)].set_facecolor('#21262d')
    table[(0, j)].set_text_props(color=WHITE, fontweight='bold')

# Estilo filas alternas + resaltar logística y dual
col_highlight = {1: C_EXP, 2: C_LOG, 3: C_GOM, 4: C_DUAL}
for i in range(1, len(rows)+1):
    for j in range(len(col_headers)):
        cell = table[(i, j)]
        if j == 0:
            cell.set_facecolor('#1c2128')
            cell.set_text_props(color=MUTED)
        else:
            cell.set_facecolor('#0d1117')
            cell.set_text_props(color=WHITE)
        cell.set_edgecolor(GRID)

# Columna logística (j=2) con borde verde
for i in range(0, len(rows)+1):
    table[(i, 2)].set_edgecolor(C_LOG)

# Última fila — resaltar recomendaciones
for j in range(1, 5):
    cell = table[(len(rows), j)]
    txt = rows[-1][j]
    if '✓✓' in txt:
        cell.set_facecolor('#0a2a1a')
        cell.set_text_props(color=C_LOG if j==2 else C_DUAL, fontweight='bold')

fig.text(0.5, 0.01,
    'Conclusión: La Logística es el modelo principal recomendado (S-curve, academicamente estándar). '
    'El Régimen Dual es la extensión táctica vinculada al detector SOX/Cobre.',
    ha='center', fontsize=8.5, color=MUTED, style='italic')

out_path = '/sessions/exciting-clever-brown/mnt/Cartera-Inversion/exports/modelo_curvas_comparativa.png'
plt.savefig(out_path, dpi=150, bbox_inches='tight', facecolor=BG)
print(f'Guardado: {out_path}')
plt.close()
