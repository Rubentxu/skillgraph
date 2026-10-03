"""B3 — I4 comprueba referencias que existen, y no solo capabilities.

**LO QUE MEDIDO ANTES DE ESCRIBIR NADA** (`.pipelinek/b3_i4_measure.py`),
con el registro real que construye la CLI:

```
registry construido por `_load_registry` : {'code.analysis': 'packs:DomainPack/code-analysis'}

caso                                       deps                                violaciones
dep que NO existe en ninguna parte        ('skillgraph.libs.http',)          ('I4',)
dep que SI existe (el pack del proyecto)  ('packs:DomainPack/code-analysis',) ('I4',)
dep = 'code.analysis' (que ademas es cap)  ('code.analysis',)                 ()
```

Leido de izquierda a derecha: **I4 rechazaba una referencia que
EXISTIA** —el unico pack del proyecto—, y **solo pasaba cuando el autor
escribia como «dependencia» el nombre de una capability**.

La comprobacion no era el problema. Contraejemplo, mismo invariante con
la dependencia puesta a mano en el mapa:

```
con el registry REAL (sin la dep)  -> ('I4',)
con la dependencia A MANO          -> ()
```

El problema era la FUENTE: `cli/commands/expansion.py:148::_load_registry`
construia el mapa recorriendo `spec_json.capabilities` de cada pack y en
ningun momento miraba `new_dependencies`. Un registro bien construido
PARA I3 —que pregunta «esta capability autorizada?»— que no servia
PARA I4 —que pregunta «esta referencia existe?»—.

**LO QUE SE DECIDIO**, y es la razon de que este fichero afirme el
comportamiento nuevo y no fije el roto:

> Dar formato a las dependencias (`namespace:Kind/name`), indexando el
> registro por referencia. I4 pasa a ser un invariante real.

El formato no es inventado: es el que ya usan `ResourceIdentity` y el
que `_load_registry` ya producia como VALOR. Lo que faltaba era
indexar por el.

**POR QUE NO HAY RUPTURA DE DATOS.** Medido, no supuesto: las
propuestas **no se persisten en la base**. `record_rejection`
(`graph_expansion.py:606`) escribe un JSON de auditoria en
`expansion_rejections/`, y las propuestas aceptadas no se guardan. El
campo `new_dependencies` solo existe en el JSON que el usuario aporta
en cada invocacion de la CLI. Darle formato cambia la validacion de
entrada, no la lectura de nada almacenado.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from skillgraph.core.errors import ValidationError
from skillgraph.domain.dsl import PlanBuilder, node_name
from skillgraph.governance.graph_expansion import (
    ExpansionRegistry,
    GraphExpansionProposal,
    resource_ref,
    validate,
)
from skillgraph.platform.storage import Storage
from skillgraph.resources.bricks import Brick, ResourceIdentity

TENANT = "t-b3i4"
PROJECT = "p-b3i4"

#: El unico DomainPack del proyecto de prueba. EXISTE.
PACK_REF = "packs:DomainPack/code-analysis"

#: Una referencia bien formada que no existe en ninguna parte.
REF_INEXISTENTE = "packs:DomainPack/no-existe"


def _pack(storage: Storage, name: str, capabilities: tuple[str, ...]) -> None:
    """Un `DomainPack` de verdad, con la API del dominio.

    La primera version de este fixture hacia `INSERT` en SQL crudo con
    `spec_json = {"spec": {"capabilities": [...]}}`. **Esa forma no la
    produce nadie**: `cli/support.py:299` lee `spec_json` y se lo pasa a
    `Brick(spec=...)` tal cual, y `resources/registry.py:131` valida
    `spec.get("capabilities")` sobre ese mismo dict. Con esa forma el
    registro salia VACIO, y la conclusion habria sido «I4 rechaza todo
    porque el registro esta vacio», que es distinto de lo que dice este
    fichero.

    Es el error de WI-106 por segunda vez en el mismo sitio y de otra
    forma: primero una copia del criterio, luego una forma inventada del
    dato. Los dos hacen que el guard mida una realidad que no existe.
    """
    storage.upsert_resource(
        Brick(
            identity=ResourceIdentity(
                tenant_id=TENANT,
                project_id=PROJECT,
                namespace="packs",
                kind="DomainPack",
                name=name,
            ),
            api_version="skillgraph.dev/v1alpha1",
            kind="DomainPack",
            spec={"version": "1", "capabilities": list(capabilities)},
        )
    )


def _plan() -> Any:
    return (
        PlanBuilder().add_node(node_name("n1"), expected="texto").starts_at(node_name("n1")).build()
    )


def _proposta(*, caps: tuple[str, ...], deps: tuple[str, ...]) -> GraphExpansionProposal:
    return GraphExpansionProposal(
        proposal_id="p-b3i4",
        base_revision="rev-1",
        problem_observed="medicion",
        evidence=(),
        operations=(),
        new_dependencies=tuple(resource_ref(d) for d in deps),
        capabilities_needed=caps,
        scope="NODE",
        attachment_point="n1",
        rollback_plan=(),
        authorization="policy_approved",
        created_at="2026-10-03T00:00:00Z",
        author="b3",
    )


@pytest.fixture
def despliegue() -> Any:
    """Storage con UN DomainPack, y el registro que construye la CLI DE VERDAD.

    El registro se pide importando la funcion de produccion, no
    reimplementando su criterio: la primera version de este fichero
    traia su propia copia, y las mutaciones M19/M20 —que cambian
    `_load_registry` de verdad— salieron NO_CAZADAS por eso. Un guard que
    mide su propia copia no puede notar que la realidad se movio.
    """
    from skillgraph.cli.commands.expansion import _load_registry

    tmp = tempfile.TemporaryDirectory()
    db = Path(tmp.name) / "b3i4.sqlite"
    storage = Storage(db)
    _pack(storage, "code-analysis", ("code.analysis",))
    storage.close()
    yield _load_registry(db, tenant_id=TENANT, project_id=PROJECT)
    storage.close()


class TestElRegistroTieneDosVistas:
    """I3 y I4 son dos preguntas distintas. Un solo mapa no las contesta."""

    def test_ve_las_capabilities_para_i3(self, despliegue: Any) -> None:
        assert "code.analysis" in despliegue.capabilities

    def test_ve_las_referencias_para_i4(self, despliegue: Any) -> None:
        assert PACK_REF in despliegue.references, (
            "el registro no conoce la referencia del unico pack del "
            "proyecto. Sin esto I4 no tiene fuente y vuelve a rechazar "
            "lo que existe."
        )

    def test_una_capability_no_figura_como_referencia(self, despliegue: Any) -> None:
        """Y al reves: una capability no es una referencia.

        Es la confusion que hacia pasar a I4 con
        `new_dependencies: ['code.analysis']`, y la que hacia que el
        invariante midiera la confusion del autor en vez de la existencia
        de la referencia.
        """
        assert "code.analysis" not in despliegue.references

    def test_el_registro_rechaza_una_referencia_en_la_vista_de_capabilities(
        self,
    ) -> None:
        """La guarda que impide volver a mezclar las dos vistas.

        Sin ella, el defecto original podria volver por la otra puerta:
        un `capabilities` que contenga tambien las referencias haria que
        I4 volviera a «funcionar» —porque la referencia estaria en el
        mapa— sin que I4 llegue a mirar `references`. Es la misma
        confusion,solo que con el dict al reves.

        Se mide aqui, sobre el dataclass, y no mutando `_load_registry`:
        la sonda de esa mutacion daba un `IndentationError` en vez de un
        cambio de comportamiento, y una sonda que rompe la sintaxis no
        mide el defecto que dice medir.
        """
        with pytest.raises(ValidationError):
            ExpansionRegistry(capabilities={"packs:DomainPack/x": "packs:DomainPack/x"})


class TestElFormatoDeReferencia:
    """`ns:Kind/name`, que es el que ya usa `ResourceIdentity`."""

    def test_una_referencia_valida_pasa(self) -> None:
        assert resource_ref("packs:DomainPack/code-analysis")

    @pytest.mark.parametrize(
        "mala",
        [
            "",
            "   ",
            "packs",  # sin Kind/name
            "packs:DomainPack",  # sin /name
            "packs:DomainPack/",  # nombre vacio
            ":DomainPack/code",  # namespace vacio
            "packs:/code",  # kind vacio
            "packs:DomainPack/code/extra",  # de mas de una barra
        ],
    )
    def test_una_referencia_mala_no_se_puede_construir(self, mala: str) -> None:
        """Validacion en el smart constructor, no en la validacion.

        Una referencia con formato invalido no es una referencia que no
        existe: es una referencia mal escrita, y las dos cosas merecen
        errores distintos. Si el formato se comprueba aqui, `I4` solo ve
        referencias que podrian existir, que es lo que el blueprint pide.
        """
        with pytest.raises(ValidationError):
            resource_ref(mala)

    def test_el_error_dice_que_formato_pide(self) -> None:
        """El mensaje dice la forma, no solo «invalido».

        Sin la forma, quien escribe la propuesta tiene que buscar el
        formato en el codigo, y lo va a escribir mal otra vez.
        """
        with pytest.raises(ValidationError) as exc:
            resource_ref("packs:DomainPack")
        assert "ns:Kind/name" in str(exc.value)


class TestI4AhoraComprueba:
    """El invariante, ya con la fuente que le faltaba."""

    def test_i4_acepta_una_referencia_que_existe(self, despliegue: Any) -> None:
        """La fila que antes daba I4 y ahora no.

        `packs:DomainPack/code-analysis` es el unico pack del proyecto.
        Antes se rechazaba; hoy es una referencia legitima.
        """
        resultado = validate(
            _proposta(caps=(), deps=(PACK_REF,)), plan=_plan(), registry=despliegue
        )
        assert "I4" not in resultado.violated_invariants, (
            "I4 sigue rechazando una referencia que EXISTE. Ha vuelto a quedarse sin fuente."
        )

    def test_i4_rechaza_una_referencia_que_no_existe(self, despliegue: Any) -> None:
        """Y la otra mitad: que siga rechazando lo que no existe.

        Sin este test, «I4 no salta nunca» pasaria. Con el, I4 solo puede
        bajar cuando la referencia EXISTE, que es la propiedad entera.
        """
        resultado = validate(
            _proposta(caps=(), deps=(REF_INEXISTENTE,)),
            plan=_plan(),
            registry=despliegue,
        )
        assert "I4" in resultado.violated_invariants

    def test_i4_distingue_una_de_otra(self, despliegue: Any) -> None:
        """Las dos mitades en un solo test, porque la propiedad es la diferencia.

        Comparar contra dos registros o contra dos listas de
        expectativas seria dos tests que pueden pasar los dos rotos.
        """
        buena = validate(_proposta(caps=(), deps=(PACK_REF,)), plan=_plan(), registry=despliegue)
        mala = validate(
            _proposta(caps=(), deps=(REF_INEXISTENTE,)),
            plan=_plan(),
            registry=despliegue,
        )
        assert ("I4" in buena.violated_invariants) is False
        assert ("I4" in mala.violated_invariants) is True

    def test_una_capability_ya_no_pasa_como_dependencia(self, despliegue: Any) -> None:
        """La confusion que hacia pasar a I4, ya no pasa.

        Antes `new_dependencies: ['code.analysis']` era la unica forma de
        que I4 bajara, porque el registro solo tenia claves de
        capability. Ese camino se cierra.
        """
        # El nombre de una capability NO es una referencia valida, y eso
        # se decide al CONSTRUIR, no al validar. Antes esa confusion era
        # lo unico que hacia pasar a I4; ahora ni llega a existir.
        with pytest.raises(ValidationError):
            resource_ref("code.analysis")


class TestI3NoSeRompe:
    """El arreglo de I4 no puede costar I3."""

    def test_i3_sigue_aceptando_una_capability_registrada(self, despliegue: Any) -> None:
        resultado = validate(
            _proposta(caps=("code.analysis",), deps=()),
            plan=_plan(),
            registry=despliegue,
        )
        assert "I3" not in resultado.violated_invariants

    def test_i3_sigue_rechazando_una_capability_desconocida(self, despliegue: Any) -> None:
        resultado = validate(
            _proposta(caps=("telemetry.query",), deps=()),
            plan=_plan(),
            registry=despliegue,
        )
        assert "I3" in resultado.violated_invariants

    def test_las_dos_preguntas_son_independientes(self, despliegue: Any) -> None:
        """Capability registrada + referencia inexistente: solo I4.

        Y capability desconocida + referencia existente: solo I3. Si
        alguna vez saltan juntas, es que las dos vistas se han
        mezclado, que es el defecto que se vino a arreglar.
        """
        a = validate(
            _proposta(caps=("code.analysis",), deps=(REF_INEXISTENTE,)),
            plan=_plan(),
            registry=despliegue,
        )
        b = validate(
            _proposta(caps=("telemetry.query",), deps=(PACK_REF,)),
            plan=_plan(),
            registry=despliegue,
        )
        assert a.violated_invariants == ("I4",)
        assert b.violated_invariants == ("I3",)
