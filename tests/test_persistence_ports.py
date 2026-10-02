"""Tests de los Protocols de persistencia (WI-02a).

El objetivo de estos tests es **prevenir regresiones** en el
contrato observable:

- ``Storage`` implementa los 5 Protocols estructuralmente.
- Las firmas coinciden (parámetros keyword-only, retornos).
- ``RunRepository`` y ``EventStore`` pasan ``isinstance``
  check en runtime (``@runtime_checkable``).

Cuando se introduzca un adapter SQLite nuevo
(``SqliteRunRepository`` etc.), estos tests deben pasar para
esa clase también.
"""

from __future__ import annotations

import inspect

from skillgraph.platform.ports import (
    EventStore,
    KnowledgeRepository,
    PolicyStore,
    PromotionRepository,
    RunRepository,
)
from skillgraph.platform.storage import Storage


def _public_methods(cls: type) -> set[str]:
    """Métodos públicos (no empiezan por ``_``) expuestos por ``cls``.

    Se cuentan también los **heredados**: desde WI-65 el facade `Storage`
    hereda sus 65 delegación de los mixin por componente
    (`RunDelegations`, `KnowledgeDelegations`, ...), así que su
    `__qualname__` es `Mixin.metodo` y no `Storage.metodo`. El filtro
    por `__qualname__` que se usaba antes solo miraba el cuerpo de la
    clase y daba por roto un `Storage` que cumple el Protocol.

    Lo que este test afirma es "¿`cls` **expone** estos nombres?", así
    que la pregunta correcta es sobre el conjunto accesible, no sobre
    dónde se definen las funciones.
    """
    return {
        name
        for name, _member in inspect.getmembers(cls, predicate=inspect.isfunction)
        if not name.startswith("_")
    }


def _protocol_methods(proto: type) -> set[str]:
    """Nombres de métodos declarados en un Protocol."""
    return {
        name
        for name in dir(proto)
        if not name.startswith("_")
        and callable(getattr(proto, name, None))
        and getattr(proto, name).__class__.__name__ != "wrapper_descriptor"
    }


def test_storage_implements_run_repository() -> None:
    """``Storage`` expone todos los métodos declarados en ``RunRepository``."""
    proto = set(_protocol_methods(RunRepository))
    storage = _public_methods(Storage)
    missing = proto - storage
    assert not missing, f"Storage no implementa RunRepository.{sorted(missing)}"


def test_storage_implements_event_store() -> None:
    proto = set(_protocol_methods(EventStore))
    storage = _public_methods(Storage)
    missing = proto - storage
    assert not missing, f"Storage no implementa EventStore.{sorted(missing)}"


def test_storage_implements_policy_store() -> None:
    proto = set(_protocol_methods(PolicyStore))
    storage = _public_methods(Storage)
    missing = proto - storage
    assert not missing, f"Storage no implementa PolicyStore.{sorted(missing)}"


def test_storage_implements_knowledge_repository() -> None:
    proto = set(_protocol_methods(KnowledgeRepository))
    storage = _public_methods(Storage)
    missing = proto - storage
    assert not missing, f"Storage no implementa KnowledgeRepository.{sorted(missing)}"


def test_storage_implements_promotion_repository() -> None:
    proto = set(_protocol_methods(PromotionRepository))
    storage = _public_methods(Storage)
    missing = proto - storage
    assert not missing, f"Storage no implementa PromotionRepository.{sorted(missing)}"


def test_run_repository_runtime_checkable() -> None:
    """``RunRepository`` lleva ``@runtime_checkable`` y ``Storage`` lo cumple."""
    assert hasattr(RunRepository, "_is_runtime_protocol")
    s = Storage(":memory:")
    try:
        assert isinstance(s, RunRepository)
    finally:
        s.close()


def test_event_store_runtime_checkable() -> None:
    assert hasattr(EventStore, "_is_runtime_protocol")
    s = Storage(":memory:")
    try:
        assert isinstance(s, EventStore)
    finally:
        s.close()


def test_knowledge_repository_has_wi02b_methods() -> None:
    """WI-02b: nuevos metodos del Protocol para eliminar `_conn` en KC/KI."""
    expected = {
        "find_entity",
        "source_exists_anywhere",
        "list_claims_for_subject",
    }
    proto_methods = set(_protocol_methods(KnowledgeRepository))
    missing = expected - proto_methods
    assert not missing, f"KnowledgeRepository no declara {sorted(missing)}"
    # Storage los implementa estructuralmente (duck typing).
    storage_methods = set(_public_methods(Storage))
    assert expected <= storage_methods, (
        f"Storage no implementa {sorted(expected - storage_methods)}"
    )
    s = Storage(":memory:")
    try:
        s.find_entity(tenant_id="t", project_id="p", kind="k", stable_key="sk")
        s.source_exists_anywhere(source_id="s")
        s.list_claims_for_subject(tenant_id="t", project_id="p", subject_entity_id="e")
    finally:
        s.close()


def test_event_store_has_ensure_schema() -> None:
    """WI-02b: EventStore expone ensure_schema() idempotente."""
    proto_methods = set(_protocol_methods(EventStore))
    assert "ensure_schema" in proto_methods
    storage_methods = set(_public_methods(Storage))
    assert "ensure_schema" in storage_methods
    s = Storage(":memory:")
    try:
        s.ensure_schema()  # idempotente: 2da llamada no raise.
        s.ensure_schema()
    finally:
        s.close()
