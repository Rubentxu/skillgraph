#!/usr/bin/env bash
# scripts/ci.sh — DELEGADO en la receta canónica. No es una receta propia.
#
# Uso:
#   bash scripts/ci.sh              # verificación (delega en .pipeline.kts)
#   bash scripts/ci.sh --quick      # iteración RED/GREEN: pytest a pelo, NO certifica
#
# Por qué delegar y no repetir (WI-99)
# -----------------------------------
# Este script ejecutaba su propia receta: `ruff format --check`, `ruff check` y
# `pytest` a pelo. Medido en WI-99, esa es exactamente la receta cuyo
# instrumento se sabe ciego: sin el hook `.pth` de `scripts/coverage.sh`, el
# CLI ejecutado por subproceso no se ve, y `cli/commands/runs.py` mide 39 %
# frente al 87,96 % de la instrumentada.
#
# Y era peor que imprecisa. `scripts/audit_bundle.sh` —que existe PARA
# producir evidencia reproducible para una auditoría independiente— lo
# invocaba, así que la evidencia versionada en `audits/cleanroom-evidence/`
# se producía con un instrumento que mide la mitad y que no ejecutaba
# ninguno de los cuatro contratos exigibles.
#
# Al delegar, arreglar una vez arregla las dos cosas: `ci.sh` deja de ser
# una cuarta receta y `audit_bundle.sh` pasa a producir la evidencia con el
# instrumento correcto.
#
# Lo que NO hace
# --------------
# * No ejecuta los contratos por su cuenta. La receta canónica es la dueña.
# * No es más rápida. `pytest` a pelo son ~130 s; la canónica ~245 s. La
#   diferencia es el coste de instrumentar los subprocesos, y es el mismo
#   que mide WI-93. Para iteración usar `--quick`.
# * No sustituye a la CI. `AGENTS.md` («CI Local Obligatorio») manda:
#   `mise exec -- pipelinek run --rerun --db .pipelinek/db.sqlite
#   --control-root .pipelinek/control .pipeline.kts`.

set -uo pipefail

# `set -e` NO está activo (para poder recoger el rc del motor), así que un
# `cd` fallido no abortaría: el script seguiría ejecutando la receta canónica
# sobre el directorio desde el que se invocó. shellcheck SC2164.
cd "$(dirname "$0")/.." || {
    echo "=== ci: ERROR: no se pudo ir a la raiz del repo ===" >&2
    exit 7
}

QUICK=0
if [ "${1:-}" = "--quick" ]; then
    QUICK=1
fi

if [ "$QUICK" -eq 1 ]; then
    # Modo de iteración, NO de certificación. Deliberadamente sin
    # instrumentación: es más rápido y por eso no sirve para medir.
    echo "=== ci: modo rapido (NO certifica; ver --quick en la cabecera) ==="
    uv run ruff format --check src tests
    uv run ruff check src tests
    uv run pytest --tb=short
    echo "=== ci: OK (rapido, sin instrumentar) ==="
    exit 0
fi

# --- Verificación: delegar en la receta canónica --------------------------
#
# `mise trust` es obligatorio en un árbol nuevo. MEDIDO en WI-99: sin él,
# `mise exec` responde «Trust them with `mise trust`» y NO ejecuta nada.
# El comando canónico de AGENTS.md no lo menciona, así que un auditor que
# clone el repositorio y ejecute lo documentado obtiene un error de mise en
# vez de una verificación. Es idempotente, así que se puede llamar siempre.
if command -v mise >/dev/null 2>&1; then
    mise trust >/dev/null 2>&1 || true
    # MEDIDO en WI-99: `pipelinek` abre el fichero SQLite, no el directorio
    # que lo contiene. En un clon nuevo, sin esto, el comando canónico de
    # AGENTS.md muere con
    #   java.sql.SQLException: path to '.pipelinek/db.sqlite': ... does not exist
    # y el auditor recibe un error de motor en vez de una verificacion. Se
    # versiona un `.gitkeep` por el mismo motivo, pero un arbol de trabajo
    # usado puede haber perdido el directorio; `mkdir -p` es idempotente.
    mkdir -p .pipelinek
    echo "=== ci: delegando en la receta canonica (.pipeline.kts) ==="
    mise exec -- pipelinek run --rerun \
        --db .pipelinek/db.sqlite \
        --control-root .pipelinek/control \
        .pipeline.kts
    # Sin `|`, el exit code es el del motor. Con un pipe habria que ir a
    # por ${PIPESTATUS[0]}, que es la trampa que .pipeline.kts documenta.
    exit $?
fi

echo "=== ci: ERROR: mise no esta instalado ===" >&2
echo "       La verificacion canonica la ejecuta pipelinek, que se fija" >&2
echo "       en mise.toml. Sin mise no hay verificacion que valga." >&2
echo "       Instalacion: https://mise.jdx.dev/getting-started.html" >&2
exit 6
