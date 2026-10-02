"""WI-95: el CHANGELOG afirma releases que no existen y calla releases que sí.

Por que este fichero existe
---------------------------
`STATE.yaml` tiene una red que lo ata a `git tag` con igualdad exacta
(`tests/test_state_release_integrity.py`, 8 tests, de WI-74). **`CHANGELOG.md`
no tenia ninguna.** Medido antes de escribir esto:

    tags SemVer en git .................. 46
    versiones distintas en CHANGELOG .... 44
    tags SIN seccion .................... 2   (v0.16.14, v0.16.15)
    secciones SIN tag ................... 0
    cabeceras [Unreleased] de bloques ya publicados ... 3
    tests que parseen el CHANGELOG ...... 0

Las tres cabeceras `[Unreleased]` eran de WI-89 (v0.16.15) y WI-87 + WI-88
(v0.16.14): tres bloques **publicados hace dos releases** que el CHANGELOG
seguia declarando sin publicar. Es la misma forma que el resto de los hallazgos
de WI-91 a WI-94: un documento que afirma algo y nada lo comprueba.

Que fijan estos tests
--------------------
No comprueban el texto de una seccion concreta — eso se agingeja y se
falsearia. Comprueban la **propiedad** que el fichero dice tener:

  1. Biyeccion con `git tag`: todo tag SemVer tiene seccion, y toda seccion
     con version tiene tag. Sin esto, `v0.16.14` y `v0.16.15` pueden quedar
     sin publicar en el changelog sin que nadie se entere.
  2. Nada publicado se anuncia como `[Unreleased]`. Un `[Unreleased]` es una
     promesa de que el trabajo aun no ha salido; si el tag existe, la promesa
     es falsa.
  3. Una seccion `(cont.)` va detras de su version, que es lo que la hace una
     continuacion y no una version suelta.
"""

from __future__ import annotations

import re
import subprocess
from itertools import pairwise
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parent.parent
CHANGELOG: Final = ROOT / "CHANGELOG.md"
SEMVER: Final = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
CABECERA: Final = re.compile(r"^## \[([^\]]+)\](.*)$", re.M)


def _secciones() -> list[tuple[str, bool]]:
    """(version, es_continuacion) en el orden en que aparecen en el fichero.

    El `(cont.)` va FUERA de los corchetes — `## [0.16.19] (cont.) — ...` — y
    un regex que se quede en el primer `]` no lo ve. Ya le paso un texto por
    la version equivocada por eso.
    """
    out: list[tuple[str, bool]] = []
    for titulo, resto in CABECERA.findall(CHANGELOG.read_text(encoding="utf-8")):
        m = re.match(r"(\d+\.\d+\.\d+)", titulo)
        if m:
            out.append((m.group(1), "(cont.)" in resto))
    return out


def _tags() -> list[str]:
    salida = subprocess.run(
        ("git", "tag", "--list", "v*"),
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return sorted(
        {t[1:] for t in salida.stdout.split() if SEMVER.match(t)},
        key=lambda v: tuple(int(p) for p in v.split(".")),
    )


def _en_changelog() -> set[str]:
    return {v for v, _ in _secciones()}


# --- 1. Biyeccion con git -------------------------------------------------


class TestBiyeccionConGit:
    def test_todo_tag_semver_tiene_seccion(self) -> None:
        """Un tag que no aparece en el changelog es una release sin publicar.

        MEDIDO en WI-95: faltaban `v0.16.14` y `v0.16.15`. Sus commits si
        estaban, etiquetados y registrados en STATE.yaml; lo que faltaba era
        el relato, que es lo que se lee para saber que cambio.
        """
        faltan = [v for v in _tags() if v not in _en_changelog()]
        assert not faltan, (
            f"tags de git sin seccion en CHANGELOG.md: {faltan}. Una release "
            "que no aparece en el changelog no se puede contar"
        )

    def test_toda_seccion_con_version_tiene_tag(self) -> None:
        """La inversa: una seccion que anuncia una version que no existe."""
        inventadas = [v for v in sorted(_en_changelog()) if v not in set(_tags())]
        assert not inventadas, (
            f"CHANGELOG.md tiene seccion de versiones que git no tiene: {inventadas}"
        )

    def test_no_hay_secciones_para_v(self) -> None:
        """La convencion es `[0.16.19]`, sin la `v` que si lleva el tag."""
        for titulo, _ in CABECERA.findall(CHANGELOG.read_text(encoding="utf-8")):
            assert not re.match(r"^v\d", titulo), (
                f"la seccion `{titulo}` lleva la `v` del tag; la convencion del "
                "fichero es la version sin `v`"
            )


# --- 2. Nada publicado puede anunciado como [Unreleased] -------------------


class TestNadaPublicadoSeAnunciaComoUnreleased:
    def test_no_hay_unreleased_que_false(self) -> None:
        """MEDIDO en WI-95: tres, de WI-87, WI-88 y WI-89.

        Un `[Unreleased]` es una promesa de que el trabajo no ha salido. Si el
        bloque ya esta en un tag, la promesa es falsa y el changelog esta
        mintiendo sobre lo que el proyecto ha entregado.
        """
        texto = CHANGELOG.read_text(encoding="utf-8")
        falsos = [ln for ln in texto.splitlines() if re.match(r"^## \[Unreleased\]", ln)]
        assert not falsos, (
            "estos bloques estan `[Unreleased]` pero su release ya existe:\n  "
            + "\n  ".join(falsos)
        )

    def test_la_seccion_de_la_iniciativa_no_es_una_version(self) -> None:
        """`[Unreleased — evolution-v2 ...]` no es una seccion de release.

        Es legitimo: no reclama una version, es un registro de la iniciativa.
        Se comprueba explicitamente para que el test de arriba no lo mate por

        exceso de celo.
        """
        texto = CHANGELOG.read_text(encoding="utf-8")
        assert "## [Unreleased — evolution-v2" in texto, (
            "la seccion de la iniciativa evolution-v2 sigue en su sitio"
        )


# --- 3. La regla de (cont.) ------------------------------------------------


class TestReglaDeContinuacion:
    def test_una_continuacion_tiene_su_version_padre_justo_antes(self) -> None:
        """`[0.16.18] (cont.)` sin `[0.16.18]` antes es una version suelta."""
        huerfanas = [
            v
            for i, (v, cont) in enumerate(_secciones())
            if cont and (i == 0 or _secciones()[i - 1][0] != v)
        ]
        assert not huerfanas, (
            f"secciones (cont.) sin su version padre inmediatamente antes: {huerfanas}"
        )

    def test_solo_la_primera_seccion_de_una_version_no_es_continuacion(self) -> None:
        """A partir de la segunda, toda seccion de una version es `(cont.)`.

        La mutacion M3 de este bloque hizo justo lo contrario —convertir un
        `(cont.)` en una seccion de version mas— y **no la cazó** ningun
        test. La asercion que existia solo miraba el numero de repeticiones,
        y dos secciones no son «mas de dos». El invariante correcto no es
        contar: es que **solo la primera aparicion de una version puede no
        ser continuacion**. Sin eso, la convencion `(cont.)` es
        decorativa, porque nada obliga a marcarla.
        """
        vistas: dict[str, int] = {}
        sospechosas: list[str] = []
        for v, cont in _secciones():
            vistas[v] = vistas.get(v, 0) + 1
            if vistas[v] > 1 and not cont:
                sospechosas.append(f"{v} (aparicion #{vistas[v]})")
        assert not sospechosas, (
            "estas secciones repiten una version y no son continuaciones: "
            f"{sospechosas}. A partir de la segunda aparicion debe ser `(cont.)`"
        )


# --- El desorden del tramo antiguo, medido y ACEPTADO -----------------------


class TestOrdenDelTramoAntiguo:
    """Esto documenta un defecto MEDIDO que este bloque NO arregla.

    El tramo antiguo del fichero no esta en orden descendente: a partir de
    `0.14.1` salta a `0.7.0`, recorre `0.7.0 .. 0.3.0` en ASCENDENTE, y luego
    `0.8.1 .. 0.14.0` tambien en ascendente, con un `0.8.0 -> 0.7.3` suelto.

    NO se corrige aqui, y el motivo es una decision, no una pereza:

      * Es **cosmetico**. Ningun lector, script ni release depende del orden.
      * Es **preexistente** y de una epoca con otra convencion.
      * Corregirlo mueve 20 secciones de sitio, y mover texto historico es
        exactamente el riesgo de reescribir historia que este proyecto lleva
        cuatro bloques evitando (WI-91, WI-92, WI-93, WI-94).

    La alternativa —exigir orden descendente— haria fallar el guard en el
    primer run y enseRIA a ignorar al guard, que es peor que el defecto.

    Lo que se hace en su lugar es que quede **escrito**, medido y con las
    referencias, para que la decision sea reversible si alguien la quiere
    tomar con criterio.
    """

    def test_el_tramo_moderno_se_mantiene_ordenado(self) -> None:
        """El desorden antiguo se acepta; el moderno no, y se vigila.

        Este test NO exige orden global —exigirlo haria fallar el guard en el
        primer run por culpa de 20 secciones de 2026-09, y un guard que
        falla por ruido se aprende a ignorar—. Exige algo mas estrecho y
        util: que **la zona que SI se escribe hoy** siga en orden
        descendente. Si alguien reordena el tramo antiguo, este test no le
        molesta; si alguien inserta mal una seccion nueva, si.
        """
        seq = [v for v, _ in _secciones()]
        desorden = [
            (a, b)
            for a, b in pairwise(seq)
            if tuple(int(p) for p in b.split(".")) > tuple(int(p) for p in a.split("."))
        ]
        # El tramo moderno (>= 0.14.1) SI esta ordenado; el desorden es anterior.
        moderno = [(a, b) for a, b in desorden if tuple(int(p) for p in a.split(".")) >= (0, 14, 1)]
        assert not moderno, (
            f"el tramo moderno se ha desordenado: {moderno}. El desorden antiguo "
            "esta aceptado y documentado; el moderno no lo esta"
        )
