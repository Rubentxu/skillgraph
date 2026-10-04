"""Sonda de mutacion de B8: ¿los guards del contrato saben ver rojo?

Por que existe
--------------
Un guard que solo sabe dar verde no mide. Los 66 tests de
`tests/test_b8_package_contract.py` pueden estar verdes con el contrato
roto si lo que miden no es lo que dicen medir, y la unica manera de
saberlo es romper el codigo a proposito.

Las sondas apuntan a las cuatro cosas que este bloque decide, y cada
una rompe UNA. No se prueba «el fichero entero esta mal», que es como
se obtiene un 8/8 sin informacion.

Lo que hay que tener cuidado
----------------------------
Que una sonda **encuentre su texto**. Un harness que no encuentra el
patron que dice mutar no esta probando nada, y contarlo como «no
cazada» —que es un resultado VERDE— es la forma de mentir mas
sencilla que hay. Por eso `SIN_SONDA` se cuenta aparte de `CAZADA`, y
`SIN_SONDA` hace que el script salga con 1.

Los ficheros se guardan como BYTES y se restauran como BYTES.
Reescribir el fichero con lo que el harness cree que leyo es como se
corrompe un arbol sin que nadie lo note.

Uso:
    .venv/bin/python scripts/mutate_b8_package_contract.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

RAIZ: Path = Path(__file__).resolve().parent.parent

MANIFIESTO: Path = RAIZ / "src" / "skillgraph" / "packaging" / "manifest.py"

TESTS: tuple[str, ...] = ("tests/test_b8_package_contract.py",)


class Sonda(NamedTuple):
    etiqueta: str
    relativo: str
    antes: str
    despues: str

    @property
    def ruta(self) -> Path:
        return RAIZ / self.relativo


SONDAS: tuple[Sonda, ...] = (
    Sonda(
        "M1  las clausulas se evaluan con OR en vez de con AND",
        "src/skillgraph/packaging/manifest.py",
        'return all(_cumple_clausula(actual, clausula.strip()) for clausula in requisito.split(","))',
        'return any(_cumple_clausula(actual, clausula.strip()) for clausula in requisito.split(","))',
    ),
    Sonda(
        "M2  tener la capability basta, la version ya no se comprueba",
        "src/skillgraph/packaging/manifest.py",
        "        elif instalada != cap.version:",
        "        elif False:",
    ),
    Sonda(
        "M3  `PACK_KINDS` se escribe a mano y se queda corto",
        "src/skillgraph/packaging/manifest.py",
        "PACK_KINDS: Final[frozenset[str]] = frozenset(get_args(PackKind))",
        "PACK_KINDS: Final[frozenset[str]] = frozenset(\n"
        '    {"SkillPackage", "ControllerPackage", "CapabilityAdapter", "DomainPack"}\n'
        ")",
    ),
    Sonda(
        "M4  el aislamiento deja de ser una comparacion",
        "src/skillgraph/packaging/manifest.py",
        "        return self.nivel_de_aislamiento >= objetivo",
        "        return self.nivel_de_aislamiento <= objetivo",
    ),
    Sonda(
        "M5  `metadatos` vuelve a ser el dict vivo del llamante",
        "src/skillgraph/packaging/manifest.py",
        '        object.__setattr__(self, "metadatos", MappingProxyType(dict(self.metadatos)))',
        '        object.__setattr__(self, "metadatos", self.metadatos)',
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


def _fallidos(salida: str) -> tuple[str, ...]:
    return tuple(
        linea
        for linea in salida.splitlines()
        if linea.startswith(("FAILED", "ERROR")) and "::" in linea
    )


def _invalidar_cache() -> None:
    """Borra los `__pycache__` de lo que se ha tocado.

    Sin esto, el harness puede MENTIR. Lo que paso, medido: M4 invierte
    la comparacion de `es_al_menos` y el `finally` restaura el fichero
    byte a byte —`git status` sale limpio y el `sha` coincide— pero M5
    sigue cazando los tests de M4, no los suyos.

    La causa es la cache de bytecode. Al restaurar se reescribe el
    `.py` con los mismos bytes y el `mtime` puede no avanzar lo
    suficiente para que Python lo considere mas nuevo que el `.pyc`, que
    se queda con la version MUTADA. O sea: el arbol estava restaurado y
    ejecutando la version equivocada a la vez.

    "Restaurado byte a byte" no es "el arbol esta como estaba". Lo
    segundo es lo que hay que comprobar, y para eso esta la vuelta
    final a la suite.
    """
    import shutil

    for sub in ("src", "tests", "scripts"):
        for cache in (RAIZ / sub).rglob("__pycache__"):
            shutil.rmtree(cache, ignore_errors=True)


def main() -> int:
    sondas = SONDAS

    guardados = {s.ruta: s.ruta.read_bytes() for s in sondas}
    cazadas = 0
    sin_sonda: list[str] = []
    causas: list[frozenset[str]] = []

    for sonda in sondas:
        texto = guardados[sonda.ruta].decode("utf-8")
        apariciones = texto.count(sonda.antes)
        if apariciones != 1:
            sin_sonda.append(sonda.etiqueta)
            print(f"{sonda.etiqueta}\n     SIN SONDA: aparece {apariciones} veces")
            continue

        sonda.ruta.write_text(texto.replace(sonda.antes, sonda.despues), encoding="utf-8")
        _invalidar_cache()
        try:
            proc = _ejecutar_tests()
        finally:
            sonda.ruta.write_bytes(guardados[sonda.ruta])
            _invalidar_cache()

        if proc.returncode == 0:
            print(f"{sonda.etiqueta}\n     NO CAZADA: el guard no discrimina")
            continue

        cazadas += 1
        fallos = _fallidos(proc.stdout)
        causas.append(frozenset(fallos))
        resumen = [
            linea for linea in proc.stdout.splitlines() if " passed" in linea or " failed" in linea
        ]
        print(f"{sonda.etiqueta}\n     CAZADA  {resumen[-1] if resumen else ''}")
        for f in fallos[:3]:
            print(f"       {f}")

    bytes_ok = all(ruta.read_bytes() == guardados[ruta] for ruta in guardados)
    # Y ahora la comprobacion que FALTABA: que el arbol no solo tenga
    # los bytes de antes, sino que EJECUTE como estaba. Una sonda puede
    # dejar el arbol en un estado que los bytes no delatan, y ya lo hizo.
    _invalidar_cache()
    vuelta = _ejecutar_tests()
    ejecuta_ok = vuelta.returncode == 0
    resumen = [
        linea for linea in vuelta.stdout.splitlines() if " passed" in linea or " failed" in linea
    ]
    distintas = len(causas) == len(set(causas))
    print("-" * 78)
    print(f"sondas que discriminan: {cazadas} de {len(sondas)}")
    print(f"sondas sin texto que mutar: {len(sin_sonda)}")
    print(f"cada sonda con sus propios tests: {distintas} ({len(set(causas))} conjuntos distintos)")
    print(f"arbol restaurado byte a byte: {bytes_ok}")
    print(f"arbol EJECUTANDO como estaba: {ejecuta_ok}  {resumen[-1] if resumen else ''}")
    if not bytes_ok or not ejecuta_ok:
        print("AVISO: el arbol no quedo como estaba. Revisa antes de seguir.")
        return 2
    return 0 if cazadas == len(sondas) and not sin_sonda else 1


if __name__ == "__main__":
    raise SystemExit(main())
