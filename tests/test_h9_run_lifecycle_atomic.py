"""H9-limitacion-7 Slice 4: atomicidad workflow_runs <-> eventos del run.

Las 3 grietas del H9-plan-b-atomicity-characterization.md que quedan:

  Ruta A: ``Storage.create_run_atomically`` -- RunCreated + INSERT run en una transaccion.
  Ruta E: ``Storage.transition_run_state_atomically`` FAILED terminal.
  Ruta G: ``Storage.transition_run_state_atomically`` COMPLETED.

Cada test inyecta un fallo en el INSERT de ``runtime_events`` y exige
que el rollback conjunto deje ``workflow_runs`` y ``runtime_events`` en
el mismo estado anterior (ambos INEXISTENTES o ambos YA CONSISTENTES).

Critico: estos tests son de ``Storage``, no del RunController. Verifican
que las APIs atomicas de Storage cumplen el contrato (recuperacion de la
grieta documentada). Para verificacion de extremo a extremo a traves
del RunController existen T12-T14 (atomicidad de nodos) y T15-T20
(regresion LIMITACION-7). El operador autorizo el path Storage para este
slice y prohibio tocar el codigo de RunController fuera de las 3 rutas
autorizadas (create_run, FAILED nodo, FAILED budget + COMPLETED).

Los tests replican las llamadas que hara el RunController contra
``Storage``: ``create_run_atomically`` y ``transition_run_state_atomically``
reciben un ``RuntimeEvent`` y los parametros del run.
"""

from __future__ import annotations

import sqlite3
import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from skillgraph.platform.storage import Storage  # noqa: E402
from skillgraph.runtime.engine import EventBuilder, RuntimeEvent  # noqa: E402

# ---------- infraestructura de fault injection ----------


class _FaultyCursor:
    """Cursor que cuenta ``execute()`` y falla al N-esimo.

    El contrato de ``sqlite3.Connection.cursor().execute(...)`` es lo que
    el Storage usa en transaccion: cada ``exec_sql`` produce un cursor
    fresco y lo ejecuta. ``executescript`` (BEGIN/COMMIT) no falla.
    """

    def __init__(self, real_cursor, counter, fail_at):
        self._cur = real_cursor
        self._counter = counter
        self._fail_at = fail_at

    def execute(self, sql, params=()):
        self._counter["calls"] += 1
        if self._counter["calls"] == self._fail_at:
            raise sqlite3.OperationalError("injected fault: fault_count")
        return self._cur.execute(sql, params)

    def executescript(self, script):
        return self._cur.executescript(script)

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def close(self):
        return self._cur.close()


class _FaultyConnection:
    """Connection que devuelve cursores faltables.

    Sustituye a ``Storage._conn``. Mantiene la identidad: las
    comprobaciones ``is instance(self._conn, sqlite3.Connection)``
    (si las hay) siguen viendose verdaderas gracias al ``__class__``.
    Pero el cursor retornado es nuestro ``_FaultyCursor``.
    """

    # Mantenemos el isinstance real comprando la clase.
    # Pydantic/SQLAlchemy style check requiere duck-typing; aqui
    # el Storage solo usa ``cursor()``, ``commit()``, ``rollback()``,
    # ``close()`` -- los envolvemos todos.

    def __init__(self, real_conn, fail_at):
        self._conn = real_conn
        self._counter = {"calls": 0}
        self._fail_at = fail_at

    def cursor(self):
        return _FaultyCursor(self._conn.cursor(), self._counter, self._fail_at)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    def execute(self, sql, params=()):
        """Cuenta TODAS las sentencias (incluyendo INSERT/UPDATE/SELECT),
        excepto BEGIN/COMMIT/ROLLBACK/SAVEPOINT/RELEASE.

        ``_atomic_state_and_event`` usa ``self._conn.execute(...)`` para
        BEGIN/INSERT-estado y ``cursor().execute(...)`` para el INSERT
        del evento. Ambas formas deben contar porque el fault debe poder
        inyectarse en cualquiera (excepto las control de transaccion).
        """
        op = sql.strip().split(None, 1)[0].upper() if sql.strip() else ""
        if op not in {"BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT", "RELEASE"}:
            self._counter["calls"] += 1
            if self._counter["calls"] == self._fail_at:
                raise sqlite3.OperationalError("injected fault: fault_count")
        return self._conn.execute(sql, params)


class ConnFaultyStorage(Storage):
    """Storage que inyecta un fallo en el N-esimo ``cursor().execute()``.

    Reutiliza la migracion y el ``self._conn`` real; solo envuelve la
    conexion en ``_FaultyConnection`` para que ``_atomic_state_and_event``
    vea cursores faltables.
    """

    def __init__(self, db_path: str, fail_at: int) -> None:
        # Llamamos directamente a sqlite3.connect con la ruta objetivo
        # y luego inyectamos el wrapper. Storage.__init__ ya hizo
        # la migracion; tenemos que abrir otra vez o reusar su pool.
        # Lo mas limpio: dejar que Storage cree su conexion, y
        # luego intercambiarla por el wrapper.
        self._fail_at = fail_at
        # No tocamos Storage.__init__ porque crea self._conn + ejecuta
        # la migracion; replicamos la apertura para poder envolver
        # *antes* de cualquier ejecucion del usuario.

        real = sqlite3.connect(db_path, isolation_level=None)
        real.row_factory = sqlite3.Row
        real.execute("PRAGMA journal_mode=WAL")
        real.execute("PRAGMA foreign_keys=ON")
        faulty = _FaultyConnection(real, fail_at)
        self._conn = faulty
        self._owns_conn = True
        # No ejecutar migracion desde ConnFaultyStorage: la migracion
        # ha de estar hecha de antemano en la BD por un Storage limpio.
        # Asi el wrapper se asocia SOLO a operaciones del usuario.

    @property
    def counter(self) -> int:
        return self._conn._counter["calls"]


@pytest.fixture
def fresh_db(tmp_path):
    """Crea una BD limpia con migracion aplicada, devuelve la ruta."""
    db_path = str(tmp_path / "test_atomicity.sqlite")
    # Aplicar migracion con un Storage limpio y cerrar.
    bootstrap = Storage(path=db_path)
    bootstrap.close()  # type: ignore[attr-defined]
    return db_path


def _run_event(tenant_id: str, project_id: str, run_id: str) -> RuntimeEvent:
    return EventBuilder(
        tenant_id=tenant_id,
        project_id=project_id,
        correlation_id=run_id,
    ).run_created(run_id=run_id, initial_node="start")


def _completed_event(
    tenant_id: str, project_id: str, run_id: str, state: str, at: str | None
) -> RuntimeEvent:
    builder = EventBuilder(
        tenant_id=tenant_id,
        project_id=project_id,
        correlation_id=run_id,
    )
    if state == "COMPLETED":
        return builder.run_completed(run_id=run_id, state="COMPLETED")
    return builder.run_completed(run_id=run_id, state=state, at=at)


# ---------- Test 1: Ruta A -- create_run_atomically ----------


class TestCreateRunEventAtomicity:
    """Ruta A: INSERT workflow_runs + INSERT runtime_events transaccional."""

    def test_create_run_atomicity_with_fault_at_event_insert(self, fresh_db: str) -> None:
        """Falla el INSERT del evento -> el run NO debe quedar creado."""
        tenant_id = "t-ac"
        project_id = "p-ac"
        run_id = "r-ac-" + uuid.uuid4().hex[:8]
        event = _run_event(tenant_id, project_id, run_id)

        # BEGIN pasa por _FaultyConnection.execute pero NO cuenta.
        # INSERT workflow_runs = call #1 (NO falla).
        # INSERT runtime_events = call #2 (FALLA aqui).
        faulty = ConnFaultyStorage(db_path=fresh_db, fail_at=2)
        try:
            with pytest.raises(sqlite3.OperationalError):
                faulty.create_run_atomically(
                    event=event,
                    run_id=run_id,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    plan_json="{}",
                    initial_node="start",
                )
        finally:
            faulty.close()  # type: ignore[attr-defined]

        # Verificar estado: el run NO existe, el evento TAMPOCO.
        # El rollback conjunto debe haber limpiado cualquier escritura.
        verify = Storage(path=fresh_db)
        try:
            run_row = verify._conn.execute(
                "SELECT state FROM workflow_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            event_count = verify._conn.execute(
                "SELECT COUNT(*) FROM runtime_events "
                "WHERE run_id = ? AND event_kind = 'RunCreated'",
                (run_id,),
            ).fetchone()[0]
        finally:
            verify.close()  # type: ignore[attr-defined]

        assert run_row is None, (
            f"GRIETA: workflow_runs tiene run {run_id} a pesar de rollback "
            f"(state={run_row[0] if run_row else None})"
        )
        assert event_count == 0, (
            f"GRIETA: runtime_events tiene {event_count} RunCreated para run {run_id} tras rollback"
        )


# ---------- Test 2: Ruta E -- transition_run_state_atomically (FAILED) ----------


class TestTransitionRunStateEventAtomicity:
    """Ruta E: UPDATE workflow_runs + INSERT runtime_events transaccional."""

    def test_failed_terminal_atomicity_with_fault_at_event_insert(self, fresh_db: str) -> None:
        """El run creado, falla el INSERT del RunCompleted -> rollback conjunto.

        Preparacion: crear un run pre-existente en estado ACTIVE.
        Operacion: transition a FAILED con evento RunCompleted(state=FAILED).
        """
        tenant_id = "t-fe"
        project_id = "p-fe"
        run_id = "r-fe-" + uuid.uuid4().hex[:8]

        # Crear run normal (sin fault).
        bootstrap = Storage(path=fresh_db)
        try:
            bootstrap._conn.execute(
                "INSERT INTO workflow_runs "
                "(run_id, tenant_id, project_id, state, plan_json, current_node) "
                "VALUES (?, ?, ?, 'ACTIVE', '{}', ?)",
                (run_id, tenant_id, project_id, "start"),
            )
            bootstrap._conn.commit()
        finally:
            bootstrap.close()  # type: ignore[attr-defined]

        # Verificar el run existe en ACTIVE y no hay RunCompleted.
        verify_pre = Storage(path=fresh_db)
        try:
            pre_run = verify_pre._conn.execute(
                "SELECT state FROM workflow_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            pre_events = verify_pre._conn.execute(
                "SELECT COUNT(*) FROM runtime_events WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]
        finally:
            verify_pre.close()  # type: ignore[attr-defined]
        assert pre_run is not None and pre_run[0] == "ACTIVE"
        assert pre_events == 0

        event = _completed_event(tenant_id, project_id, run_id, "FAILED", "start")
        # BEGIN NO cuenta. UPDATE workflow_runs = #1. INSERT event = #2 FALLA.
        faulty = ConnFaultyStorage(db_path=fresh_db, fail_at=2)
        try:
            with pytest.raises(sqlite3.OperationalError):
                faulty.transition_run_state_atomically(
                    event=event,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    run_id=run_id,
                    state="FAILED",
                    current_node="start",
                )
        finally:
            faulty.close()  # type: ignore[attr-defined]

        # Verificar: state SIGUE en ACTIVE (rollback conjunto),
        # no hay RunCompleted.
        verify = Storage(path=fresh_db)
        try:
            post_run = verify._conn.execute(
                "SELECT state FROM workflow_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            post_events = verify._conn.execute(
                "SELECT COUNT(*) FROM runtime_events "
                "WHERE run_id = ? AND event_kind = 'RunCompleted'",
                (run_id,),
            ).fetchone()[0]
        finally:
            verify.close()  # type: ignore[attr-defined]

        consistent = post_run is not None and post_run[0] == "ACTIVE" and post_events == 0
        assert consistent, (
            f"GRIETA: rollback incompleto. "
            f"state={post_run[0] if post_run else None} (esperado ACTIVE), "
            f"RunCompleted count={post_events} (esperado 0)"
        )


# ---------- Test 3: Ruta G -- transition_run_state_atomically (COMPLETED) ----------


class TestCompletionEventAtomicity:
    """Ruta G: COMPLETED + RunCompleted event atomicos."""

    def test_completed_terminal_atomicity_with_fault_at_event_insert(self, fresh_db: str) -> None:
        tenant_id = "t-cc"
        project_id = "p-cc"
        run_id = "r-cc-" + uuid.uuid4().hex[:8]

        bootstrap = Storage(path=fresh_db)
        try:
            bootstrap._conn.execute(
                "INSERT INTO workflow_runs "
                "(run_id, tenant_id, project_id, state, plan_json, current_node) "
                "VALUES (?, ?, ?, 'ACTIVE', '{}', ?)",
                (run_id, tenant_id, project_id, "start"),
            )
            bootstrap._conn.commit()
        finally:
            bootstrap.close()  # type: ignore[attr-defined]

        event = _completed_event(tenant_id, project_id, run_id, "COMPLETED", None)
        faulty = ConnFaultyStorage(db_path=fresh_db, fail_at=2)
        try:
            with pytest.raises(sqlite3.OperationalError):
                faulty.transition_run_state_atomically(
                    event=event,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    run_id=run_id,
                    state="COMPLETED",
                    current_node=None,
                )
        finally:
            faulty.close()  # type: ignore[attr-defined]

        verify = Storage(path=fresh_db)
        try:
            post_run = verify._conn.execute(
                "SELECT state FROM workflow_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            post_events = verify._conn.execute(
                "SELECT COUNT(*) FROM runtime_events "
                "WHERE run_id = ? AND event_kind = 'RunCompleted'",
                (run_id,),
            ).fetchone()[0]
        finally:
            verify.close()  # type: ignore[attr-defined]

        consistent = post_run is not None and post_run[0] == "ACTIVE" and post_events == 0
        assert consistent, (
            f"GRIETA: rollback incompleto en COMPLETED. "
            f"state={post_run[0] if post_run else None} (esperado ACTIVE), "
            f"RunCompleted count={post_events} (esperado 0)"
        )


# ---------- Test 4: idempotencia transaccional ----------


class TestReopenAfterInjectedFault:
    """Tras un fallo inyectado, una nueva operacion atomica con un evento
    DISTINTO debe poder finalizar la transicion sin residuos previos."""

    def test_reopen_after_fault_at_event_insert_keeps_consistency(self, fresh_db: str) -> None:
        tenant_id = "t-rh"
        project_id = "p-rh"
        run_id = "r-rh-" + uuid.uuid4().hex[:8]
        first_event = _completed_event(tenant_id, project_id, run_id, "FAILED", "start")
        # Setup: run pre-existente en ACTIVE.
        bootstrap = Storage(path=fresh_db)
        try:
            bootstrap._conn.execute(
                "INSERT INTO workflow_runs "
                "(run_id, tenant_id, project_id, state, plan_json, current_node) "
                "VALUES (?, ?, ?, 'ACTIVE', '{}', ?)",
                (run_id, tenant_id, project_id, "start"),
            )
            bootstrap._conn.commit()
        finally:
            bootstrap.close()  # type: ignore[attr-defined]

        # Primer intento: falla el INSERT del evento (fail_at=2: UPDATE=#1, INSERT event=#2).
        faulty = ConnFaultyStorage(db_path=fresh_db, fail_at=2)
        try:
            with pytest.raises(sqlite3.OperationalError):
                faulty.transition_run_state_atomically(
                    event=first_event,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    run_id=run_id,
                    state="FAILED",
                    current_node="start",
                )
        finally:
            faulty.close()  # type: ignore[attr-defined]

        # Segundo intento: nuevo evento, sin fault. Debe completar y dejar
        # estado consistente (FAILED + 1 RunCompleted).
        second_event = _completed_event(tenant_id, project_id, run_id, "FAILED", "start")
        # Mutamos event_id del segundo_event para diferenciarlo y que el
        # UNIQUE de runtime_events no choque con el primero.
        new_event = RuntimeEvent(
            event_id=str(uuid.uuid4()),
            tenant_id=second_event.tenant_id,
            project_id=second_event.project_id,
            event_kind=second_event.event_kind,
            run_id=second_event.run_id,
            resource_ref=second_event.resource_ref,
            causation_id=second_event.causation_id,
            correlation_id=second_event.correlation_id,
            payload=dict(second_event.payload),
            timestamp=second_event.timestamp,
            schema_version=second_event.schema_version,
        )

        clean = Storage(path=fresh_db)
        try:
            clean.transition_run_state_atomically(
                event=new_event,
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run_id,
                state="FAILED",
                current_node="start",
            )
        finally:
            clean.close()  # type: ignore[attr-defined]

        verify = Storage(path=fresh_db)
        try:
            run_row = verify._conn.execute(
                "SELECT state FROM workflow_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            event_count = verify._conn.execute(
                "SELECT COUNT(*) FROM runtime_events "
                "WHERE run_id = ? AND event_kind = 'RunCompleted'",
                (run_id,),
            ).fetchone()[0]
        finally:
            verify.close()  # type: ignore[attr-defined]

        assert run_row is not None and run_row[0] == "FAILED", (
            f"Reopen fallo: state={run_row[0] if run_row else None} (esperado FAILED)"
        )
        # Una sola transaccion completa despues del reopen: 1 RunCompleted.
        assert event_count == 1, f"Reopen fallo: RunCompleted count={event_count} (esperado 1)"


# ---------- Test 5-7: no-duplicacion en camino feliz ----------
#
# Blindaje contra una regresion donde alguien duplique `EventLog.append`
# o agregue una llamada paralela a `_insert_event_in_tx` dentro de
# las APIs atomicas. Las pruebas en fallo cubren el rollback conjunto;
# las de camino feliz cubren la parte complementaria: que un camino
# exitoso NO produce duplicados.
#
# Operador: "la transaccion garantiza coherencia de las dos escrituras,
# no idempotencia de solicitudes repetidas." Este blindaje NO prueba
# idempotencia (que es UAT-07, ya cubierto en otros tests); prueba
# que UNA llamada a la API atomica produce EXACTAMENTE una fila de
# runtime_events y una fila (o UPDATE) de workflow_runs.


class TestNoDuplicationOnHappyPath:
    """Una sola invocacion de la API atomica -> un solo evento."""

    def test_create_run_atomically_produces_single_run_created_event(self, fresh_db: str) -> None:
        tenant_id = "t-nd-create"
        project_id = "p-nd-create"
        run_id = "r-nd-create-" + uuid.uuid4().hex[:8]
        event = _run_event(tenant_id, project_id, run_id)

        storage = Storage(path=fresh_db)
        try:
            storage.create_run_atomically(
                event=event,
                run_id=run_id,
                tenant_id=tenant_id,
                project_id=project_id,
                plan_json="{}",
                initial_node="start",
            )
        finally:
            storage.close()  # type: ignore[attr-defined]

        verify = Storage(path=fresh_db)
        try:
            run_rows = verify._conn.execute(
                "SELECT COUNT(*) FROM workflow_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]
            event_rows = verify._conn.execute(
                "SELECT COUNT(*) FROM runtime_events "
                "WHERE run_id = ? AND event_kind = 'RunCreated'",
                (run_id,),
            ).fetchone()[0]
            all_for_run = verify._conn.execute(
                "SELECT COUNT(*) FROM runtime_events WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]
        finally:
            verify.close()  # type: ignore[attr-defined]

        assert run_rows == 1, (
            f"No-duplicacion rota: workflow_runs tiene {run_rows} filas para run_id={run_id} (esperado 1)"
        )
        assert event_rows == 1, (
            f"No-duplicacion rota: hay {event_rows} RunCreated para run_id={run_id} (esperado 1)"
        )
        assert all_for_run == 1, (
            f"No-duplicacion rota: hay {all_for_run} eventos totales para run_id={run_id} (esperado 1)"
        )

    def test_transition_run_state_atomically_produces_single_run_completed_event_failed(
        self, fresh_db: str
    ) -> None:
        """FAILED terminal debe producir UN solo RunCompleted(state=FAILED)."""
        tenant_id = "t-nd-fail"
        project_id = "p-nd-fail"
        run_id = "r-nd-fail-" + uuid.uuid4().hex[:8]
        bootstrap = Storage(path=fresh_db)
        try:
            bootstrap._conn.execute(
                "INSERT INTO workflow_runs "
                "(run_id, tenant_id, project_id, state, plan_json, current_node) "
                "VALUES (?, ?, ?, 'ACTIVE', '{}', ?)",
                (run_id, tenant_id, project_id, "start"),
            )
            bootstrap._conn.commit()
        finally:
            bootstrap.close()  # type: ignore[attr-defined]

        event = _completed_event(tenant_id, project_id, run_id, "FAILED", "start")
        storage = Storage(path=fresh_db)
        try:
            storage.transition_run_state_atomically(
                event=event,
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run_id,
                state="FAILED",
                current_node="start",
            )
        finally:
            storage.close()  # type: ignore[attr-defined]

        verify = Storage(path=fresh_db)
        try:
            run_state = verify._conn.execute(
                "SELECT state FROM workflow_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]
            completed = verify._conn.execute(
                "SELECT COUNT(*) FROM runtime_events "
                "WHERE run_id = ? AND event_kind = 'RunCompleted'",
                (run_id,),
            ).fetchone()[0]
            all_for_run = verify._conn.execute(
                "SELECT COUNT(*) FROM runtime_events WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]
        finally:
            verify.close()  # type: ignore[attr-defined]

        assert run_state == "FAILED", (
            f"No-duplicacion rota: workflow_runs.state={run_state!r} (esperado 'FAILED')"
        )
        assert completed == 1, f"No-duplicacion rota: hay {completed} RunCompleted (esperado 1)"
        assert all_for_run == 1, (
            f"No-duplicacion rota: hay {all_for_run} eventos totales (esperado 1)"
        )

    def test_transition_run_state_atomically_produces_single_run_completed_event_completed(
        self, fresh_db: str
    ) -> None:
        """COMPLETED debe producir UN solo RunCompleted(state=COMPLETED)."""
        tenant_id = "t-nd-comp"
        project_id = "p-nd-comp"
        run_id = "r-nd-comp-" + uuid.uuid4().hex[:8]
        bootstrap = Storage(path=fresh_db)
        try:
            bootstrap._conn.execute(
                "INSERT INTO workflow_runs "
                "(run_id, tenant_id, project_id, state, plan_json, current_node) "
                "VALUES (?, ?, ?, 'ACTIVE', '{}', ?)",
                (run_id, tenant_id, project_id, "start"),
            )
            bootstrap._conn.commit()
        finally:
            bootstrap.close()  # type: ignore[attr-defined]

        event = _completed_event(tenant_id, project_id, run_id, "COMPLETED", None)
        storage = Storage(path=fresh_db)
        try:
            storage.transition_run_state_atomically(
                event=event,
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run_id,
                state="COMPLETED",
                current_node=None,
            )
        finally:
            storage.close()  # type: ignore[attr-defined]

        verify = Storage(path=fresh_db)
        try:
            run_state = verify._conn.execute(
                "SELECT state FROM workflow_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]
            completed = verify._conn.execute(
                "SELECT COUNT(*) FROM runtime_events "
                "WHERE run_id = ? AND event_kind = 'RunCompleted' "
                "AND json_extract(payload_json, '$.state') = 'COMPLETED'",
                (run_id,),
            ).fetchone()[0]
            all_for_run = verify._conn.execute(
                "SELECT COUNT(*) FROM runtime_events WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]
        finally:
            verify.close()  # type: ignore[attr-defined]

        assert run_state == "COMPLETED", (
            f"No-duplicacion rota: workflow_runs.state={run_state!r} (esperado 'COMPLETED')"
        )
        assert completed == 1, (
            f"No-duplicacion rota: hay {completed} RunCompleted(COMPLETED) (esperado 1)"
        )
        assert all_for_run == 1, (
            f"No-duplicacion rota: hay {all_for_run} eventos totales (esperado 1)"
        )
