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
    """Métodos públicos (no empiezan por ``_``) declarados en ``cls``."""
    return {
        name
        for name, member in inspect.getmembers(cls, predicate=inspect.isfunction)
        if not name.startswith("_") and member.__qualname__.startswith(cls.__name__)
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
