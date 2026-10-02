#!/usr/bin/env bash
# scripts/coverage.sh — medicion de cobertura que VE el CLI ejecutado por subproceso.
#
# Por que existe (WI-75, cierra la deuda de instrumentacion de WI-57/WI-63):
#
#   La suite de SkillGraph ejercita la frontera CLI casi siempre por
#   SUBPROCESO (`sys.executable -m skillgraph ...` con cwd=tmp_path).
#   Medido el 2026-10-02 con `pytest --cov=skillgraph.cli`:
#
#       CLI total = 65.86 %   ->  POR DEBAJO del contrato AGENTS.md §6.3 (>=70 %)
#       expansion.py = 40 %, runs.py = 37 %, pack.py = 46 %
#
#   Ese "incumplimiento" era CEGUERA DEL INSTRUMENTO, no deuda de tests.
#   Con esta receta el mismo codigo mide 94 % (ver `session-journal`):
#
#       CLI total 65.86 % -> 94 %   |  expansion.py 40 % -> 82 %
#       runs.py      37 % -> 86 %   |  pack.py      46 % -> 78 %
#       run.py       81 % -> 96 %   |  support.py   69 % -> 85 %
#
#   Los tres ingredientes, y por que los tres hacen falta:
#
#   1. HOOK .pth con `coverage.process_startup()` en el site-packages del
#      venv. Sin el, COVERAGE_PROCESS_START no lo lee NADIE y el
#      subproceso no instrumenta nada. Este hook venia colado a mano en
#      el venv local (a1_coverage.pth, 2026-09-23) y NO estaba declarado en
#      pyproject.toml ni en uv.lock: en una maquina nueva `uv sync` no lo
#      instalaba y la receta reproducia el 0 % en silencio. Por eso este
#      script lo CREA si falta, en vez de asumirlo.
#
#   2. `parallel = true` en [run]. Sin el, todos los procesos escriben el
#      MISMO fichero de datos y el ultimo pisa a los demas: el
#      "last-writer-wins" que WI-57 midio como "knowledge 95 % vs runs 9 %"
#      en un mismo run. Con parallel, cada proceso escribe su propio
#      <data_file>.<host>.<pid>.<rand> y `coverage combine` los funde.
#
#   3. `data_file` ABSOLUTO (este es el bug que mas confundia). Los tests
#      lanzan la CLI con cwd=tmp_path por aislamiento, asi que un
#      data_file RELATIVO resuelve dentro del tmp de pytest — y pytest lo
#      borra al terminar. Medido: con data_file relativo se recuperaban 4
#      ficheros de datos (solo el proceso principal) y expansion.py daba
#      0 % pese a 15+ invocaciones reales de la CLI. Con data_file
#      absoluto: 26 ficheros y expansion.py pasa a 45 % solo con el fichero
#      de tests/test_h4_expansion_cli.py.
#
#   4. pytest-cov para el PRINCIPAL, hook para los SUBPROCESOS, y los dos
#      escribiendo en el MISMO data_file. Medido: corriendo `pytest` a pelo
#      (sin --cov, solo el hook) la suite completa daba 60 % — expansion.py
#      82 % pero runtime/locks.py 35 %: el perfil del proceso principal se
#      perdia. pytest-cov es quien debe medir el proceso que importa; el
#      hook solo aporta lo que pytest-cov no ve.
#
# Uso:
#   bash scripts/coverage.sh                    # suite completa
#   bash scripts/coverage.sh tests/test_h4_*.py   # subconjunto
#
# Salida:
#   exit 0 -> cobertura medida y reportada
#   exit !=0 -> pytest fallo (el informe se imprime igualmente, y el exit
#               code es el de pytest, no el de coverage)
#
# NO usar esto como gate de CI: .pipeline.kts corre pytest sin coverage a
# proposito (la instrumentacion de subproceso multiplica el tiempo de
# suite). Es una herramienta de medicion, invoked a mano.

set -uo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$PWD"

# --- 1. hook .pth -----------------------------------------------------------
# Reutiliza el que ya exista (p.ej. `a1_coverage.pth`); si no hay ninguno
# que llame a process_startup, lo crea. Idempotente.
SITE_PACKAGES="$(uv run python -c 'import site; print(site.getsitepackages()[0])')"
if grep -lqs 'process_startup' "$SITE_PACKAGES"/*.pth 2>/dev/null; then
    echo "=== coverage: hook .pth ya presente ==="
else
    printf '%s\n' 'import coverage; coverage.process_startup()' >"$SITE_PACKAGES/coverage.pth"
    echo "=== coverage: hook .pth creado en $SITE_PACKAGES/coverage.pth ==="
    echo "    (necesario: sin el, COVERAGE_PROCESS_START no lo lee el subproceso)"
fi

# --- 2. config con parallel + data_file absoluto ---------------------------
# El nombre `.coverage.rc` (y no `.coverage-rc`) es deliberado: casa con el
# patron `.coverage.*` del .gitignore, igual que los ficheros de datos
# paralelos. Un nombre con guion lo dejaba sin ignorar y ensuciaba el
# arbol, que es requisito del checklist de release.
RC="$REPO_ROOT/.coverage.rc"
cat >"$RC" <<EOF
[run]
branch = true
source = skillgraph
parallel = true
sigterm = true
data_file = $REPO_ROOT/.coverage.parallel

[report]
show_missing = true
skip_covered = false
skip_empty = true
fail_under = 80
EOF

export COVERAGE_PROCESS_START="$RC"

# --- 3. medir, combinar, reportar ------------------------------------------
# pytest-cov mide el PROCESO PRINCIPAL y el hook del punto 1 mide cada
# SUBPROCESO. Los dos escriben en el MISMO data_file (con parallel=true),
# asi que `coverage combine` funde ambos sin perder nada.
#
# Medido 2026-10-02: correr `pytest` a pelo (sin --cov) y dejar que solo
# el hook midiera daba 60 % en la suite completa — expansion.py 82 %
# (subproceso bien medido) pero runtime/locks.py 35 % (el perfil del
# proceso principal se perdia). Con pytest-cov a cargo del principal, los
# dos van al mismo sitio y la medicion es estable.
uv run coverage erase --rcfile="$RC"

echo "=== coverage: pytest (principal via pytest-cov, subprocesos via hook) ==="
uv run pytest -q -p no:cacheprovider --cov=skillgraph --cov-config="$RC" "$@"
PYTEST_RC=$?

echo "=== coverage: combine ==="
uv run coverage combine --rcfile="$RC"

echo "=== coverage: report ==="
uv run coverage report --rcfile="$RC"
REPORT_RC=$?

# El exit code es el de pytest: un fallo de tests no debe quedar tapado
# por un informe que se imprimiria igual.
if [ "$PYTEST_RC" -ne 0 ]; then
    exit "$PYTEST_RC"
fi
exit "$REPORT_RC"
