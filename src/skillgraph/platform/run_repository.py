"""SqliteRunRepository: componente real de runs para WI-56 (ADR-0016).

Extrae el cluster de SQL de runs de ``Storage`` (19 metodos) siguiendo
el corte 1 de la ADR-0016: mismo SQL, mismo orden de parametros, misma
semantica transaccional, cero ediciones en callers.

El componente comparte la ``sqlite3.Connection`` del ``Storage`` (I3):
no abre conexiones propias, no duena el schema (I4) y los helpers
atomicos ``_insert_event_in_tx`` / ``_atomic_state_and_event`` se
resuelven TARDE via ``self._storage`` para que el monkeypatch de los
tests H9/H10 sobre ``storage._insert_event_in_tx`` siga surtiendo
efecto (I1). Las fachadas ``run_repository()`` y ``uow.runs`` pasan a
devolver esta instancia cacheada; ``Storage`` conserva los 19 metodos
como delegados de una linea (634 call-sites sin tocar, REQ-WI56-1).
"""

from __future__ import annotations

import sqlite3
from contextlib import suppress
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from skillgraph.runtime.engine import RuntimeEvent

from skillgraph.core.errors import IdempotencyError, NotFoundError
from skillgraph.core.runtime_types import NON_TERMINAL_RUN_STATES
from skillgraph.platform.ports import (
    StoredEvent,
    StoredNodeExecution,
    StoredRun,
)
from skillgraph.platform.row_mappers import (
    _row_to_node_execution,
    _row_to_run,
    _row_to_stored_event,
)
from skillgraph.platform.storage import Storage

__all__ = ["SqliteRunRepository"]


class SqliteRunRepository:
    """Implementacion real de ``RunRepository`` sobre la conexion de
    ``Storage``. No duena el schema ni la migracion; solo habla SQL
    del cluster runs con la misma forma que ``Storage`` tenia."""

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @property
    def _conn(self) -> sqlite3.Connection:
        """Conexion compartida con el ``Storage`` dueno del schema."""
        return self._storage._conn  # composicion interna acordada en ADR-0016

    def find_active_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
    ) -> str | None:
        """Devuelve el run_id del Run mas reciente en estado no terminal
        para (tenant, project), o ``None`` si no hay ninguno.

        No terminal = ``CREATED``, ``ACTIVE`` o ``WAITING`` (ver
        ``NON_TERMINAL_RUN_STATES``). ``COMPLETED``, ``FAILED`` y
        ``CANCELLED`` se consideran terminales: el siguiente ``sg run``
        debe crear un Run nuevo.

        Cumple UAT-06: tras un crash con un Run ACTIVE, el CLI lo
        encuentra y lo reanuda en lugar de crear otro.
        """
        # Construir placeholders de tamaño dinamico (NO expone SQL al caller,
        # solo la consulta SQL).
        placeholders = ",".join("?" * len(NON_TERMINAL_RUN_STATES))
        params: list[Any] = [*NON_TERMINAL_RUN_STATES, tenant_id, project_id]
        row = self._conn.execute(
            f"""
            SELECT run_id FROM workflow_runs
            WHERE state IN ({placeholders})
              AND tenant_id = ? AND project_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            params,
        ).fetchone()
        if row is None:
            return None
        return row["run_id"]

    def list_runs(
        self,
        *,
        tenant_id: str,
        project_id: str,
        state: str | None = None,
        limit: int = 50,
    ) -> list[StoredRun]:
        """Lista Runs de un (tenant, project) ordenados por mas reciente.

        Args:
            state: si se da, filtra por estado exacto (e.g. "CREATED",
                "ACTIVE", "COMPLETED", "FAILED", "CANCELLED").
            limit: tope de filas devueltas (default 50). 0 o negativo
                se trata como sin limite.

        Orden por `rowid DESC` (monótono, mas reciente primero).
        No usamos `created_at` porque SQLite lo genera con
        `datetime('now')` y dos inserciones en el mismo segundo
        empatan.

        Lectura pura: no participa en transacciones compartidas.

        WI-32.4: devuelve ``list[StoredRun]`` (frozen + slots) en
        vez de ``list[dict[str, Any]]``, evitando que ``sqlite3.Row``
        escape de ``platform/``.
        """
        if limit <= 0:
            limit = 10**9  # cap practico: no necesitamos >10^9 runs
        sql = (
            "SELECT run_id, tenant_id, project_id, state, current_node, "
            "       plan_json, created_at, updated_at "
            "FROM workflow_runs "
            "WHERE tenant_id = ? AND project_id = ?"
        )
        params: list[Any] = [tenant_id, project_id]
        if state is not None:
            sql += " AND state = ?"
            params.append(state)
        sql += " ORDER BY rowid DESC LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_run(r) for r in rows]

    def get_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> StoredRun:
        """Devuelve el DTO de un Run.

        Lanza ``NotFoundError`` si no existe. API explicita para que
        `RunController.show_run` no dependa de `load_run` (que es
        la API de runtime pero tiene la misma semantica).

        WI-32.4: devuelve ``StoredRun`` (frozen + slots) en vez de
        ``dict`` mutable, evitando que ``sqlite3.Row`` escape de
        ``platform/``.
        """
        row = self._conn.execute(
            "SELECT run_id, tenant_id, project_id, state, current_node, "
            "       plan_json, created_at, updated_at "
            "FROM workflow_runs "
            "WHERE tenant_id = ? AND project_id = ? AND run_id = ?",
            (tenant_id, project_id, run_id),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"run no encontrado: {run_id}")
        return _row_to_run(row)

    def list_events_for_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> list[StoredEvent]:
        """Lista eventos de un Run ordenados por sequence ASC.

        Lectura pura: usada por `RunController.logs_run` para
        mostrar el timeline de eventos al operador. NO filtra por
        `correlation_id` porque el `run_id` ya esta indexado
        (`events_by_run`).

        WI-32.2: mapea ``Row -> StoredEvent`` antes de devolver. El
        consumer (RunController/EventLog) recibe DTOs inmutables en
        vez de filas SQLite.
        """
        rows = self._conn.execute(
            "SELECT * FROM runtime_events "
            "WHERE tenant_id = ? AND project_id = ? AND run_id = ? "
            "ORDER BY sequence ASC",
            (tenant_id, project_id, run_id),
        ).fetchall()
        return [_row_to_stored_event(r) for r in rows]

    def load_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> StoredRun:
        """Carga el DTO de `workflow_runs` para (tenant, project, run).

        Lanza ``NotFoundError`` si no existe. Sustituye a la lectura
        directa sobre ``self._conn.execute(...)`` que realizaba
        ``RunController._load_run``. Es una lectura pura: no participa
        en transacciones compartidas con ``EventLog.append``.

        WI-32.4: devuelve ``StoredRun`` (frozen + slots) en vez de
        ``dict``. ``RunController`` consume el DTO directamente sin
        depender de ``sqlite3``.
        """
        row = self._conn.execute(
            """
            SELECT * FROM workflow_runs
            WHERE tenant_id = ? AND project_id = ? AND run_id = ?
            """,
            (tenant_id, project_id, run_id),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"run no encontrado: {run_id}")
        return _row_to_run(row)

    def list_node_executions(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        node_name: str,
    ) -> list[StoredNodeExecution]:
        """Lista NodeExecutions de un (run, node_name) ordenadas por
        ``started_at ASC``.

        Sustituye a la lectura directa que realizaba
        ``RunController._node_executions_for``. Lectura pura:
        orden estable, sin filtrado por estado (la query del
        RunController original tampoco filtraba).

        WI-32.4: devuelve ``list[StoredNodeExecution]`` en vez de
        ``list[dict]``.
        """
        rows = self._conn.execute(
            """
            SELECT * FROM node_executions
            WHERE tenant_id = ? AND project_id = ? AND run_id = ?
              AND node_name = ?
            ORDER BY started_at ASC
            """,
            (tenant_id, project_id, run_id, node_name),
        ).fetchall()
        return [_row_to_node_execution(r) for r in rows]

    # ---------- H9-Plan-B: APIs atomicas estado+evento ----------
    #
    # Estas APIs combinan la mutacion de `node_executions` con la insercion
    # de su(s) evento(s) en `runtime_events`, todo dentro de UNA transaccion
    # SQLite sobre `self._conn`. Si cualquier INSERT o UPDATE falla, ROLLBACK
    # automatico: no se confirma el estado ni el evento, garantizando la

    def list_executed_node_names(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> tuple[str, ...]:
        """Devuelve los `node_name` DISTINCT con ``state='SUCCEEDED'``
        para un run, ordenados alfabéticamente.

        Sustituye a la lectura directa que realizaba
        ``RunController._executed_node_names``. Lectura pura: el orden
        alfabético hace el resultado determinista y testeable sin
        depender del orden de inserción.
        """
        rows = self._conn.execute(
            """
            SELECT DISTINCT node_name FROM node_executions
            WHERE tenant_id = ? AND project_id = ? AND run_id = ?
              AND state = 'SUCCEEDED'
            ORDER BY node_name ASC
            """,
            (tenant_id, project_id, run_id),
        ).fetchall()
        return tuple(r["node_name"] for r in rows)

    def recover_interrupted_node_executions(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> int:
        """Transiciona TODOS los NodeExecution en ``RUNNING`` sin
        ``finished_at`` a ``READY`` para un run.

        Sustituye a ``RunController._recover_interrupted``: el original
        abría una transacción por cada fila (bucle ``for r in rows: with
        self._conn: ...``). Esta versión abre UNA sola transacción para
        todas las filas. Es una escritura atómica en sí misma: si algo
        falla dentro de la operación, ninguna fila queda a medias.

        Esta operación NO emite eventos. S4 del plan H9-BSlice3.

        Devuelve el número de filas recuperadas (0 si no había ninguna).
        """
        with self._conn:
            cur = self._conn.execute(
                """
                UPDATE node_executions
                SET state = 'READY', finished_at = datetime('now')
                WHERE tenant_id = ? AND project_id = ? AND run_id = ?
                  AND state = 'RUNNING' AND finished_at IS NULL
                """,
                (tenant_id, project_id, run_id),
            )
            return cur.rowcount

    def transition_run_state(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        state: str,
        current_node: str | None,
    ) -> None:
        """Transiciona el ``state`` y/o ``current_node`` de un Run.

        UPDATE no-op si el run no existe. Sustituye a
        ``RunController._set_run_state``.

        No emite eventos. Si la operación debe ir coordinada con
        ``EventLog.append`` (lo más habitual), el llamador hace el
        append DESPUES. Esto preserva el contrato actual: la
        atomicidad entre state y eventos sigue siendo responsabilidad
        del orquestador (RunController), no de Storage. Ver decisión
        arquitectónica del 2026-09-23 18:24.

        ``state`` debe ser uno de los literales ``RunState``; validación
        tipica la hace el type checker, no este método (Storage expone
        ``str`` para no acoplarse a tipos del runtime).
        """
        with self._conn:
            self._conn.execute(
                """
                UPDATE workflow_runs
                SET state = ?, current_node = ?,
                    updated_at = datetime('now')
                WHERE tenant_id = ? AND project_id = ? AND run_id = ?
                """,
                (state, current_node, tenant_id, project_id, run_id),
            )

    def start_node_execution(
        self,
        *,
        node_execution_id: str,
        tenant_id: str,
        project_id: str,
        run_id: str,
        node_name: str,
        attempt: int,
        context_hash: str,
        handoff_json: str,
    ) -> None:
        """Inserta un NodeExecution en estado ``RUNNING``.

        Sustituye a la parte INSERT del RunController._execute_one.
        El ``node_execution_id`` lo genera el llamador (ver
        ``new_node_execution_id``); el state queda fijado a
        ``RUNNING`` y ``started_at`` se materializa en SQL con
        ``datetime('now')``.

        No emite eventos. La coordinación con
        ``EventLog.append(events.node_started(...))`` sigue siendo
        del llamador (RunController._execute_one).
        """
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO node_executions
                    (node_execution_id, run_id, tenant_id, project_id,
                     node_name, attempt, state, context_hash, handoff_json,
                     started_at)
                VALUES (?, ?, ?, ?, ?, ?, 'RUNNING', ?, ?, datetime('now'))
                """,
                (
                    node_execution_id,
                    run_id,
                    tenant_id,
                    project_id,
                    node_name,
                    attempt,
                    context_hash,
                    handoff_json,
                ),
            )

    def complete_node_execution(
        self,
        *,
        node_execution_id: str,
        outcome: str,
        result_json: str,
    ) -> None:
        """Transiciona un NodeExecution a ``SUCCEEDED`` con outcome y
        result_json ya serializado.

        Sustituye a la parte UPDATE SUCCEEDED del RunController._execute_one.

        No emite eventos. La coordinacion con
        ``EventLog.append(events.node_completed(...))`` y
        ``EventLog.append(events.evidence_produced(...))`` sigue siendo
        del llamador.

        ``result_json`` debe llegar ya como string (la API no serializa;
        es responsabilidad del llamador que ``result`` sea JSON-able).
        """
        with self._conn:
            self._conn.execute(
                """
                UPDATE node_executions
                SET state = 'SUCCEEDED', outcome = ?, result_json = ?,
                    finished_at = datetime('now')
                WHERE node_execution_id = ?
                """,
                (outcome, result_json, node_execution_id),
            )

    def mark_node_failed(
        self,
        *,
        node_execution_id: str,
        error: str,
    ) -> None:
        """Transiciona un NodeExecution a ``FAILED`` con un mensaje de
        error legible (sin stack).

        Sustituye a ``RunController._mark_node_failed``.

        No emite eventos. La coordinacion con
        ``EventLog.append(events.node_failed(...))`` sigue siendo del
        llamador.
        """
        with self._conn:
            self._conn.execute(
                """
                UPDATE node_executions
                SET state = 'FAILED', error = ?, finished_at = datetime('now')
                WHERE node_execution_id = ?
                """,
                (error, node_execution_id),
            )

    def start_node_execution_atomically(
        self,
        *,
        event: RuntimeEvent,
        node_execution_id: str,
        tenant_id: str,
        project_id: str,
        run_id: str,
        node_name: str,
        attempt: int,
        context_hash: str,
        handoff_json: str,
    ) -> None:
        """Inserta NodeExecution RUNNING y el evento `NodeStarted` en
        la MISMA transaccion. Si algo falla, rollback completo.

        Idempotente por `UNIQUE(event_id)`: reintentos con el mismo
        `event.event_id` lanzan `IdempotencyError` y rollbackean la
        fila (si se intento re-insertar). Equivalente semantico a
        "el primer commit gana".

        H9-Plan-B: cierra la grieta atomica B del documento
        `docs/architecture/h9-plan-b-atomicity-characterization.md` §3.
        """

        sql = (
            "INSERT INTO node_executions "
            "(node_execution_id, run_id, tenant_id, project_id, "
            "node_name, attempt, state, context_hash, handoff_json, "
            "started_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'RUNNING', ?, ?, datetime('now'))"
        )
        params = (
            node_execution_id,
            run_id,
            tenant_id,
            project_id,
            node_name,
            attempt,
            context_hash,
            handoff_json,
        )
        try:
            self._storage._atomic_state_and_event(
                event=event,
                exec_sql=(sql, params),
            )
        except sqlite3.IntegrityError as exc:
            raise IdempotencyError(f"evento duplicado: {event.event_id}") from exc

    def update_node_execution_handoff(
        self,
        *,
        node_execution_id: str,
        context_hash: str,
        handoff_json: str,
    ) -> None:
        """Persiste el context_hash y el handoff_json definitivos de una
        NodeExecution ya insertada (H9-context-in-run).

        La fila se crea con placeholders vacios antes de compilar el
        handoff (para que un fallo de compilacion pueda dejarla FAILED
        via `mark_node_failed_atomically`); este UPDATE la rellena.
        """
        self._conn.execute(
            "UPDATE node_executions "
            "SET context_hash = ?, handoff_json = ? "
            "WHERE node_execution_id = ?",
            (context_hash, handoff_json, node_execution_id),
        )
        self._conn.commit()

    def complete_node_execution_atomically(
        self,
        *,
        event_completed: RuntimeEvent,
        event_evidence: RuntimeEvent,
        node_execution_id: str,
        outcome: str,
        result_json: str,
    ) -> None:
        """Actualiza NodeExecution a SUCCEEDED + inserta `NodeCompleted`
        + inserta `EvidenceProduced` en la MISMA transaccion.

        H9-Plan-B: cierra la grieta atomica C del documento
        `docs/architecture/h9-plan-b-atomicity-characterization.md` §3.
        """

        sql = (
            "UPDATE node_executions "
            "SET state = 'SUCCEEDED', outcome = ?, result_json = ?, "
            "finished_at = datetime('now') "
            "WHERE node_execution_id = ?"
        )
        params = (outcome, result_json, node_execution_id)
        try:
            self._conn.execute("BEGIN")
            self._conn.execute(sql, params)
            cur = self._conn.cursor()
            self._storage._insert_event_in_tx(cur, event_completed)
            self._storage._insert_event_in_tx(cur, event_evidence)
            self._conn.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            with suppress(sqlite3.Error):
                self._conn.execute("ROLLBACK")
            raise IdempotencyError(
                f"evento duplicado en complete_node_execution_atomically: "
                f"{event_completed.event_id} o {event_evidence.event_id}"
            ) from exc
        except BaseException:
            # Cualquier otro fallo dentro de la transaccion: ROLLBACK
            # best-effort y se propaga intacto. Ver el comentario de
            # `_tx` para por que `BaseException` y no `Exception`.
            with suppress(sqlite3.Error):
                self._conn.execute("ROLLBACK")
            raise

    def mark_node_failed_atomically(
        self,
        *,
        event: RuntimeEvent,
        node_execution_id: str,
        error: str,
    ) -> None:
        """Actualiza NodeExecution a FAILED + inserta `NodeFailed` en
        la MISMA transaccion.

        H9-Plan-B: cierra la grieta atomica D del documento
        `docs/architecture/h9-plan-b-atomicity-characterization.md` §3.
        """

        sql = (
            "UPDATE node_executions "
            "SET state = 'FAILED', error = ?, finished_at = datetime('now') "
            "WHERE node_execution_id = ?"
        )
        params = (error, node_execution_id)
        try:
            self._storage._atomic_state_and_event(
                event=event,
                exec_sql=(sql, params),
            )
        except sqlite3.IntegrityError as exc:
            raise IdempotencyError(f"evento duplicado: {event.event_id}") from exc

    def create_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        plan_json: str,
        initial_node: str,
    ) -> str:
        """Crea un Run en estado ``CREATED`` y devuelve su ``run_id``.

        Sustituye al INSERT directo del ``RunController.create_run``.
        El ``run_id`` se genera aqui (Storage es la unica pieza que
        sabe de IDs). El plan se persiste como JSON ya serializado
        (responsabilidad del caller preservar el ``sort_keys=True``).

        No emite eventos. La coordinacion con
        ``EventLog.append(events.run_created(...))`` sigue siendo del
        llamador.
        """
        # Import lazy para evitar ciclo runtime<->platform: la
        # funcion generadora de IDs vive en runtime.runcontroller
        # (Etapa 0), pero este modulo (Storage) no debe importarlo en
        # top-level. El coste de un import por llamada es nulo
        # (importlib lo cachea) frente al riesgo de un ciclo.
        from skillgraph.runtime.runcontroller import new_run_id

        run_id = new_run_id()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO workflow_runs
                    (run_id, tenant_id, project_id, state, plan_json,
                     current_node)
                VALUES (?, ?, ?, 'CREATED', ?, ?)
                """,
                (
                    run_id,
                    tenant_id,
                    project_id,
                    plan_json,
                    initial_node,
                ),
            )
        return run_id

    def create_run_atomically(
        self,
        *,
        event: RuntimeEvent,
        run_id: str,
        tenant_id: str,
        project_id: str,
        plan_json: str,
        initial_node: str,
    ) -> str:
        """Crea un Run en estado ``CREATED`` y emite el evento
        ``RunCreated`` en UNA SOLA transaccion SQLite.

        Esta es la grieta A del
        ``h9-plan-b-atomicity-characterization.md``: ``Storage.create_run``
        hace INSERT + COMMIT en una transaccion, y ``EventLog.append``
        hace INSERT + COMMIT en otra. Si la segunda falla (fault
        injection, ``MemoryError``, etc.), el run quedaba confirmado
        sin su evento. Aqui ambas escrituras viven en el mismo
        ``BEGIN/COMMIT/ROLLBACK`` via ``_atomic_state_and_event``.

        El ``run_id`` lo aporta el caller (tipicamente el RunController
        via ``new_run_id()``) para que el evento pueda construirse
        con el run_id final antes de la transaccion (consumidores del
        evento esperan ver el run_id, no un placeholder). La firma
        del evento y sus campos se preservan intactos; el llamador
        construye el ``RuntimeEvent`` con ``EventBuilder.run_created(...)``
        y lo pasa aqui.

        Idempotencia: el UNIQUE sobre ``runtime_events.event_id``
        cumple UAT-07 (replay-safe). Si un proceso cae tras commitear
        la transaccion completa y reintenta con el mismo ``event_id``,
        la segunda invocacion lanza ``IdempotencyError``. En ese caso
        el run ya esta creado (commit anterior), y el caller debe
        tratar el duplicado como exito idempotente, no como fallo.

        Equivalencia con ``create_run``:
          - El INSERT en workflow_runs usa los mismos campos y valores.
          - El ``run_id`` que se persiste es el que el caller aporto.
        """

        sql = (
            "INSERT INTO workflow_runs "
            "(run_id, tenant_id, project_id, state, plan_json, current_node) "
            "VALUES (?, ?, ?, 'CREATED', ?, ?)"
        )
        params = (
            run_id,
            tenant_id,
            project_id,
            plan_json,
            initial_node,
        )
        try:
            self._storage._atomic_state_and_event(
                event=event,
                exec_sql=(sql, params),
            )
        except sqlite3.IntegrityError as exc:
            raise IdempotencyError(
                f"evento duplicado en create_run_atomically: {event.event_id}"
            ) from exc
        return run_id

    def transition_run_state_atomically(
        self,
        *,
        event: RuntimeEvent,
        tenant_id: str,
        project_id: str,
        run_id: str,
        state: str,
        current_node: str | None,
    ) -> None:
        """Transiciona el ``state`` y/o ``current_node`` de un Run
        y emite el evento ``RunCompleted`` (o el que corresponda) en
        UNA SOLA transaccion SQLite.

        Esta es la grieta E y la mitad de la G del
        ``h9-plan-b-atomicity-characterization.md``:
        ``Storage.transition_run_state`` y ``EventLog.append`` van en
        commits separados. Aqui ambos viven en el mismo
        ``BEGIN/COMMIT/ROLLBACK``.

        ``state`` debe ser uno de los literales ``RunState``; la
        validacion de tipo la hace el type checker, no este metodo.
        ``current_node`` puede ser ``None`` (transiciones terminales
        que cierran el run: ``COMPLETED`` con ``None``).

        Idempotencia: el UNIQUE sobre ``runtime_events.event_id``
        cumple UAT-07. Si un proceso cae tras commitear la
        transaccion completa, un reintento con el mismo ``event_id``
        lanza ``IdempotencyError``. El caller debe tratarlo como
        exito idempotente.

        UPDATE no-op si el run no existe: la fila simplemente no se
        modifica y el evento SI se inserta. Esto preserva la
        semantica de ``transition_run_state`` original.
        """

        sql = (
            "UPDATE workflow_runs "
            "SET state = ?, current_node = ?, "
            "    updated_at = datetime('now') "
            "WHERE tenant_id = ? AND project_id = ? AND run_id = ?"
        )
        params = (state, current_node, tenant_id, project_id, run_id)
        try:
            self._storage._atomic_state_and_event(
                event=event,
                exec_sql=(sql, params),
            )
        except sqlite3.IntegrityError as exc:
            raise IdempotencyError(
                f"evento duplicado en transition_run_state_atomically: {event.event_id}"
            ) from exc
