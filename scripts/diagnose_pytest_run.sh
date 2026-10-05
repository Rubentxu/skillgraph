#!/usr/bin/env bash
# scripts/diagnose_pytest_run.sh — lo que pytest dijo, y lo dijo AL FINAL.
#
# Por que existe (B21):
#
#   MEDIDO sobre las doce consolas de `unit-tests` que hay en
#   `.pipelinek/control/`: las DOCE terminan sin una sola linea `FAILED`, y sin
#   embargo una de ellas —3bb3a3b8, un run que SI fallo— trae la linea entera.
#   La diferencia no es el motor: es EN QUE MOMENTO SE IMPRIME.
#
#   El motor se queda con la COLA de la salida de cada step y recorta A MEDIA
#   LINEA: las doce consolas terminan en mitad de un
#   `mavis-trash: moved to trash: '...`. Y `scripts/coverage.sh` imprime la
#   tabla de cobertura DESPUES de pytest, asi que empuja las lineas `FAILED`
#   fuera de la cola. En el run de 2026-10-02 la tabla no llego a imprimirse y
#   el `FAILED` sobrevivio; en los de B20 el informe si salio y se perdio.
#
#   O sea: el dato existia, lo que no existia era que nadie lo dijera al final.
#   Y `scripts/coverage.sh:203-209` YA lo sabe y YA lo hace con la linea de
#   resumen, por el mismo motivo y con el mismo mecanismo. Lo que faltaba era
#   aplicarlo a la otra mitad del diagnostico.
#
# LA REGLA, y por que no es «imprime las FAILED»:
#
#   LO QUE PYTEST DICE DE SUS FALLOS TIENE QUE APARECER DESPUES DE LA ULTIMA
#   TABLA DE COBERTURA. No «que se impriman las FAILED» —eso es la
#   implementacion de hoy, que es justo lo que un arreglo posterior dejaria
#   de hacer sin que nadie lo note—, sino que el diagnostico no puede volver
#   a ficar fuera de la cola por una tabla que se le anteponga. Asi el
#   arreglo aguanta que la tabla crezca.
#
# Uso:
#   bash scripts/diagnose_pytest_run.sh <log-de-pytest>
#
# Salida: siempre 0. Esto imprime, no juzga: quien juzga es el exit code de
# pytest, y un diagnostico que decidiera por el taparia.

set -uo pipefail

LOG="${1:?falta la ruta del log de pytest}"

if [ ! -f "$LOG" ]; then
    echo "diagnostico: el log no existe, $LOG"
    exit 0
fi

# Cuantos fallos se imprimen. Declarado y no medido porque no depende de
# nada: por encima de este numero lo que se pierde es el propio diagnostico,
# porque la cola se come el final. Se dice EN VOZ ALTA cuando se recorta, que
# es el unico modo de que un recorte no parezca un resultado.
MAX_FALLIDOS=20

echo "=== coverage: resumen de pytest ==="
RESUMEN="$(grep -Eo '[0-9]+ (passed|failed|error|xfailed|skipped)[^=]*' "$LOG" | tail -1)"
echo "pytest: ${RESUMEN:-SIN RESUMEN}"

echo "=== coverage: tests que fallaron ==="

# `^FAILED ` y no `FAILED`: en la seccion FAILURES pytest dibuja la cabecera
# con guiones bajos, y la unica linea que NOMBRA el test es la del resumen
# corto, que es la que se quiere. MEDIDO en el run 3bb3a3b8, que es el unico
# que hoy llega al journal.
FALLIDOS="$(grep -E '^FAILED ' "$LOG" || true)"

if [ -z "$FALLIDOS" ]; then
    echo "(ninguno)"
    exit 0
fi

TOTAL_FALLIDOS="$(printf '%s\n' "$FALLIDOS" | grep -c '^FAILED ')"
if [ "$TOTAL_FALLIDOS" -gt "$MAX_FALLIDOS" ]; then
    printf '%s\n' "$FALLIDOS" | head -n "$MAX_FALLIDOS"
    echo "... y $((TOTAL_FALLIDOS - MAX_FALLIDOS)) mas. ESTA RECORTADO: el numero"
    echo "anterior es el bueno y este print no lo reemplaza."
else
    printf '%s\n' "$FALLIDOS"
fi

exit 0
