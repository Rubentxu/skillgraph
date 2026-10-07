"""B34 — Una superficie de consulta, y que la usen TODAS.

**LO QUE SE MIDIO ANTES DE ESCRIBIR UNA LINEA.** El roadmap pide seis
consultas y un transporte:

```
knowledge what      que se sabe de X
knowledge why       por que se afirmo eso
knowledge impact    a que afecta
knowledge changed   que cambio
knowledge conflicts que se contradice
knowledge evidence  de donde sale
```

Medido sobre el arbol real:

| pregunta | ¿existe la consulta? |
|---|---|
| what | SI — `list_claims_for_subject` |
| changed | SI — `claims_at_revision` (B29), `claims_desde_commit` (B32) |
| conflicts | SI — `conflicts_for` (B27) + `resolver` (B28) |
| evidence | SI — `get_evidences_for_claim` |
| impact | SI en `Storage`, **NO en el Protocol** — `list_claims_by_object_entity` (B25) |
| why | NO — pero es composicion de tres lecturas que ya existen |

Y ademas:

```
sg.knowledge.query   CONSULTAS = {"claims", "resource"}   -> de las seis, NINGUNA
MCP                  0 ficheros, 0 menciones
CLI `knowledge`      stale, invalidate, refresh, compile, trace, resolve
```

**LA LECTURA QUE DEFINE EL BLOQUE.** Cinco de las seis consultas ya
existen y la sexta es una composicion de lecturas. **B34 no es un bloque de
consultas: es un bloque de superficie.** Lo que falta no es poder responder,
sino un modelo unico que las nombre, y que ninguna superficie tenga que
reconstruir el retrieval o la autoridad por su cuenta — que es
literalmente el gate que el roadmap escribe.

Por eso este modulo NO hace SQL y NO tiene metodo por consulta visible desde
afuera: tiene UN metodo, `responder`, que es el unico sitio donde se decide
que se pregunta. Un `if` por pregunta, en un solo sitio, es lo que hace que
la CLI y la capability puedan compartirlo sin que ninguna lo reimplemente.

**LO QUE `why` SIGNIFICA AQUI, Y POR QUE SE DICE.** `why` responde **por que
se AFIRMO esto**, y se construye con lo que el sistema sabe: la evidencia
que lo respalda, la fuente de la que salio, quien lo extrajo, y el claim que
reemplaza (B29). **NO responde por que el mundo es como es**, y no puede:
eso exigiria causalidad, y el sistema tiene procedencia, no causa. Un
`why` que prometiese lo segundo y entregara lo primero seria la peor
version de este bloque, porque el nombre suggestia justo lo que no tiene.
"""

from __future__ import annotations

import typing
from dataclasses import dataclass
from typing import Any, Final, Literal

from skillgraph.core.errors import ValidationError
from skillgraph.knowledge.authority import Resolution, resolver
from skillgraph.knowledge.graph import Conflicto, Source
from skillgraph.platform.ports.repositories import KnowledgeRepository

__all__ = [
    "CONSULTAS",
    "PREGUNTA",
    "Consulta",
    "Procedencia",
    "Respuesta",
    "SuperficieConocimiento",
    "pregunta",
    "respuesta_a_payload",
]

#: Las seis preguntas del roadmap, como ADT cerrado (`AGENTS.md` 2.1).
#:
#: Crecer este `Literal` es un cambio de contrato del blueprint y necesita
#: ADR, por la misma razon que `SourceKind`, `QueryIntent` y
#: `AssertionOrigin`. No es una lista de cadenas porque una lista se puede
#: alargar sin que nadie se entere de que el contrato cambio.
PREGUNTA: Final = Literal[
    "what",
    "why",
    "impact",
    "changed",
    "conflicts",
    "evidence",
]

#: Derivado del `Literal` (regla QW-E, la de `SOURCE_KINDS`). Un conjunto
#: escrito a mano seria una segunda fuente de verdad que se desincroniza en
#: cuanto alguien anada un valor al `Literal`, y entonces la validacion
#: rechaza el valor nuevo mientras el tipo lo acepta. B25 sufrio esa
#: divergencia y desde entonces la regla no se negocia.
CONSULTAS: Final[frozenset[str]] = frozenset(typing.get_args(PREGUNTA))


def pregunta(s: str) -> PREGUNTA:
    """Smart constructor: valida que la pregunta exista.

    Se llama en la FRONTERA —la CLI y la capability— y no dentro de
    `responder`, porque el error tiene que llegar a quien escribió la
    consulta, no a quien la ejecuto. Es el mismo tratamiento que
    `query_intent()` en `knowledge/authority.py`.
    """
    if s not in CONSULTAS:
        raise ValidationError(f"pregunta {s!r} desconocida. Preguntas: {sorted(CONSULTAS)}")
    return typing.cast("PREGUNTA", s)


@dataclass(frozen=True, slots=True)
class Consulta:
    """Lo que se pregunta. Inmutable, y validado al construir.

    **POR QUE UN SOLO ADT PARA LAS SEIS.** Si cada consulta tuviera su
    propia forma de entrada, cada superficie tendría que saber cual es cual
    antes de poder despachar, y ese `if` es exactamente lo que el gate
    prohibe: una superficie reconstruyendo el modelo por su cuenta.

    Los tres campos opcionales **no son** «lo que cada consulta necesita»,
    son «lo que las consultas de historial necesitan», y se validan con la
    pregunta en vez de dejarlo al runtime: `why` sin `claim_id` no tiene
    respuesta, y decirlo aqui es mas barato que decirlo tres capas mas
    abajo.
    """

    pregunta: PREGUNTA
    subject: str
    claim_id: str | None = None
    revision: str | None = None
    commit: str | None = None

    def __post_init__(self) -> None:
        if not self.subject or not self.subject.strip():
            raise ValidationError("Consulta.subject no puede estar vacio")
        if self.pregunta == "why" and not self.claim_id:
            raise ValidationError(
                "«why» necesita el claim_id: se responde POR QUE se afirmo ESA "
                "afirmacion, y sin decir cual es la pregunta no tiene sujeto"
            )
        if self.commit is not None and self.pregunta != "changed":
            raise ValidationError(
                f"«{self.pregunta}» no se pregunta por un commit: `commit` es de "
                "«changed», y dejarlo en las demas seria un parametro que nadie "
                "mira y que ademas sugiere que todas las preguntas son historicas"
            )


@dataclass(frozen=True, slots=True)
class Procedencia:
    """De donde sale UNA afirmacion. La respuesta de `why` y de `evidence`.

    Se llama `Procedencia` y no `Evidencia` a proposito: la evidencia es UNA
    de las cuatro cosas que responde, y nombrar el conjunto como la parte
    haria que `why` pareciera una consulta de evidencia cuando tambien
    responde de que commit salio y quien lo extrajo.

    Los cuatro campos son declarativos: no se deduce ninguno del otro. Una
    afirmacion puede tener evidencia y ningun commit (`local_file`), o
    commit y ninguna evidencia si se registro a mano. Un constructor que
    exigiera los cuatro estaria invitando a rellenarlos de mentira.
    """

    claim_id: str
    assertion_origin: str
    extraction_method: str
    extractor_version: str
    evidence_ids: tuple[str, ...]
    source_id: str | None
    source_kind: str | None
    git_commit_sha: str | None
    supersedes_claim_id: str | None


@dataclass(frozen=True, slots=True)
class Respuesta:
    """La respuesta. **UNA sola forma para las seis preguntas.**

    Es el punto del bloque: si cada superficie recibiera un tipo distinto
    segun la pregunta, cada una tendria que ramificar por ella. Con una
    forma unica, la CLI renderiza y la capability serializa sin preguntar
    nunca cual es la pregunta.

    Los campos que no aplican a una pregunta van a su valor de ausencia —
    `None` o `()`— y **no se omiten**, porque un campo ausente y un campo
    vacio son cosas distintas y un `dict` que a veces no tiene una clave es
    la forma de que un consumidor adivine.
    """

    consulta: Consulta
    #: Los claims de la respuesta. **`Any`, y no `Claim`, a proposito.**
    #:
    #: El puerto `KnowledgeRepository` declara `Any` en estas consultas
    #: porque no debe conocer el ADT de `knowledge.graph`, que es del lado
    #: de arriba. MEDIDO al cablear la CLI: lo que llega es `StoredClaim`,
    #: que tiene `object_entity_id: str` con el criterio de XOR del repo,
    #: y `Claim` tiene `object_entity: EntityRef | None`. Anotar `Claim`
    #: habria sido MENTIR con tipos, y el type-checker no lo habria
    #: cazado porque el puerto devuelve `Any`: el error habria salido en
    #: runtime, en la primera linea que leyera un campo.
    claims: tuple[Any, ...] = ()
    #: `conflicts` solamente. `None` cuando no se pregunto por conflictos,
    #: que es distinto de `()`: `()` es «no hay conflictos» y `None` es
    #: «esta respuesta no habla de conflictos».
    conflicto: Conflicto | None = None
    #: `conflicts` solamente, y solo si hubo conflicto que resolver.
    resolucion: Resolution | None = None
    #: `why` y `evidence`.
    procedencia: tuple[Procedencia, ...] = ()

    @property
    def vacia(self) -> bool:
        """Si la respuesta no trae nada.

        Y es `False` cuando hay un conflicto ABIERTO aunque no haya
        ninguna afirmacion en el: un conflicto sin resolver es una
        respuesta, no un silencio.
        """
        if self.conflicto is not None or self.resolucion is not None:
            return False
        return not (self.claims or self.procedencia)


class SuperficieConocimiento:
    """El modelo unico. **Un metodo, seis preguntas.**

    Inyecta el `KnowledgeRepository` **por constructor**, como `Protocol`
    que es (`AGENTS.md` 4.3), y por el mismo motivo que
    `KnowledgeQueryCapability`: la capacidad que lo usa se puede probar sin
    abrir una base de datos.

    **POR QUE NO HAY UN METODO POR CONSULTA.** Habria seis metodos
    publicos, y entonces «la superficie reconstruye el retrieval por su
    cuenta» dejaria de ser una frase del roadmap y pasaria a ser la forma
    del codigo: cada superficie elegiria el metodo que le conviene y
    construiria su propia combinacion. Con `responder(consulta)`, el
    `if` esta en un unico sitio y la unica decision —que se pregunta— la
    toma quien escribe el `Literal`.
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

    def responder(self, consulta: Consulta) -> Respuesta:
        """La unica puerta. Despacha y devuelve SIEMPRE la misma forma."""
        metodo = getattr(self, f"_responde_{consulta.pregunta}")
        return metodo(consulta)  # type: ignore[no-any-return]

    # -- what ---------------------------------------------------------------

    def _responde_what(self, c: Consulta) -> Respuesta:
        """Lo que se afirma del sujeto. Sin resolver, sin jerarquizar.

        **POR QUE NO RESUELVE.** `what` no es una pregunta por una
        AFIRMACION, es una pregunta por todas las que hay del sujeto, y
        por eso devuelve todas, incluidas las que se contradicen entre
        si. Quien quiera
        «la buena» la pregunta con `conflicts` y un `intent`, que es donde
        el sistema Sabe cual es buena. Poner el resolver aqui seria quitarle
        la eleccion al que pregunta, y volverian las dos mitades del
        problema de B28: una respuesta sin decir por que.
        """
        claims = tuple(
            self._knowledge.list_claims_for_subject(
                tenant_id=self._tenant_id,
                project_id=self._project_id,
                subject_entity_id=c.subject,
            )
        )
        return Respuesta(consulta=c, claims=claims)

    # -- why ----------------------------------------------------------------

    def _responde_why(self, c: Consulta) -> Respuesta:
        """Por que se AFIRMO esa afirmacion. Procedencia, no causa.

        Se compone de lecturas que ya existen y **no anade ninguna consulta**:
        el claim, su evidencia, su fuente. Es el unico caso de los seis que
        no tiene una consulta propia, y por eso lleva su propia seccion:
        que aqui no haya SQL nuevo es un resultado medido, no un atajo.
        """
        claim = self._knowledge.get_claim(
            tenant_id=self._tenant_id,
            project_id=self._project_id,
            claim_id=c.claim_id or "",
        )
        if claim is None:
            return Respuesta(consulta=c)
        evidencias = self._knowledge.get_evidences_for_claim(
            tenant_id=self._tenant_id,
            project_id=self._project_id,
            claim_id=claim.claim_id,
        )
        source = self._knowledge.get_source(
            tenant_id=self._tenant_id,
            project_id=self._project_id,
            source_id=claim.source_id,
        )
        return Respuesta(
            consulta=c,
            claims=(claim,),
            procedencia=(self._procedencia_de(claim, source, evidencias),),
        )

    # -- impact -------------------------------------------------------------

    def _responde_impact(self, c: Consulta) -> Respuesta:
        """A que afecta: la arista INVERSA.

        `what` va del sujeto a sus afirmaciones; `impact` va de una entidad
        a las afirmaciones que la **mencionan como objeto**. Son dos
        direcciones de la misma arista y por eso son dos preguntas y no
        una con un parametro: una con parametro obliga al que pregunta a
        saber que la arista tiene dos sentidos, que es el mismo defecto que
        confundo los dos relojes en B29 y B32.
        """
        claims = tuple(
            self._knowledge.list_claims_by_object_entity(
                tenant_id=self._tenant_id,
                project_id=self._project_id,
                object_entity_id=c.subject,
            )
        )
        return Respuesta(consulta=c, claims=claims)

    # -- changed ------------------------------------------------------------

    def _responde_changed(self, c: Consulta) -> Respuesta:
        """Que se sabia, en una revision o desde un commit.

        Los dos relojes siguen siendo dos: `revision` es el orden de
        observacion local (B29) y `commit` es la ascendencia real (B32). No
        se traducen uno en otro, y se da que solo uno puede venir: un
        commit no es una revision y compararlos seria la falta que B32
        declaro.
        """
        if c.commit is not None:
            return Respuesta(
                consulta=c,
                claims=tuple(
                    self._knowledge.claims_desde_commit(
                        tenant_id=self._tenant_id,
                        project_id=self._project_id,
                        commit_sha=c.commit,
                    )
                ),
            )
        revision = c.revision or "HEAD"
        return Respuesta(
            consulta=c,
            claims=tuple(
                self._knowledge.claims_at_revision(
                    tenant_id=self._tenant_id,
                    project_id=self._project_id,
                    subject_entity_id=c.subject,
                    revision=revision,
                )
            ),
        )

    # -- conflicts ----------------------------------------------------------

    def _responde_conflicts(self, c: Consulta) -> Respuesta:
        """Que se contradice, y —si se pregunto— quien gana para que intencion.

        Aqui SI se resuelve, y es el unico de los seis donde eso pasa: la
        resolucion es parte de la pregunta. Se delega en `resolver` de B28
        y **no se reimplementa**, porque una segunda implementacion del
        ranking por intencion es exactamente la falta que B28 cerro.

        Y el `intencion` NO se deduce: se pide. Sin el, se devuelven los
        conflictos SIN resolver, que es la respuesta honesta a «¿qué se
        contradice?» — y no «no hay respuesta», que es lo que Contestaria
        un `default` silencioso.
        """
        conflictos = self._knowledge.conflicts_for(
            tenant_id=self._tenant_id,
            project_id=self._project_id,
            subject_entity_id=c.subject,
        )
        if not conflictos:
            return Respuesta(consulta=c)
        primero: Conflicto = conflictos[0]
        intencion = self._intencion_de(c)
        if intencion is None:
            # Las afirmaciones viajan TAMBIEN sin intencion. MEDIDO al
            # ejecutar la CLI: devolver solo el `conflicto` renderizaba una
            # linea de cabecera y nada debajo, y eso no es «no se
            # contradice» — es «contradicte esto» sin decir que. Quien
            # pregunta por un conflicto quiere VER las dos.
            return Respuesta(consulta=c, conflicto=primero, claims=primero.afirmaciones)
        return Respuesta(
            consulta=c,
            conflicto=primero,
            resolucion=resolver(primero, intencion=intencion),
            claims=primero.afirmaciones,
        )

    # -- evidence -----------------------------------------------------------

    def _responde_evidence(self, c: Consulta) -> Respuesta:
        """De donde sale. La misma procedencia que `why`, sin el `claim_id`
        obligatorio.

        Y la diferencia con `why` es de ALCANCE, no de forma: `evidence`
        pregunta por un sujeto y devuelve la procedencia de todas sus
        afirmaciones; `why` pregunta por UNA. Por eso `why` exige
        `claim_id` y `evidence` no — y por eso comparten el mismo tipo de
        respuesta, que es lo que hace que la superficie sea UNA.
        """
        claims = tuple(
            self._knowledge.list_claims_for_subject(
                tenant_id=self._tenant_id,
                project_id=self._project_id,
                subject_entity_id=c.subject,
            )
        )
        procedencia = []
        for claim in claims:
            evidencias = self._knowledge.get_evidences_for_claim(
                tenant_id=self._tenant_id,
                project_id=self._project_id,
                claim_id=claim.claim_id,
            )
            source = self._knowledge.get_source(
                tenant_id=self._tenant_id,
                project_id=self._project_id,
                source_id=claim.source_id,
            )
            procedencia.append(self._procedencia_de(claim, source, evidencias))
        return Respuesta(consulta=c, claims=claims, procedencia=tuple(procedencia))

    # -- lo que comparten ---------------------------------------------------

    def _intencion_de(self, c: Consulta) -> str | None:
        """La intencion, si la traia.

        Vive en `revision` cuando la pregunta es `conflicts` porque es el
        unico hueco que queda sin usar, y **eso es un sobreuso que se
        declara**: un campo que significa dos cosas segun la pregunta es la
        razon por
        la que la `Consulta` no crece con un `intent: str | None` propio,
        que seria lo limpio. Se deja asi y se escribe porque el
        sobreuso se ve al leer el `__post_init__`, y un campo extra que
        solo dos de las seis preguntas usan seria ruido en las otras cuatro.
        """
        return c.revision if c.pregunta == "conflicts" and c.revision else None

    def _procedencia_de(
        self, claim: Any, source: Source | None, evidencias: tuple[Any, ...]
    ) -> Procedencia:
        """Un claim y sus lecturas -> su `Procedencia`.

        `evidencias` se reduce a identificadores a proposito: la
        procedencia responde **de donde** sale, y el contenido de la
        evidencia es lo que contesta `evidence` con su propia consulta. Meter
        aqui el payload haria que `why` creciera sin limite y sin que nadie
        lo pidiera.
        """
        return Procedencia(
            claim_id=claim.claim_id,
            assertion_origin=claim.assertion_origin,
            extraction_method=claim.extraction_method,
            extractor_version=claim.extractor_version,
            evidence_ids=tuple(str(getattr(e, "evidence_id", e)) for e in evidencias),
            source_id=source.source_id if source is not None else None,
            source_kind=source.kind if source is not None else None,
            git_commit_sha=getattr(source, "git_commit_sha", None) if source else None,
            supersedes_claim_id=getattr(claim, "supersedes_claim_id", None),
        )


def respuesta_a_payload(respuesta: Respuesta) -> dict[str, Any]:
    """La `Respuesta`, en la forma que viaja por `CapabilityResult.payload`.

    **POR QUE SE SERIALIZA EL `Literal` Y NO SOLO SU VALOR.** Un
    `Literal` serializado es una cadena, y quien la reciba tendria que
    saber el vocabulario para validarla. Se manda la cadena **y** la lista
    de las seis, para que un agente pueda ver el contrato cerrado sin
    tener que leer el codigo: es lo mismo que hace `CAPABILITY_VERSION`
    desde el otro lado, y lo que hace que este payload sea un contrato y no
    una convencion.

    Y se serializa con `asdict` por el motivo que ya se pago una vez en
    `ObservationEnvelope`: un campo anadido al ADT y olvidado aqui es un
    dato que sale del sistema sin que nadie lo note.
    """
    from dataclasses import asdict

    datos = asdict(respuesta)
    datos["vocabulario"] = sorted(CONSULTAS)
    return datos
