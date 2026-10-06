"""B22, medicion: quien ESCRIBE en el arbol de trabajo real durante la suite.

La pregunta NO es «que test parece que escribe» —eso se lee, y leer el texto
mide el texto—. La pregunta es «que ficheros versionados cambian de contenido
mientras corre la suite», y eso se INSTRUMENTA.

Como se instrumenta
-------------------
Se envuelven las tres superficies de escritura que el repo usa de verdad
—``Path.write_text``, ``Path.write_bytes`` y ``os.utime``— y se registra el
destino ANTES y DESPUES de la llamada. Un destino cuenta cuando, resuelto,
cae dentro del arbol de trabajo REAL y git lo versiona.

Por que «versionado por git» y no «dentro del arbol»
---------------------------------------------------
Porque el arbol de trabajo tambien contiene lo que NO es fuente: las
coberturas paralelas (``.coverage.parallel.<host>.<pid>``), los artefactos de
la receta, los temporales. Esos cambios no rompen a nadie. Lo que rompe es
que un fichero que git versiona tenga otro contenido mientras otro
instrumento lo esta leyendo, porque ahi el arbol deja de ser la verdad y
todo lo que se deriva de el esta midiendo un arbol inventado.

Se usa ``git ls-files``: la lista de versionados la dice git, no este
script, y por eso no se queda vieja en silencio.

Que NO mide
-----------
Los ficheros de este directorio —``.pipelinek/``— no estan versionados, asi
que escribir la medicion aqui no se cuenta como un hallazgo. Y una escritura
hecha por un SUBPROCESO (no por este interprete) no pasa por estos tres
envoltorios: queda fuera, y se declara como limite en vez de disimularse.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import subprocess
import sys
import traceback
from contextlib import suppress
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

# Donde se deja el informe. Se imprime por stdout SIEMPRE, y ademas se escribe
# aqui solo si se pasa `--salida`. Se escribe por defecto en `.pipelinek/`, que
# NO esta versionado, y eso es DEUDA REGISTRADA (bl-bl-01M41DFZEZ0003882TZNP7NPM0):
# 25 ficheros versionados citan rutas de ahi, luego la evidencia de la campana
# no es reproducible por quien la lee. Este fichero vive en `scripts/`
# precisamente para no ampliar el problema: la medicion es reproducible porque
# el instrumento esta en el repo, aunque el texto que produce no lo este.
SALIDA = RAIZ / ".pipelinek" / "b22_medicion.txt"


def _versionados() -> frozenset[Path]:
    """Los ficheros que git versiona, resueltos y absolutos.

    Lo dice ``git ls-files``, no una lista escrita aqui: escrita a mano se
    queda vieja en silencio, que es la clase de defecto que esta serie lleva
    veintidos bloques midiendo.
    """
    proc = subprocess.run(
        ["git", "-C", str(RAIZ), "ls-files", "-z"],
        capture_output=True,
        check=True,
    )
    return frozenset(
        (RAIZ / rel.decode("utf-8")).resolve() for rel in proc.stdout.split(b"\0") if rel
    )


VERSIONADOS = _versionados()

# La superficie envuelta, para poder desenvolverla en el teardown.
_ORIG = {
    "write_text": pathlib.Path.write_text,
    "write_bytes": pathlib.Path.write_bytes,
    "utime": os.utime,
}

HALLAZGOS: list[tuple[str, str, int, str]] = []


def _registra(superficie: str, destino: object, marco: str, antes: str | None) -> None:
    try:
        resuelto = Path(os.fsdecode(destino)).resolve()  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return
    if resuelto not in VERSIONADOS:
        return
    # «Escribir» y «cambiar» NO son lo mismo, y la diferencia es la propiedad.
    # Un `finally` que restaura los bytes originales ESCRIBE y NO CAMBIA: es
    # el mecanismo correcto de un test que necesita deformar y restaurar. Lo
    # que rompe a un instrumento que esta leyendo es el contenido DISTINTO
    # durante la ventana, no el hecho de haber abierto el fichero en modo
    # escritura. Por eso se comparan los bytes de antes y despues, y no se
    # cuenta el numero de escrituras.
    despues = hashlib.sha256(resuelto.read_bytes()).hexdigest() if resuelto.exists() else None
    HALLAZGOS.append((superficie, str(resuelto.relative_to(RAIZ)), antes != despues, marco))


def _marco() -> str:
    """La linea del test que esta escribiendo, leida de la traza viva.

    La pila termina en [..., <quien escribe>, envoltorio, _marco]: ``_marco``
    se evalua como ARGUMENTO de ``_registra``, luego ``_registra`` todavia
    NO esta en la pila y el ultimo frame de ``pila[:-2]`` es el que escribe.
    Recortar uno mas —que es lo que hacia la primera version— devolvia
    ``pytest_pyfunc_call`` en vez del test: el instrumentador no fallaba,
    pero nombraba mal al autor, que es justo el dato que hace accionable el
    hallazgo.
    """
    marco_este = __file__
    for marco in reversed(traceback.extract_stack()[:-2]):
        if marco.filename == marco_este:
            continue
        return f"{Path(marco.filename).name}:{marco.lineno} {marco.name}"
    return "<fuera de tests/>"


def _envuelve(superficie: str, conversion) -> None:
    original = _ORIG[superficie]

    def envoltorio(self, *args, **kwargs):
        try:
            antes = (
                hashlib.sha256(Path(os.fsdecode(self)).resolve().read_bytes()).hexdigest()
                if superficie != "utime"
                else None
            )
        except (OSError, TypeError, ValueError):
            antes = None
        resultado = original(self, *args, **kwargs)
        # El instrumentador NUNCA propaga: un guard que rompe la corrida que lo
        # certify es peor que no tener guard.
        with suppress(Exception):
            _registra(superficie, args[0] if superficie == "utime" else self, _marco(), antes)
        return resultado

    conversion(envoltorio)


def _instala() -> None:
    _envuelve("write_text", lambda f: setattr(pathlib.Path, "write_text", f))
    _envuelve("write_bytes", lambda f: setattr(pathlib.Path, "write_bytes", f))
    _envuelve("utime", lambda f: setattr(os, "utime", f))


def _desinstala() -> None:
    pathlib.Path.write_text = _ORIG["write_text"]  # type: ignore[method-assign]
    pathlib.Path.write_bytes = _ORIG["write_bytes"]  # type: ignore[method-assign]
    os.utime = _ORIG["utime"]  # type: ignore[assignment]


def _informa() -> None:
    agregado: dict[tuple[str, str, bool, str], int] = {}
    for superficie, relativo, cambio, marco in HALLAZGOS:
        clave = (superficie, relativo, cambio, marco)
        agregado[clave] = agregado.get(clave, 0) + 1

    graves = sum(n for (_s, _r, cambio, _m), n in agregado.items() if cambio)
    benignas = sum(n for (_s, _r, cambio, _m), n in agregado.items() if not cambio)

    lineas = [
        "B22 — escrituras al arbol de trabajo REAL durante la suite",
        f"raiz: {RAIZ}",
        f"ficheros versionados por git: {len(VERSIONADOS)}",
        f"escrituras registradas: {len(HALLAZGOS)}",
        f"  de las que CAMBIAN el contenido: {graves}",
        f"  de las que restauran los mismos bytes: {benignas}",
        "",
        "sitios que CAMBIAN el contenido (los que rompen a un instrumento que lee):",
    ]
    # MEDIDO: la primera version de estas dos listas desempaquetaba como
    # `(s, r, cambio, m)` y luego imprimia `relativo` y `marco` —los NOMBRES
    # que deja el `for` de arriba, que al ser un for normal y no una
    # comprension, liguen en el ambito de la funcion y valen el ULTIMO
    # hallazgo—. Las dieciocho filas graves salian todas con el autor del
    # ultimo, y las benignas bien, porque su lista si usaba sus propias
    # variables. Un informe que miente sobre QUIEN escribe es peor que uno
    # que no informa: por eso las dos listas desempaquetan sus propias.
    graves_lista = [
        f"{n:>4}x  {superficie:<11} {relativo:<34} {marco}"
        for (superficie, relativo, cambio, marco), n in sorted(
            agregado.items(), key=lambda kv: -kv[1]
        )
        if cambio
    ]
    lineas += graves_lista or ["  NINGUNO."]
    lineas += ["", "sitios que solo restauran (escriben pero NO cambian):"]
    benignas_lista = [
        f"{n:>4}x  {superficie:<11} {relativo:<34} {marco}"
        for (superficie, relativo, cambio, marco), n in sorted(
            agregado.items(), key=lambda kv: -kv[1]
        )
        if not cambio
    ]
    lineas += benignas_lista or ["  NINGUNO."]
    lineas += [
        "",
        "LIMITES DECLARADOS:",
        "- Una escritura hecha por un subproceso no pasa por estos envoltorios.",
        "- Solo se envuelven write_text, write_bytes y os.utime.",
    ]
    SALIDA.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print("\n".join(lineas))


_instala()


def pytest_sessionfinish(session, exitstatus):
    _desinstala()
    _informa()


if __name__ == "__main__":
    print(
        "Este modulo se carga como plugin de pytest: python -m pytest -p b22_measure",
        file=sys.stderr,
    )
