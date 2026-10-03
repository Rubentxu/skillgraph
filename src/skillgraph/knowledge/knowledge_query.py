"""B3-cierre R1 — el PRIMER adapter de capability de produccion.

Hasta aqui, el unico `Capability` del repo vivia dentro de un fichero de
test. Eso deja el gate del roadmap sin nada que demostrar fuera del
testsuite:

    ROADMAP.md §B3 — «Se puede anadir una capability (tipo, contrato,
    adapter, controller opcional, policy, tests) SIN MODIFICAR
    `RunController`, el storage base ni el motor del workflow.»

Un contrato que solo cumple un doble de test es una forma de contrato, no
un contrato.

**POR QUE ESTA, Y POR QUE ESTA EN ESTE PAQUETE.**

El roadmap lista siete capabilities candidatas. Seis son de productos
externos —`CodeAnalysis`, `TelemetryQuery`, `SecretAccess`— y SkillGraph
**no** debe reconstruirlas: el nucleo no puede conocer CogniCode ni Chronos
ni secretless, que es lo que vigila `TestElNucleoNoImportaAdapters`. La
septima, `KnowledgeQuery`, es **dominio propio**: el grafo de conocimiento
es de este repo, y su acceso ya estaba declarado como `Protocol` en
`platform/ports/repositories.py` sin que nadie lo usara como capability.

Vive en `knowledge/` y no en un `platform/adapters/` nuevo por dos motivos
concretos. Primero: es la capability **de esta capa**, y la capa ya existe y
ya tiene su contexto acotado; un paquete nuevo con una sola clase dentro
seria estructura para no estructurar. Segundo, y mas importante: un
`adapters/` al lado de los puertos pondria la implementacion a la vista de
su propio contrato, que es el camino corto a que un adapter se confunda con
un puerto. Aqui el contrato se importa por su ruta completa
(`platform.ports.capabilities`), y el origen queda a la vista de quien
busque de donde sale una capability.

**POR QUE DEPENDE DEL `Protocol` Y NO DE `Storage`.** La anotacion es
`KnowledgeRepository`, no `Storage`. Invertir por el puerto es lo que pide
`AGENTS.md 4.3`, y es lo que hace que este adapter se pueda probar sin
abrir una base de datos. Lo que se necesita —leer claims y leer recursos—
ya estaba en el puerto; lo que hace es **usarlo como capability**, que es
justo el trabajo que B3 vino a hacer.

**LA PROCEDENCIA, Y POR QUE ES POR ELEMENTO.** `CapabilityResult` lleva
`adapter`, que dice quien ejecuto. Eso responde «¿quien ejecuto esto?», pero
no «¿de donde salio ESTO?». B6 quiere poder distinguir `observed` de lo que
un agente afirmo, y para eso cada elemento que sale de aqui lleva su
`source_id` y su `checked_at_revision`: la revision contra la que se
comparo. Sin eso, una afirmacion y una medicion viajan con el mismo aspecto
y la pregunta no tiene respuesta.
"""

from __future__ import annotations

from typing import Any, Final, Literal

from skillgraph.core.errors import ValidationError
from skillgraph.platform.ports.capabilities import (
    CapabilityRequest,
    CapabilityResult,
    CapabilitySpec,
)
from skillgraph.platform.ports.repositories import KnowledgeRepository

__all__ = [
    "CONSULTAS",
    "KNOWLEDGE_QUERY",
    "KnowledgeQueryCapability",
]

#: El TIPO de esta capability. Constante, no cadena suelta
#: (`AGENTS.md 2.4`): es un conjunto cerrado —`claims` y `resource`— y
#: vive aqui su unica definicion.
KNOWLEDGE_QUERY: Final[str] = "sg.knowledge.query"

#: Que se puede preguntar. Cerrado, y validado al ENTRAR, no al devolver:
#: una pregunta mal formada y una que no encuentra nada son dos fallos que
#: el operador arregla de dos maneras, y si se comprobaran juntas «no
#: salio nada» dejaria de significar una sola cosa.
CONSULTAS: Final[frozenset[str]] = frozenset({"claims", "resource"})

_CLAIMS: Final[Literal["claims"]] = "claims"
_RESOURCE: Final[Literal["resource"]] = "resource"


class KnowledgeQueryCapability:
    """La capability de produccion que demuestra que el contrato se cumple.

    Inyecta el `KnowledgeRepository` **por constructor**, como `Protocol`
    que es. Sin registro global, sin singleton, sin lazy: el adaptador que
    sabe es el despliegue, y lo recibe.

    No implementa el `Protocol` `Capability` con `inherit`: es
    estructural, y `test_cumple_el_protocol_estructural` lo comprueba con
    `isinstance`. Heredarlo anadiria una dependencia del adapter al puerto
    de hereda que no compra nada.
    """

    def __init__(
        self,
        knowledge: KnowledgeRepository,
        *,
        tenant_id: str,
        project_id: str,
    ) -> None:
        self._knowledge = knowledge
        self._tenant_id = tenant_id
        self._project_id = project_id

    @property
    def spec(self) -> CapabilitySpec:
        """La identidad. La `version` la hereda del puerto, no se escribe aqui.

        Si el adapter declarase su propia version, cada adapter podria
        inventar la suya y no habria nada que comparar. Que la version
        viva en el puerto es lo que hace que `requires.capabilities` de B8
        tenga algo que versionar.
        """
        return CapabilitySpec(
            type_name=KNOWLEDGE_QUERY,
            summary="Consulta el grafo de conocimiento y devuelve la procedencia de cada elemento",
        )

    def invoke(self, request: CapabilityRequest) -> CapabilityResult:
        """Responde, y responde con la procedencia de lo que devuelve.

        El `kind` es **obligatorio**: sin el se lanza. Adivinarlo
        convertiria «no se que preguntar» en «no hay nada», y esas dos
        cosas se confonden tres capas mas abajo, que es donde un `None` se
        convierte en un fallo silencioso.
        """
        consulta = self._consulta_de(request)
        if consulta == _CLAIMS:
            elementos = self._claims(request.subject)
        else:
            elementos = self._recurso(request.subject)
        return CapabilityResult(
            spec=self.spec,
            adapter=type(self).__name__,
            payload={
                "subject": request.subject,
                "consulta": consulta,
                "elementos": elementos,
            },
        )

    @staticmethod
    def _consulta_de(request: CapabilityRequest) -> str:
        """Valida `arguments['kind']` AL ENTRAR. Ver la nota de `CONSULTAS`."""
        crudo = request.arguments.get("kind")
        if crudo is None:
            raise ValidationError(
                f"{KNOWLEDGE_QUERY} necesita 'kind' en arguments. Opciones: {sorted(CONSULTAS)}"
            )
        if not isinstance(crudo, str) or crudo not in CONSULTAS:
            raise ValidationError(
                f"consulta {crudo!r} no soportada por {KNOWLEDGE_QUERY}. "
                f"Opciones: {sorted(CONSULTAS)}"
            )
        return crudo

    def _claims(self, subject: str) -> tuple[dict[str, Any], ...]:
        """Los claims de un sujeto, cada uno con su procedencia.

        `source_id` y `checked_at_revision` viajan por elemento porque la
        procedencia es **de la afirmacion**, no de la consulta: dos claims
        del mismo sujeto pueden venir de fuentes distintas y comparar
        contra revisiones distintas, y un unico `adapter` en el raiz
        direia lo mismo de las dos.
        """
        claims = self._knowledge.list_claims_for_subject(
            tenant_id=self._tenant_id,
            project_id=self._project_id,
            subject_entity_id=subject,
        )
        return tuple(
            {
                "claim_id": c.claim_id,
                "subject_entity_id": c.subject_entity_id,
                "predicate": c.predicate,
                "object_literal": c.object_literal,
                "source_id": c.source_id,
                "checked_at_revision": c.checked_at_revision,
                "extraction_method": c.extraction_method,
                "stale": c.stale,
            }
            for c in sorted(claims, key=lambda x: x.claim_id)
        )

    def _recurso(self, subject: str) -> tuple[dict[str, Any], ...]:
        """Un recurso por su uid. Ausente: lista vacia, no error.

        Aqui la ausencia **si** es un dato y no un fallo: preguntar por un
        recurso que no existe es una pregunta legitima con respuesta «no»,
        y el `subject` viaja en el payload para que se distinga de no
        haber preguntado.
        """
        recurso = self._knowledge.get_resource(subject)
        if recurso is None:
            return ()
        return (
            {
                "uid": recurso.uid,
                "kind": recurso.kind,
                "namespace": recurso.namespace,
                "name": recurso.name,
                "api_version": recurso.api_version,
            },
        )
