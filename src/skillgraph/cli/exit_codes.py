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

#  WI-109. La tabla que convierte el `code` de una excepcion en exit code.
#
#  AGENTS.md 1.2 dice: "Cada excepcion lleva un `code` estable (`sg_*`)
#  usado por la CLI para traducir a exit codes". Antes de WI-109 eso era
#  falso por partida triple: el `code` no se traducía (el runner hacia
#  `except SkillGraphError -> EXIT_DOMAIN` para todo), la decision la
#  tomaba el TIPO en cada `except` explicito, y no habia ninguna tabla que
#  lo hiciera.
#
#  Aqui, y no en `runner.py`, porque este modulo no importa nada
#  (ADR-0016). `parser.py` lo consume sin arrastrar `Storage` ni
#  `pack_loader`; una traduccion en `runner.py` seria inalcanzable desde
#  ahi y devolveria a `parser.py` a la colision con el 2 de argparse.
#
#  Los codigos ausentes caen en EXIT_DOMAIN a proposito: 0 significa
#  exito, y un error de dominio que saliera con 0 seria peor que uno que
#  sale con 10. Un `code` desconocido es un error de dominio, no un
#  exito.
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

#: Traduccion `code` -> exit code. Solo los codigos que el operador puede
#: necesitar distinguir por separado; el resto cae en ``EXIT_DOMAIN``.
#:
#: Se declaran SOLO los dos que el contrato externo de `exit_codes.py`
#: documenta como exit codes propios (11 y 12). Anadir aqui un codigo con
#: un exit code nuevo es un cambio de contrato: es una release MINOR.
EXIT_POR_CODE: Final[dict[str, int]] = {
    "sg_parse": EXIT_PARSE,
    "sg_validation": EXIT_VALIDATION,
}


def exit_para(exc: object) -> int:
    """Exit code de la CLI para una excepcion de dominio.

    Funcion PURA sobre `exc.code`: no mira la clase, no mira la jerarquia
    y no toca disco ni reloj. Dos errores con el mismo `code` dan el
    mismo exit code, que es justo lo que hace que el `code` pueda ser la
    clave de la tabla.

    Acepta `object` y no `SkillGraphError` a proposito: este modulo no
    importa nada (ver arriba), y `main()` tambien captura
    `FileNotFoundError`, que no tiene atributo `code`. Una excepcion sin
    `code` da EXIT_DOMAIN en vez de levantar `AttributeError`: fallar al
    traducir un fallo es el peor de los dos mundos.
    """
    code = getattr(exc, "code", None)
    if not isinstance(code, str):
        return EXIT_DOMAIN
    return EXIT_POR_CODE.get(code, EXIT_DOMAIN)


__all__ = [
    "EXIT_BAD_NAME",
    "EXIT_DB_MISSING",
    "EXIT_DOMAIN",
    "EXIT_OK",
    "EXIT_PARSE",
    "EXIT_PLAN_NOT_FOUND",
    "EXIT_POR_CODE",
    "EXIT_PROJECT_EXISTS",
    "EXIT_PROJECT_NOT_FOUND",
    "EXIT_RUN_FAILED",
    "EXIT_RUN_INCOMPLETE",
    "EXIT_USAGE",
    "EXIT_VALIDATION",
    "exit_para",
]
