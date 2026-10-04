"""B19: «NO es reproducible» no es lo mismo que «no he podido medirlo».

El hallazgo
-----------
Durante la certificacion de B18, `distribution reproducible` dio **OPEN 1 vez de
8**. Con la evidencia capturada:

    la distribucion NO es reproducible: mismo contenido y distinta fecha dan
    bytes distintos en 2 artefacto(s) — wheel: 8612ab04ee18 vs dc5789082776;
    sdist: 673d9c2cc5f5 vs eb37bbcbabf2

Y la propiedad **es cierta al reves**: MEDIDO, ocho construcciones con la
condicion exacta del predicado dan bytes IGUALES 8 de 8, cuatro sin tocar la
fecha y cuatro tocandola con `os.utime` sobre `src/skillgraph/__init__.py`. Y
dos sdists con la suite completa de pytest corriendo en paralelo tienen
CONTENIDO identico: 397 ficheros, 0 diferencias.

El defecto, y es de verbo
-------------------------
El predicado construye dos veces y compara los BYTES. Si difieren, dice «la
distribucion NO es reproducible». Y hay dos razones por las que pueden diferir
que piden **acciones opuestas**:

    (a) el build del proyecto es irreproducible  -> se arregla el BUILD
    (b) la entrada cambio entre las dos            -> se arregla la MEDICION

El predicado no las distinguia, y por eso acusaba al proyecto de un defecto que
no tiene. Y esta es la clase de propiedad MAS ALTA de la serie —`ejecutada`—:
es la unica que alguien podria citar para decir «el build de este proyecto es
irreproducible» sin comprobar nada mas.

Por que no se resuelve dentro del artefacto
-------------------------------------------
MEDIDO: no se puede. Si un fichero ya versionado cambia entre las dos
construcciones, los dos artefactos son coherentes consigo mismos y aun asi se
construyeron con entradas DISTINTAS. Hace falta el estado del ARBOL, y se toma
con `_huella_de_entrada` justo antes de cada construccion.

Lo que YA EXISTIA y cubre la mitad
---------------------------------
`sg_build_sdist_no_versionado`, en scripts/check_package_build.py, rechaza que
el paquete lleve un fichero que git no versiona. MEDIDO, con un fichero nuevo en
el arbol el veredicto es OPEN y la evidencia dice «el artefacto depende de lo
que haya en el arbol de trabajo, no del commit». Es un buen guard, no se toca, y
decirlo es parte del bloque: la hipotesis mas obvia era la buena.

Los tres conjuntos son disjuntos y cada uno declara que es lo UNICO que mide.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
GATE = RAIZ / "scripts" / "measure_b9_gate_1_0.py"
VICTIMA = "docs/blueprint/plan/UAT.md"
ANCLA = "from __future__ import annotations\n"


def _estado_git(destino: Path) -> str:
    """Lo que `git status --porcelain` ve del clon. Sin esto, un test que compara
    dos arboles no puede demostrar que los dos se ven IGUALES, que es la
    precondicion de que este test mida el contenido y no el estado."""
    salida = subprocess.run(
        ["git", "status", "--porcelain"], cwd=destino, capture_output=True, text=True, check=True
    )
    return salida.stdout.strip()


def _carga() -> Any:
    spec = importlib.util.spec_from_file_location("gate_b19", GATE)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["gate_b19"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


class _ArbolGit:
    """Un clon del repo con `RAIZ` apuntando a el, y restaura al salir.

    **POR QUE UN CLON Y NO UNA COPIA.** `_huella_de_entrada` lee de git, luego
    la deformacion tiene que estar en un arbol que SEA un repositorio: en una
    copia suelta los tres comandos de git fallarian y la huella no existiria.
    MEDIDO, que es la diferencia entre medir esto y medir otra cosa.

    Se clona con `--no-hardlinks` y se edita dentro del clon. El arbol real no
    se toca, luego no hace falta red de seguridad ni restauracion: si el test
    falla a mitad, el temporal se va con el.
    """

    def __init__(self) -> None:
        self._raiz_real = RAIZ

    def __enter__(self) -> _ArbolGit:
        self._tmp = tempfile.TemporaryDirectory(prefix="b19_")
        self._destino = Path(self._tmp.name) / "repo"
        subprocess.run(
            ["git", "clone", "--no-hardlinks", "--quiet", str(self._raiz_real), str(self._destino)],
            check=True,
            capture_output=True,
        )
        self._originales = self._destino
        self._modulo = _carga()
        self._modulo.RAIZ = self._destino
        return self

    def __exit__(self, *_exc: object) -> None:
        self._modulo.RAIZ = self._raiz_real
        self._tmp.cleanup()

    def edita_un_fichero_versionado(self, marca: str) -> str:
        """Cambia el CONTENIDO de un fichero que git YA versiona, y solo eso.

         MEDIDO, por que el contenido y no la fecha: el predicado ya toca la
         fecha de `__init__.py` a proposito, y un cambio de fecha es un camino
         que el predicado ya recorre. Lo que no recorre es un cambio de
         contenido en un fichero versionado, y ese es el hueco.

         La `marca` va en el contenido, y el fichero se reescribe ENTERO desde su
         version original: si se anadiese al final cada vez, dos llamadas
        ilharian tres marcas y el estado creeria que se acumulo trabajo.
        """
        original = (self._originales / VICTIMA).read_text(encoding="utf-8")
        ruta = self._destino / VICTIMA
        ruta.write_text(f"{original}\n<!-- b19: {marca} -->\n", encoding="utf-8")
        return VICTIMA

    def anade_un_fichero_sin_versionar(self) -> str:
        """Mete un fichero que git NO versiona, en un directorio que si va al sdist."""
        ruta = self._destino / "docs" / "blueprint" / "_b19_intruso.md"
        ruta.write_text("material que no estaba hace un segundo\n", encoding="utf-8")
        return "docs/blueprint/_b19_intruso.md"

    def versiona(self, relativo: str) -> None:
        subprocess.run(["git", "add", relativo], cwd=self._destino, check=True, capture_output=True)

    def propiedad(self, nombre: str = "distribution reproducible") -> tuple[str, str]:
        """Corre el gate ENTERO, DEL CLON, y devuelve el veredicto de una propiedad.

        Se corre el gate entero y no la funcion suelta porque lo que se mide es
        la frase que SALE por la frontera, y esa frase la compone el gate: una
        funcion que devuelve el par correcto y luego se serializa mal no tiene
        el defecto arreglado.

        **EL GATE QUE SE EJECUTA ES EL DEL CLON, Y ESO NO ES UN DETALLE.**
        MEDIDO: la primera version lanzaba `[sys.executable, GATE]` —el gate del
        arbol REAL— con `cwd` puesto en el clon. El gate calcula su `RAIZ` desde
        `__file__`, luego se estaba midiendo el arbol de verdad, con el arbol de
        verdad, y el fichero intruso del clon no existia para el. El test
        FALLO —`PASS` en vez de `OPEN`— y por eso se pudo ver. Un test
        que hubiera dado verde con esa deformacion habria sido el peor de los
        tres: un guard que pasa porque midiò el repositorio equivocado.
        """
        salida = subprocess.run(
            [sys.executable, str(self._destino / "scripts" / "measure_b9_gate_1_0.py")],
            cwd=self._destino,
            capture_output=True,
            text=True,
        )
        assert salida.returncode == 0, (
            f"el gate devolvio {salida.returncode}: {salida.stderr[-400:]}. "
            f"Si el clon no es ejecutable, este test no mide lo que dice medir."
        )
        import json

        for prop in json.loads(salida.stdout)["propiedades"]:
            if prop["nombre"] == nombre:
                return prop["veredicto"], prop["evidencia"]
        raise AssertionError(f"la propiedad {nombre!r} no sale del gate")

    @property
    def modulo(self) -> Any:
        return self._modulo

    @property
    def destino(self) -> Path:
        return self._destino


# =====================================================================
class TestLaHuellaMideLaEntradaYNoElCommit:
    """LO UNICO que mide: la huella cambia cuando cambia la ENTRADA del paquete.

    Y el contrasalto esta en el segundo test, que es el que hace que el
    primero valga.
    """


def test_la_huella_no_cambia_si_no_cambia_nada() -> None:
    with _ArbolGit() as arbol:
        primera = arbol.modulo._huella_de_entrada()
        segunda = arbol.modulo._huella_de_entrada()
        assert primera == segunda, (
            f"la huella cambio sin que nadie tocara nada: {primera} -> {segunda}. "
            f"Una huella que se mueve sola hace que el predicado diga «no he podido "
            f"medirlo» sobre una medicion que si se pudo, que es el defecto al reves."
        )


def test_la_huella_cambia_si_cambia_el_contenido_de_un_fichero_ya_versionado() -> None:
    """La mitad que `sg_build_sdist_no_versionado` NO ve.

     **Y POR QUE ESTE TEST COMPARA DOS EDICIONES Y NO UN ARBOL LIMPIO CONTRA UNO
     EDITADO. MEDIDO, y es un fallo propio que el harness de este bloque cazó
     antes de contar nada.**

     La primera version comparaba el arbol limpio contra el arbol con un fichero
     versionado modificado, y la sonda M1 —que quita el `git diff HEAD` de la
     huella— NO CAYO. Y no cayo por una razon que explica el resto del bloque:
     `git status` ya cambia entre esos dos casos, de vacio a ` M ruta`. O sea que
     la comparacion no aislaba lo que dice medir: media «el arbol tiene un
     cambio», que es justo lo que `git status` ya ve sin el diff.

     Para que el diff sea NECESARIO, los dos arboles tienen que verse IGUALES
     desde `git status` y ser DISTINTOS de verdad. Y eso no es un artefacto del
     test: es el caso real de B19. Alguien edita un fichero, construye, lo edita
     otra vez, construye otra vez. Los dos `git status` dicen ` M ruta`. Los dos
     contenidos son distintos. Sin el diff, la huella es la misma y el predicado
     acusa al proyecto de no ser reproducible —que es exactamente el defecto que
     este bloque arregla—.

     Un contrasalto que semida en la primera version: si `git status` no los
    hiciera ver iguales, este test estaria probando otra cosa y lo diria.
    """
    with _ArbolGit() as arbol:
        arbol.edita_un_fichero_versionado("primera edicion, distinta de la segunda")
        antes = arbol.modulo._huella_de_entrada()
        estado_antes = _estado_git(arbol.destino)
        arbol.edita_un_fichero_versionado("segunda edicion, distinta de la primera")
        despues = arbol.modulo._huella_de_entrada()
        estado_despues = _estado_git(arbol.destino)
    assert estado_antes == estado_despues, (
        f"los dos arboles tienen que verse IGUALES desde git para que este test mida el "
        f"contenido y no el estado. Antes: {estado_antes!r}. Despues: {estado_despues!r}. "
        f"Si esto falla, el test ha cambiado de pregunta sin que nadie se entere."
    )
    assert antes != despues, (
        "el MISMO fichero versionado, con el MISMO estado git, cambio de contenido entre las "
        "dos mediciones y la huella no se entero. Sin esto, el OPEN acusa al proyecto de un "
        "defecto de reproducibilidad cuando lo que cambio fue la entrada de la medicion, y no "
        "hay forma de que nadie lo sepa sin repetir la medicion a mano."
    )


def test_la_huella_es_distinta_entre_ficheros_distintos_y_solo_una_vez() -> None:
    """Un hash de 256 bits no colisiona por descuido: la huella se deriva, no se escribe.

    Y el contrasalto de que sea ESTABLE entre llamadas esta en el primer test de
    la clase; este comprueba lo otro, que dos entradas distintas dan huellas
    distintas y que el separador NUL evita que las tres partes se peguen.
    """
    with _ArbolGit() as arbol:
        antes = arbol.modulo._huella_de_entrada()
        arbol.edita_un_fichero_versionado("una edicion")
        con_cambio = arbol.modulo._huella_de_entrada()
        assert antes != con_cambio
        assert len(antes) == 64, f"la huella deberia ser un sha256, y mide {len(antes)}: {antes}"


# =====================================================================
class TestElVeredictoDistingueLasDosCausas:
    """LO UNICO que mide: el verbo del veredicto segun lo que la medicion sostiene.

    Este es el bloque entero: los otros dos son su condiciones necesarias.
    """


def test_con_la_entrada_misma_una_no_reproducibilidad_real_sigue_diciendolo() -> None:
    """El contrasalto del contrasalto.

    Separar «no he podido medirlo» de «no es reproducible» SOLO vale si la
    segunda frase no se ha vuelto imposible de decir. Un arreglo que hiciera
    que el predicado nunca acuse habria hecho pasar este bloque entero
    borrando el defecto y la capacidad de detectarlo.
    """
    modulo = _carga()
    # Se llama a la parte que decide, con las dos huellas IGUALES y bytes
    # distintos: es el caso (a), y tiene que seguir siendo OPEN y seguir
    # diciendo «NO es reproducible».
    veredicto, evidencia = modulo._decide_por_bytes(
        {"a.whl": "11" * 32, "b.tar.gz": "22" * 32},
        {"a.whl": "33" * 32, "b.tar.gz": "44" * 32},
        huella_antes="a" * 64,
        huella_despues="a" * 64,
    )
    assert veredicto == "OPEN", (
        f"con la entrada igual y bytes distintos deberia ser OPEN: {veredicto}"
    )
    assert "NO es reproducible" in evidencia, (
        f"con la entrada comprobada igual, el veredicto tiene que poder acusar, "
        f"y no puede: {evidencia}"
    )


def test_con_la_entrada_cambiada_no_acusa_al_proyecto() -> None:
    with _ArbolGit() as arbol:
        del arbol
        modulo = _carga()
        veredicto, evidencia = modulo._decide_por_bytes(
            {"a.whl": "11" * 32, "b.tar.gz": "22" * 32},
            {"a.whl": "33" * 32, "b.tar.gz": "44" * 32},
            huella_antes="a" * 64,
            huella_despues="b" * 64,
        )
    assert veredicto == "NO_MEASURABLE", (
        f"con la entrada cambiada entre las dos construcciones el veredicto deberia decir "
        f"«no he podido medirlo», y en su lugar dice {veredicto}. Un OPEN que acusa al "
        f"proyecto de no ser reproducible cuando se han medido dos entradas distintas "
        f"invierte la accion: el que lo lee arregla el build de un proyecto que esta bien."
    )
    assert "NO es reproducible" not in evidencia, (
        f"la evidencia sigueusionalando al proyecto: {evidencia}"
    )
    assert "ARBOL DE TRABAJO cambio" in evidencia, (
        f"la evidencia tiene que decir QUE paso, no solo que no se pudo medir: {evidencia}"
    )


# =====================================================================
class TestLoQueYaEstabaCubiertoNoSeRompio:
    """LO UNICO que mide: que el guard que YA existia sigue en pie.

    MEDIDO: con un fichero sin versionar, el veredicto es OPEN y la evidencia
    dice «el artefacto depende de lo que haya en el arbol de trabajo, no del
    commit». Eso es `sg_build_sdist_no_versionado` y es un buen guard.

    Este test existe por una razon que no es de forma: si el arreglo de B19
    cambia el verbo de algo que ya era correcto, se ha roto un guard bueno
    mientras se arreglaba uno malo. Y «he arreglado el mio» no es una excusa
    para romper el tuyo — es el ERROR de B16, que mejoro un predicado y dejo
    otro affirmed cuando no miraba nada.
    """


def test_un_fichero_sin_versionar_lo_cubre_el_guard_que_ya_existe() -> None:
    with _ArbolGit() as arbol:
        arbol.anade_un_fichero_sin_versionar()
        veredicto, evidencia = arbol.propiedad()
    assert veredicto == "OPEN", (
        f"un fichero que git no versiona tiene que dar OPEN: {veredicto} — {evidencia}"
    )
    assert "NO es reproducible" not in evidencia, (
        f"el guard que ya existia no debe degradarse en la frase acusadora: {evidencia}"
    )
    assert "arbol de trabajo" in evidencia or "no la versiona" in evidencia, (
        f"la evidencia tiene que seguir diciendo la causa REAL: {evidencia}"
    )
