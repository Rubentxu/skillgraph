#!/usr/bin/env python3
"""B23 — el harness de la verdad que ahora cruza la ventana.

Que tiene que demostrar
-----------------------
Que los guards de B23 vigilan lo que dicen vigilar. Y no por lectura: una
sonda DESHAce cada una de las seis propiedades y exige que caiga el test
DIAGNOSTICO de esa una.

Cada sonda deshace UNA cosa y exige los tests diagnosticos de ESA cosa. La
causa de una sonda es su conjunto de tests diagnosticos, no todo lo que se
puso rojo: cuatro sondas que heredan el fallo de la quinta se contarian
como cuatro y el numero seria falso —el error de WI-113 y de B14.

Lo que hace distinto a este bloque, y por que las sondas son de este tipo
-----------------------------------------------------------------------------
Las seis propiedades son nuevas, y una sonda que rompe el modulo entero no
demuestra nada: cae todo y parece que el guard funciona. Por eso cada sonda
deshace UNA rama y no el fichero entero, y cada una exige el test que
DIAGNOSTICA esa rama.

Layc las sondas:

  M1  la raiz se usa        -> el veredicto del sandbox sale del REPO. El
                              fallo de volver a derivar RAIZ de __file__.
  M2  la ventana se contrasta -> una ventana mintiendo sale coherente. El
                              fallo de borrar la llamada a la funcion.
  M3  el bloque se cruza     -> bloque y workitems dejan de cruzarse. El
                              fallo de borrar la comparacion.
  M4  el roadmap no se      -> dos ventanas dejan de cruzarse entre si. El
    contradice               fallo de borrar SOLO esa rama.
  M5  el verificador lee     -> total_colectado publica un recuento de una
    una raiz de verdad       colecta que no termino. El fallo de no mirar el
                              codigo de salida.
  M6  la derivacion mide     -> la ventana deja decontraste y el guard de
                              R2/R4 pasa sin leer. El fallo de devolver ().

El guard anti-destruccion
-------------------------
`git checkout --` restaura DEL INDICE. Sin commit debajo, «restaurar» y
«borrar» son la misma operacion. Por eso el veredicto final exige LAS DOS
cosas: que la suite pase y que `git status` de los mutables este limpio.
Comprobar la suite NO es comprobar que el arbol volvio.

El harness se comprueba a si mismo
----------------------------------
Antes de mutar, colecta la suite y exige dos cosas: que cada nombre de cada
`esperados` EXISTA, y que cada ancla `antes` sea UNICA. Sin eso, una sonda
con un nombre mal escrito se contaria como cazada con menos causa, y una
sonda con un ancla repetida deshaceria el texto equivocado sin que se note.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PY = sys.executable

MUTABLES = (
    RAIZ / "scripts" / "project_truth.py",
    RAIZ / "tests" / "test_b23_instrumento_verdad.py",
)

SUITES = (
    "tests/test_b23_instrumento_verdad.py",
    "tests/test_b0_truth_convergence.py",
    # M5 diagnostica con un test de B14: el que mide que un recuento de una
    # colecta interrumpida no se publique. Ese test vivia alli y no en el
    # fichero nuevo, asi que sin esta suite la sonda M5 no tendria contra que
    # caer y el harness contaria un fallo como una victoria.
    "tests/test_b14_truth_single_reader.py",
)


@dataclass(frozen=True, slots=True)
class Sonda:
    nombre: str
    fichero: str
    antes: str
    despues: str
    esperados: tuple[str, ...] = field(default=())
    porque: str = ""


SONDAS: tuple[Sonda, ...] = (
    Sonda(
        nombre="M1_la_raiz_se_usa",
        fichero="scripts/project_truth.py",
        # La raiz se vuelve a derivar del script: el fallo exacto que B23
        # midio. `--raiz` deja de affectar la lectura.
        antes="    raiz = args.raiz if args.raiz is not None else RAIZ_POR_DEFECTO",
        despues="    raiz = RAIZ_POR_DEFECTO",
        esperados=("test_el_veredicto_del_arbol_no_es_el_del_repo",),
        porque="el sandbox volveria a devolver la verdad del repo",
    ),
    Sonda(
        nombre="M2_la_ventana_se_contrasta",
        fichero="scripts/project_truth.py",
        # La ventana se lee pero no se cruza: exactamente el defecto medido,
        # donde project_truth decia coherente con seis contradicciones.
        antes=(
            "    problemas: list[str] = []\n"
            "    donde = raiz if raiz is not None else RAIZ_POR_DEFECTO\n"
            "    problemas.extend(_contradicciones_de_la_ventana(v, ventanas))\n"
            "    problemas.extend(_ventanas_entre_si(ventanas))"
        ),
        despues=(
            "    problemas: list[str] = []\n"
            "    donde = raiz if raiz is not None else RAIZ_POR_DEFECTO"
        ),
        esperados=("test_una_version_que_miente_se_ve", "test_un_tag_que_miente_se_ve"),
        porque="la ventana mintiendo volveria a salir coherente",
    ),
    Sonda(
        nombre="M3_el_bloque_se_cruza",
        fichero="scripts/project_truth.py",
        antes=(
            '    if v["bloque"] != v["workitem_state"]:\n'
            "        problemas.append(\n"
            "            f\"bloque: el ROADMAP declara {v['bloque']}, STATE declara {v['workitem_state']}\"\n"
            "        )"
        ),
        despues="    if False:\n        pass",
        esperados=("test_un_bloque_que_no_es_el_de_state_se_ve",),
        porque="el ROADMAP podria declarar B99 sin que nadie lo note",
    ),
    Sonda(
        nombre="M4_el_roadmap_no_se_contradice",
        fichero="scripts/project_truth.py",
        antes="    problemas.extend(_ventanas_entre_si(ventanas))",
        despues="    pass",
        esperados=("test_dos_versiones_distintas_se_ve",),
        porque="dos ventanas inconsistentes entre si pasarian sin verse",
    ),
    Sonda(
        nombre="M5_el_recuento_mide_la_raiz",
        fichero="scripts/project_truth.py",
        # `total_colectado` deja de mirar el codigo de salida: publicaria un
        # recuento parcial. Es el fallo que B14 cerro y que sigue vivo si
        # alguien toca esta linea.
        antes="    if proc.returncode != 0:\n        parcial = _COLECTADOS.search(proc.stdout)",
        despues="    if False:\n        parcial = _COLECTADOS.search(proc.stdout)",
        esperados=("test_una_colecta_interrumpida_no_publica_un_recuento",),
        porque="un recuento de una colecta que no termino se publicaria",
    ),
    Sonda(
        nombre="M6_la_derivacion_mide",
        fichero="scripts/project_truth.py",
        # La derivacion deja de encontrar ventanas. Si devolviera (), los
        # tests de R2 y R4 pasarian sin leer nada.
        antes="    if _TESTS_VENTANA.search(linea) is None:\n            continue",
        despues="    if True:\n            continue",
        esperados=("test_encuentra_las_dos_ventanas_que_hay",),
        porque="la derivacion devolveria la lista vacia y R2/R4 pasarían sin medir",
    ),
)


def _corre(args: list[str], timeout: int = 900) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=RAIZ, capture_output=True, text=True, check=False, timeout=timeout
    )


def _restaura() -> None:
    _corre(["git", "checkout", "--", *[str(m.relative_to(RAIZ)) for m in MUTABLES]])


def _anclas_validas() -> list[str]:
    errores: list[str] = []
    for s in SONDAS:
        texto = (RAIZ / s.fichero).read_text(encoding="utf-8")
        if texto.count(s.antes) != 1:
            errores.append(
                f"{s.nombre}: el ancla aparece {texto.count(s.antes)} veces en {s.fichero} "
                "(tiene que ser exactamente 1; si no, deshaceria el texto equivocado)"
            )
    return errores


def _nombres_validos() -> list[str]:
    proc = _corre(
        [
            PY,
            "-m",
            "pytest",
            "-q",
            "--collect-only",
            "--no-header",
            "-p",
            "no:cacheprovider",
            *SUITES,
        ]
    )
    colectados = {ln.strip() for ln in proc.stdout.splitlines() if "::" in ln}
    errores: list[str] = []
    for s in SONDAS:
        for esperado in s.esperados:
            if not any(esperado in c for c in colectados):
                errores.append(f"{s.nombre}: el test '{esperado}' no existe en la suite")
    return errores


def _aplica(s: Sonda) -> None:
    ruta = RAIZ / s.fichero
    texto = ruta.read_text(encoding="utf-8")
    assert texto.count(s.antes) == 1, f"{s.nombre}: ancla no unica en {s.fichero}"
    ruta.write_text(texto.replace(s.antes, s.despues), encoding="utf-8")


def _corre_suite() -> tuple[int, set[str], bool]:
    proc = _corre([PY, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", *SUITES])
    caidos = {
        ln.split("::", 1)[1].split(" ")[0]
        for ln in proc.stdout.splitlines()
        if ln.startswith("FAILED ") and "::" in ln
    }
    errores = {
        ln.split(" ", 1)[1].split(" ")[0]
        for ln in proc.stdout.splitlines()
        if ln.startswith("ERROR ") and " " in ln
    }
    no_colecto = proc.returncode in (2, 3) or "Interrupted" in proc.stdout
    return proc.returncode, caidos | errores, no_colecto


def main() -> int:
    print("=" * 78)
    print("B23 — harness de la ventana, la raiz y el bloque")
    print("=" * 78)

    problemas = _anclas_validas() + _nombres_validos()
    if problemas:
        print("ABORTA: el harness no se autocomprueba")
        for p in problemas:
            print(f"  {p}")
        return 2
    print(f"autocomprobacion: {len(SONDAS)} sondas, anclas unicas, nombres existen")

    _restaura()
    rc, caidos, no_colecto = _corre_suite()
    if rc != 0 or no_colecto:
        print(f"ABORTA: la suite no esta verde antes de mutar (rc={rc})")
        for c in sorted(caidos):
            print(f"  {c}")
        return 2
    print("suite verde antes de mutar: OK\n")

    cazadas: list[str] = []
    invalidas: list[str] = []
    fallos: list[str] = []

    for s in SONDAS:
        _restaura()
        try:
            _aplica(s)
        except AssertionError as exc:
            fallos.append(f"{s.nombre}: {exc}")
            continue

        rc, caidos, no_colecto = _corre_suite()
        if no_colecto:
            invalidas.append(f"{s.nombre}: la suite no termino (rc={rc}); no mide nada")
            _restaura()
            continue

        diagnosticos = {e for e in s.esperados if any(e in c for c in caidos)}
        if diagnosticos == set(s.esperados):
            cazadas.append(s.nombre)
            print(f"  CAZADA  {s.nombre}")
            print(f"          {s.porque}")
        else:
            fallo = f"{s.nombre}: no cayeron {sorted(set(s.esperados) - diagnosticos)}; cayeron {sorted(caidos)}"
            invalidas.append(fallo)
            print(f"  INVALIDA {fallo}")
        _restaura()

    rc, caidos, no_colecto = _corre_suite()
    verde = rc == 0 and not caidos and not no_colecto
    limpio = not _corre(
        ["git", "status", "--porcelain", "--", *[str(m.relative_to(RAIZ)) for m in MUTABLES]]
    ).stdout.strip()

    print()
    print("=" * 78)
    print(f"  cazadas  {len(cazadas)}/{len(SONDAS)}")
    print(f"  invalidas {len(invalidas)}/{len(SONDAS)}")
    print(f"  suite verde tras restaurar: {verde}")
    print(f"  mutables limpios en git:    {limpio}")
    print("=" * 78)
    for i in invalidas:
        print(f"  INVALIDA: {i}")
    for f in fallos:
        print(f"  FALLO:   {f}")

    return 0 if (len(cazadas) == len(SONDAS) and verde and limpio) else 1


if __name__ == "__main__":
    raise SystemExit(main())
