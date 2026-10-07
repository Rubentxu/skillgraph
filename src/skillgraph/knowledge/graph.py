"""Modelo de conocimiento H3 (Slice 1).

Doc externo:
  external/blueprint-v1/docs/08-conocimiento-y-contexto.md
  external/blueprint-v1/adr/ADR-0007-conocimiento-vinculado-a-fuentes.md

Este modulo define los ADT **inmutables** que representan las entidades
del subsistema de conocimiento:

- `Source`      Una unidad de contenido identificable (commit, archivo, doc).
- `Entity`      Algo sobre lo que se afirma (file, function, module, ...).
- `Evidence`    Un dato observable extraido de una Source.
- `Claim`       Una afirmacion sobre una Entity, sostenida por Evidences.
- `Finding`     Resultado de aplicar una regla a una Entity.
- `OutcomeTrace` Un recorrido verificable que enlaza Claims y Evidences.

Por que frozen + slots:
- `frozen=True`  garantiza que una vez emitido un Claim, su contenido
  no cambia. Es la base de la trazabilidad.
- `slots=True`   elimina `__dict__` y rechaza atributos no declarados;
  detecta typos en tests antes de que se propaguen a SQL.

Por que smart constructors:
- `SourceID("")` debe fallar rapido, no propagar una ID vacia hasta el
  momento del INSERT.
- `EntityID("foo.py")` sin prefijo `kind:` es ambiguo en el catalogo;
  lo rechazamos al cruzar el limite del modulo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, NewType

from skillgraph.core.errors import (
    InvalidAssertionOriginError,
    InvalidClaimObjectError,
    InvalidEntityIDError,
    InvalidSourceError,
    InvalidSourceIDError,
)
from skillgraph.core.runtime_types import (
    ASSERTION_ORIGINS,
    CLAIM_PREDICATES,
    AssertionOrigin,
    ClaimPredicate,
    FindingResult,
    FreshnessState,
    PredicadoDePack,
    RuleRef,
    SourceKind,
    TraceKind,
    predicado_de_pack,
)

# --- Identificadores nominales (NewType sobre str) -----------------------
#
# NewType no afecta runtime (siguen siendo str), pero el type-checker
# trata `SourceID` y `EntityID` como tipos incompatibles. Asi, pasar un
# `EntityID` donde se espera `SourceID` falla en `mypy` sin afectar
# serializacion JSON ni queries SQL.

SourceID = NewType("SourceID", str)
"""Identificador unico de una Source. Formato libre, no vacio."""

EntityID = NewType("EntityID", str)
"""Identificador unico de una Entity. Formato obligatorio `kind:key`."""

ClaimID = NewType("ClaimID", str)
"""Identificador unico de una Claim (UUIDv5 derivado del contenido)."""

EvidenceID = NewType("EvidenceID", str)
"""Identificador unico de una Evidence (UUIDv5 sobre source_id+content)."""

FindingID = NewType("FindingID", str)
"""Identificador unico de un Finding."""

TraceID = NewType("TraceID", str)
"""Identificador unico de un OutcomeTrace."""


# --- Smart constructors ---------------------------------------------------
#
# Validan los invariantes de formato en el limite del modulo, NO dentro
# de Storage. Asi, si alguien crea un `Source` con un ID vacio pero no
# lo persiste, el error ya esta capturado.


def source_id(raw: str) -> SourceID:
    """Smart constructor para SourceID: rechaza vacios."""
    if not raw or not raw.strip():
        raise InvalidSourceIDError("source_id no puede estar vacio")
    return SourceID(raw.strip())


def entity_id(raw: str) -> EntityID:
    """Smart constructor para EntityID: exige formato `kind:key`."""
    if not raw or ":" not in raw:
        raise InvalidEntityIDError(f"entity_id debe tener formato 'kind:key' (recibido {raw!r})")
    return EntityID(raw)


def entity_ref(raw: str) -> EntityRef:
    """Smart constructor para EntityRef: delega en `entity_id`.

    **POR QUE NO DUPLICA EL FORMATO.** Un `EntityRef` **es** una `EntityID`,
    asi que la validacion del `kind:key` ya existe y ya tiene su error. Copiarla
    aqui seria una segunda version de la misma regla, que divergiria el dia que
    cambie la de `entity_id` — y divergiria en silencio, porque las dos seguirian
    dando verde por separado.

    Un constructor por `NewType`, que es lo que pide `AGENTS.md` §2.3.
    """
    return EntityRef(entity_id(raw))


# --- ADT inmutables -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Source:
    """Una unidad de contenido de la que se extrae evidencia.

    El `content_hash` identifica el contenido (e.g. SHA-256 para un
    commit Git, sha256 de bytes para un archivo, URL+timestamp para
    external_doc). Si el contenido cambia, se crea una Source nueva
    con `source_id` distinto.

    Invariantes (validados en `__post_init__`):
    - `content_hash` no vacio.
    - Si `kind` empieza por `git_`, entonces `git_commit_sha` obligatorio.
    """

    source_id: SourceID
    kind: SourceKind
    content_hash: str
    locator: dict[str, Any]
    git_commit_sha: str | None
    git_tree_sha: str | None
    working_tree_status: dict[str, Any] | None
    checked_at: str  # ISO-8601 UTC
    freshness: FreshnessState

    def __post_init__(self) -> None:
        if not self.content_hash:
            raise InvalidSourceError("content_hash no puede estar vacio")
        # Validar kind contra el Literal SourceKind. El Literal NO se
        # valida en runtime por `from __future__ import annotations`,
        # asi que usamos typing.get_args sobre el tipo ya importado.
        import typing

        valid_kinds = typing.get_args(SourceKind)
        if self.kind not in valid_kinds:
            raise InvalidSourceError(
                f"Source kind={self.kind!r} invalido. Valores permitidos: {sorted(valid_kinds)}"
            )
        if self.kind.startswith("git_") and not self.git_commit_sha:
            raise InvalidSourceError(
                f"Source {self.source_id!r} kind={self.kind} requiere git_commit_sha"
            )


@dataclass(frozen=True, slots=True)
class Entity:
    """Algo sobre lo que se afirma algo (Claim) o se aplica una regla (Finding).

    `kind` describe el tipo (file, function, module, contract, ...).
    `stable_key` es un identificador estable (path relativo o qualified name).
    """

    entity_id: EntityID
    kind: str
    stable_key: str


@dataclass(frozen=True, slots=True)
class Evidence:
    """Un dato observable extraido de una Source.

    `content` puede ser `dict[str, Any]` (e.g. metricas) o `str`
    (e.g. snippet de codigo). La serializacion a SQL lo trata siempre
    como JSON.
    """

    evidence_id: EvidenceID
    kind: str  # "metric" | "snippet" | "log_line" | "commit_message"
    content: dict[str, Any] | str
    source_id: SourceID
    observed_at: str  # ISO-8601 o commit SHA


@dataclass(frozen=True, slots=True)
class EntityRef:
    """Una referencia a otra Entity, usada como OBJETO de un Claim.

    **POR QUE UN TIPO Y NO UNA CADENA.** Antes de B25, `Claim.object_literal`
    era `Any`, luego cualquier cadena era un literal legitimo y el sistema no
    tenia forma de decir si una de ellas apuntaba a algo. Eso se midio: dos
    claims cuyo objeto era `str` en los dos casos, y el sistema incapaz de
    distinguirlos.

    Escalar a tipo es lo que hace que la pregunta del bloque —«¿lo diferencia?»—
    tenga respuesta. `EntityRef` NO es igual a la cadena que lleva dentro, que
    es justo por lo que un round-trip que degrade a `str` se nota.
    """

    entity_id: EntityID


@dataclass(frozen=True, slots=True)
class Claim:
    """Afirmacion verificable sobre una Entity, sostenida por Evidences.

    La unicidad en BD es por
    `(subject_entity_id, predicate, source_id, checked_at_revision)`,
    asi que el mismo Claim se puede re-registrar bajo una nueva
    `checked_at_revision` para representar la evolucion historica.

    **EL OBJETO ES EXACTAMENTE UNO: LITERAL O ENTIDAD (B25).** Antes era solo
    literal, y por eso no se podia expresar «A usa B». Ahora el campo nuevo
    `object_entity` es la puerta, y la invariante es que las dos no se puedan
    usar a la vez ni dejar las dos fuera.

    `object_literal` pasa a `Any = None`, y `None` deja de ser un literal
    valido: es lo que significa «el objeto no es un literal, mira
    `object_entity`». Se estrecha el dominio legal, y se puede: MEDIDO, nadie
    usaba `object_literal=None` antes de este cambio.
    """

    claim_id: ClaimID
    subject_entity_id: EntityID
    predicate: ClaimPredicate | PredicadoDePack
    #: Sin default **a proposito**. En cuanto `object_literal` deja de ser
    #: obligatorio —porque `None` pasa a significar «el objeto es la entidad»—
    #: todos los campos de despues tendrian que llevar default, y `source_id`
    #: acabaria siendo opcional. Prefiero que quien afirma sin fuente lo pase
    #: explicito: un claim sin fuente es un claim sin respaldo, y que el
    #: constructor lo admita es una forma de no notarlo.
    object_literal: Any
    source_id: SourceID
    evidence_ids: tuple[EvidenceID, ...] = field(default_factory=tuple)
    extraction_method: str = "static_analysis"
    extractor_version: str = "skillgraph/0.1.0"
    #: Quien afirma, no COMO se extrajo (gate B6). Eje DISTINTO de
    #: `extraction_method` y deliberadamente aparte: ver la nota larga de
    #: `AssertionOrigin` en `core/runtime_types.py`. El default es
    #: `observed` porque es el unico origen que no promete autoridad.
    assertion_origin: AssertionOrigin = "observed"
    checked_at_revision: str = ""
    stale: bool = False
    #: B25. Va **al final** a proposito: los campos siguientes ya tienen
    #: default, y anadirlo aqui mantiene intacta la compatibilidad posicional
    #: de los cinco anteriores. Un campo nuevo en medio habria hecho que
    #: `Claim("id", "sujeto", "line_count", 42, "src")` —posicional, como
    #: aparece en codigo existente— empezara a meter `source_id` en este.
    object_entity: EntityRef | None = None
    # --- B29: VENTANA DE VIGENCIA. Los tres AL FINAL, por el mismo motivo. ---
    #: **VALID time**, y NO es `checked_at_revision`. Aquel dice cuando lo
    #: VIMOS; este dice cuando el hecho ERA CIERTO. Son los dos ejes de
    #: `06-SPEC` §1, y confundirlos no era una falta de estilo: era no tener
    #: un eje con el que comparar, luego no poder distinguir «cambio» de
    #: «contradiccion». MEDIDO: sin esto, dos filas de la MISMA fuente en
    #: revisiones consecutivas daban un conflicto, y `resolver` contestaba
    #: «gana NADIE» a algo que si tiene respuesta en cada instante.
    #:
    #: `None` = «no caduca». Es el valor del grafo que ya existia y es el
    #: correcto por defecto: una afirmacion no caduca por no saber cuando.
    valid_from_revision: str | None = None
    valid_until_revision: str | None = None
    #: La cadena de supersesion: que afirmacion **reemplazo** a cual.
    #:
    #: MEDIDO antes del bloque: NO existia ninguna columna ni funcion que
    #: dijera que `c-B` sustituyo a `c-A`. Habia dos filas con dos revisiones,
    #: y nada mas; podrian ser un cambio o dos herramientas discrepantes, y no
    #: habia forma de saberlo.
    supersedes_claim_id: ClaimID | None = None

    def __post_init__(self) -> None:
        # B25: un predicado del nucleo o un predicado de pack. El conjunto de
        # siete NO crece; lo que se abre es la forma. Un string sin punto no
        # es de ninguno de los dos y se sigue rechazando, que es lo que hace
        # que `test_claim_unknown_predicate_raises` siga verde.
        if self.predicate not in CLAIM_PREDICATES:
            predicado_de_pack(self.predicate)

        # B25: exactamente uno de los dos objetos. Se comprueba con la MISMA
        # pregunta que la base (un XOR), para que las dos capas no puedan
        # discrepar: si aqui se invirtiera el criterio, la base rechazaria
        # filas que Python acepta y el fallo apareceria en el sitio mas caro.
        es_literal = self.object_literal is not None
        es_entidad = self.object_entity is not None
        if es_literal == es_entidad:
            raise InvalidClaimObjectError(
                f"Claim {self.claim_id!r} necesita exactamente un objeto: "
                + (
                    "llevo los dos (un literal y una entidad), y entonces no se sabe "
                    "cual de los dos es la verdad"
                    if es_literal
                    else "no llevo ninguno; un claim tiene que afirmar algo"
                )
            )

        # B29: un claim no puede supersederse a si mismo. Es la unica
        # invariante de la supersesion que se puede comprobar aqui, y se
        # comprueba porque el bucle que la recorre en `claims_at_revision` no
        # tiene por donde defenderse: entraria en un ciclo infinito.
        if self.supersedes_claim_id == self.claim_id:
            raise InvalidClaimObjectError(
                f"Claim {self.claim_id!r} se supersede a si mismo: una cadena de "
                "supersesion con un ciclo no se puede recorrer"
            )

        if self.assertion_origin not in ASSERTION_ORIGINS:
            raise InvalidAssertionOriginError(
                f"assertion_origin {self.assertion_origin!r} fuera de {sorted(ASSERTION_ORIGINS)}"
            )


@dataclass(frozen=True, slots=True)
class Finding:
    """Resultado de aplicar una regla a una Entity.

    `valid_until_revision` opcional: si el siguiente commit invalida
    la regla, el Finding queda como `inconclusive` por diseno del
    KnowledgeController (slice 2).
    """

    finding_id: FindingID
    entity_id: EntityID
    observation: str
    rule_ref: RuleRef
    rule_version: str
    evidence_ids: tuple[EvidenceID, ...]
    result: FindingResult
    valid_until_revision: str | None


@dataclass(frozen=True, slots=True)
class OutcomeTrace:
    """Recorrido verificable: enlaza Claims y Evidences en orden.

    Por diseno NO duplica contenido: solo almacena referencias (ver
    blueprint §9). El lector (humano o agente) reconstruye el contenido
    desde los IDs via Storage.
    """

    trace_id: TraceID
    kind: TraceKind
    name: str
    project_id: str
    created_at: str
    claim_refs: tuple[ClaimID, ...] = field(default_factory=tuple)
    evidence_refs: tuple[EvidenceID, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ClaimRecorded:
    """Lo que `record_claim` devuelve: **el claim_id y si colisiono**.

    **POR QUE NO ES UN `str`.** Antes `record_claim` devolvia el `claim_id` que
    se le habia dado, y con `INSERT OR IGNORE` eso miente: el `UNIQUE` de
    `(subject_entity_id, predicate, source_id, checked_at_revision)` puede
    rechazar el INSERT y el metodo devuelve igual, como si hubiera escrito.

    MEDIDO en B27: dos afirmaciones opuestas con la MISMA fuente y la MISMA
    revision dejan **una** fila —la primera— y quien escribe cree haber
    registrado la suya. No se pierde una fila: se pierde **la verdad de lo que
    se afirmo**, en silencio.

    **`valor_previo` Y `valor_intento`, POR QUE LOS DOS.** Un aviso de
    «conflicto» sin los dos valores no es accionable: quien lo recibe no sabe si
    lo que se solapa es `true` o `false`, y el aviso se vuelve un «algo va mal»
    sin poder hacer nada con el.
    """

    claim_id: ClaimID
    conflicto: bool
    valor_previo: Any = None
    valor_intento: Any = None


@dataclass(frozen=True, slots=True)
class Conflicto:
    """Dos o mas afirmaciones sobre lo MISMO que dicen cosas DISTINTAS.

    **UN CONFLICTO ES UN GRUPO, NO UN PAR.** Tres afirmaciones que se
    contradicen son un conflicto con tres afirmaciones, no tres conflictos. Sin
    agrupar, «cuantas contradicciones hay» seria el numero de claims y no el de
    contradicciones —dos grupos de tres darian seis— y quien lo leyera contaria
    algo que no es lo que cree.

    **`afirmaciones` es ORDENADO Y ESTABLE**, y es la propiedad que hace posible
    B28. Un conflict set que dependa del orden en que SQLite devuelva las filas
    no es un conflict set: es el estado de un `SELECT` sin `ORDER BY`. Dos
    consultas iguales darian listas distintas y cualquier consumidor que las
    comparara fallaria de forma intermitente —que es la forma mas cara de
    fallar, porque no falla en la prueba que lo escribio.
    """

    subject_entity_id: EntityID
    predicate: str
    afirmaciones: tuple[Claim, ...]

    @property
    def claim_ids(self) -> tuple[ClaimID, ...]:
        """Los ids, en el mismo orden estable que `afirmaciones`."""
        return tuple(c.claim_id for c in self.afirmaciones)


def vigente_en(
    desde: int | None,
    hasta: int | None,
    seq: int,
) -> bool:
    """¿El hecho era cierto en la posicion `seq` de la historia?

    **ES PURA A PROPOSITO, Y POR ESO VIVE AQUI Y NO EN EL REPOSITORIO.** La
    ventana es un intervalo, y un intervalo necesita un orden; el orden vive en
    `revision_registro`, que es una tabla. Si la comparacion viviera alli, no se
    podria probar sin abrir un SQLite, y una regla de intervalo sin tests
    unitarios es una regla que se rompe en silencio.

    Args:
        desde: `seq` de `valid_from_revision`, o `None` si no caduca por abajo.
        hasta: `seq` de `valid_until_revision`, o `None` si sigue vigente.
        seq: la posicion que se pregunta.

    Returns:
        `True` si el hecho era cierto en `seq`. **Cerrada por abajo, ABIERTA
        por arriba**: una ventana es `[desde, hasta)`.

        **Y LA SEMANTICA DEL EXTREMO SUPERIOR ESTA MEDIDA, NO ADOPTADA.** La
        primera version de este bloque hizo la ventana **cerrada por los dos
        lados**, y entonces en `revB` el claim viejo seguia vigente y la
        consulta por revision devolvia `['c-A', 'c-B']` — las dos
        afirmaciones, que es justo la respuesta que B29 viene a eliminar.

        Lo que lo decide es el gate de `06-SPEC` §9, escrito por el bloque:

            commit A: A -> calls B        commit B: A -> calls C
            at(A) -> calls B             at(B)  -> calls C

        En `revB` la respuesta es `calls C`, y **no** las dos. Si el extremo
        superior fuera inclusivo, `at(B)` tendria que devolver las dos, que es
        la mitad de un conflicto. Luego `hasta` es la PRIMERA revision en la
        que el hecho ya no es cierto, y la ventana es `[desde, hasta)`.

        Esa forma ademas hace que las ventanas sean **contiguas sin huecos**:
        `[revA, revB)` y `[revB, ...)` no dejan instante sin respuesta, que es
        lo que un intervalo semiabierto garantiza y lo que un intervalo cerrado
        por los dos lados NO hacia —en el frontier se solaparian—.

    **UNA VENTANA AL REVES DEVUELVE `False` EN TODAS PARTES.** Con `desde=5,
    hasta=2` no hay ningun `seq` que la satisfaga, y eso es lo que hace que
    `vigente_en` sea **total**: quien la llama nunca tiene que mirar
    `desde <= hasta` antes de preguntar.
    """
    if desde is not None and seq < desde:
        return False
    return not (hasta is not None and seq >= hasta)


__all__ = [
    "Claim",
    "ClaimID",
    "ClaimRecorded",
    "Conflicto",
    "Entity",
    "EntityID",
    "EntityRef",
    "Evidence",
    "EvidenceID",
    "Finding",
    "FindingID",
    "OutcomeTrace",
    "Source",
    "SourceID",
    "TraceID",
    "entity_id",
    "entity_ref",
    "predicado_de_pack",
    "source_id",
    "vigente_en",
]
