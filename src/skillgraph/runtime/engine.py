"""Contrato de eventos del runtime (Etapa 2 / S0).

Doc externo:
  external/blueprint-v1/docs/05-workflows-y-ciclo-de-vida.md §4 (eventos).
  external/blueprint-v1/docs/06-controladores.md §7 (bucle de
  reconciliacion).

Un evento es un hecho append-only que afecta al estado del run o del
nodo. La identidad del evento (`event_id`) es la UNICA defensa contra
duplicacion: el EventLog NO usa el orden temporal como autoridad.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from skillgraph.core.errors import IdempotencyError, IntegrityError, ValidationError
from skillgraph.core.runtime_types import EVENT_KINDS
from skillgraph.platform.ports import EventStore, StoredEvent
from skillgraph.runtime.redaction import redact_payload

SCHEMA_VERSION = 1

# WI-112: reloj inyectable. Antes `RuntimeEvent` usaba
# `default_factory=lambda: datetime.now(UTC)`, y una lambda que captura
# el reloj real no tiene por donde pasarle otro: "se puede mockear" era
# cierto solo con monkeypatch del modulo. `now_iso(clock=...)` es la via.
Clock = Callable[[], datetime]

# QW-D (WI-31, 2026-09-27): ``EVENT_KINDS`` se importa desde
# ``skillgraph.core.runtime_types``. La unica fuente de verdad es el
# Literal ``EventType``; ``EVENT_KINDS`` se deriva de ``get_args()``.
# Si necesitas anadir un evento nuevo, declaralo en ``EventType``
# (en runtime_types.py) y un ADR con la justificacion del contrato.


def now_iso(clock: Clock | None = None) -> str:
    """ISO 8601 UTC sin microsegundos. Unico punto de lectura del reloj.

    WI-112: este helper declara desde hace tiempo ser el "unico punto de
    definicion" y habia **10** llamadas a `datetime.now` repartidas por el
    nucleo, en tres formatos distintos. Dos instantes del mismo segundo
    podian serializarse a dos strings que no se comparaban entre si.

    Aqui se lee el reloj real, y en ningun otro sitio de
    `src/skillgraph/`. Para fijarlo en un test se pasa `clock`: no hace
    falta monkeypatchear el modulo.

    `clock` es `Callable[[], datetime]`. Se pasa explicito en vez de
    leer un global porque `AGENTS.md` 1.4 prohibe el estado global
    mutable, y un reloj global seria exactamente eso.
    """
    momento = clock() if clock is not None else datetime.now(UTC)
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=UTC)
    return momento.astimezone(UTC).replace(microsecond=0).isoformat()


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    """Hecho inmutable del runtime.

    Coincide con el contrato del blueprint §4 (eventos), incluyendo
    los campos obligatorios.
    """

    event_id: str
    tenant_id: str
    project_id: str
    event_kind: str
    run_id: str | None
    resource_ref: str
    causation_id: str | None
    correlation_id: str | None
    payload: dict[str, Any]
    # WI-112: antes era `field(default_factory=lambda:
    # datetime.now(UTC).isoformat())` — una lambda que capturaba el reloj
    # real, con su propio formato y su propia copia. `AGENTS.md` 1.3 pide
    # un default factory con `datetime.now(UTC)`, asi que el default se
    # queda; lo que cambia es que ahora el reloj se lee a traves de
    # `now_iso`, y por tanto con el formato unico del nucleo.
    #
    # La via de inyeccion es `now_iso(clock=...)` y `EventBuilder
    # ._emit(timestamp=...)`, no este default: un default factory que
    # llama al reloj es comodo de usar y opaco de fijar.
    timestamp: str = field(default_factory=now_iso)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.event_kind not in EVENT_KINDS:
            raise ValidationError(f"event_kind desconocido: {self.event_kind!r}")


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runtime_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    event_kind TEXT NOT NULL,
    run_id TEXT,
    resource_ref TEXT NOT NULL,
    causation_id TEXT,
    correlation_id TEXT,
    payload_json TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    schema_version INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS events_by_run
    ON runtime_events(tenant_id, project_id, run_id);
CREATE INDEX IF NOT EXISTS events_by_resource
    ON runtime_events(tenant_id, project_id, resource_ref);
"""


class EventLog:
    """Registro append-only de eventos del runtime.

    WI-02b: ya no recibe ``sqlite3.Connection`` directo; depende del
    :class:`skillgraph.platform.ports.EventStore` Protocol. La logica
    de redaccion y validacion permanece en ``EventLog`` (las politicas
    de tenant, el orden de operaciones); la persistencia y migracion
    delega al ``EventStore`` adapter (que cumple el UNIQUE(event_id)
    por constraint, no por codigo).
    """

    def __init__(
        self,
        events: EventStore,
        *,
        policy_resolver: Callable[[str], str | None] | None = None,
    ) -> None:
        """Inicializa el EventLog.

        Args:
            events: implementacion del Protocol ``EventStore``. Suele ser
                ``Storage(:memory:)`` o ``Storage(path).event_store()``
                en tests, o un adapter SQLite dedicado.
            policy_resolver: callable opcional que, dado un ``tenant_id``,
                devuelve la politica de redaccion (``"none"|"metadata"|
                "payload"|"full"``). Si devuelve None, se usa el
                default ``"metadata"`` (secure-by-default). Si el callable
                es None (caso por defecto), el EventLog redacta con
                ``"metadata"``: claves conservadas, valores
                ``[REDACTED]``. Los tenants que necesiten ``"none"``
                deben declararlo explicitamente via ``Storage.upsert_policy``
                o un ``policy_resolver`` que devuelva ``"none"``.
        """
        self._events = events
        self._policy_resolver = policy_resolver
        # Migracion idempotente delega al EventStore (cumple AC-3):
        # el schema ya vive en platform/, no aqui.
        self._events.ensure_schema()

    def _resolve_policy(self, tenant_id: str) -> str:
        """Resuelve la politica efectiva para un tenant.

        Sin resolver: default ``"metadata"`` (secure-by-default; redacta
        valores, conserva claves). El caller puede sobreescribir via
        ``Storage.upsert_policy`` (per-tenant) o ``policy_resolver``.
        Resolver devuelve None: default ``"metadata"``.
        Resolver devuelve un valor: se valida y se aplica tal cual.

        Nota: el cambio de default (pre-QW-B era ``"none"``) es un
        cambio de seguridad deliberado: secure-by-default. Los
        tenants que necesiten ``"none"`` deben declararlo explicitamente
        via ``upsert_policy``. Ver audit 2026-09-27 / WI-31 QW-B.
        """
        if self._policy_resolver is None:
            return "metadata"
        policy = self._policy_resolver(tenant_id)
        if policy is None:
            return "metadata"
        return policy

    def append(self, event: RuntimeEvent) -> int:
        """Inserta un evento. Devuelve el sequence asignado.

        Si el ``event_id`` ya existe (duplicado), lanza ``IdempotencyError``
        — la idempotencia vive en el UNIQUE de la tabla gestionada por
        el ``EventStore``, no en codigo de EventLog.
        Esto cumple UAT-07: evento entregado dos veces NO duplica.

        S5 Etapa 7: si hay ``policy_resolver`` configurado, el payload
        se redacta ANTES de persistir. El ``RuntimeEvent`` original
        NO se muta (es frozen); se calcula el payload redactado y se
        pasa al ``EventStore.record_event``. Asi ``logs_run`` y todos
        los tests siguen viendo el evento ORIGINAL (no el redactado),
        pero en disco solo aparece la version redactada.
        """
        policy = self._resolve_policy(event.tenant_id)
        persisted_payload = redact_payload(event.payload, policy)
        try:
            sequence = self._events.record_event(
                tenant_id=event.tenant_id,
                project_id=event.project_id,
                event_id=event.event_id,
                event_kind=event.event_kind,
                resource_ref=event.resource_ref,
                payload=persisted_payload,
                run_id=event.run_id,
                causation_id=event.causation_id,
                correlation_id=event.correlation_id,
                timestamp=event.timestamp,
            )
        except IntegrityError as exc:
            # UNIQUE(event_id) -> el evento ya estaba. UAT-07.
            # El adapter SQLite delega a sqlite3.IntegrityError; los
            # adapters no-SQL deberian traducir a IntegrityError propia
            # (MismatchedError del core).
            raise IdempotencyError(f"evento duplicado: {event.event_id}") from exc
        return sequence

    def events_for_run(self, *, tenant_id: str, project_id: str, run_id: str) -> list[StoredEvent]:
        """Devuelve los eventos del run como DTOs ``StoredEvent`` (WI-32.2 R1 strict).

        WI-32.2 (audit 2026-09-27): antes devolvia ``list[dict]`` construido
        a mano desde ``sqlite3.Row``. Ahora el ``EventStore`` Protocol ya
        filtra: el adapter SQLite mapea ``Row -> StoredEvent`` y este
        metodo simplemente reenvia. Esto cierra el objetivo 2 de WI-32:

          "ningun ``sqlite3.Row`` fuera de ``platform/``"

        Para consumidores que esperan dict (legacy API), cada DTO expone
        ``StoredEvent.to_dict()``.
        """
        return self._events.list_events_for_run(
            tenant_id=tenant_id, project_id=project_id, run_id=run_id
        )

    def has_event(self, event_id: str) -> bool:
        """Test de presencia por ``event_id`` via el Protocol.

        WI-32.2: el adapter devuelve ``StoredEvent | None`` en vez de
        ``sqlite3.Row | None``. Aqui solo nos importa la presencia.
        """
        return self._events.fetch_event_raw(event_id=event_id) is not None


def new_event_id() -> str:
    return str(uuid.uuid4())


# --- Builder funcional para eventos ----------------------------------------


class EventBuilder:
    """Constructor inmutable de `RuntimeEvent` con smart constructors.

    Cada metodo (`run_created`, `node_scheduled`, ...) devuelve un NUEVO
    `RuntimeEvent` ya validado. Elimina el boilerplate de repetir los
    7 argumentos comunes en cada sitio del RunController.

    Reglas (AGENTS.md §2 y §11.9):
    - Inmutable: cada llamada devuelve un nuevo `RuntimeEvent`,
      no muta estado.
    - Errores tipados: la validacion vive en `RuntimeEvent.__post_init__`.
    """

    __slots__ = ("_correlation_id", "_project_id", "_tenant_id")

    def __init__(
        self,
        *,
        tenant_id: str,
        project_id: str,
        correlation_id: str,
    ) -> None:
        self._tenant_id = tenant_id
        self._project_id = project_id
        self._correlation_id = correlation_id

    def _emit(
        self,
        *,
        kind: str,
        run_id: str | None,
        resource_ref: str,
        payload: dict[str, Any],
        causation_id: str | None = None,
        timestamp: str | None = None,
    ) -> RuntimeEvent:
        return RuntimeEvent(
            event_id=new_event_id(),
            tenant_id=self._tenant_id,
            project_id=self._project_id,
            event_kind=kind,
            run_id=run_id,
            resource_ref=resource_ref,
            causation_id=causation_id,
            correlation_id=self._correlation_id,
            payload=payload,
            # WI-112: el reloj se lee en UN sitio, `now_iso`. Quien
            # quiera fijarlo pasa `timestamp`; si no, lo lee de ahi.
            timestamp=timestamp if timestamp is not None else now_iso(),
        )

    def run_created(self, *, run_id: str, initial_node: str) -> RuntimeEvent:
        return self._emit(
            kind="RunCreated",
            run_id=run_id,
            resource_ref=f"run/{run_id}",
            payload={"initial_node": initial_node},
        )

    def node_scheduled(
        self, *, run_id: str, node_execution_id: str, node_name: str, attempt: int
    ) -> RuntimeEvent:
        return self._emit(
            kind="NodeScheduled",
            run_id=run_id,
            resource_ref=f"node/{node_execution_id}",
            payload={
                "node_name": node_name,
                "node_execution_id": node_execution_id,
                "attempt": attempt,
            },
        )

    def handoff_created(
        self, *, run_id: str, node_execution_id: str, context_hash: str
    ) -> RuntimeEvent:
        return self._emit(
            kind="HandoffCreated",
            run_id=run_id,
            resource_ref=f"handoff/{node_execution_id}",
            payload={
                "node_execution_id": node_execution_id,
                "context_hash": context_hash,
            },
        )

    def node_started(self, *, run_id: str, node_execution_id: str) -> RuntimeEvent:
        return self._emit(
            kind="NodeStarted",
            run_id=run_id,
            resource_ref=f"node/{node_execution_id}",
            payload={"node_execution_id": node_execution_id},
        )

    def node_completed(
        self,
        *,
        run_id: str,
        node_execution_id: str,
        outcome: str,
        context_hash: str,
    ) -> RuntimeEvent:
        return self._emit(
            kind="NodeCompleted",
            run_id=run_id,
            resource_ref=f"node/{node_execution_id}",
            payload={
                "node_execution_id": node_execution_id,
                "outcome": outcome,
                "context_hash": context_hash,
            },
        )

    def node_failed(
        self,
        *,
        run_id: str,
        node_execution_id: str,
        error: str,
        outcome: str | None = None,
    ) -> RuntimeEvent:
        payload: dict[str, Any] = {
            "node_execution_id": node_execution_id,
            "error": error,
        }
        if outcome is not None:
            payload["outcome"] = outcome
        return self._emit(
            kind="NodeFailed",
            run_id=run_id,
            resource_ref=f"node/{node_execution_id}",
            payload=payload,
        )

    def evidence_produced(
        self,
        *,
        run_id: str,
        node_execution_id: str,
        outcome: str,
        context_hash: str,
        evidence_ref: str,
    ) -> RuntimeEvent:
        return self._emit(
            kind="EvidenceProduced",
            run_id=run_id,
            resource_ref=f"evidence/{node_execution_id}",
            payload={
                "node_execution_id": node_execution_id,
                "outcome": outcome,
                "context_hash": context_hash,
                "evidence_ref": evidence_ref,
            },
        )

    def run_completed(self, *, run_id: str, state: str, at: str | None = None) -> RuntimeEvent:
        payload: dict[str, Any] = {"state": state}
        if at is not None:
            payload["at"] = at
        return self._emit(
            kind="RunCompleted",
            run_id=run_id,
            resource_ref=f"run/{run_id}",
            payload=payload,
        )

    def budget_exceeded(
        self,
        *,
        run_id: str,
        kind: str,
        limit: int,
        observed: int,
    ) -> RuntimeEvent:
        """Emite un evento BudgetExceeded cuando un Run viola su presupuesto.

        Args:
            run_id: identificador del Run.
            kind: tipo de presupuesto violado (`visits` | `runtime` |
                `events`). Es una categoria de negocio, no del evento
                mismo; el `event_kind` siempre es `BudgetExceeded`.
            limit: limite configurado en el RunBudget.
            observed: valor observado al momento de la violacion.

        Raises:
            ValidationError: si `kind` no esta en el conjunto canonico.
        """
        if kind not in {"visits", "runtime", "events"}:
            raise ValidationError(
                f"budget kind invalido: {kind!r} (esperado visits|runtime|events)"
            )
        return self._emit(
            kind="BudgetExceeded",
            run_id=run_id,
            resource_ref=f"run/{run_id}",
            payload={
                "kind": kind,
                "limit": int(limit),
                "observed": int(observed),
            },
        )
