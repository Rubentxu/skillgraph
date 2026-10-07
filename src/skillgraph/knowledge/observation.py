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
    entity_ref,
    source_id,
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
    "envelope_a_payload",
    "envelope_de_payload",
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
    #:
    #: **B35: POR QUE ESTE CAMPO NO TIENE PRODUCTOR, MEDIDO.** Aqui vivia la
    #: advertencia de que una ingesta habia encontrado un conflicto. MEDIDO al
    #: certify B35: `normalizar` —la unica via que construye este valor— deriva
    #: el `claim_id` de (sujeto, predicado, objeto, fuente, revision), luego dos
    #: claims distintos tienen id distinto y **ningun `UNIQUE` puede rechazarlos**.
    #: El aviso solo puede aparecer cuando quien construye el `Claim` a mano
    #: reutiliza un `claim_id` con otro valor, y esa via es la **promocion**,
    #: que no pasa por aqui: recoge su propio aviso en
    #: `cli/commands/promotion.py`.
    #:
    #: El campo **se queda** por dos razones, y no por pereza: `normalizar` es
    #: puro y no puede saber nada de la base, luego un campo de resultado de
    #: escritura en un valor de modelo ya era una categoria equivocada; y
    #: quitarlo seria romper un contrato publico sin ganar nada measurable. Lo
    #: que se quito fue el PRODUCTOR, que era codigo muerto.
    conflictos: tuple[ClaimID, ...] = ()

    @property
    def claim_ids(self) -> tuple[ClaimID, ...]:
        """Los ids derivados, en orden de observacion."""
        return tuple(c.claim_id for c in self.claims)


# ---------------------------------------------------------------------------
# B35 — el contrato de frontera, en las dos direcciones
# ---------------------------------------------------------------------------
#
# MEDIDO antes de escribir esto (`scripts/measure_b35_vertical.py`):
#
#   serializadores en src/ : 2 definiciones de `envelope_a_payload` para 1
#                            nombre —`code_analysis` y `telemetry_query`— y
#                            EJECUTADOS sobre el mismo envelope dan claves
#                            distintas y `observations` con forma distinta
#                            (`list` una, `tuple` la otra).
#   deserializadores       : 0 en `src/`.
#
# Y el inverso no es que faltara por descuido: **estaba escrito a mano en dos
# ficheros de test** (`test_b31::envelope_real` y `test_b33::_envelope_de`),
# porque `ingerir(...)` exige un `ObservationEnvelope` y la capability
# devuelve un `dict`. Dos copias que ya habian divergido: una leia el
# `producer` del payload y la otra `cap.spec` de la capability.
#
# Por eso el par vive AQUI, junto al ADT que define el contrato, y no en cada
# capability. Un contrato de frontera con dos serializadores y ningun
# deserializador no es un contrato: son tres piezas que nadie sostengo juntas.


def envelope_a_payload(envelope: ObservationEnvelope) -> dict[str, Any]:
    """``ObservationEnvelope`` -> el `dict` que viaja por `CapabilityResult`.

    **UNA sola implementacion, y es la que usan todas las capabilities.**
    MEDIDO: `code_analysis` y `telemetry_query` tenian cada una la suya, con el
    mismo nombre, y no hacian lo mismo — una anadia `vocabulario` y
    devolvia `observations` como `list`, la otra era `asdict` a pelo y la
    devolvia como `tuple`. Dos funciones homonimas con contratos distintos no
    son una redundancia: son una decision que ya se tomo dos veces y al reves.

    `object_entity` se serializa a texto porque es un `EntityRef` (que en
    runtime es `str`) y un `dict` que no sabe convertirlo revienta con un
    `TypeError` en lugar de perder el dato en silencio.

    Args:
        envelope: lo que produce la capability.

    Returns:
        Un `dict` JSON-compatible. Las `observations` son SIEMPRE una `tuple`
        de `dict`, en ese orden, para que la ida y la vuelta sean un
       emparejamiento posicional y no dependa del orden de las claves.
    """
    return {
        "producer": {
            "type_name": envelope.producer.type_name,
            # **LA `version` DEL SPEC, MEDIDO.** `CapabilitySpec` tiene tres
            # campos y esta es la que se perdia: el `UNIQUE` de `CapabilityRegistry`
            # es `(type_name, version)`, luego un payload que la tira permite
            # registrar dos adapters que se solapan sin que nada lo diga.
            "version": envelope.producer.version,
            "summary": envelope.producer.summary,
        },
        "adapter": envelope.adapter,
        "source_id": str(envelope.source_id),
        "subject": str(envelope.subject),
        "observed_at": envelope.observed_at,
        "revision": envelope.revision,
        "version": envelope.version,
        "kind": envelope.kind,
        "observed_from": envelope.observed_from,
        "observed_to": envelope.observed_to,
        "observations": tuple(
            {
                "predicate": o.predicate,
                "object_literal": o.object_literal,
                # **NO `str(o.object_entity)`, MEDIDO.** `EntityRef` es un
                # dataclass, no un `NewType` sobre `str`: `str()` de el da su
                # `repr` —`EntityRef(entity_id='module:os')`—, y un round-trip
                # que degrada a `str` se nota, que es justo lo que el docstring
                # de `EntityRef` (B25) escribe al principio. Lo que viaja es
                # el `entity_id` de dentro, que si es un `EntityID`.
                "object_entity": None
                if o.object_entity is None
                else str(o.object_entity.entity_id),
                "extraction_method": o.extraction_method,
            }
            for o in envelope.observations
        ),
    }


def envelope_de_payload(payload: dict[str, Any]) -> ObservationEnvelope:
    """El `dict` del payload -> ``ObservationEnvelope``. El camino de vuelta.

    **POR QUE ESTA EN `src/` Y NO EN LOS TESTS.** Porque es la mitad que
    faltaba de un contrato, y estaba en los tests. `ingerir(...)` pide un
    `ObservationEnvelope`; una capability devuelve un `dict`; el paso entre
    ellos no existia en produccion y estaba escrito a mano en dos ficheros de
    test —que ya divergian, porque una copiaba el `producer` del payload y la
    otra lo tomaba de la capability—. Una copia que lee el `producer` de la
    capability **no comprueba la ida y la vuelta**: comprueba que la capability
    sepa su propio nombre.

    **SE VALIDA CON LOS MISMOS ADTs, NO A MANO.** Se reconstruye por los
    constructores —`ObservationEnvelope` y `Observation` validan en
    `__post_init__`— y no con `ObservationEnvelope(**payload)`, porque el
    `producer` llega como `dict` y el dataclass quiere un `CapabilitySpec`, y
    porque las observaciones llegan como `dict` y quieren `Observation`. El
    error de un payload mal formado sale de aqui, con el mensaje del dominio, y
    no de un `TypeError` tres capas mas abajo, en el dato.

    Args:
        payload: lo que devuelve `CapabilityResult.payload["envelope"]`.

    Returns:
        El envelope, validado por sus propios constructores.

    Raises:
        EnvelopeInvalido: si el payload no trae las claves que el contrato
            exige, o si lo que trae no puede ser un envelope valido. Es un
            error de dominio y por tanto lleva `code` y se traduce a exit code.
    """
    if not isinstance(payload, dict):
        raise EnvelopeInvalido(
            f"envelope_de_payload espera un dict y recibio {type(payload).__name__}"
        )

    faltantes = [c for c in _CLAVES_OBLIGATORIAS if c not in payload]
    if faltantes:
        raise EnvelopeInvalido(
            f"el payload del envelope no trae {faltantes}; el contrato es "
            f"{sorted(_CLAVES_OBLIGATORIAS)} y lo que llega es {sorted(payload)}"
        )

    productor = payload["producer"]
    if (
        not isinstance(productor, dict)
        or "type_name" not in productor
        or "version" not in productor
    ):
        raise EnvelopeInvalido(
            f"envelope_de_payload: 'producer' tiene que ser el dict con "
            f"'type_name', 'version' y 'summary', y es {productor!r}. Un "
            f"CapabilitySpec serializado es justamente eso, y si no lo es el "
            f"payload no lo produjo envelope_a_payload"
        )

    return ObservationEnvelope(
        producer=CapabilitySpec(
            type_name=str(productor["type_name"]),
            version=str(productor["version"]),
            summary=str(productor.get("summary", "")),
        ),
        adapter=str(payload["adapter"]),
        source_id=source_id(str(payload["source_id"])),
        subject=entity_id(str(payload["subject"])),
        observed_at=str(payload["observed_at"]),
        revision=str(payload["revision"]),
        observations=tuple(
            _observacion_de(o, indice=i) for i, o in enumerate(payload["observations"])
        ),
        version=str(payload["version"]),
        kind=payload["kind"],
        observed_from=payload["observed_from"],
        observed_to=payload["observed_to"],
    )


#: Lo que un payload de envelope NO puede no traer. Se declara una vez y lo
#: usan `envelope_de_payload` y su test, para que anadir un campo al ADT no
#: obligue a descubrir en produccion que nadie lo serializa.
_CLAVES_OBLIGATORIAS: Final[frozenset[str]] = frozenset(
    {
        "producer",
        "adapter",
        "source_id",
        "subject",
        "observed_at",
        "revision",
        "version",
        "kind",
        "observed_from",
        "observed_to",
        "observations",
    }
)


def _observacion_de(dato: Any, *, indice: int) -> Observation:
    """Una observacion del payload, validada por su propio constructor.

    `object_entity` vuelve como texto o como `None`, y se pasa por
    `entity_ref` para que `Observation` lo valide igual que si hubiera
    llegado entero. MEDIDO: la copia de B31 en los tests solo pasaba
    `object_literal` y se comia el `object_entity` en silencio —que es el
    mismo defecto que el bug latente de B31 en la reconstruccion del
    `Claim`, y por la misma razon: una copia de una regla la aplica cuando le
    place y calla cuando no.

    **Y LA AUSENCIA NO ES EL `None`, QUE ES LO QUE CUESTA MEDIRLO.** El
    `extraction_method` distingue tres cosas que a primera vista son dos:

    ```
    clave AUSENTE            -> METODO_EXTERNO   (el que no sabe de si mismo)
    clave presente, None     -> None             (y se conserva)
    clave presente, "regex"  -> "regex"
    ```

    MEDIDO: con `dato.get("extraction_method") or METODO_EXTERNO` la ida y la
    vuelta NO era identidad — un envelope con `extraction_method=None` volvia
    con `METODO_EXTERNO`—, porque `None` significa «metodo externo» pero no es
    la misma cadena. Los dos son certainos para el `claim_id`, y aun asi un
    test que compruebe `ida_y_vuelta == env` falla, y rightly: la propiedad que
    ese test afirma es la IDENTIDAD, y `None` no es `'external_capability'`.

    La distinction que si importa es la de una clave que no viene —que es un
    adaptador viejo, o uno que no conoce el campo de B31— frente a una clave
    que viene con `None`. La primera se rellena; la segunda se respeta.
    """
    if not isinstance(dato, dict):
        raise EnvelopeInvalido(
            f"envelope_de_payload: observations[{indice}] tiene que ser un dict "
            f"y es {type(dato).__name__}"
        )
    entidad = dato.get("object_entity")
    # `.get(k, POR_DEFECTO)` devuelve el defecto solo si la clave NO ESTA. Una
    # clave presente con valor `None` devuelve `None`, que es lo que hay que
    # conservar. Un `or` no sirve aqui: `None or X` es `X`, y con literales
    # `False` y `0` pasaria lo mismo con el objeto.
    metodo = dato.get("extraction_method", METODO_EXTERNO)
    return Observation(
        predicate=str(dato["predicate"]),
        object_literal=dato.get("object_literal"),
        object_entity=None if entidad is None else entity_ref(str(entidad)),
        extraction_method=None if metodo is None else str(metodo),
    )


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
