"""
Backtesting del modelo Escasez y Resiliencia
Metodología: train 70% / test 30% por activo
Modelo: V(t) = Capital × (1+r)^t × Φ_L(t)/Φ_L(0)  |  Φ_L(t) = 1 + K/(1+e^(-γ(t-t₀)))
Métricas: RMSE, MAE, R², hit-rate direccional
Test estadístico: ¿mejora Φ_L significativamente sobre baseline?
"""
import csv, os, json, math
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from datetime import datetime

# ── Configuración ──────────────────────────────────────────────────
HIST_DIR = '/sessions/exciting-clever-brown/mnt/Cartera-Inversion/historico'
OUT_DIR  = '/sessions/exciting-clever-brown/mnt/Cartera-Inversion/tesis/figuras'
os.makedirs(OUT_DIR, exist_ok=True)

BG    = '#0d1117'; PANEL = '#161b22'; GRID  = '#21262d'
WHITE = '#e6edf3'; MUTED = '#8b949e'
C_BASE= '#e3b341'; C_EXP = '#ff7b72'; C_LOG = '#79c0ff'; C_ACT = '#56d364'

plt.rcParams.update({
    'figure.facecolor': BG,  'axes.facecolor': PANEL,
    'axes.edgecolor':  GRID, 'axes.labelcolor': WHITE,
    'xtick.color': MUTED,   'ytick.color': MUTED,
    'text.color':  WHITE,   'grid.color':  GRID,
    'grid.linewidth': 0.6,  'legend.facecolor': '#1c2128',
    'legend.edgecolor': GRID,
})

ACTIVOS = {
    'Cobre':        ('GB00B15KXQ89', 'Escasez Física'),
    'Met. Prec.':   ('JE00B1VS3W29', 'Escasez Física'),
    'Robótica':     ('IE00BYZK4552', 'Autorrepl. IA'),
    'AI & Data':    ('IE00BGV5VN51', 'Autorrepl. IA'),
    'MSCI World':   ('IE00B03HCZ61', 'Resiliencia'),
    'Small-Cap':    ('IE00B42W4L06', 'Resiliencia'),
    'Bitcoin':      ('BTC-EUR',      'Escasez Digital'),
    'Uranio':       ('IE000M7V94E1', 'Energía/Grid'),
    'WisdomBTC':    ('GB00BJYDH287', 'Escasez Digital'),
}

# ── Carga de datos ─────────────────────────────────────────────────
def load_series(isin):
    path = os.path.join(HIST_DIR, f'{isin}.csv')
    rows = []
    with open(path) as f:
        for row in csv.DictReader(f):
            try:
                rows.append((datetime.strptime(row['fecha'], '%Y-%m-%d'),
                             float(row['precio_cierre'])))
            except: pass
    rows.sort()
    return rows

# ── Modelos ────────────────────────────────────────────────────────
def model_baseline(t, r):
    return (1 + r) ** t

def model_logistic(t, r, K, gamma, t0):
    phi = 1 + K / (1 + np.exp(-gamma * (t - t0)))
    return (1 + r) ** t * phi

# ── Optimización por grid + coordinate descent ─────────────────────
def mse_loss(y_pred, y_true):
    return np.mean((y_pred - y_true) ** 2)

def fit_baseline(t_train, y_train):
    """Calibrar r desde los datos."""
    best_r, best_mse = 0.10, 1e18
    for r in np.arange(0.0, 0.60, 0.01):
        pred = y_train[0] * model_baseline(t_train, r)
        loss = mse_loss(pred, y_train)
        if loss < best_mse:
            best_mse, best_r = loss, r
    return {'r': best_r}

def fit_exp(t_train, y_train, r):
    """Calibrar λ dado r."""
    best_lam, best_mse = 0.0, 1e18
    for lam in np.arange(-0.1, 0.6, 0.005):
        loss = mse_loss(pred, y_train)
        if loss < best_mse:
            best_mse, best_lam = loss, lam
    return {'r': r, 'lam': best_lam}

def fit_logistic(t_train, y_train, r):
    """Calibrar K, γ, t₀ dado r — grid search grueso + refinamiento."""
    best = {'K': 1.0, 'gamma': 0.5, 't0': np.mean(t_train)}
    best_mse = 1e18

    max_t = max(t_train)
    for K in np.arange(0.5, 10.0, 0.5):
        for gamma in np.arange(0.2, 3.0, 0.2):
            for t0 in np.arange(0.5, max_t, max_t/6):
                pred = y_train[0] * model_logistic(t_train, r, K, gamma, t0)
                loss = mse_loss(pred, y_train)
                if loss < best_mse:
                    best_mse = loss
                    best = {'K': K, 'gamma': gamma, 't0': t0}

    # Refinamiento local
    K0, g0, t00 = best['K'], best['gamma'], best['t0']
    for K in np.arange(max(0.1, K0-0.5), K0+0.6, 0.1):
        for gamma in np.arange(max(0.05, g0-0.3), g0+0.35, 0.05):
            for t0 in np.arange(max(0.1, t00-0.5), t00+0.6, 0.1):
                pred = y_train[0] * model_logistic(t_train, r, K, gamma, t0)
                loss = mse_loss(pred, y_train)
                if loss < best_mse:
                    best_mse = loss
                    best = {'K': K, 'gamma': gamma, 't0': t0}
    return {'r': r, **best}

# ── Métricas ───────────────────────────────────────────────────────
def metrics(y_pred, y_true, name=''):
    n = len(y_true)
    rmse = math.sqrt(np.mean((y_pred - y_true)**2))
    mae  = np.mean(np.abs(y_pred - y_true))
    ss_res = np.sum((y_true - y_pred)**2)
    ss_tot = np.sum((y_true - np.mean(y_true))**2)
    r2   = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    # Hit-rate: ¿el modelo predice la dirección correcta?
    if n > 1:
        dir_pred = np.diff(y_pred) > 0
        dir_real = np.diff(y_true) > 0
        hitrate  = np.mean(dir_pred == dir_real)
    else:
        hitrate = 0.5
    return {'model': name, 'rmse': rmse, 'mae': mae, 'r2': r2, 'hitrate': hitrate}

# ── Wilcoxon signed-rank test (sin scipy) ─────────────────────────
def wilcoxon_approx(errors_a, errors_b):
    """Test de Wilcoxon aproximado: ¿son los errores de B menores que los de A?"""
    diffs = np.abs(errors_b) - np.abs(errors_a)  # negativo = B mejor
    diffs = diffs[diffs != 0]
    n = len(diffs)
    if n < 5:
        return None, None
    ranks = np.argsort(np.abs(diffs)) + 1
    W_plus  = np.sum(ranks[diffs > 0])
    W_minus = np.sum(ranks[diffs < 0])
    W = min(W_plus, W_minus)
    # Aproximación normal para n >= 10
    mu_W    = n * (n+1) / 4
    sigma_W = math.sqrt(n * (n+1) * (2*n+1) / 24)
    z = (W - mu_W) / sigma_W if sigma_W > 0 else 0
    # p-value aproximado (dos colas, distribución normal)
    p = 2 * (1 - _norm_cdf(abs(z)))
    return z, p

def _norm_cdf(x):
    """CDF normal estándar aproximada."""
    t = 1 / (1 + 0.2316419 * abs(x))
    poly = t*(0.319381530 + t*(-0.356563782 + t*(1.781477937 +
           t*(-1.821255978 + t*1.330274429))))
    return 1 - (1/math.sqrt(2*math.pi)) * math.exp(-x*x/2) * poly if x >= 0 \
           else (1/math.sqrt(2*math.pi)) * math.exp(-x*x/2) * poly

# ══════════════════════════════════════════════════════════════════
# BUCLE PRINCIPAL
# ══════════════════════════════════════════════════════════════════
results = []
fit_details = {}

for nombre, (isin, pilar) in ACTIVOS.items():
    path = os.path.join(HIST_DIR, f'{isin}.csv')
    if not os.path.exists(path): continue
    serie = load_series(isin)
    if len(serie) < 100: continue

    # Normalizar tiempo en años desde primer dato
    t0_date = serie[0][0]
    t_all   = np.array([(d - t0_date).days / 365.25 for d, _ in serie])
    p_all   = np.array([p for _, p in serie])
    p_norm  = p_all / p_all[0]   # precio normalizado a 1

    # Train / Test split 70/30
    split   = int(len(t_all) * 0.70)
    t_train, p_train = t_all[:split], p_norm[:split]
    t_test,  p_test  = t_all[split:], p_norm[split:]
    t0_test  = t_all[split]       # tiempo inicio del test

    # Calibrar modelos en TRAIN
    params_base = fit_baseline(t_train, p_train)
    r_cal = params_base['r']
    params_exp  = fit_exp(t_train, p_train, r_cal)
    params_log  = fit_logistic(t_train, p_train, r_cal)

    # Predecir en TEST (rebase en el primer punto del test)
    p0_test   = p_test[0]
    t_rel     = t_test - t0_test   # tiempo relativo desde inicio del test

    pred_base = p0_test * model_baseline(t_rel, params_base['r'])
    pred_log  = p0_test * model_logistic(t_rel, params_log['r'],
                                          params_log['K'], params_log['gamma'],
                                          params_log['t0'] - t0_test)

    # Métricas
    m_base = metrics(pred_base, p_test, 'Baseline')
    m_exp  = metrics(pred_exp,  p_test, 'Logístico')
    m_log  = metrics(pred_log,  p_test, 'Logístico')

    # Test Wilcoxon: logístico vs baseline
    err_base = pred_base - p_test
    err_log  = pred_log  - p_test
    z_stat, p_val = wilcoxon_approx(err_base, err_log)

    # λ_eff del modelo logístico
    K, g, t0_fit = params_log['K'], params_log['gamma'], params_log['t0']
    lam_eff = g * K / (4 + 2*K)

    results.append({
        'nombre': nombre, 'isin': isin, 'pilar': pilar,
        'n_train': split, 'n_test': len(t_test),
        'train_years': round(t_train[-1] - t_train[0], 1),
        'test_years':  round(t_test[-1] - t_test[0], 1),
        'r': r_cal,
        'lam_orig': params_exp['lam'],
        'K': K, 'gamma': g, 't0': round(t0_fit, 2),
        'lam_eff': round(lam_eff, 3),
        'rmse_base': m_base['rmse'],  'r2_base': m_base['r2'],  'hit_base': m_base['hitrate'],
        'rmse_exp':  m_exp['rmse'],   'r2_exp':  m_exp['r2'],   'hit_exp':  m_exp['hitrate'],
        'rmse_log':  m_log['rmse'],   'r2_log':  m_log['r2'],   'hit_log':  m_log['hitrate'],
        'z_wilcoxon': z_stat, 'p_wilcoxon': p_val,
        'log_beats_base': m_log['rmse'] < m_base['rmse'],
        'log_beats_exp':  m_log['rmse'] < m_exp['rmse'],
    })
    fit_details[nombre] = {
        't_all': t_all.tolist(), 'p_norm': p_norm.tolist(),
        't_train': t_train.tolist(), 't_test': t_test.tolist(),
        'p_train': p_train.tolist(), 'p_test': p_test.tolist(),
        'pred_base': pred_base.tolist(), 'pred_exp': pred_exp.tolist(),
        'pred_log':  pred_log.tolist(),
        'split_idx': split, 't0_test': float(t0_test),
        'pilar': pilar,
    }
    print(f"✅ {nombre:<12} | r={r_cal:.2f} K={K:.1f} γ={g:.2f} t₀={t0_fit:.1f} | "
          f"RMSE(log)={m_log['rmse']:.4f} R²={m_log['r2']:.3f} "
          f"{'🏆' if m_log['rmse']<m_base['rmse'] else '  '}")

# ══════════════════════════════════════════════════════════════════
# FIGURA 1: FITS POR ACTIVO (3×3)
# ══════════════════════════════════════════════════════════════════
n_act = len(results)
ncols = 3
nrows = math.ceil(n_act / ncols)
fig, axes = plt.subplots(nrows, ncols, figsize=(16, 4.5*nrows), facecolor=BG)
fig.suptitle('Backtesting del modelo — Train 70% / Test 30% por activo\n'
             'Precio normalizado (inicio = 1)',
             color=WHITE, fontweight='bold', fontsize=12, y=1.01)

axes_flat = axes.flat if hasattr(axes, 'flat') else [axes]
for ax, res in zip(axes_flat, results):
    nombre = res['nombre']
    d = fit_details[nombre]
    ax.set_facecolor(PANEL)

    t_all   = np.array(d['t_all'])
    p_norm  = np.array(d['p_norm'])
    t_test  = np.array(d['t_test'])
    p_test  = np.array(d['p_test'])
    t0_test = d['t0_test']

    # Precio real completo
    ax.plot(t_all, p_norm, color=C_ACT, lw=1.2, alpha=0.7, label='Real')

    # Sombra zona test
    ax.axvspan(t0_test, t_all[-1], alpha=0.08, color=WHITE)
    ax.axvline(t0_test, color=MUTED, lw=1, ls='--', alpha=0.5)

    # Predicciones en test
    ax.plot(t_test, d['pred_base'], color=C_BASE, lw=1.5, ls=':', label=f"Base R²={res['r2_base']:.2f}")
    ax.plot(t_test, d['pred_exp'],  color=C_EXP,  lw=1.5, ls='--', label=f"Exp  R²={res['r2_exp']:.2f}")
    ax.plot(t_test, d['pred_log'],  color=C_LOG,  lw=2.0, label=f"Log  R²={res['r2_log']:.2f}")

    # Anotación ganador
    winner = 'LOG' if res['log_beats_base'] and res['log_beats_exp'] else \
             'EXP' if res['rmse_exp'] < res['rmse_base'] and res['rmse_exp'] < res['rmse_log'] else 'BASE'
    col_w = C_LOG if winner=='LOG' else C_EXP if winner=='EXP' else C_BASE
    ax.text(0.98, 0.04, f'★ {winner}', transform=ax.transAxes,
            ha='right', fontsize=8, color=col_w, fontweight='bold')

    # p-value
    if res['p_wilcoxon'] is not None:
        sig = '***' if res['p_wilcoxon']<0.01 else '**' if res['p_wilcoxon']<0.05 \
              else '*' if res['p_wilcoxon']<0.10 else 'ns'
        ax.text(0.02, 0.96, f"p={res['p_wilcoxon']:.3f}{sig}", transform=ax.transAxes,
                ha='left', va='top', fontsize=7.5, color=MUTED)

    ax.set_title(f"{nombre}  [{res['pilar']}]", color=WHITE, fontsize=9)
    ax.set_xlabel('Años desde inicio'); ax.set_ylabel('Precio norm.')
    ax.legend(fontsize=7, loc='upper left'); ax.grid(True, alpha=0.25)
    # Línea divisoria train/test
    y_range = ax.get_ylim()
    ax.text(t0_test + 0.05, y_range[0] + (y_range[1]-y_range[0])*0.02,
            'TEST →', fontsize=7, color=MUTED)

for ax in list(axes_flat)[n_act:]:
    ax.set_visible(False)

plt.tight_layout()
fig.savefig(os.path.join(OUT_DIR, 'backtest_fits.png'), dpi=140, bbox_inches='tight', facecolor=BG)
plt.close()
print(f"\n✅ Figura 1 guardada: backtest_fits.png")

# ══════════════════════════════════════════════════════════════════
# FIGURA 2: RESUMEN MÉTRICAS + λ_eff
# ══════════════════════════════════════════════════════════════════
fig = plt.figure(figsize=(16, 10), facecolor=BG)
gs  = gridspec.GridSpec(2, 3, figure=fig, hspace=0.45, wspace=0.35,
                        left=0.07, right=0.97, top=0.92, bottom=0.08)
fig.suptitle('Resumen estadístico del backtesting — Modelo Escasez y Resiliencia',
             color=WHITE, fontweight='bold', fontsize=13)

nombres = [r['nombre'] for r in results]
x = np.arange(len(nombres))

# Panel 1: RMSE comparado
ax1 = fig.add_subplot(gs[0, 0])
ax1.set_facecolor(PANEL)
w = 0.28
ax1.bar(x - w,   [r['rmse_base'] for r in results], width=w, color=C_BASE, alpha=0.85, label='Baseline')
ax1.bar(x,       [r['rmse_exp']  for r in results], width=w, color=C_EXP,  alpha=0.85, label='Logístico')
ax1.bar(x + w,   [r['rmse_log']  for r in results], width=w, color=C_LOG,  alpha=0.85, label='Logístico')
ax1.set_xticks(x); ax1.set_xticklabels(nombres, rotation=30, ha='right', fontsize=7.5)
ax1.set_title('RMSE en test (↓ mejor)', color=WHITE); ax1.legend(fontsize=7.5)
ax1.grid(True, alpha=0.25, axis='y')

# Panel 2: R² comparado
ax2 = fig.add_subplot(gs[0, 1])
ax2.set_facecolor(PANEL)
ax2.bar(x - w,   [r['r2_base'] for r in results], width=w, color=C_BASE, alpha=0.85, label='Baseline')
ax2.bar(x,       [r['r2_exp']  for r in results], width=w, color=C_EXP,  alpha=0.85, label='Logístico')
ax2.bar(x + w,   [r['r2_log']  for r in results], width=w, color=C_LOG,  alpha=0.85, label='Logístico')
ax2.axhline(0, color=MUTED, lw=0.8, ls=':')
ax2.set_xticks(x); ax2.set_xticklabels(nombres, rotation=30, ha='right', fontsize=7.5)
ax2.set_title('R² en test (↑ mejor)', color=WHITE); ax2.legend(fontsize=7.5)
ax2.grid(True, alpha=0.25, axis='y')

# Panel 3: Hit-rate direccional
ax3 = fig.add_subplot(gs[0, 2])
ax3.set_facecolor(PANEL)
ax3.bar(x - w,   [r['hit_base'] for r in results], width=w, color=C_BASE, alpha=0.85, label='Baseline')
ax3.bar(x,       [r['hit_exp']  for r in results], width=w, color=C_EXP,  alpha=0.85, label='Logístico')
ax3.bar(x + w,   [r['hit_log']  for r in results], width=w, color=C_LOG,  alpha=0.85, label='Logístico')
ax3.axhline(0.5, color=MUTED, lw=1, ls='--', label='Azar (50%)')
ax3.set_xticks(x); ax3.set_xticklabels(nombres, rotation=30, ha='right', fontsize=7.5)
ax3.set_title('Hit-rate direccional (↑ mejor)', color=WHITE); ax3.legend(fontsize=7.5)
ax3.grid(True, alpha=0.25, axis='y'); ax3.set_ylim(0, 1)

# Panel 4: λ_orig vs λ_eff — validación de la fórmula de equivalencia
ax4 = fig.add_subplot(gs[1, 0])
ax4.set_facecolor(PANEL)
lam_orig = [r['lam_orig'] for r in results]
lam_eff  = [r['lam_eff']  for r in results]
ax4.scatter(lam_orig, lam_eff, color=C_LOG, s=70, zorder=5)
for r in results:
    ax4.annotate(r['nombre'], (r['lam_orig'], r['lam_eff']),
                 textcoords='offset points', xytext=(4,3), fontsize=7, color=MUTED)
# Línea identidad
lims = [min(lam_orig+lam_eff)-0.02, max(lam_orig+lam_eff)+0.02]
ax4.plot(lims, lims, color=MUTED, lw=1, ls='--', alpha=0.5, label='y=x (identidad)')
ax4.set_xlabel('λ_orig (modelo logístico)'); ax4.set_ylabel('λ_eff = γK/(4+2K)')
ax4.set_title('Validación fórmula equivalencia λ', color=WHITE)
ax4.legend(fontsize=8); ax4.grid(True, alpha=0.25)

# Panel 5: Parámetros K y γ por pilar
ax5 = fig.add_subplot(gs[1, 1])
ax5.set_facecolor(PANEL)
pilar_colors = {
    'Escasez Física': C_BASE, 'Autorrepl. IA': C_LOG,
    'Resiliencia': MUTED, 'Escasez Digital': '#d2a8ff', 'Energía/Grid': C_EXP
}
for r in results:
    col = pilar_colors.get(r['pilar'], WHITE)
    ax5.scatter(r['gamma'], r['K'], color=col, s=90, zorder=5, alpha=0.9)
    ax5.annotate(r['nombre'], (r['gamma'], r['K']),
                 textcoords='offset points', xytext=(4, 3), fontsize=7, color=col)
# Leyenda pilares
for pilar, col in pilar_colors.items():
    ax5.scatter([], [], color=col, label=pilar, s=60)
ax5.set_xlabel('γ (velocidad adopción)'); ax5.set_ylabel('K (multiplicador máximo)')
ax5.set_title('Parámetros calibrados K vs γ por pilar', color=WHITE)
ax5.legend(fontsize=7, loc='upper right'); ax5.grid(True, alpha=0.25)

# Panel 6: p-values del test Wilcoxon
ax6 = fig.add_subplot(gs[1, 2])
ax6.set_facecolor(PANEL)
p_vals = [r['p_wilcoxon'] if r['p_wilcoxon'] is not None else 0.99 for r in results]
cols_p = [C_LOG if p < 0.10 else C_EXP if p < 0.25 else MUTED for p in p_vals]
bars = ax6.bar(x, p_vals, color=cols_p, alpha=0.85)
ax6.axhline(0.05, color=C_LOG,  lw=1.5, ls='--', label='p=0.05 (sig.)')
ax6.axhline(0.10, color=C_BASE, lw=1.0, ls=':',  label='p=0.10')
ax6.set_xticks(x); ax6.set_xticklabels(nombres, rotation=30, ha='right', fontsize=7.5)
ax6.set_title('Test Wilcoxon: Logístico vs Baseline\n(p < 0.05 → mejora significativa)', color=WHITE)
ax6.legend(fontsize=7.5); ax6.grid(True, alpha=0.25, axis='y')
ax6.set_ylim(0, max(p_vals)*1.2 + 0.05)

plt.savefig(os.path.join(OUT_DIR, 'backtest_metricas.png'), dpi=140, bbox_inches='tight', facecolor=BG)
plt.close()
print(f"✅ Figura 2 guardada: backtest_metricas.png")

# ══════════════════════════════════════════════════════════════════
# RESUMEN ESTADÍSTICO FINAL
# ══════════════════════════════════════════════════════════════════
print("\n" + "═"*90)
print("RESUMEN BACKTESTING — Modelo Escasez y Resiliencia")
print("═"*90)
print(f"{'Activo':<13} {'Pilar':<16} {'r':>5} {'K':>5} {'γ':>5} {'t₀':>5} "
      f"{'λ_eff':>6} | {'RMSE_B':>7} {'RMSE_L':>7} {'ΔR²':>7} | {'p-val':>7} {'sig':>4} {'winner':>6}")
print("─"*90)

n_wins_log = 0
n_sig = 0
for r in results:
    delta_r2 = r['r2_log'] - r['r2_base']
    winner = '✅ LOG' if r['log_beats_base'] and r['log_beats_exp'] else \
             '   EXP' if r['rmse_exp'] < r['rmse_base'] else '  BASE'
    if '✅' in winner: n_wins_log += 1
    sig_str = ''
    if r['p_wilcoxon'] is not None:
        sig_str = '***' if r['p_wilcoxon']<0.01 else '**' if r['p_wilcoxon']<0.05 \
                  else '*' if r['p_wilcoxon']<0.10 else 'ns'
        if r['p_wilcoxon'] < 0.10: n_sig += 1
    p_str = f"{r['p_wilcoxon']:.3f}" if r['p_wilcoxon'] is not None else '  N/A'
    print(f"{r['nombre']:<13} {r['pilar']:<16} {r['r']:>5.2f} {r['K']:>5.1f} "
          f"{r['gamma']:>5.2f} {r['t0']:>5.1f} {r['lam_eff']:>6.3f} | "
          f"{r['rmse_base']:>7.4f} {r['rmse_log']:>7.4f} {delta_r2:>+7.3f} | "
          f"{p_str:>7} {sig_str:>4} {winner:>6}")

print("─"*90)
print(f"\n📊 El modelo Logístico gana en RMSE: {n_wins_log}/{len(results)} activos "
      f"({100*n_wins_log/len(results):.0f}%)")
print(f"📊 Mejora estadísticamente significativa (p<0.10): {n_sig}/{len(results)} activos")

# Guardar JSON para el notebook
json_path = '/sessions/exciting-clever-brown/mnt/Cartera-Inversion/tesis/datos/backtest_results.json'
os.makedirs(os.path.dirname(json_path), exist_ok=True)
with open(json_path, 'w') as f:
    json.dump({'results': results}, f, indent=2, default=str)
print(f"\n✅ Resultados guardados: {json_path}")
