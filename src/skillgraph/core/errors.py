"""Excepciones de dominio de SkillGraph.

La estrategia de tests exige mensajes accionables: cada error lleva un
código estable, el path del recurso y la regla violada.
"""

from __future__ import annotations


class SkillGraphError(Exception):
    """Raíz del árbol de excepciones del núcleo."""

    code: str = "sg_error"


class ValidationError(SkillGraphError):
    """Un recurso no cumple el contrato declarativo."""

    code = "sg_validation"


class ParseError(SkillGraphError):
    """Un recurso no pudo parsearse (front matter o YAML inválido)."""

    code = "sg_parse"


class UnknownKindError(ValidationError):
    """El `kind` del recurso no está registrado en el catálogo de tipos."""

    code = "sg_unknown_kind"


class IdentityConflictError(ValidationError):
    """Mismo (tenant, project, namespace, kind, name) ya registrado."""

    code = "sg_identity_conflict"


class IdempotencyError(SkillGraphError):
    """La operacion ya habia sido aplicada (UNIQUE sobre event_id)."""

    code = "sg_idempotency"


class IntegrityError(SkillGraphError):
    """Violacion de una invariante relacional del adapter de persistencia.

    WI-02b: introducida para que ``EventLog`` capture el
    ``sqlite3.IntegrityError`` del adapter SQLite y lo traduzca a un
    error tipado de dominio. El adapter (no el log de eventos) es el
    unico responsable de la unicidad (``UNIQUE(event_id)``); el log lo
    traduce para que el caller vea la jerarquia ``SkillGraphError`` y
    no la jerarquia ``sqlite3``.
    """

    code = "sg_integrity"


class SchemaTooNewError(SkillGraphError):
    """La base de datos declara un esquema MAS NUEVO que este codigo.

    B12. Antes de B12 esto no podia ocurrir porque la version no se movia
    nunca: `SCHEMA_VERSION` era 1 desde WI-65 y se escribia con
    `INSERT OR IGNORE` sin que nadie lo leyera. Una base «del futuro» era
    indistinguible de una de ayer, y el codigo la abria en silencio —que es
    la forma barata de perder datos en la siguiente escritura—.

    Se traduce a `EXIT_DOMAIN` (10) por la tabla de WI-109: es un error de
    dominio, y su `code` es propio para que un `code` compartido no lo
    vuelva indistinguible de otro.
    """

    code = "sg_schema_too_new"


class NotFoundError(SkillGraphError):
    """Un recurso o fixture solicitada no existe."""

    code = "sg_not_found"


class OutcomeInvalidError(ValidationError):
    """El outcome del agente no esta declarado en el WorkflowPlan."""

    code = "sg_outcome_invalid"


class StateTransitionError(ValidationError):
    """Una transicion de estado no es legal."""

    code = "sg_state_transition"


class MaxIterationsExceeded(SkillGraphError):
    """El bucle de reconciliacion agoto el presupuesto de iteraciones."""

    code = "sg_max_iterations"


# --- H4 Slice 1: errores de expansion controlada -----------------------


class InvalidExpansionError(SkillGraphError):
    """Una propuesta de expansion controlada viola una invariante.

    Ver blueprint §5 §6 (literal). Las invariantes se codifican como
    ``I1..I6`` en el resultado de ``validate`` y en ``InvalidProposal``.
    """

    code = "sg_invalid_expansion"


class UnauthorizedExpansionError(SkillGraphError):
    """La propuesta no tiene una autorizacion explicita valida.

    El modo ``manual_signed`` requiere firmante + timestamp;
    ``policy_approved`` requiere timestamp; ``auto_low_risk`` se
    auto-aprueba por la naturaleza de las operaciones.
    """

    code = "sg_unauthorized_expansion"


# --- H3 Slice 1: errores del modelo de conocimiento -----------------------


class InvalidSourceIDError(ValidationError):
    """Un SourceID no cumple el formato esperado (vacio o no normalizado)."""

    code = "sg_invalid_source_id"


class InvalidEntityIDError(ValidationError):
    """Un EntityID no cumple el formato `kind:key`."""

    code = "sg_invalid_entity_id"


class InvalidSourceError(ValidationError):
    """Una instancia de Source no cumple sus invariantes (e.g. git_* sin SHA)."""

    code = "sg_invalid_source"


class UnknownClaimPredicateError(ValidationError):
    """El predicado de un Claim no esta registrado en CLAIM_PREDICATES."""

    code = "sg_unknown_predicate"


class InvalidClaimObjectError(ValidationError):
    """El objeto de un Claim no es exactamente UNO de: literal o entidad.

    **EXISTE Y NO REUTILIZA `UnknownClaimPredicateError` A PROPÓSITO.** Son dos
    ejes distintos —el predicado y el objeto— y `AGENTS.md` §1.2 exige que cada
    clase declare su `code`: dos errores que comparten `code` no pueden salir
    con exit codes distintos, y entonces el `code` deja de ser clave. Es
    exactamente lo que WI-109 cerró.
    """

    code = "sg_invalid_claim_object"


class InvalidAssertionOriginError(ValidationError):
    """El origen epistemico de un Claim no esta en el vocabulario B6.

    `code` PROPIO y no compartido: WI-109 demostro que dos errores con el
    mismo `code` no pueden salir con exit codes distintos, y entonces el
    `code` deja de ser la clave con la que se traduce. Este nace con el
    suyo.
    """

    code = "sg_invalid_assertion_origin"


class EnvelopeInvalido(ValidationError):
    """Una `Observation` del envelope no afirma nada, o afirma las dos cosas.

    **NO es `InvalidClaimObjectError` aunque la pregunta parezca la misma.** La
    de B25 responde de un `Claim` ya construido, y la garantia la sostienen tres
    capas (este error, `Claim.__post_init__` y el CHECK de SQL). Esta responde de
    un `Observation`, que es todavia un **dato de entrada de una herramienta
    externa**: lo que falla ahi es la frontera, y la frontera no es la misma
    capa. Si las dos compartieran clase, una colapsaria a la otra y el
    `code` —que es la clave con la que la CLI traduce a exit code— dejaria de
    distinguir «el Claim esta mal» de «lo que llego de fuera esta mal».

    Se declara en `core/errors.py` y no en `knowledge/observation.py` porque el
    guard de WI-109 deriva el conjunto de clases **recorriendo el paquete
    entero**: un error definido en el modulo que lo usa solo se contaria cuando
    ese modulo se importara, y un guard que depende del orden de importacion no
    mide.
    """

    code = "sg_envelope_invalido"


class UnknownEnvelopeVersionError(ValidationError):
    """El envelope declara una version que este sistema no entiende.

     **POR QUE ESTO ES UN ERROR Y NO UN DEFAULT.** Un envelope con version
     desconocida es una herramienta hablando un contrato que este core no
    implementa. Aceptarla «con lo que haya» seria perder el dato en silencio y
     descubrirlo mucho despues, en el dato; rechazarla aqui deja el fallo donde
     es: en la frontera, con el mensaje diciendo que version se esperaba.

     El mensaje lleva SIEMPRE la version que se espera, para que quien lo recibe
     sepa que actualizar. Un «version no soportada» sin la version buena obliga a
     buscar el numero en el codigo.
    """

    code = "sg_unknown_envelope_version"


class UnknownQueryIntentError(ValidationError):
    """La intencion de consulta no es una de las del ADT.

    **POR QUE NO ES `ValidationError` SOLO.** Lo es: hereda de ahi, y por eso la
    CLI la traduce como error de entrada de usuario y no como fallo interno.
    Pero tiene clase propia porque `code` propio, y por la misma razon que
    termino WI-109: **dos errores que comparten `code` no pueden salir con exit
    codes distintos, y el `code` deja de ser clave**.

    Y lo que falla aqui no es un dato cualquiera: es **la pregunta**. Un string
    libre para la intencion (la spec lo prohibe, 05-SPEC §3) haria que dos
    perfiles que quieren decir lo mismo se llamaran distinto, y nadie podria
    notar que se estaban contradiciendo.
    """

    code = "sg_unknown_query_intent"


class AuthorityProfileInvalido(ValidationError):
    """La politica de autoridad no declara un ranking utilizable.

    Tres formas de declararlo mal, y las tres son el mismo defecto: una
    preferencia **vacia** (no dice quien manda), un origen **que no existe**
    (no se puede cumplir) y un origen **repetido** (el orden deja de
    signifcar algo, porque la prioridad se declara dos veces con valores
    distintos).
    """

    code = "sg_authority_profile_invalido"


class PerfilIncoherenteError(ValidationError):
    """Se ha usado una politica que responde a OTRA pregunta.

    **EL DEFECTO EXACTO QUE B28 EXISTE PARA EVITAR, declarado como error.** Un
    perfil de `intended_behavior` aplicado a una consulta `actual_behavior`
    responderia «¿que devolvio produccion?» con la politica de «¿que esta
    permitido?». El resultado seria un ganador, y el ganador estaria equivocado
    con una explicacion que pareciara convincent: es el fallo mas caro de esta
    serie, porque no se ve.

    No se corrige usando el perfil «de todos modos»: usar una politica que no
    corresponde a la pregunta es un error de quien pregunta, y ocultarlo
    convierte un error visible en uno invisible.
    """

    code = "sg_perfil_autoridad_incoerente"


class SkillGraphWarning(UserWarning):
    """Raíz de los warnings no fatales de SkillGraph.

    NO rompe el flujo: el caller decide que hacer (log, abortar, continuar).
    Vive como `UserWarning` para que `warnings.warn()` la trate como warning
    estandar de Python (visible con `-W error::UserWarning` si se quiere
    estricto).
    """

    code: str = "sg_warning"


class UnknownSourceError(SkillGraphError):
    """Una Source solicitada por ID no existe."""

    code = "sg_unknown_source"


class UnknownEntityError(SkillGraphError):
    """Una Entity solicitada por ID no existe."""

    code = "sg_unknown_entity"


class UnknownClaimError(SkillGraphError):
    """Un Claim solicitado por ID no existe."""

    code = "sg_unknown_claim"


class StaleKnowledgeWarning(SkillGraphWarning):
    """Una operacion se completo pero el conocimiento involucrado esta stale.

    NO aborta: el controller ya registro los datos. El caller decide
    si abortar (`-W error::StaleKnowledgeWarning`) o continuar.
    """

    code = "sg_stale_knowledge"


class DulwichNotAvailableError(SkillGraphError):
    """Operacion Git solicitada pero `dulwich` no esta instalado.

    Se lanza desde `git_source.py` cuando el caller pide funcionalidad
    que requiere la dependencia opcional `skillgraph[git]` y el modulo
    no se puede importar.
    """

    code = "sg_dulwich_not_installed"


class CyclicDependencyError(SkillGraphError):
    """El traversal de dependencias encontro un ciclo.

    NO aborta la operacion global; aborta SOLO el traversal. El caller
    puede recibir este error si configura ciclos como no permisibles.
    """

    code = "sg_cyclic_dependency"


#: Subclase de Warning para reportar ciclos durante traversal.
#: Hereda de SkillGraphWarning para que el caller pueda usar
#: `warnings.filterwarnings("error::CyclicDependencyWarning", ...)`
#: si quiere tratar ciclos como fatales.
class CyclicDependencyWarning(SkillGraphWarning):
    """El traversal detecto un ciclo. Continua, NO aborta."""

    code = "sg_cyclic_dependency_warn"


class RefreshFailedError(SkillGraphError):
    """`refresh_source` no pudo reactivar ninguna Claim.

    Indica que la `new_revision` no aporta evidences compatibles con
    las Claims stale. NO aborta el flujo, pero el caller deberia
    registrar el incidente.
    """

    code = "sg_refresh_failed"


class HopLimitExceededWarning(SkillGraphWarning):
    """El traversal de dependencias alcanzo `max_hops` antes de agotar.

    NO fatal. El caller decide si continuar o re-intentar con mas hops
    (`-W error::HopLimitExceededWarning` lo convertiria en error).
    """

    code = "sg_hop_limit_exceeded"


class StaleKnowledgeError(SkillGraphError):
    """`compile_handoff` fallo porque habia Claims stale y policy=strict.

    NO aborta llamadas menos estrictas: el caller elige strict/best_effort
    en la receta.
    """

    code = "sg_stale_knowledge_error"


class MissingObligatoryError(SkillGraphError):
    """`compile_handoff` fallo porque un selector obligario no resolvio.

    El error message incluye el selector que fallo.
    """

    code = "sg_missing_obligatory"


class TokenBudgetExceededError(SkillGraphError):
    """`compile_handoff` fallo porque el conocimiento obligatorio no cabe
    en `token_budget` (con `overflow_strategy=fail`).
    """

    code = "sg_token_budget_exceeded"


class RecipeNotFoundError(SkillGraphError):
    """`recipe_ref` no corresponde a una receta registrada o cargable."""

    code = "sg_recipe_not_found"


# Public API surface for `from skillgraph.core.errors import *`.
# Mantener sincronizado con las clases definidas en este modulo.
__all__ = [
    "AuthorityProfileInvalido",
    "CyclicDependencyError",
    "CyclicDependencyWarning",
    "DulwichNotAvailableError",
    "EnvelopeInvalido",
    "HopLimitExceededWarning",
    "IdempotencyError",
    "IdentityConflictError",
    "InvalidEntityIDError",
    "InvalidExpansionError",
    "InvalidSourceError",
    "InvalidSourceIDError",
    "MaxIterationsExceeded",
    "MissingObligatoryError",
    "NotFoundError",
    "OutcomeInvalidError",
    "ParseError",
    "PerfilIncoherenteError",
    "RecipeNotFoundError",
    "RefreshFailedError",
    "SkillGraphError",
    "SkillGraphWarning",
    "StaleKnowledgeError",
    "StaleKnowledgeWarning",
    "StateTransitionError",
    "TokenBudgetExceededError",
    "UnauthorizedExpansionError",
    "UnknownClaimError",
    "UnknownClaimPredicateError",
    "UnknownEntityError",
    "UnknownEnvelopeVersionError",
    "UnknownKindError",
    "UnknownQueryIntentError",
    "UnknownSourceError",
    "ValidationError",
]
