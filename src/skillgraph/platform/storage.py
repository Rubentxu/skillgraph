"""Almacenamiento SQLite para SkillGraph (Etapa 0/1 / spike S1).

Decisiones de diseño (external/blueprint-v1/docs/09-persistencia.md):
- Bases separadas por tenant/proyecto; aquí usamos una sola base SQLite
  por proyecto, indexada por tenant_id/project_id en cada tabla para
  reforzar el aislamiento en queries.
- WAL activado para lectores concurrentes.
- Interfaz `Storage` no expone SQL directo: futuras migraciones (S2)
  no deberían tocar el código de controladores.

Auditoría de duplicación:
- Esta clase NO reemplaza al parser ni al registro. Toma `Brick` ya
  validado (doc 03 + doc 04) y lo persiste.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from skillgraph.core.errors import IdempotencyError, ValidationError

# Re-exports: los componentes extraidos en WI-56 (ADR-0016 cortes 2-5)
# y sus mappers siguen importando estos DTOs **desde** `storage` en vez
# de desde `ports`. Es el shim de compatibilidad que el corte 1 creo.
# Declararlos en `__all__` los marca como usados: sin esto, ruff los
# borra por F401 en cuanto `Storage` deja de usarlos internamente, y
# revienta 7 modulos a la vez. NO eliminar sin migrar esos imports.
from skillgraph.knowledge.graph import (
    Claim,
    Entity,
    Evidence,
    Finding,
    OutcomeTrace,
    Source,
)
from skillgraph.platform import journal
from skillgraph.platform.ports import (
    StoredBudget,
    StoredClaim,
    StoredEvent,
    StoredEvidence,
    StoredNodeExecution,
    StoredPromotion,
    StoredRelation,
    StoredResource,
    StoredRun,
)

# WI-86: este bloque reexportaba los 7 simbolos de `row_mappers` (6
# mappers + `_uid` + `MAPPER_NAMES`) para que sus hermanos los importaran
# desde el facade. Medido: cada uno aparecia **exactamente dos veces** en
# este fichero —una aqui y otra en `__all__`— y **ninguno se usaba en una
# sola linea de codigo dentro de `storage.py`**. Los 5 consumidores reales
# (`event_store`, `knowledge_repository`, `policy_store`,
# `promotion_repository`, `run_repository`) ahora los importan de
# `row_mappers`, que es una hoja: no depende de nada que dependa de ellos,
# asi que el rodeo por el facade no evitaba ningun ciclo.
#
# El comentario anterior decia que se exportaban «porque `event_store` y
# `policy_store` los importan desde ahi». Era cierto para esos dos y
# falso como justificacion: eran cinco, y ninguno tenia una razon para no
# ir a la hoja.
#
# WI-81 ya habia retirado los 7 alias de WI-56 (corte 3) de este mismo
# bloque; este los retira por completo. Ver `tests/test_wi81_dead_aliases.py`
# y `tests/test_wi86_no_facade_hop.py`.
from skillgraph.platform.schema import SCHEMA_SQL as _SCHEMA_SQL, SCHEMA_VERSION
from skillgraph.platform.storage_delegations import (
    EventStoreDelegations,
    KnowledgeDelegations,
    PolicyDelegations,
    PromotionDelegations,
    RunDelegations,
)
from skillgraph.platform.uow import SqliteUnitOfWork
from skillgraph.resources.bricks import Brick

if TYPE_CHECKING:
    from skillgraph.platform.event_store import SqliteEventStore
    from skillgraph.platform.knowledge_repository import SqliteKnowledgeRepository
    from skillgraph.platform.policy_store import SqlitePolicyStore
    from skillgraph.platform.promotion_repository import SqlitePromotionRepository
    from skillgraph.platform.run_repository import SqliteRunRepository
    from skillgraph.runtime.engine import RuntimeEvent

__all__ = [
    "SCHEMA_VERSION",
    "_SCHEMA_SQL",
    "Brick",
    "Claim",
    "Entity",
    "Evidence",
    "Finding",
    "OutcomeTrace",
    "Source",
    "SqliteUnitOfWork",
    "Storage",
    "StoredBudget",
    "StoredClaim",
    "StoredEvent",
    "StoredEvidence",
    "StoredNodeExecution",
    "StoredPromotion",
    "StoredRelation",
    "StoredResource",
    "StoredRun",
]


# ADR-0015: `PROMOTION_STATUSES` y `NON_TERMINAL_RUN_STATES` ya no viven
# aqui. Son vocabulario de dominio, no de persistencia: los define
# `core.runtime_types` derivandolos de sus ADT (`PromotionStatus` y
# `RunState - TERMINAL_RUN_STATES`). Este modulo declaraba copias escritas
# a mano que nadie ligaba con el `CHECK` de SQLite ni con el Literal, y
# los repositorios las importaban de la fachada en vez de la hoja.
class Storage(
    RunDelegations,
    KnowledgeDelegations,
    PromotionDelegations,
    EventStoreDelegations,
    PolicyDelegations,
):
    """Interfaz de almacenamiento para un proyecto.

    Diseñada para fallar rápido en errores de identidad y validación,
    sin exponer SQL a los controladores.

    WI-33: ``Storage`` es ahora un facade delgado sobre
    ``SqliteUnitOfWork``. Los 5 bounded-context adapters (runs,
    events, knowledge, governance, policy) comparten la misma
    ``sqlite3.Connection``. El facade expone cada metodo publico
    como alias directo sobre el adapter correspondiente.
    """

    # Nombres de metodos publicos declarados en los 5 adapters de
    # ``skillgraph.platform.uow``. Documenta la superficie; NO se
    # consume en ninguna parte (``__init__`` no hace bind de metodos:
    # el facade tiene sus propios metodos SQL y los adapters delegan
    # en el, no al reves).
    #
    # WI-45: se corrige el comentario, que afirmaba que estos nombres
    # "se bind-an en __init__". No era cierto, y por eso la lista
    # arrastraba dos nombres que ningun metodo real tiene
    # (``get_redaction_policy`` / ``set_redaction_policy``). La
    # lista ahora nombra lo que el facade implementa de verdad.
    _PUBLIC_METHODS = frozenset(
        {
            # SqliteRunAdapter (RunRepository)
            "list_runs",
            "get_run",
            "load_run",
            "list_node_executions",
            "find_active_run",
            "list_executed_node_names",
            "recover_interrupted_node_executions",
            "transition_run_state",
            "start_node_execution",
            "complete_node_execution",
            "mark_node_failed",
            "create_run",
            "transition_run_state_atomically",
            "start_node_execution_atomically",
            "complete_node_execution_atomically",
            "mark_node_failed_atomically",
            "update_node_execution_handoff",
            # SqliteEventAdapter (EventStore)
            "list_events_for_run",
            "fetch_event_raw",
            "record_event",
            # SqliteKnowledgeAdapter (KnowledgeRepository)
            "get_resource",
            "list_resources",
            "dependencies_of",
            "dependents_of",
            "upsert_resource",
            "add_relation",
            # SqliteGovernanceAdapter (PromotionRepository)
            "get_promotion",
            "list_promotions",
            # SqlitePolicyAdapter (PolicyStore) — los metodos reales
            # del facade; los del adapter se llaman get/set_redaction_policy
            # y delegan aqui.
            "get_policy",
            "upsert_policy",
        }
    )

    @property
    def uow(self) -> SqliteUnitOfWork:
        """Acceso al ``SqliteUnitOfWork`` underlying (WI-33).

        La UoW es estable: la misma instancia para todo el ciclo
        de vida del ``Storage``. Esto permite a tests verificar
        ``storage.uow is storage.uow``.

        Tipo: ``SqliteUnitOfWork``. Esta propiedad es la API
        publica de WI-33: los tests nuevos pueden usar
        ``storage.uow.runs.list_runs(...)`` en vez de la facade
        ``storage.list_runs(...)``.
        """
        return self._uow

    #: Segundos que SQLite espera a que otro proceso libere un lock antes
    #: de declarar `database is locked`. MEDIDO en B2: sin esto, ocho
    #: procesos abriendo la misma base al mismo tiempo hacen que uno —o
    #: varios— muera en el `PRAGMA journal_mode = WAL` de la linea de
    #: abajo, y las escrituras de ese proceso se pierden sin dejar
    #: rastro. Con 5 s, ocho procesos concurrentes escriben las 80 filas.
    #:
    #: El valor NO es arbitrario: es el mismo que el de `sqlite3.connect`
    #: por defecto, y por eso pasaba desapercibido —hasta que alguien
    #: abre la base desde dos procesos a la vez, que es exactamente lo
    #: que B2 vino a probar. Ver `tests/test_b2_real_concurrency.py`.
    _BUSY_TIMEOUT_S: Final[float] = 5.0

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # `check_same_thread=False` permite reuso desde threads de pytest
        # (los tests no usan threads todavía, pero la propiedad
        # es útil cuando entremos a Etapa 2).
        self._conn = sqlite3.connect(
            str(self.path),
            isolation_level=None,
            check_same_thread=False,
            timeout=self._BUSY_TIMEOUT_S,
        )
        self._conn.row_factory = sqlite3.Row
        # MEDIDO en B2 y corregido en B9: el `PRAGMA journal_mode = WAL` NO
        # era gratis. El PRAGMA es idempotente —si la base ya esta en WAL,
        # no cambia nada— y aun asi **toma un lock de escritura para
        # averiguar que no hace nada**. Con diez procesos abriendo la misma
        # base a la vez, uno moria con `database is locked` ANTES de
        # escribir una sola fila. Sus escrituras se perdian sin dejar
        # rastro: sin excepcion en el padre, sin log, y con un run que
        # «funciona» al que solo le falta un evento.
        #
        # Poner `timeout` en el `connect` de arriba es necesario pero no
        # suficiente: el default de `sqlite3.connect` ya son 5 s, y el
        # fallo seguia apareciendo. El `busy_timeout` no cubre esta
        # ventana porque el bloqueo ocurre DENTRO de la conversion del
        # journal, no en la espera por un lock de escritura normal.
        #
        # El arreglo —preguntar el modo antes de cambiarlo, releer entre
        # reintentos y dormir entre ellos— vive en `platform.journal`, no
        # aqui: es una politica de la base y no de la fachada, y ahi no
        # cabe sin romper el umbral de WI-65. El porque de cada parte esta
        # escrito alli, con las mediciones que la sostienen.
        journal.asegura_wal(self._conn)
        self._conn.execute("PRAGMA foreign_keys = ON")
        # WI-56 cortes 1-2: cache de los componentes reales del
        # cluster runs y del cluster policy/budget (lazy en sus
        # factorias).
        self._run_repository: SqliteRunRepository | None = None
        self._policy_store: SqlitePolicyStore | None = None
        self._knowledge_repository: SqliteKnowledgeRepository | None = None
        self._event_store: SqliteEventStore | None = None
        self._promotion_repository: SqlitePromotionRepository | None = None
        self._migrate()
        # WI-33 (R2 audit externo): el ``SqliteUnitOfWork`` owns la
        # conexion y expone 5 bounded-context adapters que la
        # comparten. ``Storage`` sigue siendo el facade historico,
        # con sus metodos SQL directos. Los adapters son NUEVAS
        # implementaciones que viven en ``platform/uow.py`` y se
        # acceden via ``storage.uow.runs.list_runs(...)``.
        #
        # WI-33 NO reemplaza los metodos del facade. Esto preserva
        # la API actual y evita recursion: el facade tiene sus
        # implementaciones SQL, los adapters tienen las suyas
        # (inicialmente delegando al facade, pero con la UoW como
        # single owner de la conexion).
        from skillgraph.platform.uow import (
            SqliteEventAdapter,
            SqliteGovernanceAdapter,
            SqliteKnowledgeAdapter,
            SqlitePolicyAdapter,
            SqliteRunAdapter,
            SqliteUnitOfWork,
        )

        self._runs_adapter = SqliteRunAdapter(_conn=self._conn, _storage=self)
        self._events_adapter = SqliteEventAdapter(_conn=self._conn, _storage=self)
        self._knowledge_adapter = SqliteKnowledgeAdapter(_conn=self._conn, _storage=self)
        self._governance_adapter = SqliteGovernanceAdapter(_conn=self._conn, _storage=self)
        self._policy_adapter = SqlitePolicyAdapter(_conn=self._conn, _storage=self)
        self._uow = SqliteUnitOfWork(
            runs=self._runs_adapter,
            events=self._events_adapter,
            knowledge=self._knowledge_adapter,
            governance=self._governance_adapter,
            policy=self._policy_adapter,
        )

    def close(self) -> None:
        """Cierra la conexion SQLite. Idempotente: doble close no falla.

        QW-C: permite que ``Storage`` se use como context manager
        (``with Storage(path) as s: ...``) sin generar
        ``ResourceWarning: unclosed database``. ``__exit__`` llama
        a este metodo; tests que ya usan ``storage.close()`` siguen
        funcionando igual.
        """
        # sqlite3.Connection.close() es idempotente en Python >=3.10,
        # pero por seguridad marcamos una bandera para dobles llamadas.
        with suppress(sqlite3.ProgrammingError):
            self._conn.close()

    def __enter__(self) -> Storage:
        """Soporte ``with Storage(path) as s: ...``.

        Devuelve ``self`` para que el cuerpo del ``with`` pueda usar
        el storage directamente.
        """
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        """Cierra la conexion al salir del ``with``. Ignora la excepcion
        del cuerpo (no la suprime: el caller la ve normalmente).

        Si el cuerpo lanzo una excepcion, sqlite3 cierra la transaccion
        abierta (rollback automatico) y nosotros cerramos la conexion.
        """
        self.close()
        # No devolvemos True: la excepcion (si la hubo) se propaga.

    # ----- factorías de puertos (WI-02a) -------------------------------
    # ``Storage`` implementa los 5 Protocols de persistencia
    # (``RunRepository``, ``EventStore``, ``KnowledgeRepository``,
    # ``PromotionRepository``, ``PolicyStore``) por duck typing
    # estructural: sus métodos públicos coinciden con las firmas
    # declaradas en ``skillgraph.platform.ports``. Estas factorías
    # permiten a los consumidores del core (RunController, EventLog)
    # recibir la abstracción sin acoplarse a la clase concreta
    # ``Storage``. La factoría devuelve ``self`` para preservar el
    # sharing de conexión: cualquier mutación sobre ``Storage``
    # sigue siendo visible de inmediato para los adapters.
    #
    # Cuando se introduzcan ``SqliteRunRepository`` etc. en WI-02b,
    # estas factorías pueden delegar a ellos sin cambiar la firma.

    def run_repository(self) -> SqliteRunRepository:
        """Devuelve el componente REAL del cluster runs (WI-56).

        Una unica instancia por ``Storage`` (cacheada): identidad
        estable entre llamadas, conexion compartida, SQL viviendo en
        ``platform/run_repository.py``. El facade conserva delegados
        con firma explicita por compatibilidad con los call-sites
        existentes (REQ-WI56-1/I1: cero ediciones en callers).
        ``getattr`` (y no acceso directo) porque los dobles de test
        que heredan de ``Storage`` sin pasar por ``__init__``
        (``ConnFaultyStorage``) no tienen el slot.
        """
        if getattr(self, "_run_repository", None) is None:
            from skillgraph.platform.run_repository import SqliteRunRepository

            self._run_repository = SqliteRunRepository(self)
        return self._run_repository

    # ----- delegados del cluster runs (WI-56 corte 1) ---------------
    # El SQL vive en ``SqliteRunRepository``; estos delegados con
    # firma explicita preservan la API del facade (I1: cero
    # ediciones en callers) y mantienen auditable la superficie
    # (el guard WI-45 comprueba keywords contra estas firmas).

    def promotion_repository(self) -> SqlitePromotionRepository:
        """Devuelve el componente REAL del cluster promotions (WI-56).

        Una unica instancia por ``Storage`` (cacheada): identidad
        estable y conexion compartida. El SQL del outbox de promocion
        (H7) vive en ``platform/promotion_repository.py`` desde el
        corte 5 de WI-56/ADR-0016. Los helpers atomicos de eventos
        permanecen en ``Storage`` (H9/H10). ``getattr`` por los dobles
        de test que heredan sin ``__init__``.
        """
        if getattr(self, "_promotion_repository", None) is None:
            from skillgraph.platform.promotion_repository import (
                SqlitePromotionRepository,
            )

            self._promotion_repository = SqlitePromotionRepository(self)
        return self._promotion_repository

    def event_store(self) -> SqliteEventStore:
        """Devuelve el componente REAL del cluster events (WI-56).

        Antes devolvia ``self`` (structural subtyping con el
        Protocol ``EventStore``); desde el corte 4 de WI-56/ADR-0016
        devuelve la instancia real de ``SqliteEventStore`` (cacheada):
        identidad estable, conexion compartida, SQL viviendo en
        ``platform/event_store.py``. Los helpers atomicos
        ``_insert_event_in_tx`` / ``_atomic_state_and_event`` siguen
        en ``Storage`` (H9/H10). ``getattr`` por los dobles de test
        que heredan sin ``__init__``.
        """
        if getattr(self, "_event_store", None) is None:
            from skillgraph.platform.event_store import SqliteEventStore

            self._event_store = SqliteEventStore(self)
        return self._event_store

    def knowledge_repository(self) -> SqliteKnowledgeRepository:
        """Devuelve el componente REAL del cluster knowledge (WI-56).

        Antes (WI-31) devolvia ``self`` (structural subtyping); desde
        el corte 3 de WI-56/ADR-0016 devuelve la instancia real de
        ``SqliteKnowledgeRepository`` (cacheada): identidad estable,
        conexion compartida, SQL viviendo en
        ``platform/knowledge_repository.py``. El facade conserva
        delegados con firma explicita por compatibilidad con los
        call-sites existentes (REQ-WI56-1/I1: cero ediciones en
        callers). ``getattr`` (y no acceso directo) por los dobles de
        test que heredan sin ``__init__``.
        """
        if getattr(self, "_knowledge_repository", None) is None:
            from skillgraph.platform.knowledge_repository import (
                SqliteKnowledgeRepository,
            )

            self._knowledge_repository = SqliteKnowledgeRepository(self)
        return self._knowledge_repository

    def policy_store(self) -> SqlitePolicyStore:
        """Devuelve el componente REAL del cluster policy/budget (WI-56).

        Una unica instancia por ``Storage`` (cacheada): identidad
        estable, conexion compartida, SQL viviendo en
        ``platform/policy_store.py``. El facade conserva delegados
        con firma explicita (I1: cero ediciones en callers).
        """
        if getattr(self, "_policy_store", None) is None:
            from skillgraph.platform.policy_store import SqlitePolicyStore

            self._policy_store = SqlitePolicyStore(self)
        return self._policy_store

    # ----- delegados policy/budget (WI-56 corte 2) -----------------
    # El SQL vive en ``SqlitePolicyStore``; delegados con firma
    # explicita preservan la API del facade.

    # ----- ciclo de vida -----

    @staticmethod
    def _anade_column_claims_assertion_origin(cur: sqlite3.Cursor) -> None:
        """Anade `claims.assertion_origin` si la tabla ya existia sin ella (B6).

        `CREATE TABLE IF NOT EXISTS` NO anade columnas a una tabla que ya
        existe: es un no-op silencioso. Medido: abriendo una base creada con
        el esquema anterior, la columna no aparecia y todos los `SELECT`
        que la nombran fallaban. Una base nueva funciona y una vieja no,
        y el fallo aparece en produccion y no en los tests, porque los
        tests construyen la base desde cero cada vez.

        Por que NO es check-then-act otra vez: B2 ya sufrio por aqui, con
        ocho procesos concurrentes perdiendo escrituras. SQLite no tiene
        `ADD COLUMN IF NOT EXISTS`, asi que no se puede resolver por
        constraint como el resto. Lo que se hace es que el `ALTER` este
        dentro de la transaccion de `_migrate` y que el error de «columna
        duplicada» —que es lo que daria el segundo proceso— se traguen
        SOLO si la columna existe ya. Se distingue la causa en el nombre
        del error, no se captura a pelo: capturar `sqlite3.OperationalError`
        entero se tragaria tambien un disco lleno.
        """
        columnas = {fila[1] for fila in cur.execute("PRAGMA table_info(claims)")}
        if "assertion_origin" in columnas:
            return
        try:
            cur.execute(
                "ALTER TABLE claims ADD COLUMN assertion_origin "
                "TEXT NOT NULL DEFAULT 'observed' CHECK (assertion_origin IN ("
                "'observed','derived-deterministically','agent-inferred',"
                "'human-asserted'))"
            )
        except sqlite3.OperationalError as exc:
            # Solo la carrera de dos procesos anadiendo la misma columna.
            if "duplicate column name" not in str(exc).lower():
                raise

    def _migrate(self) -> None:
        with self._tx() as cur:
            cur.executescript(_SCHEMA_SQL)
            self._anade_column_claims_assertion_origin(cur)
            # MEDIDO en B2: esto era `SELECT` y, si no habia fila,
            # `INSERT`. Es un **check-then-act**: dos procesos que abren
            # la base nueva a la vez ven ambos que `schema_version` esta
            # vacia, y los dos insertan. El `UNIQUE(version)` que
            # declara el propio esquema convierte la carrera en un
            # `IntegrityError` en el segundo, y ese proceso muere al
            # construirse —perdiendose todas sus escrituras, sin que
            # nadie lo note—. Con ocho procesos concurrentes, la
            # mayoria de las corridas fallaban.
            #
            # `INSERT OR IGNORE` no evita la carrera: la sigue habiendo.
            # Lo que hace es dejar que la **constraint** la resuelva, que
            # es la regla del repositorio (`AGENTS.md §8`: «idempotencia
            # por constraint, no por codigo»). El `SELECT` desaparece
            # porque era el que hacia la decision, y la decision no hace
            # falta: insertar la version dos veces da el mismo resultado
            # que insertarla una.
            cur.execute(
                "INSERT OR IGNORE INTO schema_version(version) VALUES (?)",
                (SCHEMA_VERSION,),
            )

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Cursor]:
        # Aislamiento "deferred" por defecto de sqlite3; el commit ocurre
        # al salir del bloque sin error. Si algo lanza, sqlite3 hace rollback.
        with self._conn:
            yield self._conn.cursor()

    @contextmanager
    def _atomic(self) -> Iterator[sqlite3.Cursor]:
        """Transaccion explicita con BEGIN/COMMIT/ROLLBACK.

        Necesario para operaciones multi-statement en las que un fallo
        a mitad NO deba dejar estado parcial en disco (H9-LIMITACION-7,
        V4 `record_trace`). `isolation_level=None` en `_conn` hace que
        cada `execute()` sea autocommit, por lo que `with self._conn:`
        NO rollbackea de verdad — la salida del bloque solo emite
        COMMIT o ROLLBACK si Python lo solicita explicitamente.

        Este helper:
          1. Emite `BEGIN` (start de transaccion manual).
          2. Yieldea un cursor sobre la conexion transaccional.
          3. Si el bloque retorna sin error: COMMIT explicito.
          4. Si el bloque lanza: ROLLBACK explicito + re-raise.

        Uso:
            with self._atomic() as cur:
                cur.execute(...)  # serollbackea si falla
                cur.execute(...)

        Tests: `tests/test_h9_limitacion_7_slice1.py::TestT17RecordTrace`.
        """
        self._conn.execute("BEGIN")
        cur = self._conn.cursor()
        try:
            yield cur
            self._conn.execute("COMMIT")
        except BaseException:
            # ROLLBACK es best-effort: si falla (p.ej. la conexion
            # esta rota), sqlite3 abortara la transaccion de todos
            # modos. Coherente con el patron de `*_atomically`.
            # Se capturan TODAS las excepciones (incluido KeyboardInterrupt)
            # porque el proposito es dejar la transacion consistente
            # antes de propagar: un `except Exception` dejaria el BEGIN
            # abierto si el fallo es una BaseException: un Ctrl-C no
            # debe dejar la transaccion a medias.
            with suppress(sqlite3.Error):
                self._conn.execute("ROLLBACK")
            raise

    # ----- recursos -----

    # ----- delegados del cluster knowledge (WI-56 corte 3) --------
    # El SQL vive en ``SqliteKnowledgeRepository``; delegados con
    # firma explicita preservan la API del facade (I1: cero
    # ediciones en callers).

    # ----- relaciones -----

    # ----- H3 Slice 1: conocimiento (sources, entities, claims, etc.) -----
    #
    # Estas APIs NO son CRUD plano: devuelven los ADT de `skillgraph.knowledge`
    # cuando es posible, y dejan la logica de negocio (invalidacion
    # transitiva, hashing, glosario) al KnowledgeController que se introduce
    # en Slice 2.

    # ---- Sources

    # ---- Entities

    # ---- Evidences

    # ---- Claims

    # ---- WI-02b: ports de mantenimiento (invalidation, refresh) ----

    # ---- H9-Coverage-11: lecturas puras para ContextController (ADR-0014)
    #
    # Estas 3 APIs cierran los 4 sitios `_conn.execute` directos que
    # quedaron en ContextController despues del refactor H9-BSlice3.
    # Devuelven tuplas inmutables (no list) para mantener consistencia
    # con la regla "inmutabilidad por defecto" (AGENTS.md §1.1) y para
    # que el caller no pueda mutar el resultado por accidente.

    # ---- Findings

    # ---- Outcome traces

    # ----- Events (H3 Slice 4) -----

    # ----- delegados del cluster events (WI-56 corte 4) ----------
    # El SQL vive en ``SqliteEventStore``; delegados con firma
    # explicita preservan la API del facade (I1: cero ediciones en
    # callers). Los helpers atomicos _insert_event_in_tx y
    # _atomic_state_and_event siguen AQUI (H9/H10 los parchean).

    # ----- H7 promocion entre bases (UAT-13) -----

    # ----- lecturas del ciclo de vida de un Run (H9-BSlice3-S1) -----

    def _insert_event_in_tx(
        self,
        cur: sqlite3.Cursor,
        event: RuntimeEvent,
    ) -> None:
        """Inserta un RuntimeEvent en `runtime_events` usando el cursor
        dado (que pertenece a una transaccion ya abierta por el caller).

        NO llama `cur.connection.commit()` ni `with self._conn:`. El
        caller controla la transaccion.

        **WI-114: aqui es donde se traduce el error del adapter.** El
        `UNIQUE(event_id)` de la tabla es lo que detecta el duplicado —
        la idempotencia vive en el constraint, no en codigo — pero el
        QUE sale de aqui lo decide este metodo, y no cada llamador. Un
        `sqlite3.IntegrityError` que escapara no es `SkillGraphError`,
        luego atraviesa el `except` que traduce a exit code y le llega
        al usuario como Traceback. Los cinco caminos de escritura que
        llamaban a este helper se ocupaban de traducirlo cada uno por su
        cuenta, y esa era una convencion, no una garantia: bastaba un
        llamador nuevo sin `try` para que la frontera se abriera.
        """
        import json as _json

        try:
            cur.execute(
                """
                INSERT INTO runtime_events
                    (event_id, tenant_id, project_id, event_kind, run_id,
                     resource_ref, causation_id, correlation_id,
                     payload_json, timestamp, schema_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.tenant_id,
                    event.project_id,
                    event.event_kind,
                    event.run_id,
                    event.resource_ref,
                    event.causation_id,
                    event.correlation_id,
                    _json.dumps(dict(event.payload), ensure_ascii=False),
                    event.timestamp,
                    event.schema_version,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise IdempotencyError(
                f"evento duplicado: UNIQUE(event_id) violada para {event.event_id!r}"
            ) from exc

    def _atomic_state_and_event(
        self,
        *,
        event: RuntimeEvent,
        exec_sql: tuple[str, tuple[Any, ...]],
    ) -> None:
        """Ejecuta una sentencia de mutacion de estado + el INSERT del
        evento en runtime_events bajo una SOLA transaccion SQLite
        (BEGIN explicito + COMMIT/ROLLBACK).

        Esto es necesario porque `with self._conn:` con
        ``isolation_level=None`` NO rollbackea al fallar dentro del
        cuerpo (cada ``execute`` ejecuta autocommit por sentencia).
        Plan B arranca de esta verididad: ver
        ``docs/architecture/h9-plan-b-atomicity-characterization.md``
        §3 (grieta H9-Plan-B) y §5 (estrategia).

        Un ``event_id`` duplicado sale como ``IdempotencyError``
        (UAT-07, replay-safe). **WI-114:** la traduccion la hace
        ``_insert_event_in_tx``, que es donde ocurre el INSERT, y este
        metodo solo se asegura el ROLLBACK. Antes de WI-114 este
        docstring decia «Re-raise como ``IdempotencyError``» y aqui no se
        traducia nada: lo hacia cada uno de los cinco llamadores, por
        convencion y sin ningun guard. Un docstring que promete una
        garantia que su cuerpo no da es una promesa que el codigo no
        cumple.
        """
        try:
            self._conn.execute("BEGIN")
            self._conn.execute(exec_sql[0], exec_sql[1])
            self._insert_event_in_tx(self._conn.cursor(), event)
            self._conn.execute("COMMIT")
        except BaseException:
            # El cuerpo de la transaccion puede lanzar CUALQUIER cosa
            # (validacion de dominio, TypeError, ...), no solo errores
            # de sqlite3. Estrechar aqui a `sqlite3.Error` dejaba el
            # BEGIN abierto ante un ValidationError, que es peor que
            # el except ancho que se queria evitar. Lo que si se
            # estrecha es el ROLLBACK, que solo habla de la conexion.
            with suppress(sqlite3.Error):
                self._conn.execute("ROLLBACK")
            raise


# --- Helpers de conversion row -> ADT -------------------------------------


def open_project_storage(path: str | Path) -> Storage:
    """Ayuda para abrir el almacenamiento de un proyecto.

    Cualquier error de validación aquí es bug: este helper no debería
    recibir paths fuera de los directorios gestionados por la CLI.
    """
    if not str(path).endswith(".sqlite"):
        raise ValidationError(f"Path de proyecto debe terminar en .sqlite: {path}")
    return Storage(path)
