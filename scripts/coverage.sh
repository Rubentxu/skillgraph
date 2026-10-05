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
# suite). Es una herramienta de medicion, invocada a mano.
#
# --- CORREGIDO EN WI-93 (2026-10-02) ------------------------------------
# El parrafo anterior queda RETIRADO, no borrado: describe lo que se
# creia entonces. La premisa era que la instrumentacion de subproceso
# "multiplica el tiempo de suite", y NUNCA se habia medido.
#
# MEDIDO, misma sesion, mismo arbol:
#     pytest a pelo (stage unit-tests de antes) ....... ~110 s
#     esta receta completa ...........................  203 s
#     delta ...........................................  +93 s  (~1.85x)
#
# No multiplica: cuesta un minuto y medio mas. Y la instrumentacion de
# subproceso no es un lujo, es lo que hace que la medicion sea VERDAD:
# sin el hook .pth, el CLI que la suite lanza por subproceso mide 65.86 %
# en vez de 94 %, y el "incumplimiento" del suelo del CLI seria ceguera
# del instrumento.
#
# Ademas, el otro contrato declarado (AGENTS.md §6.3, suelos POR MODULO)
# no lo comprobaba ninguna herramienta: `coverage report` solo admite un
# umbral global. Para eso esta `scripts/check_coverage_floors.py`, y para
# que las dos cosas se comprueben en la CI, .pipeline.kts corre ESTA
# receta en el stage unit-tests (una sola pasada para tests y cobertura)
# y el checker en el stage siguiente.

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
#
# LAS TRES RUTAS SE PUEDEN APUNTAR A OTRO SITIO, y no es para tests: es que el
# estado de cobertura de este script es GLOBAL y COMPARTIDO. MEDIDO en B21:
# `coverage erase` de mas abajo borra el fichero de datos, asi que un guard
# que ejecutara este script DURANTE la suite dejaria a `coverage-floors` —la
# etapa SIGUIENTE, que lee ese mismo dato— midiendo un solo fichero de test y
# poniendola en rojo. Un guard que rompe la corrida que lo certify es peor que
# no tener guard. Con estas tres variables el guard ejecuta el instrumento DE
# VERDAD sin tocar el estado del que dependen los demas.
RC="${COVERAGE_RC:-$REPO_ROOT/.coverage.rc}"
DATA_FILE="${COVERAGE_DATA_FILE:-$REPO_ROOT/.coverage.parallel}"
LOG="${COVERAGE_LOG:-$REPO_ROOT/.pipelinek/unit-tests.log}"

# --- por que la configuracion omite /tmp (MEDIDO en B20, al certificar) -----
#
# Sin el `omit` de mas abajo, la etapa unit-tests termina con rc=1 DESPUES de
# que la suite entera haya pasado: 3321 passed, 93,68 % sobre un suelo de 80, y
# luego «No source for code: '/tmp/b17_16r3_ise/src/skillgraph/__init__.py'».
#
# MEDIDO sobre el dato real: de las 376 rutas del fichero de datos, 282 eran
# de /tmp, y NINGUNA existia ya cuando llegaba el informe.
#
# De donde sale. La clase _ArbolCopiado, en tests/test_b17_pack_lifecycle_exec.py,
# abre un TemporaryDirectory con prefijo "b17_", copia src/ dentro y levanta el
# paquete de ahi como subproceso. El hook .pth del punto 1 mide ese subproceso
# con la misma destreza con la que mide cualquier otro. La copia se borra al
# terminar el test, y para cuando llega el informe la ruta ya no existe:
# coverage no puede abrir el fichero y aborta el informe ENTERO.
#
# Rompia las DOS consumidoras: coverage report, aqui, y coverage json, en
# check_coverage_floors.py, que es la etapa SIGUIENTE de la receta. Parchear
# la una habria dejado la otra roja.
#
# POR QUE NO SE RESUELVE CON [paths]. Los temporales no tienen un solo layout:
# conviven /tmp/b17_*/src/ y /tmp/b19_*/repo/src/. Remapearlos obligaria a
# enumerarlos, y enumerar layouts es la misma lista encubierta por forma que
# B20 denuncia en el predicado de la ontologia: decide COMO SE ESCRIBE la
# ruta en vez de A QUE CONJUNTO PERTENECE. La regla es una y no necesita
# lista: lo que vive fuera del arbol del repo no es codigo de este repo.
#
# NO RELAJA EL SUELO. MEDIDO: con el omit puesto, subir fail_under a 95 o a 99
# sobre el 94 % real sigue dando rc=2. Lo que se deja de exigir es que
# coverage sepa abrir ficheros que ya no existen, que no es una propiedad del
# proyecto.
#
# OJO AL ESCRIBIR DENTRO DE ESTE HEREDOC: va SIN COMILLAS, porque necesita
# expandir $REPO_ROOT. Un acento grave aqui no es decoracion, es una
# SUSTITUCION DE COMANDO. MEDIDO: con acentos graves en un comentario, la
# configuracion salio ilegible y la etapa fallo en el primer `coverage erase`,
# un segundo y medio despues de empezar. Si hay que nombrar codigo dentro,
# se pone en el comentario de aqui arriba, que es donde el shell no lo toca.
cat >"$RC" <<EOF
[run]
branch = true
source = skillgraph
parallel = true
sigterm = true
data_file = $DATA_FILE
# Lo que vive fuera del arbol del repo no es codigo de este repo, y no se
# mide. El motivo, medido, esta en el comentario de este script, encima.
omit =
    /tmp/*

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

# El log va a `.pipelinek/` porque AGENTS.md exige que los stages solo
# produzcan efectos secundarios en `.pipelinek/` y `evidence/`.
mkdir -p "$(dirname "$LOG")"

echo "=== coverage: pytest (principal via pytest-cov, subprocesos via hook) ==="
# `tee` es para poder releer la linea de resumen al final. El exit code NO se
# saca de `$?` del pipeline: con `pipefail` ese seria el de `tee` o el del
# propio pipeline, y hay que el de pytest. `${PIPESTATUS[0]}` es el unico
# que lo dice (leccion de WI-93: `if pipeline | tail; then` mide el `tail`).
uv run pytest -q -p no:cacheprovider --cov=skillgraph --cov-config="$RC" "$@" 2>&1 | tee "$LOG"
PYTEST_RC=${PIPESTATUS[0]}

echo "=== coverage: combine ==="
uv run coverage combine --rcfile="$RC"

echo "=== coverage: report ==="
uv run coverage report --rcfile="$RC"
REPORT_RC=$?

# El diagnostico se imprime AL FINAL, y no por decoracion: es la ULTIMA cosa
# que este script escribe. MEDIDO en B21: el motor se queda con la cola de la
# salida de cada step y recorta a media linea, y este script imprime ~100
# lineas de tabla de cobertura DESPUES de pytest, luego las lineas FAILED
# quedaban fuera de la cola. El dato existia —el log de esta misma corrida lo
# tiene entero—; lo que no existia era que nadie lo dijera al final.
#
# El script que reimprime vive aparte, `scripts/diagnose_pytest_run.sh`, y no
# aqui dentro, por un motivo concreto: para que un guard pueda EJECUTARLO
# contra un log real sin tener que arrancar este script entero. Un guard que
# lee el fuente de un bloque de shell mide el texto del bloque, que es
# exactamente el fallo de B20 con el heredoc de la configuracion.
bash scripts/diagnose_pytest_run.sh "$LOG"

# El exit code es el de pytest: un fallo de tests no debe quedar tapado
# por un informe que se imprimiria igual.
if [ "$PYTEST_RC" -ne 0 ]; then
    exit "$PYTEST_RC"
fi
exit "$REPORT_RC"
