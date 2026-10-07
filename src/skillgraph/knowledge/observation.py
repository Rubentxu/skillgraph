"""B26 — Una herramienta externa aporta conocimiento SIN escribir en el store.

El enunciado del bloque era: *«una herramienta externa no tiene forma de
aportar conocimiento sin escribir en el store»*. MEDIDO antes de escribir nada,
sobre el arbol real (`scripts/measure_b26_ingesta.py`):

    P1  una forma declarada y versionada      ABIERTA  (el payload es dict[str, Any])
    P2  la ingesta es idempotente              ABIERTA  (no hay ingesta)
    P3  el normalizador es puro                ABIERTA  (no hay normalizador)
    P4  la version es consultable              ABIERTA  (no hay version)
    P5  el camino existente soporta las formas  ABIERTA  <-- BUG REAL

**P5 es la que salio de un bug y no al reves.** B25 metio una segunda forma de
objeto en `Claim` (`object_entity`). La promocion construye su payload a mano y
lo reconstruye a mano, y las dos copias se quedaron con la forma de antes:

    payload del claim: {... 'object_literal': None ...}
    ¿arrastra object_entity? False
    reconstruido: InvalidClaimObjectError

Es decir: un claim cuyo objeto es una entidad **no se puede promover**, y el
fallo sale en el proyecto DESTINO, que es el que nadie mira. No es un descuido
de un campo suelto: es que ese camino serializa a mano, y **cada campo nuevo se
rompe a mano**.

# LAS TRES PIEZAS, Y POR QUE SON TRES

    capability  ──produce──▶  ObservationEnvelope  ──normalizar──▶  ADTs
    (adaptador)                (forma, versionada)     (puro)        (Claim/Entity/Source)
                                                                          │
                                                                       ingesta
                                                                       (escribe)

El **envelope** es una frontera. El **normalizador** es una funcion. La
**ingesta** es el unico punto que toca la base. Si se mezclan, el normalizador
hereda el disco y deja de ser puro, y la prueba de «ingerir dos veces» deja de
poder hacerse sin abrir una base.

# POR QUE `observed_at` ENTRA EN EL ENVELOPE

Es la linea que hace posible la pureza. Si `normalizar` hiciera `now_iso()`, dos
normalizaciones del mismo envelope darian `checked_at_revision` distintas, el
`claim_id` saldría distinto —porque `make_claim_id` lo incluye en la semilla— y
la idempotencia **se romperia sola**, sin que nada lo indicara. El reloj lo pone
quien observa, y queda en el dato.

# EL DIVIDENDO REAL

El bug de P5 no se arregla «anadiendo `object_entity` al dict»: se arregla
haciendo que la promocion deje de interpretar un dict y pase a normalizar una
forma. A partir de ahi, un campo nuevo se anade en **un** sitio —la forma— y no
en cada camino de ingesta que serialice a mano. Eso es lo que hace que esa clase
de bug no tenga donde aparecer.

# UN LIMITE DECLARADO

**El envelope no se serializa a disco en este bloque.** Es una frontera en
memoria entre una capability y la ingesta. Persistir envelopes crudos —un
«outbox de observaciones»— necesita version **y** politica de reingesta, y eso
es B27/B29. Se dice ahora para que no se lea despues como un olvido.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, get_args

from skillgraph.core.errors import EnvelopeInvalido, UnknownEnvelopeVersionError
from skillgraph.core.runtime_types import SourceKind
from skillgraph.knowledge.graph import (
    Claim,
    ClaimID,
    Entity,
    EntityID,
    EntityRef,
    Source,
    SourceID,
    entity_id,
)
from skillgraph.knowledge.knowledge_controller import make_claim_id
from skillgraph.platform.ports.capabilities import CapabilitySpec

if TYPE_CHECKING:  # pragma: no cover - solo para el type-checker
    pass

__all__ = [
    "METODO_EXTERNO",
    "VERSION_ENVELOPE",
    "EnvelopeInvalido",
    "Observation",
    "ObservationEnvelope",
    "ObservationIngesta",
    "UnknownEnvelopeVersionError",
    "normalizar",
]

#: Version de la FORMA, no del contenido.
#:
#: Sin esto no se puede rechazar lo viejo: una herramienta que cambia su forma
#: de hablar sigue intentando escribir con el contrato anterior, y el fallo
#: aparece en el dato en vez de en la frontera. Va en el core y no en el
#: adaptador por el mismo motivo que `CAPABILITY_VERSION` — si viviera en cada
#: adapter, cada adapter podria inventar la suya y no habria nada que comparar.
VERSION_ENVELOPE: Final[str] = "sg.observation/1"

#: **B31.** El metodo que se le pone a una observacion que NO declara el suyo.
#:
#: Vive aqui y no escrito en `_claim_de` a pelo por el mismo motivo que
#: `VERSION_ENVELOPE`: si cada normalizador escribiera el suyo, dos copias de
#: la misma regla divergirian sin que nada las comparara — que es el
#: error que `REGLAS_DE_NOMBRE_SEGURO` ya sufrio una vez en este repo.
#:
#: Y no es un valor arbitrario: es lo que `normalizar` ha puesto SIEMPRE, y
#: por eso un envelope de B26 o de B33 sigue produciendo claims
#: identicos. Cambiarlo seria reescribir la procedencia de todo lo ya
#: ingerido, y `why` de B34 imprimiria otra historia para datos que no han
#: cambiado.
METODO_EXTERNO: Final[str] = "external_capability"


@dataclass(frozen=True, slots=True)
class Observation:
    """Una afirmacion de una herramienta: un predicado y SU objeto.

    **EL OBJETO ES EXACTAMENTE UNO: LITERAL O ENTIDAD.** Es la misma pregunta
    que hace `Claim` y que sostiene el CHECK de SQL, a proposito: si aqui se
    admitieran las dos formas o ninguna, el error apareceria tres capas mas
    abajo, en el dato, que es donde nadie lo mira.

    `None` deja de ser un literal valido. Se estrecha el dominio, y se puede:
    MEDIDO, nadie usaba `object_literal=None` antes de B25.
    """

    predicate: str
    object_literal: Any = None
    object_entity: EntityRef | None = None
    #: **B31.** Como se extrajo ESTA observacion, cuando no coincide con el
    #: resto del envelope.
    #:
    #: El metodo vive aqui y no en el envelope a proposito, y es la unica
    #: forma de que la respuesta sea verdad. MEDIDO sobre
    #: `extract_file_signatures` de un fichero real: el analizador produce
    #: **tres** metodos distintos —`line_count`, `regex_import`, `regex_def`—
    #: y los tres son ciertos para observaciones distintas del MISMO
    #: analisis. Un envelope con un unico metodo solo podria ser verdad para
    #: una de las tres, y las otras dos harian una afirmacion falsa.
    #:
    #: Y no es cosmetico, porque B34 construyo `why` para responder «¿de
    #: donde sale esto?». Sin este campo, preguntar por que se afirma
    #: `line_count = 502` responderia «vino de una capacidad externa», que
    #: es el rotulo que el nucleo pone a todo lo que cruza la frontera.
    #:
    #: `None` significa **exactamente** lo que significaba antes de B31: el
    #: envelope es de otro mundo y no se sabe de donde salio cada cosa. Los
    #: envelopes de B26 y B33 siguen produciendo los mismos claims.
    extraction_method: str | None = None

    def __post_init__(self) -> None:
        es_literal = self.object_literal is not None
        es_entidad = self.object_entity is not None
        if es_literal == es_entidad:
            raise EnvelopeInvalido(
                f"Observation {self.predicate!r} necesita exactamente un objeto: "
                + (
                    "llevo los dos (un literal y una entidad), y entonces no se sabe "
                    "cual de los dos es la verdad"
                    if es_literal
                    else "no llevo ninguno; una observacion sin objeto no observa nada"
                )
            )


@dataclass(frozen=True, slots=True)
class ObservationEnvelope:
    """Lo que devuelve una capability cuando ha observado algo. UNA FRONTERA.

    Inmutable (`frozen=True`, `slots=True`) porque cruza de un mundo al otro: lo
    produce un adaptador, que es codigo externo al repo, y lo consume la
    ingesta. Si pudiera cambiarse por el camino, la promesa de idempotencia
    seria una promesa sobre algo que cambio.

    `observed_at` ENTRA aqui y no se lee dentro. Ver la nota del modulo.

    El `version` tiene default a `VERSION_ENVELOPE` **a proposito**: la forma
    corriente es no escribirlo. Lo que se rechaza es lo que llega con una
    version DISTINTA, y eso lo comprueba `normalizar`, en la frontera.
    """

    producer: CapabilitySpec
    adapter: str
    source_id: SourceID
    subject: EntityID
    observed_at: str
    revision: str
    observations: tuple[Observation, ...]
    version: str = VERSION_ENVELOPE
    #: **B33 / `ADR-0034`.** Que clase de contenido trae este envelope.
    #: `None` significa **exactamente** lo que significaba antes de B33:
    #: `external_doc`. No se deduce de que traiga ventana, porque una
    #: medicion de test tambien cubre un periodo, y deducir el kind de la
    #: FORMA haria que `normalizar` publicara un kind distinto para el
    #: mismo tipo de observacion segun quien la mire.
    kind: SourceKind | None = None
    #: **B33.** Cuando empieza el periodo observado. Junto con
    #: `observed_to` forma la ventana; los dos a `None` = sin periodo.
    observed_from: str | None = None
    #: **B33.** Cuando termina. `None` = la ventana sigue abierta.
    observed_to: str | None = None

    def __post_init__(self) -> None:
        if not self.adapter or not self.adapter.strip():
            raise EnvelopeInvalido("ObservationEnvelope.adapter no puede estar vacio")
        if not self.observed_at or not self.observed_at.strip():
            raise EnvelopeInvalido(
                f"ObservationEnvelope de {self.subject!r} no trae observed_at: "
                "sin el instante que observa, la ingesta tendria que leer el reloj "
                "y la idempotencia se romperia sola"
            )
        if not self.revision or not self.revision.strip():
            raise EnvelopeInvalido(
                f"ObservationEnvelope de {self.subject!r} no trae revision: "
                "sin ella el claim_id no se puede derivar del contenido"
            )
        if not self.observations:
            raise EnvelopeInvalido(
                f"ObservationEnvelope de {self.subject!r} no trae observaciones: "
                "un envelope vacio se ingeria como no-op y parece que funciono"
            )
        self._valida_ventana()

    def _valida_ventana(self) -> None:
        """La ventana se valida AQUI y no solo en `normalizar`.

        **POR QUE EN LA FRONTERA Y NO EN EL NORMALIZADOR.** La version del
        envelope se comprueba en `normalizar` a proposito, porque un
        envelope con una version desconocida todavia se puede CONSTRUIR y
        guardar para poder mirarlo. Una ventana incoherente es otra cosa: es
        un dato que no significa nada, y construirlo solo para deshacerlo
        deja que un adaptor lo registre y se le avise con un envelope
        imposible en la mano. Se valida en el sitio donde se decide, que es
        donde el error se puede nombrar.

        El `kind` se valida contra el `Literal` aqui tambien por el mismo
        motivo: un kind inventado llegaria hasta la base, donde `Source` lo
        rechazaria con un mensaje que habla de `Source` cuando el que lo
        escribio estaba construyendo un envelope.
        """
        if self.observed_to is not None and self.observed_from is None:
            raise EnvelopeInvalido(
                f"ObservationEnvelope de {self.subject!r} declara observed_to="
                f"{self.observed_to!r} sin observed_from: no se puede cerrar un "
                "periodo que no empezo"
            )
        if self.kind is not None and self.kind not in get_args(SourceKind):
            raise EnvelopeInvalido(
                f"ObservationEnvelope de {self.subject!r} declara kind={self.kind!r}, "
                f"que no es del vocabulario SourceKind {sorted(get_args(SourceKind))}"
            )


@dataclass(frozen=True, slots=True)
class ObservationIngesta:
    """Lo que el normalizador produce: ADTs, sin haber tocado nada.

    Es un **valor**: la misma entrada produce el mismo valor, y por eso el
    `claim_id` —que se deriva del contenido— sale igual en cada llamada. Es la
    razon de que la idempotencia de `ingerir` no dependa de la base.
    """

    source: Source
    entity: Entity
    claims: tuple[Claim, ...]
    #: B27. Los `claim_id` cuyo INSERT fue rechazado por el `UNIQUE` de la
    #: tupla natural, en orden de aparicion. **VACIO cuando la ingesta fue
    #: limpia**, y eso incluye reingerir lo mismo, que es idempotencia y no
    #: conflicto —por eso es una tupla y no un contador-.
    conflictos: tuple[ClaimID, ...] = ()

    @property
    def claim_ids(self) -> tuple[ClaimID, ...]:
        """Los ids derivados, en orden de observacion."""
        return tuple(c.claim_id for c in self.claims)


def normalizar(env: ObservationEnvelope) -> ObservationIngesta:
    """``ObservationEnvelope`` -> ADTs. **PURA**: ni disco, ni reloj, ni entrada.

    Todo lo que necesita entra por el envelope —el reloj incluido, en
    `observed_at`— y por eso dos llamadas seguidas con el mismo envelope dan el
    mismo `claim_id`. Un normalizador que leyera el reloj haria que la misma
    observacion produjera dos filas distintas cada vez que se reingiere, y la
    idempotencia **se romperia sola, sin que nada lo indicara**.

    La version se comprueba **aqui** y no en `__post_init__` a proposito:
    `__post_init__` rechaza una Observation sin objeto porque no hay forma de
    seguir, pero una version desconocida si se puede construir —el dataclass es
    valido, lo que no se entiende es lo que dice— y rechazarla al construir
    impediria medir a un adapter guardar y reportar el envelope que produjo.
    La frontera de la version es la puerta de entrada del dato, no su
    constructor.

    Args:
        env: el envelope a normalizar. No se muta.

    Returns:
        La ingesta de ADTs, lista para persistir o para inspeccionar.

    Raises:
        UnknownEnvelopeVersionError: si `env.version` no es la que este sistema
            entiende. El mensaje dice cual se esperaba.
    """
    if env.version != VERSION_ENVELOPE:
        raise UnknownEnvelopeVersionError(
            f"envelope de {env.producer.type_name!r} con version {env.version!r}; "
            f"este sistema entiende {VERSION_ENVELOPE!r}. Actualiza la herramienta "
            f"o baja el envelope a esa version: aceptarlo 'con lo que haya' perderia "
            f"el dato en silencio."
        )

    source = Source(
        source_id=env.source_id,
        # B26 fijaba aqui `external_doc` para toda observacion externa, y lo
        # justificaba en el propio codigo: `SourceKind` es un Literal cerrado
        # y AGENTS.md 2.1 pedia una ADR antes de anadir un valor. ESA ADR NO
        # SE ABRIO HASTA B33 (ADR-0034), y mientras tanto toda observacion
        # de runtime se guardaba como documento externo, que no es lo que es.
        #
        # MEDIDO antes de decidir, no supuesto:
        #   adr:0001           kind=external_doc
        #   runtime:ventana-1  kind=external_doc    <- indistinguibles
        #   json_extract(locator_json, '$.producer') funciona, pero sin indice
        #   y `sources` no tiene columna producer, ni adapter, ni type_name
        #
        # Ahora el kind lo DECLARA el envelope. `None` es `external_doc`, que
        # es lo que significaba antes: los adaptadores que ya escribian
        # envelopes siguen produciendo exactamente lo mismo.
        kind=env.kind if env.kind is not None else "external_doc",
        content_hash=env.revision,
        locator={
            "adapter": env.adapter,
            "producer": env.producer.type_name,
            "producer_version": env.producer.version,
        },
        git_commit_sha=None,
        git_tree_sha=None,
        working_tree_status=None,
        checked_at=env.observed_at,
        freshness="current",
        observed_from=env.observed_from,
        observed_to=env.observed_to,
    )
    entity = Entity(
        entity_id=entity_id(env.subject),
        kind="observed",
        stable_key=env.subject,
    )
    return ObservationIngesta(
        source=source,
        entity=entity,
        claims=tuple(_claim_de(o, env) for o in env.observations),
    )


def _claim_de(obs: Observation, env: ObservationEnvelope) -> Claim:
    """Un `Observation` mas su envelope -> un `Claim`.

    El `claim_id` sale de `make_claim_id`, que ya es UUIDv5 sobre
    `(subject, predicate, source, revision)`. Es determinista, y por eso la
    idempotencia sale del **contenido** y no de un contador.

    `extraction_method` no es `static_analysis` a proposito: el valor por
    defecto describe como extrae EL CORE, y esto lo observo una herramienta
    externa. Dejar el default seria decir «lo dijo el nucleo» de algo que dijo
    fuera, que es la perdida de provenance que el gate B6 prohibe.

    **B31.** Y aqui hay una salvedad que el default resuelve solo: el metodo
    se escribe a pelo unicamente cuando la observacion NO lo trae. Una
    observacion de este repo que se extrajo con un regex declara su metodo en
    `Observation.extraction_method`, y entonces el claim lo dice. Lo que no
    se puede es al reves: no hay forma de que una observacion afirme como se
    extrajo y el envelope lo sustituya por su categoria.

    `extractor_version` lleva la identidad del productor porque es lo que
    permite despues responder «¿quien afirmo esto?» — la pregunta que el
    `producer` del envelope trae justamente para eso.
    """
    return Claim(
        claim_id=make_claim_id(
            subject_entity_id=entity_id(env.subject),
            predicate=obs.predicate,
            source_id=env.source_id,
            checked_at_revision=env.revision,
            # **B31.** Sin estos dos, dos observaciones del MISMO predicado
            # en el MISMO envelope salen con el mismo `claim_id` y la segunda
            # choca con la PRIMARY KEY.
            #
            # MEDIDO: es exactamente lo que pasa si se omiten, y no se ve
            # mirando el codigo —se ve mirando el UNIQUE de la tabla, que si
            # lleva el objeto, y las filas, que no—. El `UNIQUE` estaba
            # arreglado y seguian perdiendose 2 de 7: el motor rechazaba la
            # segunda por `claim_id`, no por la tupla natural.
            object_literal=obs.object_literal,
            object_entity=obs.object_entity,
        ),
        subject_entity_id=entity_id(env.subject),
        predicate=obs.predicate,
        object_literal=obs.object_literal,
        source_id=env.source_id,
        object_entity=obs.object_entity,
        extraction_method=obs.extraction_method or METODO_EXTERNO,
        extractor_version=f"{env.producer.type_name}@{env.producer.version}",
        assertion_origin="observed",
        checked_at_revision=env.revision,
    )
