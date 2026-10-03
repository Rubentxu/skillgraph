"""B3 — el GATE: añadir una capability sin tocar el core.

La promesa de B3, textual:

> Se puede añadir una capability (tipo, contrato, adapter, controller
> opcional, policy, tests) **sin modificar** `RunController`, el storage
> base ni el motor del workflow.

Este fichero es la comprobacion. Y tiene dos mitades, porque una sola no
alcanza:

**LA PRIMERA, EJECUTADA.** Todo el recorrido con una capability
**definida dentro de este fichero de test** —sin tocar `src/`—: se
registra, se resuelve, se invoca, y su resultado vuelve con procedencia.
Si el core tuviera la capability cableada, este test no podria existir.

**LA SEGUNDA, POR AST.** Que el nucleo **no importe adapters concretos**.
Es la mitad que un test de ejecucion no puede dar: aunque todo lo de
arriba funcione, el core podria estar importando `CogniCode` por la
puerta de atras, y ahi volveria a ser SkillGraph reconstruyendo
CogniCode, Chronos o secretless —justo lo que B3 quiere evitar—. Un
guard que solo ejecuta no ve un import; un guard que solo lee no ve un
fallo en ejecucion. Hace falta el de los dos, que es la misma frontera
que el `AgentResult` de WI-113.

**POR QUE LA CAPABILITY DE ESTE TEST ES UNA INVENTADA Y NO UNA REAL.**
Porque si usara una real, el test dependeria de que exista, y el dia que
se borrara el guard caeria por una razon que no es la suya. Ademas, una
capability inventada demuestra mas: el core no sabe *cual* es la
capability, solo sabe que hay algo que la cumple. Ese es el contrato
entero.
"""

from __future__ import annotations

import ast
import tempfile
from pathlib import Path
from typing import Any

import pytest

from skillgraph.core.errors import SkillGraphError, ValidationError
from skillgraph.core.recipe import ContextRecipe
from skillgraph.domain.dsl import PlanBuilder, node_name
from skillgraph.platform.ports.capabilities import (
    Capability,
    CapabilityNotFound,
    CapabilityRegistry,
    CapabilityRequest,
    CapabilityResult,
    CapabilitySpec,
)
from skillgraph.platform.storage import Storage
from skillgraph.runtime.agent import AgentResult
from skillgraph.runtime.handoff import Handoff
from skillgraph.runtime.runcontroller import RunController

RAIZ = Path(__file__).resolve().parent.parent
SRC = RAIZ / "src" / "skillgraph"

# Una capability INVENTADA, definida aqui. Su nombre no aparece en
# ningun otro fichero del repo, y `test_el_nucleo_no_importa_adapters`
# lo comprueba: si el core la conociera, tendria que importarla de
# algun sitio, y ese sitio seria este fichero de test.
CAP_INVENTADA = "sg.test.capability.inventada"

#: Lo que declara un NODO del plan. No es una capability registrada en
#: ningun sitio: es exactamente lo que B3 dice que todavia no se
#: resuelve a nada ejecutable, y por eso los tests de integracion lo
#: usan tal cual.
CAPS_DEL_NODO = ("code.analysis", "telemetry.query")

TENANT = "t-b3"
PROJECT = "p-b3"


class CapacidadInventada:
    """Un adapter que vive solo en este test. Es legal: es un valor.

    `tipo` permite tener varias instancias con nombres distintos, que es
    lo que hace posible medir la contaminacion entre registros.
    """

    def __init__(self, tipo: str = CAP_INVENTADA) -> None:
        self._tipo = tipo

    @property
    def spec(self) -> CapabilitySpec:
        return CapabilitySpec(
            type_name=self._tipo,
            summary="no existe fuera de este fichero de test",
        )

    def invoke(self, request: CapabilityRequest) -> CapabilityResult:
        return CapabilityResult(
            spec=self.spec,
            adapter=type(self).__name__,
            payload={"visto": request.subject, "args": dict(request.arguments)},
        )


#: Un SEGUNDO tipo, tambien inventado. Existe por una sola razon: para
#: poder construir dos registros con contenidos distintos y mirar si se
#: contaminan. Con un solo tipo, un registro global se delataria —no
#: tendria nada que perder—, y el guard no tendria nada que medir.
CAP_DISTINTA = "sg.test.capability.otra"

#: Cinco mas, para medir que el INFORME de capabilities no cambia de
#: orden. Ver `test_el_orden_de_instalacion_no_cambia_el_informe`: son
#: cinco y no dos porque el orden de un `set` en Python depende del hash
#: de las cadenas, que esta aleatorizado por proceso.
CAPS_ORDEN: tuple[str, ...] = (
    "sg.test.capability.aa",
    "sg.test.capability.bb",
    "sg.test.capability.cc",
    "sg.test.capability.dd",
    "sg.test.capability.ee",
)


class _AdapterQueMira:
    """No muta nada. Solo recuerda lo que le llego."""

    def __init__(self) -> None:
        self.capabilities_vistas: tuple[str, ...] = ()

    def invoke(self, handoff: Handoff) -> AgentResult:
        self.capabilities_vistas = handoff.capabilities
        return AgentResult(outcome="text", result={"ok": True}, evidence_ref="ev-1")


class TestUnaCapabilitySeAnadeSinTocarElCore:
    """La primera mitad: se ejecuta. Sin esto, el guard de AST no basta."""

    def test_una_capability_definida_en_un_test_se_resuelve(self) -> None:
        """El recorrido entero, con el adapter naciendo en este fichero.

        Si el core tuviera las capabilities cableadas —si `resolve` fuera
        una tabla estatica en vez de un registro inyectado— este test no
        podria pasar, porque el adapter no existe fuera de aqui.
        """
        registro = CapabilityRegistry((CapacidadInventada(),))
        cap = registro.resolve(CAP_INVENTADA)
        resultado = cap.invoke(
            CapabilityRequest(
                spec=cap.spec,
                subject="un-nodo",
                arguments={"profundidad": 3},
            )
        )
        assert resultado.payload == {"visto": "un-nodo", "args": {"profundidad": 3}}
        assert resultado.spec.type_name == CAP_INVENTADA
        assert resultado.adapter == "CapacidadInventada"

    def test_el_adapter_cumple_el_contrato_declarado(self) -> None:
        """Que el `Protocol` sea el contrato, y no una decoracion.

        El `Protocol` es estructural: nadie obliga al adapter a
        implementarlo, se cumple por tener los miembros. Eso es lo que
        permite que un adapter de un pack ajeno sea aceptado sin herencia
        ni registro de clases. Pero significa tambien que el `Protocol`
        puede quedarse vacio de requisitos reales sin que nada se rompa,
        porque el codigo que lo consume es el que decide.

        Aqui se comprueba que lo declarado y lo usado coinciden: los dos
        unicos miembros son los que el recorrido de arriba necesita. Si
        `invoke` desapareciera del `Protocol`, el registro seguiria
        funcionando y este test caeria —que es justo lo que debe hacer.
        """
        assert isinstance(CapacidadInventada(), Capability)
        miembros = {nombre for nombre in dir(Capability) if not nombre.startswith("_")}
        assert "invoke" in miembros
        assert "spec" in miembros

    def test_el_resultado_lleva_la_procedencia(self) -> None:
        """«¿quien afirmo esto?» tiene que tener respuesta.

        B6 quiere que cada afirmacion del Knowledge Graph distinga
        `observed` / `derived-deterministically` / `agent-inferred` /
        `human-asserted`. Eso exige que el adapter quede en el
        RESULTADO, no en un log: un log se borra, un resultado
        persistido no. Sin este campo, la pregunta no tiene respuesta
        mas adelante, y es la pregunta que B6 va a hacer.
        """
        registro = CapabilityRegistry((CapacidadInventada(),))
        cap = registro.resolve(CAP_INVENTADA)
        resultado = cap.invoke(CapabilityRequest(spec=cap.spec, subject="s"))
        assert resultado.adapter, "el resultado no dice que adapter lo produjo"
        assert resultado.spec.version, "el resultado no dice que version del contrato"


class TestElRegistroEsUnValor:
    """Lo que hace la resolucion comprobable: que no dependa del orden.

    **POR QUE ESTA CLASE NO COMPRUEBA `a == b`, Y POR QUE ES LO IMPORTANTE.**
    La primera version de este gate decia:

    ```
    a = CapabilityRegistry((CapacidadInventada(),))
    b = CapabilityRegistry((CapacidadInventada(),))
    assert a == b  # "sin estado global, el despliegue es un VALOR"
    ```

    Dos cosas iban mal, y la segunda es la grave.

    **Fallaba hoy**, porque `CapacidadInventada` no define `__eq__` y dos
    instancias suyas no son iguales. Eso es el ruido.

    **Y no midia lo que decia.** Medido sobre un `CapabilityRegistry`
    convertido a singleton lleno al importar:

    ```
    hoy            : a == b  -> False   (el test lo exige)
    singleton      : s1 == s2 -> True   <-- la asercion PASA igual
    singleton      : s1.types  -> ('A',)  <-- la CONTAMINACION que no ve
    ```

    La igualdad entre dos registros es, literalmente, lo que un singleton
    cumple **mejor** que un valor: un singleton siempre es igual a si mismo.
    El guard exigia una propiedad cuyo unico incumplimiento era el
    correcto, y por eso no distinguia un valor de un singleton. Es el error
    de WI-114 dado la vuelta: alli el instrumento media la convencion que
    el workitem eliminaba; aqui media una convencion que si distingue, pero
    de una forma que un singleton tambien cumple.

    Lo que si discrimina es la **contaminacion**: dos registros construidos
    por separado con contenidos distintos, donde el primero no puede saber
    lo del segundo.
    """

    def test_registros_construidos_por_separado_no_se_contaminan(self) -> None:
        """La propiedad real, y la que un singleton NO puede cumplir.

        Cada registro se construye aqui, en este test, con lo que se le
        pasa. Si el registro fuera global, el segundo veria lo que se le
        dio al primero ademas de lo suyo.
        """
        a = CapabilityRegistry((CapacidadInventada(),))
        b = CapabilityRegistry((CapacidadInventada(CAP_DISTINTA),))
        assert a.types == (CAP_INVENTADA,)
        assert b.types == (CAP_DISTINTA,)
        assert CAP_DISTINTA not in a.types, "el registro A se contaminó con lo de B"
        assert CAP_INVENTADA not in b.types, "el registro B se contaminó con lo de A"

    def test_tres_registros_distintos_exigen_tres_contenidos_distintos(self) -> None:
        """La segunda mitad de la anterior, por construccion.

        No compara registros entre si —eso fue el error—: **observa tres
        registros independientes** y comprueba que cada uno ve lo suyo y
        solo lo suyo. Tres en vez de dos porque el fallo caracteristico de
        un singleton no es que los registros se mezclen, es que el segundo
        constructor **no hace nada** y devuelve el primero, con lo que dos
        registros bastarian; con tres, un constructor que acumulara en vez
        de sustituir tambien cae.

        Y `tres` se construye en orden **inverso** al esperado a proposito:
        un informe de capabilities no puede depender del orden en que se
        instalaron, asi que el `sorted` de `types` es una propiedad medida
        y no un detalle. Construirlo ya ordenado haria que esa midiese
        sola.
        """
        uno = CapabilityRegistry((CapacidadInventada(),))
        dos = CapabilityRegistry((CapacidadInventada(CAP_DISTINTA),))
        tres = CapabilityRegistry((CapacidadInventada(CAP_DISTINTA), CapacidadInventada()))
        assert uno.types == (CAP_INVENTADA,)
        assert dos.types == (CAP_DISTINTA,)
        assert tres.types == tuple(sorted((CAP_INVENTADA, CAP_DISTINTA)))

    def test_el_orden_de_instalacion_no_cambia_el_informe(self) -> None:
        """`types` es un INFORME, y un informe no se reordena solo.

        Este test existe por una mutacion que antes no la cazaba, y
        el motivo es que el fallo es **aleatorio**, no determinista.

        Sin el `sorted`, `types` devuelve `tuple({...})`, y el orden de un
        `set` de cadenas depende del hash, que Python aleatoriza por
        proceso. Medido sobre cinco elementos:

        ```
        sin PYTHONHASHSEED fijo : 8 ordenes distintos en 8 Corridas
        con PYTHONHASHSEED=0    : 1 orden en 4 corridas, y NO es el ordenado
        ```

        O sea: quitar el `sorted` es un defecto **intermitente**, y un
        defecto intermitente en un guard es peor que no tener guard,
        porque entrena a leer «a veces pasa» como ruido. Por eso aqui hay
        **cinco** capabilities y no dos: con dos, el set sale ordenado la
        mitad de las veces y el guard es una moneda al aire; con cinco, la
        probabilidad de que el set salga ordenado es de 1 entre 120.

        Y el `sorted` no es cosmetico: `types` va al mensaje de
        `CapabilityNotFound` («Resuelve: ...»), y un mensaje de error
        cuyo orden cambia entre procesos es ruido en el log y diffs
        ilegibles.
        """
        # Se instalan al REVES del orden esperado, a proposito.
        instaladas = tuple(reversed(CAPS_ORDEN))
        registro = CapabilityRegistry(tuple(CapacidadInventada(t) for t in instaladas))
        assert registro.types == CAPS_ORDEN

    def test_un_registro_no_crece_al_resolver(self) -> None:
        """Consultar no muta. Un `resolve` no es un alta perezosa.

        Se comprueba el TAMAÑO, no el contenido: si un `resolve`
        fabricara capabilities bajo demanda, `types` creceria y el
        despliegue empezaria a saber cosas que nadie instalo.
        """
        registro = CapabilityRegistry((CapacidadInventada(),))
        antes = registro.types
        registro.resolve(CAP_INVENTADA)
        assert registro.types == antes

    def test_dos_adapters_del_mismo_tipo_se_rechazan(self) -> None:
        """Un despliegue tiene UNA implementacion por capability.

        Sin esto, el ultimo importado gana y el orden de importacion
        decide el comportamiento. Elegir entre implementaciones es una
        **politica** —y por tanto una decision explicita—, no un
        accidente de construccion.
        """
        otra = CapacidadInventada()
        with pytest.raises(SkillGraphError) as exc:
            CapabilityRegistry((CapacidadInventada(), otra))
        assert "dos adapters" in str(exc.value)


class TestLaAusenciaEsUnErrorTipado:
    """Pedir lo que no se puede es un fallo del despliegue, no un `None`."""

    def test_un_spec_sin_tipo_no_se_puede_construir(self) -> None:
        """Validacion **atomica** en `__post_init__` (`AGENTS.md 2.3`).

        Un `validate()` que haya que acordarse de llamar es un `validate()`
        que algun dia no se llama, y el fallo aparece tres capas mas
        abajo. Un tipo vacio que llega al registro se vuelve una
        `CapabilityNotFound` en el uso, que blames al despliegue por un
        error de construccion.
        """
        with pytest.raises(ValidationError):
            CapabilitySpec(type_name="   ")

    def test_un_spec_sin_version_tampoco(self) -> None:
        """La version se valida igual, y es parte de la identidad.

        Sin esto, un `CapabilitySpec(type_name="x", version="")` seria
        resoluble con `version=""` y nunca con la de por defecto: una
        capability que existe y no se puede pedir, que es peor que no
        existir porque el despliegue la declara.
        """
        with pytest.raises(ValidationError):
            CapabilitySpec(type_name="code.analysis", version="")

    def test_pedir_una_capability_ausente_lanza(self) -> None:
        registro = CapabilityRegistry((CapacidadInventada(),))
        with pytest.raises(CapabilityNotFound):
            registro.resolve("code.analysis")

    def test_el_error_dice_que_hay(self) -> None:
        """«no encontrada» sin la lista obliga a un `ls` a mano.

        Y en un despliegue con packs, ese `ls` es una busqueda entre N
        fuentes. Con la lista, el caso normal —un typo— se ve en la
        linea de error.
        """
        registro = CapabilityRegistry((CapacidadInventada(),))
        with pytest.raises(CapabilityNotFound) as exc:
            registro.resolve("code.analysis")
        assert CAP_INVENTADA in str(exc.value)
        assert "code.analysis" in str(exc.value)

    def test_el_error_cuelga_del_dominio_y_tiene_code(self) -> None:
        """Para que la CLI lo traduzca a exit code (el mecanismo de WI-109).

        Un `ValueError` aqui atravesaria el `except` que traduce a exit
        code y saldria como **traceback** al usuario, que es exactamente
        el defecto que WI-109 cerro por el otro lado de la frontera.
        """
        registro = CapabilityRegistry(())
        with pytest.raises(CapabilityNotFound) as exc:
            registro.resolve("cualquiera")
        assert isinstance(exc.value, SkillGraphError)
        assert exc.value.code == "sg_capability_not_found"

    def test_resolver_lo_que_esta_no_lanza(self) -> None:
        """La otra mitad de `resolve`, que no es la Obvia.

        Medir solo que la ausencia lanza es medir la mitad interesante y
        dejar la mitad trivial sin vigilar — y esa es la que se rompe
        primero cuando alguien «simplifica» el `resolve` para que devuelva
        `None`: el test de la ausencia pasaria **mejor**, porque `None` no
        es una excepcion. Un guard que se pone mas verde al romperse es un
        guard que no puede usarse.
        """
        registro = CapabilityRegistry((CapacidadInventada(),))
        cap = registro.resolve(CAP_INVENTADA)
        assert isinstance(cap, Capability)
        assert cap.spec.type_name == CAP_INVENTADA

    def test_resolver_con_otra_version_no_encuentra(self) -> None:
        """La version es parte de la identidad, no decoracion.

        B8 hara que los packs declaren `capabilities: [code.analysis.v1]`.
        Si la version no discriminara, un pack que declara `v2` se
        resolveria contra un adapter `v1` y el contrato seria una promesa
        sin nadie detras. B8 llega despues; esta es la su condicion para
        no tener que arreglarlo cuando llegue.
        """
        registro = CapabilityRegistry((CapacidadInventada(),))
        with pytest.raises(CapabilityNotFound):
            registro.resolve(CAP_INVENTADA, version="v99")

    def test_consultar_no_es_lo_mismo_que_resolver(self) -> None:
        """`supports` pregunta; `resolve` falla. Son dos preguntas.

        Usar `resolve` dentro de un `if` seria informar de un fallo como
        si fuera una condicion normal, que es como un error se vuelve
        silencioso tres capas mas abajo.
        """
        registro = CapabilityRegistry((CapacidadInventada(),))
        assert registro.supports(CAP_INVENTADA) is True
        assert registro.supports("code.analysis") is False
        assert registro.missing_from(("code.analysis",)) == ("code.analysis",)


class TestElHandoffQueElAdapterRecibe:
    """Medido sobre el motor, no sobre el texto. Sin esto, B3 no esta
    conectado a nada: un puerto con tests que nadie usa es un modulo
    muerto que da verde.

    **LO MEDIDO ANTES DE ESCRIBIR ESTOS TESTS** (`.pipelinek/b3_measure.py`):

    ```
    capabilities que declara el NODO : ('code.analysis', 'telemetry.query')

    runtime SIN recipe_resolver
      las que vio el Adapter      : ('code.analysis', 'telemetry.query')
      las que quedaron en disco   : ('code.analysis', 'telemetry.query')

    runtime CON recipe_resolver
      las que vio el Adapter      : ('code.analysis', 'telemetry.query')
      las que quedaron en disco   : ('code.analysis', 'telemetry.query')
    ```

    Y el motivo por el que los dos caminos coinciden no es que el codigo
    lo decida: es que hay **dos** constructores de `Handoff` con
    `capabilities` distintos y `RunController` descarta uno entero:

    ```
    runcontroller._build_handoff      -> capabilities=node.capabilities
    context_controller.compile_handoff-> capabilities=build_capabilities(...)
    runcontroller._compile_knowledge  -> return compiled.knowledge   # el resto, no
    ```

    Eso es un Handoff completo —con identity, budget, capabilities y hash
    firmable— construido para usar una parte. Funciona, pero por
    accidente: en cuanto `compile_handoff` empiece a hacer lo que su
    nombre sugiere, el runtime no se enterara.
    """

    def _plan(self) -> Any:
        return (
            PlanBuilder()
            .add_node(node_name("n1"), expected="text", capabilities=CAPS_DEL_NODO)
            .starts_at(node_name("n1"))
            .build()
        )

    def test_el_adapter_recibe_las_capabilities_del_nodo(self) -> None:
        """La mitad sin receta, que es el caso normal."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "b3.sqlite")
            adapter = _AdapterQueMira()
            ctl = RunController(runs=storage, events=storage, policy=storage, adapter=adapter)
            run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=self._plan())
            ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        assert adapter.capabilities_vistas == CAPS_DEL_NODO

    def test_el_adapter_las_recibe_tambien_con_receta_de_contexto(self) -> None:
        """La mitad que importa: con `compile_handoff` en el camino.

        Si alguien «arregla» `compile_handoff` para que sus capabilities
        sustituyan a las del nodo —que es lo que su nombre sugiere hacer—,
        el Adapter dejaria de recibir lo que el nodo declara, y este test
        lo diria. Sin el, el cambio pasaria inadvertido: los tests de
        `build_capabilities` seguirian verdes porque la funcion pura no ha
        cambiado, y el unico sintoma seria un prompt sin capabilities.
        """
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "b3.sqlite")
            adapter = _AdapterQueMira()
            ctl = RunController(
                runs=storage,
                events=storage,
                policy=storage,
                adapter=adapter,
                recipe_resolver=lambda *_a, **_k: ContextRecipe(recipe_ref="recipe-b3/v1"),
                knowledge=storage,
            )
            run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=self._plan())
            ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        assert adapter.capabilities_vistas == CAPS_DEL_NODO, (
            "con receta de contexto el Adapter deja de recibir las "
            "capabilities del nodo: compile_handoff las esta "
            "sustituyendo, y el runtime no se entera."
        )

    def test_lo_que_llega_al_adapter_no_lleva_una_señal_de_frescura(self) -> None:
        """`stale` viaja en `capabilities`, y ahi NO es una capability.

        Medido, no supuesto: `build_capabilities` (context_controller.py:139)
        devuelve `("stale",)` cuando hay una Claim stale bajo `best_effort`,
        y `stale` es un valor de `FreshnessState`
        (`core/runtime_types.py:71`), no un tipo de capability.

        Este test fija el **comportamiento actual** del runtime, que es
        que el marcador no llega, y deja escrito por que. La decision
        de si `stale` debe viajar en su propio campo, o como
        capability de verdad, se toma despues y con esta medicion
        delante. Lo que este test prohibe es que cambie **por
        descuido**.
        """
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "b3.sqlite")
            adapter = _AdapterQueMira()
            ctl = RunController(
                runs=storage,
                events=storage,
                policy=storage,
                adapter=adapter,
                recipe_resolver=lambda *_a, **_k: ContextRecipe(recipe_ref="recipe-b3/v1"),
                knowledge=storage,
            )
            run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=self._plan())
            ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        assert "stale" not in adapter.capabilities_vistas


class TestElNucleoNoImportaAdapters:
    """La segunda mitad, y la que un test de ejecucion NO puede dar.

    although todo lo de arriba pase, el core podria estar importando un
    producto concreto por la puerta de atras. Eso es exactamente lo que
    B3 quiere que NO pase: `KnowledgeQuery`, `CodeAnalysis` o
    `TelemetryQuery` son capabilities, no imports de CogniCode, Chronos
    o cualquier otro producto.
    """

    #: Modulos del nucleo que NO pueden conocer adapters.
    #:
    #: La lista de **paquetes** es pequeña y es un requisito, no una
    #: enumeracion de ficheros: `runtime/` es el motor, `core/` las
    #: invariantes, `resources/` la definicion de lo que se puede pedir. Un
    #: modulo nuevo que se cree debajo de esos paquetes queda cubierto sin
    #: editar este fichero, que es la parte que se quiere automatizada.
    NUCLEO = ("runtime", "core", "resources")

    #: El suelo del rastreo, **declarado aparte a proposito**.
    #:
    #: Si el contrasalto comprobara solo que lo que hay en `NUCLEO` existe,
    #: reducir `NUCLEO` a `("runtime",)` lo dejaria en verde: `runtime` si
    #: existe, y el numero de ficheros sigue siendo mayor que el numero de
    #: paquetes. El guard se habria vaciado sin ponerse rojo, que es la
    #: forma que toma aqui «vigilar una verdad imposible de romper» — la
    #: razon por la que B1 no instrumento un contrato que nadie puede
    #: incumplir. Con el suelo separado, quitar un paquete del rastreo es
    #: quitarlo de las dos listas, y entonces este test lo dice.
    NUCLEO_MINIMO = ("runtime", "core", "resources")

    def _fuentes_del_nucleo(self) -> list[Path]:
        salida: list[Path] = []
        for paquete in self.NUCLEO:
            base = SRC / paquete
            if not base.is_dir():
                continue
            salida.extend(p for p in sorted(base.rglob("*.py")) if "__pycache__" not in p.parts)
        return salida

    def test_el_rastreo_encuentra_de_verdad_el_nucleo(self) -> None:
        """El contrasalto de que el rastreo no mida sobre la lista vacia.

        Los tres guards de esta clase iteran sobre `_fuentes_del_nucleo()`.
        Una derivacion que devolviera siempre `[]` los haria pasar a todos
        **sin mirar un solo fichero** — y con la autoridad de un nombre que
        dice lo contrario. Es el M2 de WI-110 aplicado aqui.

        Y hay una segunda mitad, mas sutil: no basta con que lo que hay en
        `NUCLEO` exista, porque `NUCLEO` se puede reducir en el mismo
        fichero que el guard. Por eso el suelo vive en `NUCLEO_MINIMO`, que
        este test exige que siga contenido en `NUCLEO`.
        """
        fuentes = self._fuentes_del_nucleo()
        assert fuentes, "el rastreo no encontro el nucleo: no mide nada"
        paquetes_vistos = {f.relative_to(SRC).parts[0] for f in fuentes}
        faltan = set(self.NUCLEO) - paquetes_vistos
        assert not faltan, f"paquetes de `NUCLEO` que no existen: {sorted(faltan)}"
        fuera = set(self.NUCLEO_MINIMO) - set(self.NUCLEO)
        assert not fuera, (
            f"el rastreo se ha encogido: {sorted(fuera)} ya no se vigilan. "
            "Quitar un paquete del nucleo del rastreo tiene que ser una "
            "decision, y deja de ser un guard."
        )
        # Si el nucleo fuera un unico fichero por paquete, la regla
        # seguiria "pasando" con una fraccion del alcance. Se pone un
        # suelo, no un exacto: el numero exacto es la lista de ficheros
        # otra vez.
        assert len(fuentes) > len(self.NUCLEO_MINIMO), (
            f"solo {len(fuentes)} ficheros para {len(self.NUCLEO_MINIMO)} "
            "paquetes: el rastreo no cubre lo que dice cubrir"
        )

    def test_el_nucleo_no_importa_nada_que_no_sea_del_repo(self) -> None:
        """Cero imports de productos externos en el motor.

        `KnowledgeQuery` es una capability que un adapter puede
        satisfacer. Si el core hiciera `import cognicode`, B3 habria
        terminado en exactamente lo que el objetivo dice que hay que
        evitar: SkillGraph reconstruyendo CogniCode.
        """
        externos = {
            "cognicode",
            "chronos",
            "secretless",
            "cogni_code",
            "mcp",
            "langchain",
            "llama_index",
            "cortex",
        }
        culpables: list[str] = []
        for ruta in self._fuentes_del_nucleo():
            arbol = ast.parse(ruta.read_text(encoding="utf-8"))
            for nodo in ast.walk(arbol):
                modulos: list[str] = []
                if isinstance(nodo, ast.Import):
                    modulos = [a.name for a in nodo.names]
                elif isinstance(nodo, ast.ImportFrom) and nodo.module and nodo.level == 0:
                    modulos = [nodo.module]
                for modulo in modulos:
                    raiz = modulo.split(".")[0].lower()
                    if raiz in externos:
                        culpables.append(
                            f"{ruta.relative_to(RAIZ)}:{nodo.lineno} importa {modulo!r}"
                        )
        assert not culpables, (
            "el nucleo importa un producto externo:\n  "
            + "\n  ".join(culpables)
            + "\n\nUn producto concreto es un ADAPTER, y un adapter entra por "
            "el registro, no por un import del motor."
        )

    def test_el_contrato_de_capability_vive_en_los_puertos(self) -> None:
        """Y no en `runtime/`, que es donde se usaria.

        Si el `Protocol` de capability viviera en el motor, importarlo
        seria un `import` de runtime desde el adapter: la dependencia
        seria en la direccion equivocada y el nucleo dejaria de poder
        hablar de capabilities sin arrastrar el motor entero.
        """
        from skillgraph.platform.ports import capabilities as mod

        assert mod.__file__ is not None
        assert "platform/ports/capabilities.py" in mod.__file__

    def test_las_capabilities_de_este_test_no_aparecen_en_src(self) -> None:
        """El contrasalto de que el core NO las conoce de antemano.

        Si cualquiera de los dos nombres apareciera en `src/`, los tests de
        arriba estarian probando una capability que el core ya tenia
        cableada, y el gate entero seria illusions: no se estaria anadiendo
        nada. Se comprueban los **dos** porque el segundo existe para medir
        la contaminacion, y un nombre que el core conociera invalidaria
        tambien esa medicion.
        """
        assert self._fuentes_del_nucleo(), "el rastreo no encontro el nucleo: no mide nada"
        inventadas = (CAP_INVENTADA, CAP_DISTINTA, *CAPS_ORDEN)
        for ruta in self._fuentes_del_nucleo():
            fuente = ruta.read_text(encoding="utf-8")
            for nombre in inventadas:
                assert nombre not in fuente, (
                    f"{ruta.relative_to(RAIZ)} menciona {nombre!r}: el core "
                    "ya conoce una capability definida en un test, que es "
                    "justo lo que este gate tiene que demostrar que NO pasa."
                )
