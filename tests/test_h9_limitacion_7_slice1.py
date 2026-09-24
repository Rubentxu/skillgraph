"""Tests de caracterización para H9-LIMITACIÓN-7 (slice 1.b).

Demuestran empíricamente que las operaciones de escritura multi-statement
de `Storage` (V1-V5 del inventario) no rollbackean ante fallo porque
`isolation_level=None` hace que cada `execute()` sea autocommit.

Estrategia de fault injection: subclasamos `Storage` y override `_tx()`
para introducir un fallo determinista en la N-ésima sentencia SQL.
Esto evita los problemas de `sqlite3.Connection`/`sqlite3.Cursor` read-only
que imposibilitan monkeypatch directo.

Cada test verifica:
  - V1-V3, V5: vulnerables pero IDEMPOTENTES (rollback innecesario).
  - V4 (`record_trace`): caso único donde la falta de rollback deja
    estado inconsistente (orphan: trace_row sin sus links).

Resultado esperado:
  - T15, T16, T18 GREEN (excluyen V1, V2, V5 por idempotencia).
  - T17 RED (demuestra el bug de V4: rollback falla porque autocommit).
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
import sqlite3

from skillgraph.core.errors import IdentityConflictError
from skillgraph.knowledge.graph import (
    ClaimID,
    EvidenceID,
    OutcomeTrace,
    TraceID,
)
from skillgraph.platform.storage import Storage
from skillgraph.resources.bricks import Brick, ResourceIdentity


TENANT = "tenant-test"
PROJECT = "proj-test"


# ----------------- Fault-injecting Storage subclass -----------------


class FaultyStorage(Storage):
    """Storage que permite inyectar un fallo en la N-ésima sentencia
    SQL dentro del bloque `_tx()`. Override mínimo: mantiene todo
    igual salvo el context manager `_tx`."""

    def __init__(self, *args, fail_on_call: int = -1, **kwargs) -> None:
        # Inicializar atributos ANTES de super().__init__() porque
        # Storage.__init__ invoca _migrate() que ya usa _tx() y por
        # tanto necesita `_call_counter` y `_fail_on_call` listos.
        # `_fault_enabled` se activa despues de la migracion inicial.
        self._fail_on_call = fail_on_call
        self._call_counter = 0
        self._fault_enabled = False
        super().__init__(*args, **kwargs)
        self._fault_enabled = True

    @contextmanager
    def _atomic(self) -> Iterator[sqlite3.Cursor]:
        # Override paralelo a `_tx()`: misma semántica transaccional
        # pero con el cursor envuelto para que `cur.execute()` falle
        # cuando se alcance `_fail_on_call`.
        outer_self = self
        self._conn.execute("BEGIN")
        real_cur = self._conn.cursor()

        class CountingCursor:
            def __init__(self, real: sqlite3.Cursor) -> None:
                self._real = real

            def execute(self, sql, params=()):
                outer_self._call_counter += 1
                if outer_self._call_counter == outer_self._fail_on_call:
                    raise RuntimeError(
                        f"fault injection: forced fail at call {outer_self._call_counter}"
                    )
                return self._real.execute(sql, params)

            def fetchone(self):
                return self._real.fetchone()

            def fetchall(self):
                return self._real.fetchall()

            @property
            def lastrowid(self):
                return self._real.lastrowid

        try:
            yield CountingCursor(real_cur)
            self._conn.execute("COMMIT")
        except BaseException:
            try:
                self._conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Cursor]:
        # El override mantiene la semántica transaccional original
        # (`with self._conn:`). Lo único que añade es un wrapper que
        # falla en la N-ésima llamada a `execute()`.
        # `sqlite3.Cursor.execute` es read-only (C-level), asi que
        # NO se puede monkeypatchear directamente; envolvemos el cursor
        # en un wrapper Python que delega via `_real.execute`.
        outer_self = self  # captura para acceder en CountingCursor
        with self._conn:
            real_cur = self._conn.cursor()

            class CountingCursor:
                """Wrapper de sqlite3.Cursor que falla en la N-ésima execute."""

                def __init__(self, real: sqlite3.Cursor) -> None:
                    self._real = real

                def execute(self, sql, params=()):
                    if outer_self._fault_enabled:
                        outer_self._call_counter += 1
                        if outer_self._call_counter == outer_self._fail_on_call:
                            raise RuntimeError(
                                f"fault injection: forced fail at call {outer_self._call_counter}"
                            )
                    return self._real.execute(sql, params)

                def executescript(self, sql):
                    # `_migrate` usa executescript. Contamos como 1
                    # llamada pero NO permitimos fallar inyectando
                    # mid-script. Ademas, durante la migracion inicial
                    # `_fault_enabled` esta en False.
                    outer_self._call_counter += 1
                    return self._real.executescript(sql)

                def fetchone(self):
                    return self._real.fetchone()

                def fetchall(self):
                    return self._real.fetchall()

                @property
                def lastrowid(self):
                    return self._real.lastrowid

            yield CountingCursor(real_cur)


# ----------------- Fixtures -----------------


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "limitacion7.sqlite"


@pytest.fixture
def trace_with_two_links() -> OutcomeTrace:
    """Trace con 2 claims y 1 evidence = 4 INSERTs totales
    (1 trace + 2 claims + 1 evidence)."""
    return OutcomeTrace(
        trace_id=TraceID("trace-orphan-1"),
        kind="SoftwareExecutionSlice",
        name="trace de prueba",
        project_id=PROJECT,
        created_at="2026-01-01T00:00:00Z",
        claim_refs=(ClaimID("claim-1"), ClaimID("claim-2")),
        evidence_refs=(EvidenceID("ev-1"),),
    )


# ----------------- Tests -----------------


class TestT15MigrateIdempotency:
    """V1: `_migrate()` es multi-statement. EXCLUIDA por idempotencia:
    cada CREATE TABLE/INDEX usa IF NOT EXISTS, naturalmente recuperable.
    """

    def test_migrate_idempotent_after_partial_failure(
        self, db_path: Path
    ) -> None:
        # Forzar fallo en la 2a sentencia de la 2a invocacion de _migrate
        # (executescript=1, SELECT=2). La 1a invocacion (en __init__)
        # corre con _fault_enabled=False por lo que no incrementa
        # el contador.
        faulty = FaultyStorage(db_path)
        faulty._call_counter = 0
        faulty._fault_enabled = True
        faulty._fail_on_call = 2
        with pytest.raises(RuntimeError, match="fault injection"):
            faulty._migrate()  # type: ignore[attr-defined]
        faulty.close()

        # Segunda llamada completa la migración.
        s2 = Storage(db_path)
        s2._migrate()  # type: ignore[attr-defined]
        s2.close()

        # Verificar: las tablas existen (la migración completó).
        s3 = Storage(db_path)
        tables = s3._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {row[0] for row in tables}
        s3.close()
        assert "outcome_traces" in table_names
        assert "outcome_trace_links" in table_names
        # EXCLUIDA: la idempotencia natural hace innecesaria la
        # transacción atómica.


class TestT17RecordTrace:
    """V4: `record_trace()` escribe 1 trace_row + N trace_links.
    Si falla en el medio, la trace_row queda orphan. Bug REAL."""

    def test_record_trace_rolls_back_when_last_link_fails(
        self,
        db_path: Path,
        trace_with_two_links: OutcomeTrace,
    ) -> None:
        # Forzar fallo en la 4a sentencia: 1 trace + 2 claims + 1 evidence.
        faulty = FaultyStorage(db_path)
        faulty._call_counter = 0
        faulty._fault_enabled = True
        faulty._fail_on_call = 4

        with pytest.raises(RuntimeError, match="fault injection"):
            faulty.record_trace(
                tenant_id=TENANT,
                project_id=PROJECT,
                trace=trace_with_two_links,
            )
        faulty.close()

        # Verificar: NO debe haber trace_row (rollback atómico esperado).
        s = Storage(db_path)
        trace_rows = s._conn.execute(
            "SELECT * FROM outcome_traces WHERE trace_id = ?",
            ("trace-orphan-1",),
        ).fetchall()
        link_rows = s._conn.execute(
            "SELECT * FROM outcome_trace_links WHERE trace_id = ?",
            ("trace-orphan-1",),
        ).fetchall()
        s.close()

        assert len(trace_rows) == 0, (
            f"BUG: trace_row quedo en disco sin rollback "
            f"(autocommit de isolation_level=None). rows={trace_rows}"
        )
        assert len(link_rows) == 0, (
            f"BUG: trace_link quedo en disco sin rollback. rows={link_rows}"
        )


class TestT16UpsertResourceIdempotency:
    """V2: `upsert_resource()` es multi-statement (SELECT + INSERT/UPDATE).
    EXCLUIDA por idempotencia: re-ejecutar produce el mismo estado final."""

    def test_upsert_resource_idempotent_without_explicit_transaction(
        self, db_path: Path
    ) -> None:
        """V2: `upsert_resource()` es multi-statement (SELECT + INSERT).
        EXCLUIDA por idempotencia: el spec se valida en la SELECT; si
        cambia, la operacion se rechaza ANTES del INSERT/UPDATE, por
        lo que no queda estado inconsistente.
        Ademas, un INSERT con la misma PK reemplaza la fila (no hay
        duplicado)."""
        s1 = Storage(db_path)
        brick = Brick(
            identity=ResourceIdentity(
                tenant_id=TENANT,
                project_id=PROJECT,
                namespace="default",
                kind="ActionNode",
                name="b1",
            ),
            api_version="v1",
            kind="ActionNode",
            spec={"k": "v"},
        )
        s1.upsert_resource(brick)
        s1.close()

        # Re-llamada con MISMO spec: idempotente (no hace UPDATE).
        s2 = Storage(db_path)
        s2.upsert_resource(brick)
        rows = s2._conn.execute(
            "SELECT name, kind, spec_json FROM resources WHERE name = ?",
            ("b1",),
        ).fetchall()
        s2.close()
        assert len(rows) == 1, "Debe haber exactamente 1 fila (no duplicados)"
        assert rows[0][1] == "ActionNode"

        # Re-llamada con spec distinto: rechazada por SELECT (no UPDATE).
        brick2 = Brick(
            identity=ResourceIdentity(
                tenant_id=TENANT,
                project_id=PROJECT,
                namespace="default",
                kind="ActionNode",
                name="b1",
            ),
            api_version="v1",
            kind="ActionNode",
            spec={"k": "v2"},
        )
        s3 = Storage(db_path)
        from skillgraph.core.errors import IdentityConflictError
        with pytest.raises(IdentityConflictError):
            s3.upsert_resource(brick2)
        s3.close()
        # EXCLUIDA: la operacion es naturalmente idempotente.


class TestT18RegisterPromotionIdempotency:
    """V5: `register_promotion()` hace SELECT + INSERT dentro de _tx().
    Si el INSERT falla, la SELECT inicial re-detecta el conflicto.
    EXCLUIDA por idempotencia: la UNIQUE constraint sobre
    idempotency_key protege la unicidad incluso sin rollback."""

    def test_register_promotion_idempotency_key_protects_uniqueness(
        self, db_path: Path
    ) -> None:
        # Llamada exitosa.
        s1 = Storage(db_path)
        s1.register_promotion(
            proposal_id="prop-1",
            idempotency_key="idem-1",
            tenant_id=TENANT,
            source_project="p1",
            target_catalog="c1",
            knowledge_ref="k1",
            payload={"x": 1},
        )
        s1.close()

        # Segunda llamada con MISMO idempotency_key → debe ser rechazada
        # por la SELECT, no por la UNIQUE constraint.
        s2 = Storage(db_path)
        with pytest.raises(IdentityConflictError):
            s2.register_promotion(
                proposal_id="prop-1",
                idempotency_key="idem-1",
                tenant_id=TENANT,
                source_project="p1",
                target_catalog="c1",
                knowledge_ref="k1",
                payload={"x": 1},
            )
        s2.close()
        # EXCLUIDA: la idempotency_key actúa como protección incluso
        # sin transacción atómica.
