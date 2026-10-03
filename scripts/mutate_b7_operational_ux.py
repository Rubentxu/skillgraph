"""Sonda de mutacion de B7: ¿los guards de B7 saben ver rojo?

Por que existe este fichero
---------------------------
Un guard que solo sabe dar verde no mide. Los tests de
`tests/test_b7_operational_ux.py` se pueden pasar en verde con el codigo
roto si lo que miden no es lo que dicen medir, y la unica forma de
saberlo es romper el codigo a proposito y mirar que se ponen rojos.

Eso es lo que hace aqui. Muta el texto REAL de los ficheros, ejecuta los
tests, y restaura el fichero con los bytes que guardo — no reescribiendo
su propio contenido, que es el modo de "restaurar" que deja el arbol
sucio sin que nadie lo note.

Lo que se vigila
----------------
B7 anadio una capa de presentacion y la metio entre el comando y la
pantalla. El defecto que ese cableado puede tener no es "la vista esta
mal": es que al repartir el texto entre dos representaciones se rompa la
que ya existia. Las tres sondas de aqui apuntan a los tres puntos donde
esa rotura puede ocurrir:

- M1  que `runs show` deje de ser `clave=valor` en texto.
- M2  que `_emit` vuelva a pasar `vacio=` a toda vista, que es el
     `TypeError` que hizo este bloque en su primera version.
- M3  que `runs list` deje de declarar su propio `(sin runs)` y se
     quede con el `(sin resultados)` por defecto de la vista.

Una sonda que no encuentra su texto NO CUENTA como cazada: se reporta
como `SIN_SONDA`, que es un fallo de la sonda, no del guard. Es la misma
distincion que en B6 evito contar mutaciones de un harness desactualizado
como si fueran propiedades del codigo.

Uso:
    .venv/bin/python scripts/mutate_b7_operational_ux.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

RAIZ: Path = Path(__file__).resolve().parent.parent

#: Ficheros que las sondas tocan. Se guardan como BYTES y se restauran
#: como BYTES: reescribir el fichero con lo que el harness cree que
#: leyó es como se corrompe un arbol sin que nadie lo note.
OBJETIVOS: tuple[Path, ...] = (RAIZ / "src/skillgraph/cli/commands/runs.py",)

#: Los tests que tienen que ponerse rojos. Son los de B7 mas los de la
#: regresion de CLI que fija el contrato externo de `runs`.
TESTS: tuple[str, ...] = (
    "tests/test_b7_operational_ux.py",
    "tests/test_cli_runs_inspect.py",
)


class Sonda(NamedTuple):
    """Una mutacion a aplicar, y donde se aplica.

    `NamedTuple` y no una dataclass porque la sonda ES sus cuatro campos:
    no tiene comportamiento propio, y hacerlos properties a mano sobre
    una tupla seria reimplementar lo que la libreria ya da.
    """

    etiqueta: str
    relativo: str
    antes: str
    despues: str

    @property
    def ruta(self) -> Path:
        return RAIZ / self.relativo


SONDAS: tuple[Sonda, ...] = (
    Sonda(
        "M1  `runs show` vuelve a `to_text` y pierde el contrato `clave=valor`",
        "src/skillgraph/cli/commands/runs.py",
        "vista.to_key_value",
        "vista.to_text",
    ),
    Sonda(
        "M2  `_emit` vuelve a pasar `vacio=` a toda vista (el TypeError original)",
        "src/skillgraph/cli/commands/runs.py",
        "return texto()",
        'return vista.to_text(vacio="(sin runs)")',
    ),
    Sonda(
        "M3  `runs list` deja de declarar su propio `(sin runs)`",
        "src/skillgraph/cli/commands/runs.py",
        'lambda: vista.to_text(vacio="(sin runs)")',
        "lambda: vista.to_text()",
    ),
)


def _ejecutar_tests() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", *TESTS, "-q", "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
        cwd=RAIZ,
        check=False,
        timeout=600,
    )


def _causales(salida: str) -> tuple[str, ...]:
    """Los tests que se pusieron rojos, que es donde se ve la causa."""
    return tuple(
        linea
        for linea in salida.splitlines()
        if linea.startswith(("FAILED", "ERROR")) and "::" in linea
    )


def main() -> int:
    guardados = {ruta: ruta.read_bytes() for ruta in OBJETIVOS}
    cazadas = 0
    sin_sonda: list[str] = []
    resumen: list[str] = []

    for sonda in SONDAS:
        texto = guardados[sonda.ruta].decode("utf-8")
        apariciones = texto.count(sonda.antes)
        if apariciones != 1:
            sin_sonda.append(sonda.etiqueta)
            resumen.append(f"{sonda.etiqueta}\n     SIN SONDA: aparece {apariciones} veces")
            print(resumen[-1])
            continue

        sonda.ruta.write_text(texto.replace(sonda.antes, sonda.despues), encoding="utf-8")
        try:
            proc = _ejecutar_tests()
        finally:
            # Bytes guardados, no contenido recalculado.
            sonda.ruta.write_bytes(guardados[sonda.ruta])

        if proc.returncode == 0:
            resumen.append(f"{sonda.etiqueta}\n     NO CAZADA: el guard no discrimina")
            print(resumen[-1])
            continue

        cazadas += 1
        fallos = _causales(proc.stdout)
        lineas = [
            linea for linea in proc.stdout.splitlines() if " passed" in linea or " failed" in linea
        ]
        resumen.append(
            f"{sonda.etiqueta}\n     CAZADA  {lineas[-1] if lineas else ''}\n"
            + "".join(f"       {f}\n" for f in fallos)
        )
        print(resumen[-1], end="")

    restaurado = all(ruta.read_bytes() == bytes for ruta, bytes in guardados.items())
    print("-" * 78)
    print(f"sondas que discriminan: {cazadas} de {len(SONDAS)}")
    print(f"sondas sin texto que mutar: {len(sin_sonda)}")
    print(f"arbol restaurado byte a byte: {restaurado}")
    if not restaurado:
        print("AVISO: el arbol NO quedo como estaba. Revisa antes de seguir.")
        return 2
    return 0 if cazadas == len(SONDAS) and not sin_sonda else 1


if __name__ == "__main__":
    raise SystemExit(main())
