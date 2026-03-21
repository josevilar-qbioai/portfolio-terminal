#!/usr/bin/env python3
"""
build.py — Regenera todos los artefactos del proyecto de tesis.

Uso:
    python3 tesis/build.py           # regenera todo
    python3 tesis/build.py --paper   # solo el paper SSRN
    python3 tesis/build.py --figures # solo las figuras
"""
import subprocess, sys, os, time

ROOT = os.path.dirname(os.path.abspath(__file__))

TASKS = {
    "paper":   (os.path.join(ROOT, "paper",      "paper_ssrn.py"),   "Paper SSRN (.docx)"),
    "figures": (os.path.join(ROOT, "laboratorio","plot_curves.py"),  "Comparativa de curvas (.png)"),
}

def run(script, label):
    print(f"\n▶ {label}")
    print(f"  {script}")
    t0 = time.time()
    result = subprocess.run(["python3", script], capture_output=True, text=True,
                            cwd=os.path.join(ROOT, ".."))
    elapsed = time.time() - t0
    if result.returncode == 0:
        for line in result.stdout.strip().splitlines():
            print(f"  ✅ {line}")
    else:
        print(f"  ❌ Error ({elapsed:.1f}s):")
        for line in result.stderr.strip().splitlines()[-10:]:
            print(f"     {line}")
    return result.returncode == 0

def main():
    args = sys.argv[1:]
    if not args:
        tasks = list(TASKS.keys())
    else:
        tasks = [a.lstrip("--") for a in args if a.lstrip("--") in TASKS]
        if not tasks:
            print(f"Tareas disponibles: {', '.join(f'--{k}' for k in TASKS)}")
            sys.exit(1)

    print("=" * 55)
    print("  Tesis: Escasez y Resiliencia — Build")
    print("=" * 55)

    ok, fail = 0, 0
    for task in tasks:
        script, label = TASKS[task]
        if run(script, label):
            ok += 1
        else:
            fail += 1

    print(f"\n{'='*55}")
    print(f"  Completado: {ok} OK · {fail} errores")
    print(f"{'='*55}")
    if fail:
        sys.exit(1)

if __name__ == "__main__":
    main()
