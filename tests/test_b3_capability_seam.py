"""B3 — la costura: el puerto de capabilities, alcanzable desde produccion.

QUE FALTA Y POR QUE ESTE FICHERO EXISTE
---------------------------------------
B3 entrego un contrato de capability (`platform/ports/capabilities.py`) y
un gate que demuestra que el contrato **se puede cumplir**: una capability
inventada dentro de un test se registra, se resuelve y se invoca.

Eso no demuestra que el **runtime lo pueda alcanzar**. Y medido
(`.pipelinek/b3_wiring_measure.py`, criterio declarado antes de mirar):

    imports_produccion               : []
    construcciones de Registry en src : []
    ficheros que importan el puerto   : tests/test_b3_capability_kernel.py
    veredicto                         : INALCANZABLE_DESDE_PRODUCCION

Dieciseis construcciones de `CapabilityRegistry` en el arbol. Las dieciseis
estan en un test. El criterio de B3 en el roadmap —«anadir una capability
sin modificar `RunController`»— se cumplia de forma **vacia**: se podia
anadir una sin tocar el core porque el core no la ve.

El hueco original —«se declaraba, se transportaba, se imprimia, se
validaba, y NADIE lo resolvia»— tenia esta forma exacta. Solo se ha movido
de sitio.

LA POLITICA, DECIDIDA EXPLICTAMENTE
----------------------------------
El registro se INYECTA y su ausencia es la politica:

  - **Sin registro** (default, `None`): el comportamiento es EXACTAMENTE el
    de hoy. Un plan que declara `'stale'` —que medimos que no es una
    capability sino un `FreshnessState`, y que `build_capabilities` produce
    — sigue ejecutandose igual. **Cero ruptura**, y por eso este cambio se
    puede aterrizar sin migrar nada.

  - **Con registro**: la declaracion pasa a ser un CONTRATO. Lo que el plan
    declara tiene que existir en el despliegue, y si no existe el nodo
    queda FAILED con `CapabilityNotFound` —un `SkillGraphError` tipado, con
    `code`, que la CLI traduce a exit code (WI-109)—.

La asimetria es el punto. Exigir siempre habria roto los 9 sitios que
construyen `node.capabilities` y los 30 que lo leen, entre ellos el
`'stale'` de `knowledge/context_controller.py:139::build_capabilities`.
Exigir nunca habria dejado el puerto sin consumidor, que es el estado
medido. Inyectar hace que la exigencia la pida **quien despliega**, y solo
si la pide.

DONDE ENTRA, Y POR QUE NO HAY QUE INVENTAR NADA
-----------------------------------------------
`RunController.__init__` ya recibe `adapter: AgentAdapter` como
dependencia inyectada por palabra clave, y `NodeExecutionDelegations` la
usa como `self._adapter`. La costura ya estaba escrita: un
`CapabilityRegistry` cabe en la misma firma.

Y el camino de error tampoco es nuevo: `_compile_node_handoff` ya captura
`SkillGraphError` y llama a `_fail_node_with` (H9-context-in-run). Lanzar
`CapabilityNotFound` desde ahi mete el nodo en FAILED con el error
persistido, sin tocar una sola linea de ese camino.

LO QUE ESTE FICHERO NO AFIRMA
-----------------------------
No se afirma que las capabilities se INVOKEN durante la ejecucion de un
nodo: no se invocan. `Handoff.capabilities` sigue siendo un
`tuple[str, ...]` y cambiar su forma esta MEDIDO como ruptura de datos
—`runtime/handoff.py:195::Handoff.to_dict` lo mete en el hash firmado—,
que es materia de B8. Lo que se hace aqui es que la declaracion tenga un
consumidor que la verifique, en vez de viajar a un prompt sin que nadie la
mire.
"""

from __future__ import annotations

import ast
import tempfile
from pathlib import Path
from typing import Any, Final

from skillgraph.core.errors import SkillGraphError
from skillgraph.domain.dsl import PlanBuilder, node_name
from skillgraph.platform.ports.capabilities import (
    CapabilityNotFound,
    CapabilityRegistry,
    CapabilityRequest,
    CapabilityResult,
    CapabilitySpec,
)
from skillgraph.platform.storage import Storage
from skillgraph.runtime.agent import AgentResult
from skillgraph.runtime.runcontroller import RunController

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
SRC: Final = REPO_ROOT / "src"
TESTS: Final = REPO_ROOT / "tests"

TENANT: Final = "t-b3seam"
PROJECT: Final = "p-b3seam"

#: La capability que declara el plan de los tests de este fichero.
DECLARADA: Final = "code.analysis"


class _CapabilityDePrueba:
    """Un `Capability` de verdad, no un espia: implementa el Protocol."""

    def __init__(self, type_name: str = DECLARADA) -> None:
        self._spec = CapabilitySpec(type_name=type_name, summary="la de este test")

    @property
    def spec(self) -> CapabilitySpec:
        return self._spec

    def invoke(self, request: CapabilityRequest) -> CapabilityResult:
        return CapabilityResult(
            spec=self._spec,
            adapter="adapter-de-prueba",
            payload={"subject": request.subject},
        )


class _AdapterQueCuenta:
    """El AgentAdapter, mas un contador de invocaciones.

    El contador existe para una propiedad que de otro modo no se puede
    observar: que un nodo FAILED **no llega a invocar el adapter**. Que el
    nodo falle ya se ve en la fila; que no se haya gastado una llamada de
    red por un plan mal declarado, no.
    """

    def __init__(self) -> None:
        self.invocaciones = 0

    def invoke(self, handoff: Any) -> AgentResult:
        self.invocaciones += 1
        return AgentResult(outcome="texto", result={"hecho": True})


def _plan(*capabilities: str) -> Any:
    return (
        PlanBuilder()
        .add_node(
            node_name("n1"),
            expected="texto",
            capabilities=tuple(capabilities),
        )
        .starts_at(node_name("n1"))
        .build()
    )


def _correr(
    *capabilities: str,
    registro: CapabilityRegistry | None = None,
    adapter: _AdapterQueCuenta | None = None,
) -> tuple[Storage, str, _AdapterQueCuenta]:
    """Ejecuta UN nodo. Devuelve (storage, run_id, adapter)."""
    tmp = tempfile.TemporaryDirectory()
    storage = Storage(Path(tmp.name) / "seam.sqlite")
    ad = adapter if adapter is not None else _AdapterQueCuenta()
    ctl = RunController(
        runs=storage,
        events=storage,
        policy=storage,
        adapter=ad,
        capabilities=registro,
    )
    run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=_plan(*capabilities))
    ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
    return storage, run_id, ad


def _nodo(storage: Storage, run_id: str) -> tuple[str, str | None]:
    """(estado, error) de la unica node_execution del run."""
    filas = storage._conn.execute(
        "SELECT state, error FROM node_executions WHERE run_id = ?", (run_id,)
    ).fetchall()
    assert len(filas) == 1, f"se esperaba 1 node_execution, hay {len(filas)}"
    return filas[0][0], filas[0][1]


class TestSinRegistroNoCambiaNada:
    """La mitad de compatibilidad. Sin esta, el arreglo es una ruptura.

    Es la mitad que hace que esto se pueda aterrizar sin migrar nada: el
    default tiene que ser `None` y `None` tiene que significar
    'exactamente lo que se hacia antes'.
    """

    def test_un_nodo_que_declara_una_capability_que_nadie_tiene_se_ejecuta_igual(self) -> None:
        """El caso REAL, no un caso inventado.

        `knowledge/context_controller.py:139::build_capabilities` produce
        `('stale',)`, y `'stale'` es un `FreshnessState`, no una
        capability. Si exigir siempre, ese plan dejaria de funcionar.
        """
        storage, run_id, _ = _correr("stale")
        estado, error = _nodo(storage, run_id)
        assert estado == "SUCCEEDED", (
            f"un plan que declara una capability sin registro dejo de "
            f"funcionar: estado={estado!r}, error={error!r}. El default "
            f"tiene que preservar el comportamiento de hoy."
        )
        storage.close()

    def test_un_nodo_sin_capabilities_tampoco_cambia(self) -> None:
        storage, run_id, _ = _correr()
        assert _nodo(storage, run_id)[0] == "SUCCEEDED"
        storage.close()


class TestConRegistroLaDeclaracionEsUnContrato:
    """La mitad nueva: quien inyecta el registro pide que se exija."""

    def test_una_capability_que_el_registro_tiene_pasa(self) -> None:
        storage, run_id, ad = _correr(
            DECLARADA, registro=CapabilityRegistry((_CapabilityDePrueba(),))
        )
        assert _nodo(storage, run_id)[0] == "SUCCEEDED"
        assert ad.invocaciones == 1
        storage.close()

    def test_una_capability_que_el_registro_no_tiene_falla_el_nodo(self) -> None:
        storage, run_id, _ = _correr("code.analysis", registro=CapabilityRegistry(()))
        estado, _error = _nodo(storage, run_id)
        assert estado == "FAILED", (
            f"el plan declara 'code.analysis' y el despliegue no la resuelve, "
            f"pero el nodo quedo {estado!r}. Un plan que promete una "
            f"capacidad que no existe no puede ejecutarse como si nada."
        )
        storage.close()

    def test_el_error_es_del_dominio_y_tiene_code(self) -> None:
        """`CapabilityNotFound` cuelga de `SkillGraphError` y trae `code`.

        No basta con que el nodo falle: tiene que fallar por una razon que
        la CLI sepa traducir a exit code (WI-109). Un `KeyError` aqui
        seria un Traceback al operador.
        """
        assert issubclass(CapabilityNotFound, SkillGraphError)
        assert CapabilityNotFound.code == "sg_capability_not_found"

    def test_el_error_dice_que_se_pidio_y_que_hay(self) -> None:
        """Las dos caras. Un 'no encontrada' sin contexto obliga a un `ls`
        a mano sobre el despliegue, que es el trabajo que el error existe
        para evitar."""
        storage, run_id, _ = _correr(
            "code.analysis", registro=CapabilityRegistry((_CapabilityDePrueba("otra"),))
        )
        _, error = _nodo(storage, run_id)
        assert error and "code.analysis" in error, (
            f"el error no dice que capability se pidio: {error!r}"
        )
        assert error and "otra" in error, (
            f"el error no dice que hay disponibles: {error!r}. Con un "
            f"despliegue de N packs, buscar a mano es el problema que el "
            f"mensaje viene a evitar."
        )
        storage.close()

    def test_el_adapter_no_se_invoca_cuando_la_resolucion_falla(self) -> None:
        """La propiedad que no se ve en la fila del nodo.

        Que el nodo quede FAILED ya se comprueba en otro test. Lo que NO
        se ve es si se gastó una llamada al adapter antes de fallar: un
        plan mal declarado que paga una llamada de red y luego falla parece
        funcional.
        """
        storage, run_id, ad = _correr("code.analysis", registro=CapabilityRegistry(()))
        assert _nodo(storage, run_id)[0] == "FAILED"
        assert ad.invocaciones == 0, (
            f"el adapter se invoco {ad.invocaciones} veces para un nodo que "
            f"no podia resolver su capability. La resolucion va ANTES de la "
            f"frontera con el adapter, y por eso no se gasta."
        )
        storage.close()


class TestElPuertoLoImportaProduccion:
    """El guard que impide que el gate vuelva a cumplirse en vacio.

    Deriva del ARBOL, no de una lista de ficheros escrita a mano. Una
    lista seria la misma trampa que `DIRECTORIOS_NO_RECETA` (WI-99): el
    guard compararia contra su propia copia y solo vigilaria lo que ya
    conoce.
    """

    def test_alguna_cosa_under_src_importa_el_puerto(self) -> None:
        importadores = _importadores_del_puerto(SRC)
        assert importadores, (
            "NINGUN modulo bajo src/ importa "
            "`skillgraph.platform.ports.capabilities`. El puerto es un "
            "contrato sin consumidor: se puede anadir una capability que "
            "nadie ejecuta, que es exactamente el hueco que B3 vino a "
            "cerrar, movido un nivel mas arriba. Ver "
            "`.pipelinek/b3_wiring_measure.py`."
        )

    def test_un_fichero_que_no_importa_el_puerto_se_reconoce_como_tal(self) -> None:
        """Contrasalto en la direccion contraria.

        Si la derivacion devolviera SIEMPRE una lista no vacia, el test de
        arriba pasaria en verde sobre cualquier arbol, y este guard no
        distinguiria un puerto conectado de uno huérfano.
        """
        assert _importadores_del_puerto(SRC / "skillgraph" / "platform" / "paths.py") == [], (
            "paths.py no importa el puerto de capabilities, y la derivacion "
            "dice que si. Con esto el test de arriba no distinguiria nada."
        )


class TestLaDerivacionDistingueLasFormasDeImportar:
    """El contrasalto del contrasalto: sobre AST SINTETICO, no sobre el repo.

    Las dos mitades anteriores se apoyan en el contenido del árbol: una
    sobre «algo importa» y otra sobre «nada importa». Una derivación rota
    que devolviera siempre la misma respuesta passaria una de las dos. Aqui
    la pregunta se le hace a la DERIVACIÓN, con fuente escrita al efecto, y
    tiene que distinguir las tres formas que existen en Python de un import
    real —y de uno que se le parece pero no lo es.
    """

    def test_reconoce_las_tres_formas_de_importar_el_puerto(self) -> None:
        for fuente in (
            "from skillgraph.platform.ports.capabilities import CapabilityRegistry",
            "from skillgraph.platform.ports import capabilities",
            "import skillgraph.platform.ports.capabilities",
        ):
            assert _importa_el_puerto(ast.parse(fuente)), (
                f"la derivacion no ve esta forma de importar el puerto: {fuente}"
            )

    def test_no_confunde_otro_modulo_del_mismo_paquete(self) -> None:
        """`repositories` esta al lado de `capabilities` en el mismo
        paquete. Confundirlas haria que el guard pasara en verde porque
        otro modulo —mucho mas usado— importa del mismo sitio."""
        for fuente in (
            "from skillgraph.platform.ports.repositories import RunRepository",
            "from skillgraph.platform.ports import repositories",
        ):
            assert not _importa_el_puerto(ast.parse(fuente)), (
                f"la derivacion toma este import por el del puerto: {fuente}"
            )

    def test_un_import_presente_en_prosa_no_cuenta(self) -> None:
        """El texto dentro de un docstring no es un import.

        Es la misma Confusion que el rastreo del reloj (WI-112): lo que
        se mide es que el modulo *llame* a importarlo, y una cadena que lo
        menciona es indistinguible de una llamada si se busca con texto.
        """
        fuente = '"""Ver skillgraph.platform.ports.capabilities para el contrato."""\nx = 1\n'
        assert not _importa_el_puerto(ast.parse(fuente))


def _importa_el_puerto(arbol: ast.AST) -> bool:
    """¿Este AST importa el modulo del puerto?

    Se aceptan las tres formas que existen en Python —`import
    ...ports.capabilities`, `from ...ports import capabilities` y `from
    ...ports.capabilities import X`— porque omitir una haria que el
    veredicto dijera 'inalcanzable' por un detalle de sintaxis, que es
    peor que no resolver. Y solo esas tres: un modulo vecino del mismo
    paquete no cuenta.
    """
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom):
            mod = nodo.module or ""
            if mod.endswith("ports.capabilities"):
                return True
            if mod.endswith("platform.ports") and any(a.name == "capabilities" for a in nodo.names):
                return True
        elif isinstance(nodo, ast.Import):
            if any(a.name.endswith("ports.capabilities") for a in nodo.names):
                return True
    return False


def _importadores_del_puerto(raiz: Path) -> list[str]:
    """Modulos del `raiz` que importan el modulo del puerto, por AST.

    Acepta un fichero o un directorio. Un fichero unico es lo que permite
    el contrasalto: «este modulo, que existe, no importa el puerto» es una
    pregunta con respuesta conocida y no depende de lo que haga el repo.
    """
    modulos = [raiz] if raiz.is_file() else sorted(raiz.rglob("*.py"))
    salida: list[str] = []
    for f in modulos:
        try:
            arbol = ast.parse(f.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        if _importa_el_puerto(arbol):
            salida.append(_rel(f))
    return sorted(set(salida))


def _rel(f: Path) -> str:
    try:
        return str(f.relative_to(REPO_ROOT))
    except ValueError:  # pragma: no cover
        return str(f)
