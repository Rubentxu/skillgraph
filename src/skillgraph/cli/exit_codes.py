"""Codigos de salida de la CLI, en un modulo hoja.

ADR-0016 (WI-88). Estos doce numeros son **contrato externo**: un operador
o un script clasifica fallos por ellos. Antes vivian en `cli/support.py`,
que importa `Storage`, `BrickRegistry`, `pack_loader`, `catalog`,
`plan_loader` y `workflow`. `cli/parser.py` no puede importarlos de ahi
sin arrastrar todo eso, y al no poder hacerlo se vio obligado a
devolver el 2 de `argparse`, que **colisiona con `EXIT_BAD_NAME`**.

Un modulo hoja, sin imports, lo resuelve por los dos lados: `parser.py`
puede consumir el contrato sin peso, y `support.py` lo reexporta para no
tocar a sus importadores.

#  0 OK
#  1 error de uso (argumento desconocido, subcomando ausente, opcion
#    invalida). Lo devuelve tambien `argparse` desde ADR-0016.
#  2 nombre de proyecto invalido
#  3 proyecto ya existe
#  4 proyecto no existe
#  5 base de datos ausente
#  6 plan no encontrado
# 10 error de dominio SkillGraph (catch-all)
# 11 parse error (workflow o brick)
# 12 validacion semantica (kind desconocido o regla violada)
# 20 run FAILED
# 21 run no terminal tras max-iterations (CANCELLED / WAITING / ACTIVE)
"""

from __future__ import annotations

from typing import Final

EXIT_OK: Final[int] = 0
EXIT_USAGE: Final[int] = 1
EXIT_BAD_NAME: Final[int] = 2
EXIT_PROJECT_EXISTS: Final[int] = 3
EXIT_PROJECT_NOT_FOUND: Final[int] = 4
EXIT_DB_MISSING: Final[int] = 5
EXIT_PLAN_NOT_FOUND: Final[int] = 6
EXIT_DOMAIN: Final[int] = 10
EXIT_PARSE: Final[int] = 11
EXIT_VALIDATION: Final[int] = 12
EXIT_RUN_FAILED: Final[int] = 20
EXIT_RUN_INCOMPLETE: Final[int] = 21

__all__ = [
    "EXIT_BAD_NAME",
    "EXIT_DB_MISSING",
    "EXIT_DOMAIN",
    "EXIT_OK",
    "EXIT_PARSE",
    "EXIT_PLAN_NOT_FOUND",
    "EXIT_PROJECT_EXISTS",
    "EXIT_PROJECT_NOT_FOUND",
    "EXIT_RUN_FAILED",
    "EXIT_RUN_INCOMPLETE",
    "EXIT_USAGE",
    "EXIT_VALIDATION",
]
