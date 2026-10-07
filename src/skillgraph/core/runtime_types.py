"""Tipos canonicos del runtime de SkillGraph.

Doc externo:
  external/blueprint-v1/docs/05-workflows-y-ciclo-de-vida.md §1-2
  (estados de run y de instancia de nodo).

Estos tipos son **ADT cerradas**: anadir un valor nuevo es un cambio
de contrato del blueprint, no un detalle local. Si necesitas un valor
nuevo, abre una ADR primero.

QW-D (WI-31, 2026-09-27): ``EventType`` Literal y ``EVENT_KINDS``
frozenset eran DOS conjuntos con interseccion de 3 valores. Ahora
hay una sola fuente: ``EventType`` Literal. ``EVENT_KINDS`` se deriva
de el via ``typing.get_args()``. El antiguo modulo ``runtime.engine``
define ``EVENT_KINDS`` por compat historica pero importa ``EventType``
de aqui; cualquier valor nuevo debe declararse en ``EventType``.

ADR-0015 (WI-87, 2026-10-02): ese mismo patron se aplicaba ya a
``SOURCE_KINDS`` (QW-E) pero se le habia escapado a dos vocabularios
mas, que vivian duplicados en la fachada de persistencia. Ahora
``NON_TERMINAL_RUN_STATES`` se deriva por complemento de
``TERMINAL_RUN_STATES``, y ``PROMOTION_STATUSES`` se deriva de
``PromotionStatus`` y genera el ``CHECK`` de SQLite en
``platform/schema.py``. Regla general: **ningun frozenset de
vocabulario se escribe a mano; se deriva de su Literal**.
"""

from __future__ import annotations

import re
from typing import Final, Literal, NewType, get_args

# --- Tipos suma (ADT cerradas) -------------------------------------------

NodeKind = Literal["DecisionNode", "ActionNode"]
"""Suma cerrada: un nodo del runtime es DecisionNode o ActionNode."""

RunState = Literal["CREATED", "ACTIVE", "WAITING", "COMPLETED", "FAILED", "CANCELLED"]
"""Ciclo de vida de un Run (blueprint §1)."""

NodeState = Literal["READY", "RUNNING", "WAITING", "SUCCEEDED", "FAILED", "STOPPED", "CANCELLED"]
"""Ciclo de vida de una instancia de nodo (blueprint §2)."""

PromotionStatus = Literal["PENDING", "IN_PROGRESS", "PUBLISHED", "FAILED"]
"""Ciclo de vida de una propuesta del outbox de promoción (UAT-13).

ADR-0015. Antes este vocabulario vivia duplicado: el ``CHECK`` de
``schema.py`` lo escribia a mano y ``platform/storage.py`` declaraba su
propio ``PROMOTION_STATUSES`` sin relacion verificada entre si.
"""

# --- H3 Slice 1: tipos de conocimiento -------------------------------------

SourceKind = Literal[
    "git_commit",
    "git_tree",
    "local_file",
    "external_doc",
    "skill_pack",
    "runtime_observation",
]
"""Tipo de fuente de la que se extrae evidencia.

- `git_commit`: snapshot inmutable de un commit.
- `git_tree`: snapshot de un tree (directorio) en un commit.
- `local_file`: archivo del workspace NO bajo git (provisional).
- `external_doc`: documento externo (URL, PDF, etc.).
- `skill_pack`: paquete de skill externa asimilada (H5). Conserva
  el material original como referencia (path + content_hash) sin
  ejecutar el codigo del paquete. Ver `skill_importer.py`.
- `runtime_observation`: **lo que se vio funcionando**, y es lo unico
  cuyo contenido es un **PERIODO** y no un instante. Es el unico kind que
  admite `observed_from`/`observed_to` (`ADR-0034`).

    El valor se decidio MEDIDO, no por simetria. Antes de B33 toda
    observacion externa —incluida la de runtime— se registraba como
    `external_doc`, que es la decision que B26 escribio en
    `knowledge/observation.py:242` y que prometo abrir una ADR porque
    `SourceKind` es un Literal cerrado (`AGENTS.md` 2.1). Esa ADR no se
    abrio hasta B33. Lo que se midio:

    ```
    adr:0001           kind=external_doc
    runtime:ventana-1  kind=external_doc     <- indistinguibles
    json_extract(locator_json, '$.producer')  FUNCIONA, pero sin indice
    columnas de sources: ni producer, ni adapter, ni type_name
    ```

    El discriminante existia dentro del `locator` y se podia consultar
    abriendo el JSON y recorriendo la tabla. No habia kind que lo
    nombrara, y la pregunta que este kind viene a responder —la que
    responde `actual_behavior`, «que devolvio produccion de verdad?»—
    es la que mas lo necesitaba.
"""

FreshnessState = Literal["fresh", "stale", "archived"]
"""Estado de actualidad de una Source.

`fresh` = el contenido coincide con el esperado.
`stale` = el contenido cambio (su hash difiere del registrado).
`archived` = retirada del catalogo activo.
"""

ClaimPredicate = Literal[
    "line_count",
    "function_count",
    "imports_module",
    "defines_symbol",
    "test_passes",
    "file_exists",
    "spec_revision",
]
"""Predicados extraibles en H3 (extensibles en H5 con Domain Packs)."""

FindingResult = Literal["pass", "fail", "inconclusive"]
"""Resultado de aplicar una regla a una entidad."""

TraceKind = Literal["SoftwareExecutionSlice"]

#: Origen epistemico de una afirmacion (gate B6).
AssertionOrigin = Literal[
    "observed",
    "derived-deterministically",
    "agent-inferred",
    "human-asserted",
]
"""QUIEN AFIRMA, y con que autoridad (gate B6 del roadmap).

Este vocabulario NO es lo mismo que `extraction_method`, y separarlos es
el punto. `extraction_method` responde «¿como se extrajo esto?» —un regex,
un analisis estatico—. Este responde «¿quien AFIRMA que es verdad y con
que autoridad?». Son ejes ortogonales: la misma afirmacion puede salir de
un regex (`derived-deterministically`) o de una persona
(`human-asserted`), y en los dos casos el metodo de extraccion es el
mismo. Un solo campo no puede decir las dos cosas: con
`extraction_method="regex_def"` no se sabe si lo afirmo la maquina o el
agente, y escribir `agent-inferred` ahi perderia el metodo.

Medido antes de anadirlo (`scripts/measure_b6_provenance.py`): no habia
ningun campo que declarara este vocabulario, y `extraction_method` era un
`str` libre al que NADIE escribe en `src/` — las diez apariciones de
`"manual"` y las cuatro de `"regex_def"` estan todas en `tests/`, y en
produccion solo existe el default de la declaracion. Un eje que nadie
rellena no puede ser donde viva el origen.

El default es `observed` y no `derived-deterministically` a proposito:
`observed` es el unico origen que no promete nada, luego es el unico
correcto para un valor por defecto. Poner el mas fuerte obligaria a
declarar la intension de cada autor; poner el mas debil obligaria a
corregir la afirmacion mas pequena. El default es la afirmacion minima
que se puede hacer sin saber quien escribe.
"""

#: Conjunto canonico de origenes epistemicos (gate B6).
ASSERTION_ORIGINS: Final[frozenset[str]] = frozenset(get_args(AssertionOrigin))
"""Derivado del Literal, por la misma regla que `SOURCE_KINDS` (QW-E).

Un conjunto escrito a mano seria una segunda fuente de verdad que se
desincroniza en cuanto alguien anada un valor al Literal, y la validacion
rechazaria el valor nuevo mientras el tipo lo acepta. Derivado, no puede
divergir.
"""
"""Tipo de OutcomeTrace. H3 cubre solo `SoftwareExecutionSlice`."""

RuleRef = Literal["max_lines_per_function", "max_complexity", "naming_convention"]
"""Reglas de software disponibles en H3."""

EventType = Literal[
    "RunCreated",
    "RunStarted",
    "RunCompleted",
    "RunFinished",
    "RunFailed",
    "NodeScheduled",
    "HandoffCreated",
    "NodeStarted",
    "NodeFinished",
    "NodeCompleted",
    "NodeFailed",
    "EvidenceProduced",
    "KnowledgeInvalidated",
    "KnowledgeRefreshed",
    "ProblemDiscovered",
    "GraphExpansionProposed",
    "GraphExpansionAccepted",
    "GraphExpansionRejected",
    "BudgetExceeded",
]
"""Tipos de evento que pueden aparecer en `runtime_events`.

QW-D: union canonica de los antiguos ``EventType`` (8 valores) y
``runtime.engine.EVENT_KINDS`` (14 valores). Las dos colecciones
estaban desincronizadas (solo 3 comunes: RunCreated, NodeStarted,
KnowledgeInvalidated). Ahora hay una sola fuente. ``EVENT_KINDS`` se
deriva de este Literal via ``get_args()``.

Si anades un evento nuevo, declaralo aqui y un ADR con la justificacion.
"""

#: Conjunto canonico derivado del Literal EventType.
#: Cualquier ``event_kind`` fuera de este set falla validacion
#: (``RuntimeEvent.__post_init__``).
EVENT_KINDS: Final[frozenset[str]] = frozenset(get_args(EventType))
"""Conjunto derivado: ``frozenset(get_args(EventType))``. Importado por
``runtime.engine`` para la validacion runtime. No redefinir en otros
modulos: una sola fuente de verdad (QW-D)."""

# --- NewType: evita confusion entre strings ------------------------------
# Un NodeName NO es un Outcome, aunque ambos sean str. Los NewType
# desaparecen en runtime (no afectan performance) pero hacen que el
# type-checker rechace mezclas accidentales.

NodeName = NewType("NodeName", str)
"""Identificador local de un nodo dentro de un WorkflowPlan."""

OutcomeLabel = NewType("OutcomeLabel", str)
"""Etiqueta declarativa que un Adapter devuelve o un WorkflowTransition declara."""

RevisionNumber = NewType("RevisionNumber", int)
"""Version monotona de un recurso (>= 1)."""

# --- Constantes runtime (validacion + branching) ------------------------

#: Conjunto canonico de kinds de nodo ejecutables.
NODE_KINDS: Final[frozenset[str]] = frozenset({"DecisionNode", "ActionNode"})

#: Estados terminales de un Run (no avanzan mas).
TERMINAL_RUN_STATES: Final[frozenset[str]] = frozenset({"COMPLETED", "FAILED", "CANCELLED"})

#: Estados no terminales de un Run (el proceso puede reanudarlos).
#:
#: ADR-0015: se declara lo *terminal* y esto se deriva por complemento,
#: de modo que ``NON_TERMINAL | TERMINAL == get_args(RunState)`` es cierto
#: por construccion. Antes ``platform/storage.py`` escribia a mano los
#: tres no terminales: anadir un estado a ``RunState`` sin tocar ese
#: fichero lo hacia TERMINAL, y UAT-06 (reanudar tras crash) fallaba
#: duplicando el run en silencio.
NON_TERMINAL_RUN_STATES: Final[frozenset[str]] = frozenset(get_args(RunState)) - TERMINAL_RUN_STATES

#: Conjunto canonico de estados de una propuesta de promocion.
PROMOTION_STATUSES: Final[frozenset[str]] = frozenset(get_args(PromotionStatus))
"""Conjunto derivado: ``frozenset(get_args(PromotionStatus))`` (ADR-0015).

``platform/schema.py`` genera el ``CHECK`` de SQLite a partir de este
conjunto, de modo que la base de datos y el validador de entrada no
pueden divergir: salen de la misma expresion.
"""

#: Estados terminales de una NodeExecution.
TERMINAL_NODE_STATES: Final[frozenset[str]] = frozenset(
    {"SUCCEEDED", "FAILED", "STOPPED", "CANCELLED"}
)

#: Conjunto canonico de kinds de fuente.
SOURCE_KINDS: Final[frozenset[str]] = frozenset(get_args(SourceKind))
"""Conjunto derivado: ``frozenset(get_args(SourceKind))`` (QW-E).

Antes era un frozenset declarado a mano con 4 valores; el Literal
``SourceKind`` tenia 5 (``skill_pack`` incluido). Validacion runtime
rechazaba ``skill_pack`` por la divergencia.

Cualquier ``source_kind`` fuera de este set falla validacion.
"""

#: Conjunto canonico de predicados de Claim (H3).
#:
#: **ESTE CONJUNTO NO CRECE, Y ES LA PROMESA DE B25.** La fila del roadmap
#: dice «un pack añade un predicado sin tocar el núcleo»: si para aceptar un
#: predicado nuevo hubiera que añadirlo aquí, la promesa sería untrue, porque
#: este fichero es justamente el núcleo. Lo que se abre es la FORMA —un
#: predicado con namespace—, no la lista.
#:
#: Su docstring de siempre ya lo anunciaba: «extensibles en H5 con Domain
#: Packs». B25 implementa lo que el vocabulario prometía.
CLAIM_PREDICATES: Final[frozenset[str]] = frozenset(
    {
        "line_count",
        "function_count",
        "imports_module",
        "defines_symbol",
        "test_passes",
        "file_exists",
        "spec_revision",
    }
)

#: Forma de un predicado que viene de un pack: `namespace.nombre`.
#:
#: `NewType` y no `Literal` porque el vocabulario es abierto POR DISEÑO, y
#: `AGENTS.md` §2.2 es exactamente este caso: strings que vienen de fuera y
#: tienen semántica propia. El type-checker separa así un predicado del núcleo
#: de uno del pack sin ningún coste en runtime.
PredicadoDePack = NewType("PredicadoDePack", str)
"""Predicado que aporta un pack, con namespace `namespace.nombre`."""

#: Un namespace, y al menos un nombre. **Al menos un punto**, que es la parte
#: que importa: `not_a_real_predicate` no lo tiene, y por eso
#: `test_claim_unknown_predicate_raises` —el unico test que depende del
#: rechazo— sigue verde sin tocarlo.
#:
#: Se regex y no un conjunto de separadores porque el criterio tiene que ser
#: una FUNCION del string, no un registro: un registro seria estado global
#: mutable (`AGENTS.md` §1.4) y haria que construir un `Claim` dependiera del
#: orden en que se instalo nada.
#:
#: La regex no lleva ancla `$` porque `re.match` ya la impone desde el inicio,
#: y una segunda ancla aqui seria ruido que sugiere que se comprueba el final.
_FORMA_PREDICADO_DE_PACK = re.compile(r"[a-z0-9][a-z0-9_-]*(\.[a-z0-9][a-z0-9_-]*)+")


def predicado_de_pack(raw: str) -> PredicadoDePack:
    """Smart constructor: un predicado de pack es `namespace.nombre` o nada.

    Lanza `UnknownClaimPredicateError` —el mismo error que el predicado
    desconocido del núcleo— porque desde fuera del dominio el fallo es el
    mismo: ese texto no nombra un predicado que exista. La exception vive en
    `core.errors`, que no importa aqui, asi que se importa perezoso: un modulo
    de tipos que importa errores termina creando el ciclo que §1.3 prohibe.
    """
    from skillgraph.core.errors import UnknownClaimPredicateError

    if not _FORMA_PREDICADO_DE_PACK.match(raw):
        raise UnknownClaimPredicateError(
            f"predicado {raw!r} no es del nucleo ({sorted(CLAIM_PREDICATES)}) "
            f"ni de un pack: un predicado de pack se escribe 'namespace.nombre'"
        )
    return PredicadoDePack(raw)


#: Conjunto canonico de resultados de Finding.
FINDING_RESULTS: Final[frozenset[str]] = frozenset({"pass", "fail", "inconclusive"})


def is_terminal_run_state(state: str) -> bool:
    """True si el estado del Run es terminal (no admite mas reconciliacion)."""
    return state in TERMINAL_RUN_STATES


def is_terminal_node_state(state: str) -> bool:
    """True si el estado de la NodeExecution es terminal."""
    return state in TERMINAL_NODE_STATES


# Public API surface for `from skillgraph.core.runtime_types import *`.
__all__ = [
    "ASSERTION_ORIGINS",
    "CLAIM_PREDICATES",
    "FINDING_RESULTS",
    "NODE_KINDS",
    "NON_TERMINAL_RUN_STATES",
    "PROMOTION_STATUSES",
    "SOURCE_KINDS",
    "TERMINAL_NODE_STATES",
    "TERMINAL_RUN_STATES",
    "AssertionOrigin",
    "ClaimPredicate",
    "EventType",
    "FindingResult",
    "FreshnessState",
    "NodeKind",
    "NodeName",
    "NodeState",
    "OutcomeLabel",
    "PredicadoDePack",
    "PromotionStatus",
    "RevisionNumber",
    "RuleRef",
    "RunState",
    "SourceKind",
    "TraceKind",
    "is_terminal_node_state",
    "is_terminal_run_state",
    "predicado_de_pack",
]
