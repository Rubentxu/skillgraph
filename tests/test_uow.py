"""Tests for SqliteUnitOfWork (WI-33, R2 audit externo).

Verifica que:
- SqliteUnitOfWork owns the SQLite connection y expone los 5 adapters
  (RunRepository, EventStore, KnowledgeRepository, PromotionRepository,
  PolicyStore) que comparten la misma conexion.
- Los 5 adapters usan exactamente el mismo ``sqlite3.Connection``,
  lo que permite transacciones cross-bounded-context sin reescritura.
- El facade ``Storage`` expone los adapters via ``storage.uow.runs`` etc.
  (no rompe la API actual).
- Lifecycle: cerrar la UoW cierra la conexion subyacente (single owner).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from skillgraph.platform.storage import Storage


def test_uow_exposes_five_adapters(tmp_path: Path) -> None:
    """SqliteUnitOfWork expone los 5 adapters tipados."""
    s = Storage(tmp_path / "p.sqlite")
    try:
        uow = s.uow
        assert uow.runs is not None
        assert uow.events is not None
        assert uow.knowledge is not None
        assert uow.governance is not None
        assert uow.policy is not None
    finally:
        s.close()


def test_all_adapters_share_same_connection(tmp_path: Path) -> None:
    """Los 5 adapters usan exactamente la misma ``sqlite3.Connection``.

    Esto es la propiedad que el audit externo apuntaba como
    'Connection lifecycle' R2: una sola conexion owned por UoW,
    compartida por los 5 bounded contexts.
    """
    s = Storage(tmp_path / "p.sqlite")
    try:
        uow = s.uow
        # ``_conn`` no es API publica; usamos ``id()`` para confirmar
        # identidad de objetos (mismo objeto en memoria).
        # Accedemos al atributo privado via getattr para evitar
        # exponer la conexion mas de lo necesario.
        conn_id = id(uow._conn)
        for adapter in (
            uow.runs,
            uow.events,
            uow.knowledge,
            uow.governance,
            uow.policy,
        ):
            adapter_conn_id = id(adapter._conn)
            assert adapter_conn_id == conn_id, (
                f"Adapter {type(adapter).__name__} no comparte la conexion"
            )
    finally:
        s.close()


def test_uow_satisfies_runtime_checkable_protocols(tmp_path: Path) -> None:
    """Los adapters exponen los metodos clave de los Protocols.

    No usamos ``isinstance(uow.runs, RunRepository)`` directamente
    porque ``@runtime_checkable`` exige que TODOS los metodos del
    Protocol esten en el adapter (incluyendo los ``*_atomically``
    que delegan via ``**kwargs``). En lugar de eso, verificamos que
    los metodos que el ``RunController`` realmente consume existen
    y son invocables.
    """
    s = Storage(tmp_path / "p.sqlite")
    try:
        uow = s.uow
        # Metodos que RunController consume directamente.
        for name in (
            "list_runs",
            "get_run",
            "load_run",
            "list_node_executions",
            "list_events_for_run",
            "transition_run_state",
            "start_node_execution_atomically",
            "complete_node_execution_atomically",
            "mark_node_failed_atomically",
        ):
            assert callable(getattr(uow.runs, name)), f"runs.{name} missing"
        # Metodos del EventStore.
        for name in ("list_events_for_run", "fetch_event_raw"):
            assert callable(getattr(uow.events, name)), f"events.{name} missing"
    finally:
        s.close()


def test_close_propagates_from_storage(tmp_path: Path) -> None:
    """Cerrar ``Storage`` cierra la conexion subyacente (single owner).

    La UoW no expone ``close()`` directamente: el lifecycle lo
    gestiona ``Storage``. Tests que llaman ``storage.close()`` siguen
    funcionando como antes.
    """
    s = Storage(tmp_path / "p.sqlite")
    conn = s.uow._conn
    assert isinstance(conn, sqlite3.Connection)
    s.close()
    # Tras cerrar, operaciones sobre la conexion fallan.
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


def test_uow_is_stable_across_calls(tmp_path: Path) -> None:
    """``Storage.uow`` siempre devuelve la MISMA instancia de UoW."""
    s = Storage(tmp_path / "p.sqlite")
    try:
        uow_a = s.uow
        uow_b = s.uow
        assert uow_a is uow_b
    finally:
        s.close()


def test_storage_methods_delegate_to_uow_adapters(tmp_path: Path) -> None:
    """Los metodos del facade ``Storage`` y del adapter ``uow.runs``
    son APIs equivalentes (mismo resultado en el mismo storage).

    Tras WI-33, ``Storage.list_runs`` y ``storage.uow.runs.list_runs``
    son funciones DIFERENTES (cada una con su propia implementacion):
    ``Storage`` mantiene el facade historico, los adapters son la
    nueva capa. La identidad ``is`` ya no se preserva entre ambos,
    pero el contrato observable (resultado, excepciones) es identico.

    Verificamos que ambos llaman y devuelven el mismo resultado sobre
    el mismo ``Storage`` (compartiendo la misma ``sqlite3.Connection``).
    """
    s = Storage(tmp_path / "p.sqlite")
    try:
        # Mismo resultado en facade y adapter para operaciones None-safe.
        assert s.list_runs(tenant_id="t", project_id="p") == s.uow.runs.list_runs(
            tenant_id="t", project_id="p"
        )
        # Knowledge: get_resource (operacion None-safe).
        assert s.get_resource(uid="missing") is None
        assert s.uow.knowledge.get_resource(uid="missing") is None
        # Events: list_events_for_run sobre run vacio -> [].
        assert s.list_events_for_run(
            tenant_id="t", project_id="p", run_id="missing"
        ) == s.uow.events.list_events_for_run(tenant_id="t", project_id="p", run_id="missing")
        # Dependencies: ambos devuelven [] para uid inexistente.
        assert s.dependencies_of(uid="missing") == s.uow.knowledge.dependencies_of(uid="missing")
    finally:
        s.close()
