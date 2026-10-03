"""B3 — el invariante I4 no comprueba lo que dice comprobar.

Medido antes de arreglar nada, con el registro real que construye la CLI
(`.pipelinek/b3_i4_measure.py`):

```
registry construido por `_load_registry` : {'code.analysis': 'packs:DomainPack/code-analysis'}

caso                                       caps                      deps                        violaciones
dep que NO existe en ninguna parte        ()                        ('skillgraph.libs.http',)  ('I4',)
dep que SI existe (el pack del proyecto) ()                        ('packs:DomainPack/code-analysis',) ('I4',)
dep = 'code.analysis' (que ademas es cap) ()                        ('code.analysis',)         ()
```

Leido de izquierda a derecha, dice tres cosas.

**1. I4 rechaza una referencia que EXISTE.** `packs:DomainPack/code-analysis`
es el unico pack del proyecto de prueba, y lo rechaza. El invariante
del blueprint es «I4: No introducir referencias INEXISTENTES»
(`governance/graph_expansion.py:20`), o sea que lo que hay que
comprobar es que la referencia apunte a algo que existe. El unico
pack que existe es rechazado.

**2. I4 pasa cuando el autor confunde una dependencia con una
capability.** Es la unica forma de que I4 pase: que la «dependencia»
se llame exactamente como una capability que el registro declare. O
sea, el invariante mide la confusion del autor, no la existencia de la
referencia.

**3. La comprobacion esta bien escrita; lo que falta es la fuente.**
Contraejemplo, mismo invariante con la dependencia puesta a mano:

```
con el registry REAL (sin la dep)  -> ('I4',)
con la dependencia A MANO          -> ()
```

`_check_capabilities` pregunta lo correcto a un registro que por
construccion no puede responderlo. `cli/commands/expansion.py:148`
construye el mapa recorriendo `spec_json.spec.capabilities` de cada
pack y **en ningun momento mira `new_dependencies`**.

**POR QUE ESTE TEST FIJA EL COMPORTAMIENTO ROTO Y NO EL DESEADO.**
Porque arreglar I4 exige decidir que es una «referencia existente», y
esa es una decision de CONTRATO: `new_dependencies` es un
`tuple[str, ...]` de forma libre —`cli/commands/expansion.py:228` hace
`tuple(raw.get("new_dependencies", []))` sin validar nada— y el unico
ejemplo que hay en el repo se llama `ghost_ref_does_not_exist`. Sin
formato declarado no hay forma de indexar nada, asi que el arreglo
correcto no es deducible de aqui.

Fijar el comportamiento actual, con el motivo escrito, es lo que hizo
B1 con las deudas: que el proximo que lo lea sepa que esta roto y por
que, en vez de encontrarlo en produccion. **Si este test falla, no se
ha roto el invariante: se ha cambiado el contrato, y eso hay que
decidir a proposito.**
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from skillgraph.domain.dsl import PlanBuilder, node_name
from skillgraph.governance.graph_expansion import (
    GraphExpansionProposal,
    validate,
)
from skillgraph.platform.storage import Storage
from skillgraph.resources.bricks import Brick, ResourceIdentity

TENANT = "t-b3i4"
PROJECT = "p-b3i4"

#: El unico DomainPack del proyecto de prueba. Existe. I4 lo rechaza igual.
PACK_REF = "packs:DomainPack/code-analysis"

#: Una referencia que no existe en ninguna parte.
DEP_INEXISTENTE = "skillgraph.libs.http"


def _pack(storage: Storage, name: str, capabilities: tuple[str, ...]) -> None:
    """Un `DomainPack` de verdad, con la API del dominio.

    La primera version de este fixture hacia `INSERT` en SQL crudo con
    `spec_json = {"spec": {"capabilities": [...]}}`. **Esa forma no la
    produce nadie**: `cli/support.py:299` lee `spec_json` y se lo pasa a
    `Brick(spec=...)` tal cual, y `resources/registry.py:131` valida
    `spec.get("capabilities")` sobre ese mismo dict. O sea, `capabilities`
    va en la RAIZ del spec, no dentro de un `spec`.

    Es el error de WI-106 por segunda vez en el mismo fichero, y de otra
    forma: primero una copia del criterio, luego una forma inventada del
    dato. Los dos hacen que el guard mida una realidad que no existe. Por
    eso este fixture usa `upsert_resource` con un `Brick`: si la forma
    real cambia, el test falla al CONSTRUIR, no al afirmar.
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


def _registry_de_produccion(db: Path) -> dict[str, str]:
    """LA FUNCION REAL, no una copia de su criterio.

    La primera version de este test traia su propia `_registry_real`, que
    reimplementaba el criterio de `cli/commands/expansion.py:148` linea a
    linea. Y eso es el error de WI-106: **el guard comparaba contra su
    propia copia**. No se nota mientras la copia coincida, y el dia que
    la funcion real cambie, el guard seguira verde midiendo la copia.

    Lo savioron las mutaciones M19 y M20, que cambian `_load_registry` de
    verdad: las dos salieron NO_CAZADAS mientras todos los demas tests
    seguian verdes. Un guard que solo mide su propia copia no puede
    notar que la realidad se movio.

    Importar la funcion real, aunque sea privada (`_load_registry`), es
    lo que convierte este fichero en un guard. Si algum dia se decide
    que el registro no pertenece a la CLI, habra que mover la funcion y
    cambiar este import — y ese cambio debe notarse, no pasar desapercibido.
    """
    from skillgraph.cli.commands.expansion import _load_registry

    return _load_registry(db, tenant_id=TENANT, project_id=PROJECT)


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
        new_dependencies=deps,
        capabilities_needed=caps,
        scope="NODE",
        attachment_point="n1",
        rollback_plan=(),
        authorization="policy_approved",
        created_at="2026-10-03T00:00:00Z",
        author="b3",
    )


@pytest.fixture
def despliegue() -> dict[str, str]:
    """Storage con UN DomainPack, y el registro que construye la CLI DE VERDAD.

    El registro se pide con la funcion de produccion, no con una
    reimplementacion: ver `_registry_de_produccion`.
    """
    tmp = tempfile.TemporaryDirectory()
    db = Path(tmp.name) / "b3i4.sqlite"
    storage = Storage(db)
    _pack(storage, "code-analysis", ("code.analysis",))
    storage.close()
    yield _registry_de_produccion(db)
    storage.close()


def test_el_registro_no_tiene_ninguna_clave_que_pueda_ser_una_referencia(
    despliegue: Any,
) -> None:
    """La fuente del invariante no puede contestar la pregunta que le hacen.

    No se afirma «que el registro este mal» —eso es conclusion—: se
    afirma el hecho del que sale, que es que sus claves son NOMBRES DE
    CAPABILITY y no REFERENCIAS.

    Y el discriminante es la FORMA, no un prefijo concreto. Una
    referencia de recurso es `namespace:Kind/name` — lleva dos puntos y
    una barra—; un nombre de capability no lleva ninguna de las dos
    cosas. La primera version de este test miraba `startswith("t-b3i4:")`,
    o sea el TENANT, y eso no puede fallar nunca: el namespace real es
    `packs`, no el tenant. Un contrasalto que no puede fallar es peor
    que no tener contrasalto, porque aparenta mirar algo.
    """
    registry = despliegue
    assert registry, "el proyecto de prueba deberia tener un DomainPack"
    for clave in registry:
        parece_referencia = ":" in clave and "/" in clave
        assert not parece_referencia, (
            f"la clave {clave!r} tiene forma de referencia de recurso "
            "(ns:Kind/name). Si el registro ha pasado a indexarse por "
            "referencia, I4 tiene fuente de verdad: eso es el ARREGLO, y "
            "hay que decidirlo a proposito, no dejarlo salir de un cambio."
        )


def test_i4_rechaza_una_referencia_que_si_existe(despliegue: Any) -> None:
    """El invariante dice «no introducir referencias INEXISTENTES».

    Esta referencia EXISTE: es el unico pack del proyecto. Y la
    asercion de abajo dice que I4 la rechaza igual.
    """
    registry = despliegue
    resultado = validate(_proposta(caps=(), deps=(PACK_REF,)), plan=_plan(), registry=registry)
    assert "I4" in resultado.violated_invariants, (
        "I4 ha cambiado de comportamiento. Puede ser un ARREGLO —si ahora "
        "distingue una referencia existente de una que no— o un EMPEORAMIENTO. "
        "En los dos casos es un cambio de contrato y hay que decidirlo a "
        "proposito, no dejar que salga de un refactor. Ver la cabecera."
    )


def test_i4_solo_pasa_cuando_la_dependencia_es_una_capability(
    despliegue: Any,
) -> None:
    """La unica forma de que I4 pase es confundir los dos conceptos.

    Y por eso I4 no es «una comprobacion que a veces pasa»: es una
    comprobacion de la confusion del autor. El nombre del unico test
    que el repo tiene con una dependencia real lo dice sin querer:
    `ghost_ref_does_not_exist`.
    """
    registry = despliegue
    como_capability = validate(
        _proposta(caps=(), deps=("code.analysis",)),
        plan=_plan(),
        registry=registry,
    )
    assert "I4" not in como_capability.violated_invariants, (
        "I4 ha cambiado: una cadena que es una capability deja de "
        "colarse como dependencia. Es un arreglo. Hay que decidirlo."
    )
    como_referencia = validate(
        _proposta(caps=(), deps=(PACK_REF,)), plan=_plan(), registry=registry
    )
    assert "I4" in como_referencia.violated_invariants


def test_la_comprobacion_en_si_esta_bien_escrita(despliegue: Any) -> None:
    """El defecto NO es de `_check_capabilities`.

    Con la dependencia puesta a mano en el registro, I4 deja de saltar.
    Eso localiza el defecto en la FUENTE —el registro se indexa por
    capability— y no en la comprobacion. Sin esta separacion, el
    arreglo natural («arreglar `_check_capabilities`») habria retocado
    codigo que ya funciona y no habria arreglado nada.
    """
    registry = despliegue
    sin_la_dep = validate(
        _proposta(caps=(), deps=(DEP_INEXISTENTE,)),
        plan=_plan(),
        registry=registry,
    )
    con_la_dep = validate(
        _proposta(caps=(), deps=(DEP_INEXISTENTE,)),
        plan=_plan(),
        registry={**registry, DEP_INEXISTENTE: "lo-que-sea"},
    )
    assert "I4" in sin_la_dep.violated_invariants
    assert "I4" not in con_la_dep.violated_invariants, (
        "I4 dejo de bajar aun con la dependencia en el mapa: la "
        "comprobacion cambio y el defecto esta en otro sitio. "
        "Re-medir antes de tocar nada."
    )


def test_i3_en_el_registro_real_si_funciona(despliegue: Any) -> None:
    """La separacion: I3 es una comprobacion REAL, y la sostiene.

    Conviene decirlo, porque si I3 tambien estuviese roto la conclusion
    seria otra. I3 pregunta «esta capability autorizada?» y el registro
    responde, porque esta indexado por capability — que es lo que I3
    necesita. El registro esta bien construido **para I3**; lo que no
    sirve es **para I4**.
    """
    registry = despliegue
    autorizada = validate(
        _proposta(caps=("code.analysis",), deps=()), plan=_plan(), registry=registry
    )
    no_autorizada = validate(
        _proposta(caps=("telemetry.query",), deps=()), plan=_plan(), registry=registry
    )
    assert "I3" not in autorizada.violated_invariants
    assert "I3" in no_autorizada.violated_invariants
