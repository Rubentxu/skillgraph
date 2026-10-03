"""B3-cierre — la mitad del gate del roadmap que faltaba.

Las seis entregas anteriores dejaron el CONTRATO (`platform/ports/
capabilities.py`) y su resolucion. Lo que no existia, y lo que el propio
bloque reconocia en su §11, es **un adapter de produccion**: el unico
`Capability` del repo vivia dentro de un test.

Eso dejaba el gate del roadmap sin nada que demostrar fuera del testsuite:

    ROADMAP.md §B3 — «Se puede anadir una capability (tipo, contrato,
    adapter, controller opcional, policy, tests) SIN MODIFICAR
    `RunController`, el storage base ni el motor del workflow.»

Un contrato que solo cumple un doble de test es una forma de contrato.

**LO QUE ESTE FICHERO MIDE, Y CADA MITADA POR SEPARADO.**

1. `TestElAdapterDeProduccionCumpleElContrato` — que exista una clase en
   `src/` que cumpla el `Protocol`, y que lo que responda sea trabajo real de un
   grafo real, no un eco del `subject`.
2. `TestElNucleoNoNombraNingunaCapability` — que ningun modulo del nucleo
   mencione el tipo de la capability. **Por AST**: un test de
   comportamiento pasaria igual con un `if tipo == "sg.knowledge.query"`
   en el cuerpo del kernel, porque el resultado es el mismo. La propiedad
   que se compra es estructural, y una propiedad estructural se mide
   estructuralmente.

**Y EL CONTRASALTO, que es la mitad importante del fichero.** Sin el, el
guard 2 pasaria con una lista vacia de ficheros que rastrear, y una lista
vacia hace que un guard que solo sabe pasar parezca uno que vigila. Es el
M2 de WI-110 aplicado aqui, y B3 ya pago dos veces un guard mal construido.
"""

from __future__ import annotations

import ast
import tempfile
from pathlib import Path
from typing import Any

import pytest

from skillgraph.core.errors import SkillGraphError
from skillgraph.platform.ports.capabilities import (
    Capability,
    CapabilityNotFound,
    CapabilityRegistry,
    CapabilityRequest,
    CapabilityResult,
    CapabilitySpec,
)

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / "src" / "skillgraph"

TENANT = "t-b3cierre"
PROJECT = "p-b3cierre"

#: El tipo de la capability de produccion. Vive en una CONSTANTE del
#: modulo de produccion, y este test la importa de ahi — no la escribe —
#: para que cambiar el nombre no pueda dejar este fichero mintiendo.
from skillgraph.knowledge.knowledge_query import (  # noqa: E402
    KNOWLEDGE_QUERY,
    KnowledgeQueryCapability,
)
from skillgraph.runtime.capability_controller import (  # noqa: E402
    CapabilityController,
    CapabilityOutcome,
)


def _brick(nombre: str, spec: dict[str, Any]) -> Any:
    from skillgraph.resources.bricks import Brick, ResourceIdentity

    return Brick(
        identity=ResourceIdentity(
            tenant_id=TENANT,
            project_id=PROJECT,
            namespace="packs",
            kind="DomainPack",
            name=nombre,
        ),
        api_version="skillgraph.io/v1",
        kind="DomainPack",
        spec=spec,
    )


class _Grafo:
    """Un grafo de conocimiento REAL, en `tmp_path`, no un doble.

    La primera medicion de B3 sustituyo el `KnowledgeController` por un
    doble con un metodo `_resolve_selectors` que no existia, devolvio
    `capabilities=()` en las dos policies, y escribio igual una
    conclusion. Un instrumento que no produce el caso no mide el caso.
    """

    def __init__(self) -> None:
        from skillgraph.knowledge.graph import Claim, Entity, Source
        from skillgraph.knowledge.knowledge_controller import KnowledgeController
        from skillgraph.platform.storage import Storage

        self._tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self._tmp.name) / "b3.sqlite")
        self.storage.register_source(
            tenant_id=TENANT,
            project_id=PROJECT,
            source=Source(
                source_id="src-b3cierre",
                kind="local_file",
                content_hash="hash-b3cierre",
                locator={"path": "src/kernel.py"},
                git_commit_sha=None,
                git_tree_sha=None,
                working_tree_status=None,
                checked_at="2026-01-01T00:00:00Z",
                freshness="fresh",
            ),
        )
        self.storage.upsert_entity(
            tenant_id=TENANT,
            project_id=PROJECT,
            entity=Entity(entity_id="ent-b3", kind="file", stable_key="src/kernel.py"),
        )
        self.brick = _brick("code-analysis", {"capacities": ["code.analysis"]})
        self.uid = self.storage.upsert_resource(brick=self.brick)
        self.claim_id = KnowledgeController(
            knowledge=self.storage, tenant_id=TENANT, project_id=PROJECT
        ).record_claim(
            claim=Claim(
                claim_id="",
                subject_entity_id="ent-b3",
                predicate="line_count",
                object_literal=42,
                source_id="src-b3cierre",
                evidence_ids=(),
                extraction_method="manual",
                extractor_version="b3cierre/0.1",
                checked_at_revision="rev-7",
            )
        )

    def cerrar(self) -> None:
        self._tmp.cleanup()


@pytest.fixture
def grafo() -> Any:
    g = _Grafo()
    yield g
    g.cerrar()


def _adapter(g: Any) -> KnowledgeQueryCapability:
    return KnowledgeQueryCapability(knowledge=g.storage, tenant_id=TENANT, project_id=PROJECT)


class TestElAdapterDeProduccionCumpleElContrato:
    """R1. Existe, esta en `src/`, y trabaja de verdad."""

    def test_el_tipo_es_una_constante_y_no_una_cadena_suelta(self) -> None:
        """El nombre vive en el modulo de produccion, no en el consumidor.

        Si el nombre estuviera aqui, cambiarlo dejaria este test
        describiendo algo que ya no existe, con toda la autoridad de un
        nombre de test.
        """
        from skillgraph.knowledge import knowledge_query

        assert KNOWLEDGE_QUERY == "sg.knowledge.query"
        assert knowledge_query.KNOWLEDGE_QUERY is KNOWLEDGE_QUERY

    def test_la_clase_esta_en_src_y_no_se_define_en_tests(self) -> None:
        """La direccion de la propiedad: de donde sale, no de donde se usa.

        Se deriva del arbol: se mira de donde se DEFINIO la clase, no de
        donde se importa. Un `import` no distingue las dos cosas.
        """
        mod = KnowledgeQueryCapability.__module__
        assert mod == "skillgraph.knowledge.knowledge_query", (
            f"el adapter de produccion deberia vivir en "
            f"skillgraph.knowledge.knowledge_query, y vive en {mod}"
        )
        definidos = [
            f
            for f in sorted(RAIZ.glob("tests/**/*.py"))
            if f"class {KnowledgeQueryCapability.__name__}" in f.read_text(encoding="utf-8")
        ]
        assert not definidos, (
            "la clase tambien esta DEFINIDA en un test, y entonces el "
            f"contrato lo cumple un doble: {definidos}"
        )

    def test_cumple_el_protocol_estructural(self, grafo: Any) -> None:
        """`Protocol` con `@runtime_checkable`: comprueba la FORMA."""
        cap = _adapter(grafo)
        assert isinstance(cap, Capability)
        assert cap.spec.type_name == KNOWLEDGE_QUERY
        assert cap.spec.version == "v1"

    def test_responde_a_una_claim_real(self, grafo: Any) -> None:
        """El recorrido entero contra el grafo real."""
        cap = _adapter(grafo)
        resultado = cap.invoke(
            CapabilityRequest(
                spec=cap.spec,
                subject="ent-b3",
                arguments={"kind": "claims"},
            )
        )
        assert isinstance(resultado, CapabilityResult)
        assert resultado.spec.type_name == KNOWLEDGE_QUERY
        assert resultado.adapter == "KnowledgeQueryCapability"
        elementos = resultado.payload["elementos"]
        assert len(elementos) == 1
        assert elementos[0]["predicate"] == "line_count"
        assert elementos[0]["object_literal"] == 42

    def test_el_resultado_real_dice_quien_y_de_donde(self, grafo: Any) -> None:
        """La procedencia, y por elemento.

        B6 quiere poder distinguir `observed` de lo que un agente
        afirmo. Sin `source_id` y `checked_at_revision` por elemento, esa
        pregunta no tiene respuesta, y la capability habría hecho el
        trabajo por la mitad.
        """
        cap = _adapter(grafo)
        payload = cap.invoke(
            CapabilityRequest(spec=cap.spec, subject="ent-b3", arguments={"kind": "claims"})
        ).payload
        elemento = payload["elementos"][0]
        assert elemento["source_id"] == "src-b3cierre"
        assert elemento["checked_at_revision"] == "rev-7"

    def test_responde_por_un_recurso_real(self, grafo: Any) -> None:
        """El otro `kind`: un recurso, por su uid."""
        cap = _adapter(grafo)
        payload = cap.invoke(
            CapabilityRequest(spec=cap.spec, subject=grafo.uid, arguments={"kind": "resource"})
        ).payload
        assert payload["elementos"][0]["name"] == "code-analysis"

    def test_no_adivina_el_kind(self, grafo: Any) -> None:
        """Sin `kind` se lanza, no se devuelve una lista vacia.

        Una lista vacia por no saber que mirar es indistinguible de «no
        hay nada», y esa es la confusion que un `None` produce tres
        capas mas abajo.
        """
        cap = _adapter(grafo)
        with pytest.raises(SkillGraphError):
            cap.invoke(CapabilityRequest(spec=cap.spec, subject="ent-b3", arguments={}))

    def test_un_subject_que_no_existe_no_inventa_nada(self, grafo: Any) -> None:
        """Ausencia real: `elementos` vacio, y se dice que se pregunto.

        Y **tupla** vacia, no lista: `AGENTS.md 1.1` pide tuplas, y el
        payload sale de la frontera hacia alguien que no deberia poder
        mutarlo. Escribir `== []` aqui habria sido un test que obliga al
        codigo a devolver un tipo mutable para que el test pase.
        """
        cap = _adapter(grafo)
        payload = cap.invoke(
            CapabilityRequest(
                spec=cap.spec, subject="ent-inexistente", arguments={"kind": "claims"}
            )
        ).payload
        assert payload["elementos"] == ()
        assert payload["subject"] == "ent-inexistente"


class TestElControllerKernel:
    """R2. El punto donde un NOMBRE se convierte en una ejecucion."""

    def test_resuelve_lo_que_el_nodo_pide(self, grafo: Any) -> None:
        """El recorrido completo, con el adapter de PRODUCCION."""
        registro = CapabilityRegistry((_adapter(grafo),))
        kernel = CapabilityController(registry=registro)
        resultados = kernel.execute(
            subject="ent-b3",
            required=(KNOWLEDGE_QUERY,),
            arguments={"kind": "claims"},
        )
        assert len(resultados) == 1
        salida = resultados[0]
        assert isinstance(salida, CapabilityOutcome)
        assert salida.requested == KNOWLEDGE_QUERY
        assert salida.result.spec.type_name == KNOWLEDGE_QUERY
        assert salida.result.adapter == "KnowledgeQueryCapability"

    def test_el_pedido_y_quien_respondio_son_dos_cosas(self, grafo: Any) -> None:
        """`CapabilityOutcome` existe por esto, y el test lo fija.

        Guardar solo el `result` pierde el pedido; guardar solo el
        pedido pierde quien respondio. Sin el par no se puede auditar
        «este nodo pidio X y alguien entrego Y».

        Y la version que se recibio se ve en `served_by` /
        `version_served`, que son el NOMBRE DE LA CLASE y la VERSION DEL
        CONTRATO: un TIPO, no una cadena suelta.
        """
        registro = CapabilityRegistry((_adapter(grafo),))
        kernel = CapabilityController(registry=registro)
        salida = kernel.execute(
            subject="ent-b3",
            required=(KNOWLEDGE_QUERY,),
            arguments={"kind": "claims"},
        )[0]
        assert salida.requested == KNOWLEDGE_QUERY
        assert salida.served_by == "KnowledgeQueryCapability"
        assert salida.version_served == "v1"

    def test_el_kernel_no_blanquea_lo_que_devuelve_el_adapter(self) -> None:
        """Un adapter que cambia entre resolucion e invocacion SE VE.

        Esta es la propiedad real de `CapabilityOutcome`, y la unica que
        no se deduce sola. `resolve` busca por `spec.type_name`, luego en
        el instante de resolver el par es identico por construccion: un
        `requested != result.spec.type_name` solo puede darse si el
        adapter **cambia** entre las dos llamadas, que es exactamente el
        despliegue que no se puede auditar.

        El kernel **revela** la divergencia en vez de taparla. Uno que
        reescribiera el `spec` del resultado para que cuadrara con el
        pedido haria que un despliegue que responde otra cosa pareciera
        conforme, y esa es la afirmacion falsa que B6 quiere detectar.

        Comparar `requested != adapter` —que es lo que haria la version
        ingenua de este test— no mide nada: son un tipo y un nombre de
        clase, y siempre difieren.
        """

        class AdapterQueCambia:
            """Se registro como una cosa y responde otra. Es un mal adapter."""

            @property
            def spec(self) -> CapabilitySpec:
                return CapabilitySpec(type_name="sg.estable", summary="se registro asi")

            def invoke(self, request: CapabilityRequest) -> CapabilityResult:
                return CapabilityResult(
                    spec=CapabilitySpec(type_name="sg.otro", summary="respondio esto"),
                    adapter=type(self).__name__,
                    payload={"cambio": True},
                )

        registro = CapabilityRegistry((AdapterQueCambia(),))
        kernel = CapabilityController(registry=registro)
        salida = kernel.execute(subject="lo-que-sea", required=("sg.estable",))[0]
        assert salida.requested == "sg.estable"
        assert salida.result.spec.type_name == "sg.otro", (
            "el kernel tiene que dejar ver la divergencia. Si este test "
            "llega a fallar aqui, el kernel esta normalizando la "
            "procedencia y despues no se puede auditar."
        )
        assert salida.served_by == "AdapterQueCambia"

    def test_avisa_de_todas_las_que_faltan(self, grafo: Any) -> None:
        """Falla por el DOMINIO, y el mensaje lista lo que hay y lo que falta.

        El caso real es el typo, y se ve en la linea de error. Un `None`
        o una lista vacia convierten un fallo del despliegue en «no hay
        nada que leer».
        """
        registro = CapabilityRegistry((_adapter(grafo),))
        kernel = CapabilityController(registry=registro)
        with pytest.raises(CapabilityNotFound) as exc:
            kernel.execute(subject="ent-b3", required=(KNOWLEDGE_QUERY, "sg.telemetry.query"))
        mensaje = str(exc.value)
        assert "sg.telemetry.query" in mensaje
        assert KNOWLEDGE_QUERY in mensaje

    def test_no_adivina_una_capability_no_declarada(self, grafo: Any) -> None:
        """Pedir `()` devuelve `()`, y no «todo lo que el registro tenga»."""
        registro = CapabilityRegistry((_adapter(grafo),))
        kernel = CapabilityController(registry=registro)
        assert kernel.execute(subject="ent-b3", required=()) == ()

    def test_no_se_inventa_el_adaptador(self) -> None:
        """Sin registro no hay kernel: se dice, no se construye uno global.

        Un kernel con un registro por defecto seria un singleton
        implicito, que es exactamente lo que `AGENTS.md 1.4` prohibe y lo
        que hizo que el primer gate de B3 no distinguiera un valor de un
        singleton.
        """
        with pytest.raises((TypeError, SkillGraphError)):
            CapabilityController()  # type: ignore[call-arg]

    def test_devuelve_una_tupla_inmutable(self, grafo: Any) -> None:
        """`AGENTS.md 1.1`: el resultado que sale de la frontera es inmutable."""
        registro = CapabilityRegistry((_adapter(grafo),))
        kernel = CapabilityController(registry=registro)
        resultados = kernel.execute(
            subject="ent-b3",
            required=(KNOWLEDGE_QUERY,),
            arguments={"kind": "claims"},
        )
        assert isinstance(resultados, tuple)
        with pytest.raises((AttributeError, TypeError)):
            resultados[0].requested = "otra"  # type: ignore[misc]


class TestElNucleoNoNombraNingunaCapability:
    """La propiedad del roadmap, medida donde se pierde: en la ESTRUCTURA.

    DERIVADO DEL ARBOL, no de una lista escrita aqui. Y con el contrasalto
    al lado, que es lo que hace que este guard valga.
    """

    #: Paquetes que NO pueden conocer un adapter concreto. `resources/` es
    #: «la definicion de lo que se puede pedir»: que un plan pueda
    #: declarar `sg.knowledge.query` es lo correcto; que el modulo que
    #: DEFINE el plan lo sepa, no.
    NUCLEO = ("runtime", "core", "resources")

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
        """EL CONTRASALTO. Sin este test, el de abajo no mide nada.

        Una derivacion que devolviera `[]` haria pasar el guard de
        nombres vacio, con la autoridad de un nombre que dice lo
        contrario. Y reducir `NUCLEO` a un paquete —que sigue existiendo—
        dejaria el recuento por encima del suelo; por eso el suelo vive
        en una lista aparte, y este test exige que siga contenido.
        """
        fuentes = self._fuentes_del_nucleo()
        assert fuentes, "el rastreo no encontro el nucleo: no mide nada"
        assert len(fuentes) >= len(self.NUCLEO), (
            f"el rastreo devolvio {len(fuentes)} ficheros para "
            f"{len(self.NUCLEO)} paquetes: esta midiendo menos de lo que dice"
        )
        paquetes_vistos = {f.relative_to(SRC).parts[0] for f in fuentes}
        faltan = set(self.NUCLEO) - paquetes_vistos
        assert not faltan, f"paquetes de `NUCLEO` que no existen: {sorted(faltan)}"
        fuera = set(self.NUCLEO_MINIMO) - set(self.NUCLEO)
        assert not fuera, (
            f"el rastreo se ha encogido: {sorted(fuera)} ya no se vigilan. "
            "Quitar un paquete del nucleo del rastreo tiene que ser una "
            "decision escrita, no una omision."
        )

    def test_el_rastreo_detecta_de_verdad_una_capability(self) -> None:
        """La segunda mitad del contrasalto, y la que faltaba.

        El otro contrasalto dice «el rastreo encuentra el nucleo»: que hay
        ficheros. Este dice **«el rastreo DETECTA»**: que sobre un fichero
        que si contiene un nombre de capability, lo encuentra.

        Sin esta mitad, cambiar el prefijo buscado de `sg.` a
        `sg.ninguna-cosa` deja el guard de nombres en verde para siempre,
        mirando y no viendo. Y es un fallo que no se ve mirando el guard:
        el codigo de deteccion es correcto, lo que esta mal es lo que
        busca.

        La referencia NO se escribe aqui a mano: se deriva del modulo de
        produccion, que es donde vive el unico nombre real. Un literal
        copiado en el test seria una segunda fuente de verdad que
        divergiria en cuanto el nombre cambie.
        """
        found = _literales_de_capability([SRC / "knowledge" / "knowledge_query.py"])
        assert KNOWLEDGE_QUERY in found, (
            "el rastreo no ve un nombre de capability que esta escrito en el "
            f"propio modulo que la define. Encontrado: {sorted(found)}"
        )

    def test_ningun_modulo_del_nucleo_nombra_la_capability(self) -> None:
        """El guard. AST, no texto.

        Se busca el NOMBRE como constante de cadena en el codigo: un
        `if tipo == "sg.knowledge.query"` es un literale, y un literale no
        se ve leyendo la prosa. Se recorre el AST porque un docstring que
        menciona el nombre es indistinguible de una llamada si se busca
        con cadena.
        """
        literature = _literales_de_capability(self._fuentes_del_nucleo())
        assert KNOWLEDGE_QUERY not in literature, (
            f"el nucleo nombra la capability {KNOWLEDGE_QUERY!r} en: "
            f"{sorted(literature.get(KNOWLEDGE_QUERY, ()))}. El kernel debe "
            "recibir NOMBRES y resolverlos contra el registro, no conocer "
            "que adapters existen."
        )

    def test_la_clase_del_adapter_tampoco(self) -> None:
        """No basta con el nombre del tipo: tampoco el de la clase.

        Un `if isinstance(cap, KnowledgeQueryCapability)` en el nucleo
        seria la misma dependencia con otro uniforme, y el guard del
        nombre pasaria sin ver nada.

        **Y AQUI ESTA LA DISTINCION QUE ESTA PRIMERA VERSION BORRO.**
        La lista prohibida incluia tambien `CapabilityController`, y el
        guard se puso rojo cuando el kernel se cableo en
        `RunController._verificar_capabilities`. Tenia razon el guard sobre
        la forma, y estaba mal la lista: `CapabilityController` NO es un
        adapter, es **el kernel**, y vive en `runtime/` por decision de
        diseno (ver el docstring de `capability_controller.py`: no va en
        `core/` porque depende de otro contexto acotado, y
        `runtime/` ya importa `platform.ports`). El nucleo orchestrar es
        usar el kernel; lo que no puede es conocer QUE adapters hay.

        Confundir los dos habria producido un guard que obliga al
        nucleo a reimplementar la resolucion para poder usarla, que es
        justo lo contrario de lo que B3 vino a hacer.
        """
        culpable: list[str] = []
        for f in self._fuentes_del_nucleo():
            arbol = ast.parse(f.read_text(encoding="utf-8"))
            for nodo in ast.walk(arbol):
                if isinstance(nodo, ast.Name) and nodo.id == KnowledgeQueryCapability.__name__:
                    culpable.append(f"{f.relative_to(SRC)}:{nodo.lineno} {nodo.id}")
                elif (
                    isinstance(nodo, ast.Attribute)
                    and nodo.attr == KnowledgeQueryCapability.__name__
                ):
                    culpable.append(f"{f.relative_to(SRC)}:{nodo.lineno} .{nodo.attr}")
        assert not culpable, (
            f"el nucleo nombra la clase de un adapter concreto: {culpable}. "
            "La frontera es que el nucleo no sepa QUE adapters hay; el kernel "
            "(`CapabilityController`) si es suyo y se usa a proposito."
        )


def _literales_de_capability(fuentes: list[Path]) -> dict[str, set[str]]:
    """Los NOMBRES de capability que aparecen como literal en el codigo.

    Se devuelven por paquete para que el fallo diga DONDE, no solo que
    fallo: un verificador que dice «falso» sin decir «donde» es un
    callejon sin salida.
    """
    vistos: dict[str, set[str]] = {}
    for f in fuentes:
        arbol = ast.parse(f.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if (
                isinstance(nodo, ast.Constant)
                and isinstance(nodo.value, str)
                and nodo.value.startswith("sg.")
            ):
                vistos.setdefault(nodo.value, set()).add(str(f.relative_to(SRC)))
    return vistos


def test_la_version_sale_del_puerto_y_no_del_adapter(grafo: Any) -> None:
    """El adapter no declara su propia version.

    La version del CONTRATO vive en el puerto, y no en cada adapter, por
    un motivo concreto: si cada adapter la declarara, cada uno podria
    inventar la suya y no habria nada que comparar. Este test puede
    fallar de verdad —basta con que el adapter deje de usar la
    constante— y por eso no se compara una constante consigo misma, que
    es un contrasalto que no puede fallar y por tanto no es un contrasalto.
    """
    from skillgraph.platform.ports.capabilities import CAPABILITY_VERSION

    assert _adapter(grafo).spec.version == CAPABILITY_VERSION
    fuente = (SRC / "knowledge" / "knowledge_query.py").read_text(encoding="utf-8")
    assert '"v1"' not in fuente and "'v1'" not in fuente, (
        "el adapter lleva su propia version escrita. La version del "
        "contrato se hereda de CAPABILITY_VERSION, en el puerto."
    )
