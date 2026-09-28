"""Red de contrato del corte 5 WI-56: SqlitePromotionRepository.

Dos bases identicas sembradas con el mismo procedimiento; dump
semantico sin columnas de reloj; UUIDs/clocks normalizados.

La red ANTES de la extraccion (RED honesto) fallaba solo en la
identidad del facade: ``promotion_repository()`` no existia y los 7
metodos del cluster promotions vivian con SQL directo en Storage.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from skillgraph.platform.storage import Storage

# ----- sembrado determinista ------------------------------------------------


def _seed(db: Path) -> None:
    storage = Storage(db)
    storage.register_promotion(
        proposal_id="prop-1",
        idempotency_key="idem-1",
        tenant_id="tenant-a",
        source_project="proj-src",
        target_catalog="catalog-x",
        knowledge_ref="skills/foo/bar",
        payload={"skill": "bar", "version": 1},
    )
    storage.register_promotion(
        proposal_id="prop-2",
        idempotency_key="idem-2",
        tenant_id="tenant-a",
        source_project="proj-src",
        target_catalog="catalog-x",
        knowledge_ref="skills/baz/qux",
        payload={"skill": "qux", "version": 2},
    )
    storage.mark_promotion_in_progress("prop-2")
    storage.close()


class DualBases:
    """Dos bases con el mismo sembrado: una para el facade, otra espejo."""

    def __init__(self, tmp_path: Path) -> None:
        self.facade_db = tmp_path / "facade.sqlite"
        self.mirror_db = tmp_path / "mirror.sqlite"
        _seed(self.facade_db)
        _seed(self.mirror_db)


@pytest.fixture()
def dual(tmp_path: Path) -> DualBases:
    return DualBases(tmp_path)


def _dump_semantic(db: Path) -> str:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    lines: list[str] = []
    for table in ("promotion_outbox",):
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        for row in sorted(rows, key=lambda r: r["proposal_id"]):
            d = dict(row)
            d.pop("created_at", None)
            d.pop("updated_at", None)
            lines.append(json.dumps(d, sort_keys=True, default=str))
    conn.close()
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def _payload_of(storage: Storage, proposal_id: str) -> dict[str, object]:
    row = storage.get_promotion(proposal_id)
    assert row is not None
    return json.loads(json.dumps(row.payload, sort_keys=True, default=str))


# ----- identidad del facade (el RED honesto del corte) ----------------------


class TestFacadeIdentity:
    def test_component_satisfies_structural_eventstore_contract(self, tmp_path: Path) -> None:
        storage = Storage(tmp_path / "s.sqlite")
        comp = storage.promotion_repository()
        assert comp.__class__.__module__ == ("skillgraph.platform.promotion_repository")
        # El Protocol PromotionRepository NO es runtime_checkable:
        # contrato estructural verificado por presencia de metodos.
        for name in (
            "register_promotion",
            "get_promotion",
            "list_pending_promotions",
        ):
            assert callable(getattr(comp, name, None)), name

    def test_component_is_cached_per_storage(self, tmp_path: Path) -> None:
        storage = Storage(tmp_path / "s.sqlite")
        assert storage.promotion_repository() is storage.promotion_repository()

    def test_two_storages_get_independent_components(self, dual: DualBases) -> None:
        a = Storage(dual.facade_db)
        b = Storage(dual.mirror_db)
        assert a.promotion_repository() is not b.promotion_repository()
        a.close()
        b.close()


# ----- contrato de operaciones (facade y componente equivalentes) ----------


class TestPromotionLifecycleContracts:
    def test_register_and_get_roundtrip(self, dual: DualBases) -> None:
        facade = Storage(dual.facade_db)
        comp = Storage(dual.mirror_db).promotion_repository()
        assert _payload_of(facade, "prop-1") == _payload_of(comp, "prop-1")
        facade.close()
        comp._storage.close()

    def test_register_duplicate_idempotency_key_conflicts(self, dual: DualBases) -> None:
        from skillgraph.core.errors import IdentityConflictError

        facade = Storage(dual.facade_db)
        comp = Storage(dual.mirror_db).promotion_repository()
        for client in (facade, comp):
            with pytest.raises(IdentityConflictError):
                client.register_promotion(
                    proposal_id="prop-dup",
                    idempotency_key="idem-1",
                    tenant_id="tenant-a",
                    source_project="proj-src",
                    target_catalog="catalog-x",
                    knowledge_ref="skills/x/y",
                    payload={},
                )
        facade.close()
        comp._storage.close()

    def test_get_unknown_returns_none(self, dual: DualBases) -> None:
        facade = Storage(dual.facade_db)
        comp = Storage(dual.mirror_db).promotion_repository()
        assert facade.get_promotion("nope") is None
        assert comp.get_promotion("nope") is None
        facade.close()
        comp._storage.close()

    def test_list_pending_includes_in_progress(self, dual: DualBases) -> None:
        facade = Storage(dual.facade_db)
        comp = Storage(dual.mirror_db).promotion_repository()
        ids_f = sorted(p.proposal_id for p in facade.list_pending_promotions())
        ids_c = sorted(p.proposal_id for p in comp.list_pending_promotions())
        assert ids_f == ids_c == ["prop-1", "prop-2"]
        facade.close()
        comp._storage.close()

    def test_list_promotions_filters_by_status(self, dual: DualBases) -> None:
        facade = Storage(dual.facade_db)
        comp = Storage(dual.mirror_db).promotion_repository()
        assert [p.proposal_id for p in facade.list_promotions(status="PENDING")] == ["prop-1"]
        assert [p.proposal_id for p in comp.list_promotions(status="PENDING")] == ["prop-1"]
        with pytest.raises(Exception, match=r"status|invalido"):
            facade.list_promotions(status="NO_EXISTE")
        facade.close()
        comp._storage.close()

    def test_mark_transitions(self, dual: DualBases) -> None:
        facade = Storage(dual.facade_db)
        comp = Storage(dual.mirror_db).promotion_repository()
        facade.mark_promotion_failed("prop-1")
        comp.mark_promotion_published("prop-2")
        assert facade.get_promotion("prop-1").status == "FAILED"
        assert comp.get_promotion("prop-2").status == "PUBLISHED"
        facade.close()
        comp._storage.close()

    def test_semantic_dump_equivalence(self, dual: DualBases) -> None:
        assert _dump_semantic(dual.facade_db) == _dump_semantic(dual.mirror_db)


# ----- helpers atomicos siguen en Storage (H9/H10) --------------------------


class TestAtomicHelpersStayOnStorage:
    def test_insert_event_in_tx_is_storage_method(self, tmp_path: Path) -> None:
        storage = Storage(tmp_path / "s.sqlite")
        assert callable(getattr(Storage, "_insert_event_in_tx", None))
        assert callable(getattr(Storage, "_atomic_state_and_event", None))
        storage.close()

    def test_event_flow_through_monkeypatched_helper(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """H9/H10: el helper atomico sigue siendo punto de inyeccion.

        La ruta atomico (state+event) de ``_atomic_state_and_event``
        llama ``Storage._insert_event_in_tx``; el INSERT del evento
        simple vive ya en el componente (corte 4) y no pasa por el
        helper. Aqui se ejercita la ruta atomica con spy.
        """
        storage = Storage(tmp_path / "s.sqlite")
        calls: list[str] = []
        original = Storage._insert_event_in_tx

        def spy(self: Storage, cur: sqlite3.Cursor, event: object) -> None:
            calls.append(getattr(event, "event_kind", "?"))
            original(self, cur, event)

        monkeypatch.setattr(Storage, "_insert_event_in_tx", spy)
        from skillgraph.runtime.engine import RuntimeEvent

        event = RuntimeEvent(
            event_id="evt-wi56-2",
            tenant_id="t",
            project_id="p",
            event_kind="RunCreated",
            run_id="r1",
            resource_ref="skills/foo/bar",
            causation_id=None,
            correlation_id=None,
            payload={"x": 1},
            schema_version=1,
        )
        # ruta atomica: mutacion de estado + evento en una sola tx
        storage._atomic_state_and_event(
            exec_sql=(
                "INSERT INTO operations(operation_id, idempotency_key, resource_uid, phase, result_ref) VALUES ('op-spy', 'idem-spy', 'res-spy', 'spy', NULL)",
                (),
            ),
            event=event,
        )
        assert calls == ["RunCreated"]
        rows = storage.list_events(tenant_id="t", project_id="p")
        assert any(getattr(r, "event_id", None) == "evt-wi56-2" for r in rows)
        storage.close()


# ----- regresion: delegados explicitos (guard WI-45) ------------------------


class TestDelegatesExplicitSignatures:
    def test_no_var_args_in_delegates(self) -> None:
        import ast
        import pathlib

        src = pathlib.Path("src/skillgraph/platform/storage.py").read_text()
        tree = ast.parse(src)
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Storage")
        promo = {
            "register_promotion",
            "get_promotion",
            "list_pending_promotions",
            "list_promotions",
            "mark_promotion_in_progress",
            "mark_promotion_published",
            "mark_promotion_failed",
        }
        for m in cls.body:
            if isinstance(m, ast.FunctionDef) and m.name in promo:
                a = m.args
                assert a.vararg is None, f"{m.name} usa *args"
                assert a.kwarg is None, f"{m.name} usa **kwargs"
                assert isinstance(m.body[0], ast.Expr) and isinstance(
                    m.body[0].value, ast.Constant
                ), f"{m.name} sin docstring"
                assert "Delegado WI-56" in m.body[0].value.value
