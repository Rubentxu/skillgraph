"""B20: el gate se contradecia a si mismo, y la razon era un sufijo.

El hallazgo
-----------
`ontology extensible` y `core sin dependencias de impl. externa` son dos
propiedades del MISMO gate sobre la MISMA frontera: que `core/` no dependa de
lo que vive fuera de el. Y se contradecian.

MEDIDO, sobre el arbol real, con un solo import puesto en `core/`:

    core/ importa skillgraph.packaging.manifest
      ontology extensible    -> PASS   «no nombra ningun tipo de recurso»
      core sin dependencias  -> OPEN   «depende de fuera de si mismo»

Dos veredictos sobre el mismo hecho, y no son el mismo. MEDIDO sobre la
superficie real del proyecto, no sobre casos inventados: **7 contradicciones de
9**.

La razon es que `ontology extensible` decidia con UN SUFIJO escrito a mano,
`^[A-Z][A-Za-z]*Pack$`, y de ese patron salen las dos mitades del defecto:

1. **No ve lo que importa.** De los ocho tipos de recurso que el proyecto
   DECLARA de verdad —`PackManifest`, `CompiledResource`, `CapabilitySpec`,
   `BrickType`, `Catalog`, `Brick`— el patron ve CERO. `PackManifest` es el
   manifiesto de un pack, el tipo central del proyecto, y no acaba en `Pack`.
2. **Ve lo que no importa.** El unico nombre que contaba era `FilaDePack`, que
   es una FILA de la tabla de packs, no un tipo de recurso. Con su import
   puesto, el veredicto era `OPEN` acusando al nucleo de depender de los
   recursos. La divergencia va en las DOS direcciones.

Y el comentario del codigo de al lado razonaba —correctamente— que no escribir
una lista de tipos evita una segunda fuente de verdad. Lo que no ve es que **un
patron por forma ES una lista**, mas corta y peor, porque decide como se
ESCRIBE un nombre en vez de a que conjunto PERTENECE. El endurecimiento de B16
fue sobre el FORMATO de la mirada —de cadenas a imports y atributos—: una vista
mas aguda de una cosa que no es la que hay.

Que entra
---------
El conjunto de tipos se DERIVA del arbol, de los paquetes que el proyecto llama
recursos por el nombre de su directorio, y la evidencia dice cuantos son y de
donde salen. Los docstrings que nombran un recurso se CUENTAN y se DICEN sin
abrir el veredicto: documentar la frontera es lo contrario de depender de ella.

El techo, y hay que decirlo
---------------------------
El arreglo deja **3** contradicciones, y no a cero, y el motivo es el hallazgo
mas incomodo del bloque: **«que es un recurso» no es un concepto que el codigo
contenga**. `CompiledResource` vive en `knowledge/`, `CapabilitySpec` en
`platform/ports/`, y el patron por nombre de directorio no los alcanza, porque
la convencion no es una definicion. Declarar el concepto es una decision de
producto, no una tarea de guard, y por eso este bloque no la toma: la mide y la
deja escrita. Sin esa decision, la propiedad tiene un techo, y un guard con
techo tiene que DECIR que lo tiene — que es lo que hace el ultimo conjunto.

Los tres conjuntos son disjuntos y cada uno declara que es lo UNICO que mide.
"""

from __future__ import annotations

import ast
import importlib.util
import pathlib
import sys
from typing import Any

RAIZ = pathlib.Path(__file__).resolve().parents[1]
GATE = RAIZ / "scripts" / "measure_b9_gate_1_0.py"
VICTIMA = "src/skillgraph/core/runtime_types.py"
ANCLA = "from __future__ import annotations\n"

#: La superficie REAL del proyecto, medida por AST y no inventada. El contrasalto
#: de que un guard de contradicciones se mida con una lista escrita a mano seria
#: que la lista misma se quede vieja sin que nadie lo note —el error de WI-114,
#: y el de B16 y el de B19—, asi que estos ocho se contrastan contra el arbol en
#: el test que los usa, y el test FALLA si alguno ya no existe.
SUPERFICIE = (
    ("skillgraph.packaging.manifest", "PackManifest"),
    ("skillgraph.knowledge.context_controller", "CompiledResource"),
    ("skillgraph.platform.ports.capabilities", "CapabilitySpec"),
    ("skillgraph.resources.registry", "BrickType"),
    ("skillgraph.resources.catalog", "Catalog"),
    ("skillgraph.domain.skill_importer", "SkillImportReport"),
    ("skillgraph.resources.bricks", "Brick"),
    ("skillgraph.packaging.registry", "FilaDePack"),
)


def _carga() -> Any:
    spec = importlib.util.spec_from_file_location("gate_b20", GATE)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["gate_b20"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


class _ArbolCopiado:
    """Una copia de `src/` con `RAIZ` apuntando a ella, y restaura al salir.

    MEDIDO: con un clon de git, `_tipos_de_recurso()` —que deriva el conjunto del
    arbol— devolveria el conjunto del ARBOL REAL y no el de la copia, luego la
    deformacion se mediria contra una verdad ajena. Una copia de `src/` evita
    tener que clonar y es suficiente: los dos predicados que se comparan solo
    leen `src/`.
    """

    def __init__(self) -> None:
        self._raiz_real = RAIZ

    def __enter__(self) -> _ArbolCopiado:
        import shutil
        import tempfile

        self._tmp = tempfile.TemporaryDirectory(prefix="b20_")
        self._destino = pathlib.Path(self._tmp.name)
        shutil.copytree(self._raiz_real / "src", self._destino / "src", symlinks=True)
        self._modulo = _carga()
        self._modulo.RAIZ = self._destino
        return self

    def __exit__(self, *_exc: object) -> None:
        self._modulo.RAIZ = self._raiz_real
        self._tmp.cleanup()

    def anade_import(self, modulo: str, clase: str) -> None:
        ruta = self._destino / VICTIMA
        texto = ruta.read_text(encoding="utf-8")
        if texto.count(ANCLA) != 1:
            raise AssertionError(
                f"el ancla aparece {texto.count(ANCLA)} veces en {VICTIMA}. Si ese modulo "
                f"ha cambiado de forma, la deformacion de este test ya no es la que dice ser."
            )
        ruta.write_text(
            texto.replace(ANCLA, f"{ANCLA}\nfrom {modulo} import {clase}  # noqa: F401\n", 1),
            encoding="utf-8",
        )

    def predicados(self) -> tuple[tuple[str, str], tuple[str, str]]:
        return (
            self._modulo._ontology_extensible(),
            self._modulo._core_sin_dependencias_de_impl_externa(),
        )

    @property
    def modulo(self) -> Any:
        return self._modulo


# =====================================================================
class TestElConjuntoSeDerivaYNoEsUnSufijo:
    """LO UNICO que mide: que lo que cuenta como recurso sale del ARBOL.

    Y el contrasalto del contrasalto esta en el segundo test: si el conjunto
    estuviera escrito a mano, el primero pasaria igual.
    """


def test_el_conjunto_de_recursos_lo_declaran_los_paquetes_no_un_sufijo() -> None:
    with _ArbolCopiado() as arbol:
        mod = arbol.modulo
        recursos = mod._tipos_de_recurso()
        modulos = {pathlib.Path(v).parts[2] for v in recursos.values()}
    assert recursos, "el conjunto de recursos ha salido vacio: nadie mira nada y todo pasa"
    assert modulos == set(mod.PAQUETES_DE_RECURSO), (
        f"el conjunto dice venir de {mod.PAQUETES_DE_RECURSO} y sus tipos viven en "
        f"{sorted(modulos)}. Si la derivacion y la constante se han desincronizado, la "
        f"evidencia esta describiendo una base que ya no es la que se recorre."
    )


def test_los_ocho_tipos_de_la_superficie_siguen_existiendo() -> None:
    """El contrasalto: si esta lista se queda vieja, el guard mide una superficie que ya no esta.

    Sin este test, `SUPERFICIE` podria seguir nombrando tipos que el proyecto borro, y
    el guard de contradicciones pasaria en verde sin comprobar nada: estaria
    midiendo que dos predicados no se contradicen sobre tipos que ya no existen.
    Es el error de WI-114 aplicado a la lista de la medicion.
    """
    declarados: set[str] = set()
    for f in sorted((RAIZ / "src" / "skillgraph").rglob("*.py")):
        arbol = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        declarados.update(n.name for n in ast.walk(arbol) if isinstance(n, ast.ClassDef))
    faltan = sorted(clase for _, clase in SUPERFICIE if clase not in declarados)
    assert not faltan, (
        f"la superficie que usa este fichero nombra clases que el proyecto ya no declara: "
        f"{faltan}. O se anadieron al proyecto, o las borro alguien, y en los dos casos "
        f"este guard esta midiendo una superficie que no existe."
    )


# =====================================================================
class TestElGateNoSeContradiceASiMismo:
    """LO UNICO que mide: que las dos propiedades digan lo mismo sobre el mismo hecho.

    Este es el bloque entero. Los otros dos son sus condiciones necesarias.
    """

    def _las_dos(self, arbol: _ArbolCopiado) -> tuple[str, str, str, str]:
        (o, _), (c, _) = arbol.predicados()
        return o, "", c, ""

    def test_un_tipo_de_recurso_que_las_dos_ven_no_puede_ser_un_solo_pass(self) -> None:
        """La forma del invariante: si la frontera se rompe, LAS DOS se abren.

        MEDIDO antes del arreglo: 7 contradicciones de 9, y la mayoria con esta
        forma —`ontology` en PASS y `core sin dependencias` en OPEN—. Un
        `PASS` que la otra propiedad contradice no es un `PASS` conservador: es
        un `PASS` que miente sobre un hecho que el gate ya ha medido bien en
        otra parte.
        """
        rotas: list[str] = []
        for modulo, clase in SUPERFICIE:
            with _ArbolCopiado() as arbol:
                arbol.anade_import(modulo, clase)
                (o, _), (c, _) = arbol.predicados()
            if c == "OPEN" and o != "OPEN":
                rotas.append(f"{clase} (ontology={o}, core_sin_dep={c})")
        # El techo, y no se maquilla: los tres que quedan son tipos que el
        # proyecto llama recursos en un paquete cuyo NOMBRE no lo dice. Cerrar
        # esta lista a cero sin declarar el concepto seria tapar el hallazgo.
        assert len(rotas) <= 3, (
            f"{len(rotas)} contradicciones, y solo se admiten 3 Pending: "
            f"{rotas}. Un guard que se pone rojo al GUARDAR la lista"
            f"anade una propiedad mas que nadie ha decidido: que pasaria a ser "
            f"la septima vez que un patron escrito a mano deja de ver la superficie."
        )

    def test_la_evidencia_dice_sobre_que_conjunto_y_sobre_que_recorrido(self) -> None:
        with _ArbolCopiado() as arbol:
            _, evidencia = arbol.modulo._ontology_extensible()
        mod = arbol.modulo
        assert f"{len(mod._tipos_de_recurso())} tipos de recurso" in evidencia, (
            f"la evidencia no dice cuantos tipos de recurso hay: {evidencia}"
        )
        assert "MEDIDO sobre" in evidencia and "ficheros de core/" in evidencia, (
            f"la evidencia no dice cuantos ficheros se recorrieron: {evidencia}"
        )
        for paquete in mod.PAQUETES_DE_RECURSO:
            assert paquete in evidencia, (
                f"la evidencia no dice de donde sale el conjunto, y no menciona {paquete}: "
                f"{evidencia}"
            )


# =====================================================================
class TestUnDocstringNoEsUnaDependencia:
    """LO UNICO que mide: que la DOCUMENTACION no abra el veredicto.

    MEDIDO, y es una DECISION, no un_descuido: `core/` menciona `WorkflowPlan`
    en tres sitios y los tres son documentacion de `NewType`. Documentar la
    frontera es lo contrario de depender de ella. Contarlos seria un `OPEN`
    sobre un arbol sano, y un `OPEN` falso en estado sano es el fallo mas caro
    que puede tener un guard, porque entrena a su lector a no creerlo.
    """


def test_un_docstring_que_nombra_un_recurso_no_abre_el_veredicto() -> None:
    with _ArbolCopiado() as arbol:
        ruta = arbol._destino / VICTIMA
        original = ruta.read_text(encoding="utf-8")
        ruta.write_text(
            original
            + '"""El nucleo documenta que un Catalog se resuelve fuera, sin depender de el."""\n',
            encoding="utf-8",
        )
        try:
            veredicto, evidencia = arbol.modulo._ontology_extensible()
        finally:
            ruta.write_text(original, encoding="utf-8")
    assert veredicto == "PASS", (
        f"un docstring que nombra un recurso no es una dependencia y no debe abrir el "
        f"veredicto: {veredicto} — {evidencia}"
    )
    assert "Catalog" in evidencia, (
        f"pero tiene que DECIRSE, porque es informacion y callarsela seria un verde que no "
        f"dice lo que sabe: {evidencia}"
    )


def test_una_cadena_que_se_ejecuta_si_es_una_dependencia() -> None:
    """El contrasalto del contrasalto: separarlos sin que los dos sean OPEN.

    Si las cadenas que se ejecutan tampoco abrieran el veredicto, el test
    anterior pasaria por el motivo equivocado: estariamos viendo que el
    clasificador nunca clasifica.
    """
    with _ArbolCopiado() as arbol:
        ruta = arbol._destino / VICTIMA
        original = ruta.read_text(encoding="utf-8")
        ruta.write_text(original + 'CATALOGO_POR_DEFECTO = "Catalog"\n', encoding="utf-8")
        try:
            veredicto, evidencia = arbol.modulo._ontology_extensible()
        finally:
            ruta.write_text(original, encoding="utf-8")
    assert veredicto == "OPEN", (
        f"una cadena que se EJECUTA y nombra un recurso si es una dependencia, y el "
        f"veredicto dice {veredicto} — {evidencia}"
    )
