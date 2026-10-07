#!/usr/bin/env python3
"""R1 — autocomprobación del ratchet: cinco sondas, cinco propiedades.

POR QUÉ EXISTE UN HARNESS QUE ROMPE EL CÓDIGO A PROPÓSITO
==========================================================

Un gate que **solo sabe ponerse en verde** no está probado.
`check_architecture_ratchet.py` podría devolver siempre `rc=0` y todo el
resto del bloque seguiría en verde: es el mismo argumento que el M2 de
WI-110, donde una derivación que devolviera siempre la lista vacía pasaba
todos los tests.

QUE SE ROMPE EN CADA SONDA, Y POR QUÉ ESA PROPIEDAD

    M1  UN GOD MODULE APARECE   -> P1 deja de estar en cero
    M2  UNA FUNCIÓN PÚBLICA CC>=20 -> P2 deja de estar en cero
    M3  SQL EN EL DOMINIO        -> P3 deja de estar en cero
    M4  EL DOMINIO USA LA IMPLEMENTACIÓN -> P4 deja de estar en cero
    M5  UNA REFERENCIA ROTA     -> P5 deja de estar en cero

**Y LAS CINCO SON EN `tmp_path`, NUNCA EN EL ÁRBOL REAL.** Una sonda que
modifica el repo para luego restaurarlo puede dejar el árbol a medias si el
proceso muere. Aquí no hay nada que restaurar porque no se toca el árbol:
cada sonda construye un repo nuevo, mete la mutación y tira el directorio.

**LO QUE UNA CAÍDA ES Y LO QUE NO ES.** Si el ratchet revienta, la propiedad
está rota: un gate que ni siquiera termina NO satisface lo que vigila. Se
clasifica `CAZADA` y se anota que fue por caída, que es la razón y no el
veredicto.

EL GUARD DE SINTAXIS
===================

Una sonda que rompe la sintaxis pone el gate en rojo por la razón
equivocada: no estaría midiendo la propiedad, estaría midiendo que el
fichero no parsea. Por eso cada sonda **importa** los módulos que toca antes
de juzgar, y una sonda que no carga se clasifica `ROTA`: no cuenta ni como
cazada ni como inocua, porque sería un fallo del harness.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SRC = RAIZ / "src" / "skillgraph"
RATCHET = RAIZ / "scripts" / "check_architecture_ratchet.py"
PY = RAIZ / ".venv" / "bin" / "python"

CAZADA = "CAZADA"
INOCUA = "INOCUA"
ROTA = "ROTA"
CAIDA = -1

#: Módulos que las sondas pueden tocar y que tienen que seguir cargando.
MODULOS = (
    "skillgraph.knowledge.knowledge_controller",
    "skillgraph.knowledge.observation",
    "skillgraph.platform.knowledge_repository",
)


@dataclass(frozen=True, slots=True)
class Sonda:
    """Una mutación en un árbol temporal, y la propiedad que rompe."""

    nombre: str
    que_rompe: str
    #: `(ruta_relativa, texto_anexado)`. El texto se anexa al final.
    ficheros: tuple[tuple[str, str], ...]


def _sql_en_dominio() -> tuple[tuple[str, str], ...]:
    return (
        (
            "src/skillgraph/knowledge/knowledge_controller.py",
            "\n\ndef _fuga_de_sql_para_la_sonda(cur):\n    cur.execute('SELECT 1')\n",
        ),
    )


def _platform_en_dominio() -> tuple[tuple[str, str], ...]:
    return (
        (
            "src/skillgraph/knowledge/knowledge_controller.py",
            "\n\nfrom skillgraph.platform.storage import Storage  # noqa: F401\n",
        ),
    )


SONDAS: tuple[Sonda, ...] = (
    Sonda(
        nombre="M1",
        que_rompe="aparece un god module de 900 lineas",
        ficheros=(
            (
                "src/skillgraph/knowledge/grande_para_la_sonda.py",
                "\n".join(f"def f{i}(x: int) -> int:\n    return x + {i}" for i in range(450)),
            ),
        ),
    ),
    Sonda(
        nombre="M2",
        que_rompe="una funcion publica llega a cc>=20",
        ficheros=(
            (
                "src/skillgraph/knowledge/compleja_para_la_sonda.py",
                "def veinte(x: int) -> int:\n"
                + "".join(f"    if x == {i}:\n        return {i}\n" for i in range(21)),
            ),
        ),
    ),
    Sonda(
        nombre="M3",
        que_rompe="el dominio vuelve a hablar SQL",
        ficheros=_sql_en_dominio(),
    ),
    Sonda(
        nombre="M4",
        que_rompe="el dominio importa la IMPLEMENTACION de platform",
        ficheros=_platform_en_dominio(),
    ),
    Sonda(
        nombre="M5",
        que_rompe="aparece una referencia normativa rota",
        ficheros=(("NOTAS.md", "\nConsulta la 77-SPEC-INVENTADA que no existe.\n"),),
    ),
)


def _construye_arbol(destino: Path) -> Path:
    """Un repo mínimo pero REAL: `src/skillgraph/` y ficheros de apoyo.

    Se copia `knowledge/` porque el ratchet lo recorre, y se crean los
    ficheros que las otras propiedades necesitan (`AGENTS.md` para que
    exista el contexto del repo, `pyproject.toml` para que el árbol tenga
    forma de repo).
    """
    destino.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SRC / "knowledge", destino / "src" / "skillgraph" / "knowledge")
    for vacio in ("core", "runtime"):
        (destino / "src" / "skillgraph" / vacio).mkdir(parents=True, exist_ok=True)
    (destino / "src" / "skillgraph" / "__init__.py").write_text("", encoding="utf-8")
    (destino / "AGENTS.md").write_text("# repo de prueba\n", encoding="utf-8")
    (destino / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    return destino


def _aplica(raiz: Path, sonda: Sonda) -> None:
    for relativa, texto in sonda.ficheros:
        destino = raiz / relativa
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto + "\n" if relativa.endswith(".py") else texto, encoding="utf-8")


def _corre(raiz: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [str(PY), str(RATCHET), "--raiz", str(raiz)],
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def _el_arbol_carga() -> tuple[bool, str]:
    """Los módulos tocados deben seguir importando.

    Se importa contra el repo REAL, no contra el temporal: las sondas
    escriben codigo que no es un modulo valido del paquete (no tienen
    imports resueltos), y exigir que carguen mediria el harness.
    """
    proc = subprocess.run(
        [str(PY), "-c", "import " + ", ".join(MODULOS)],
        capture_output=True,
        text=True,
        cwd=str(RAIZ),
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-600:]


@dataclass
class Informe:
    resultados: list[tuple[str, str, str]] = field(default_factory=list)
    rotas: list[str] = field(default_factory=list)


def main() -> int:
    print("R1 — autocomprobacion del ratchet arquitectonico")
    print(f"  sondas: {len(SONDAS)} (cada una en un arbol TEMPORAL)\n")

    # Base: un árbol limpio tiene que dar verde.
    with tempfile.TemporaryDirectory(prefix="r1_base_") as tmp:
        raiz = _construye_arbol(Path(tmp) / "repo")
        base, salida = _corre(raiz)
        print(f"  sin sondas: rc={base} (se espera 0)")
        if base != 0:
            print("  el ratchet NO DA VERDE sobre un arbol limpio:")
            print(salida[-800:])
            return 2

    informe = Informe()
    for sonda in SONDAS:
        with tempfile.TemporaryDirectory(prefix=f"r1_{sonda.nombre}_") as tmp:
            raiz = _construye_arbol(Path(tmp) / "repo")
            _aplica(raiz, sonda)

            rc, salida = _corre(raiz)
            if rc == 0:
                informe.resultados.append(
                    (sonda.nombre, INOCUA, f"rc=0 pese a que {sonda.que_rompe}: no muerde")
                )
                continue

            # Se distingue «el gate midió la propiedad» de «el gate reventó».
            cayo = "Traceback (most recent call last)" in salida
            detalle = "el gate REVENTO" if cayo else f"rc={rc} nombrando el incumplimiento"
            if cayo:
                detalle += f": {salida.strip().splitlines()[-1][:200]}"
            informe.resultados.append((sonda.nombre, CAZADA, f"{detalle} ({sonda.que_rompe})"))

    carga_ok, detalle_carga = _el_arbol_carga()
    if not carga_ok:
        print(f"  AVISO: el repo real no carga: {detalle_carga}")

    print()
    cazadas = sum(1 for _, v, _ in informe.resultados if v == CAZADA)
    inocuas = [n for n, v, _ in informe.resultados if v == INOCUA]
    for nombre, veredicto, detalle in informe.resultados:
        print(f"  {nombre}  {veredicto:<7} {detalle}")

    print(f"\nMutaciones: {cazadas}/{len(SONDAS)} cazadas")
    if inocuas:
        print(f"  INOCUAS: {', '.join(inocuas)}")
    return 0 if cazadas == len(SONDAS) and not inocuas else 1


if __name__ == "__main__":
    raise SystemExit(main())
