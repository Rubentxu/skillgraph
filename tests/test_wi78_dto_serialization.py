"""WI-78 — Asimetria en la serializacion legacy de los DTO de `ports`.

Que se encontro
---------------
`platform/ports/dto.py` esta al 89 %, por debajo del contrato de AGENTS
6.3 para modulos del core. Las lineas sin cubrir no son las claves
legacy de `__getitem__`, como parece a primera vista, sino:

- `raise KeyError(key)` en el `__getitem__` de 5 DTO,
- el metodo `get(key, default)` de StoredClaim y StoredEvidence,
- **`to_dict()` entero en 4 de los 9 DTO**.

La ultima es la que importa. `to_dict()` es la API dict-legacy que los
consumers antiguos usan ("Serializa preservando los nombres historicos de
columnas"), y la cobertura es asimetrica: hay test roundtrip para
StoredEvent, StoredRun, StoredNodeExecution, StoredResource y
StoredRelation, y **no hay ninguno** para StoredClaim, StoredEvidence,
StoredPromotion y StoredBudget.

Ningun codigo de produccion llama a estos `to_dict()` (es superficie de
compatibilidad), igual que los shims de WI-76. La diferencia es que aqui
la mitad SI esta verificada: no es un falso exito, es una red a medio
coser.

Ademas, al fijar StoredBudget aparece una contradiccion: su docstring
dice "Serializa a dict preservando todas las columnas" y el metodo
devuelve 3 claves de las 6 del DTO — omite `tenant_id`, `project_id` y
`run_id`. No hay consumidor que diga cual de las dos cosas es la correcta
(un UPDATE se puede acotar con la identidad y no necesitarla en el
payload), asi que **este test fija el comportamiento real, no el
prometido**, y la contradiccion queda reportada para decision.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from skillgraph.platform.ports import (
    StoredBudget,
    StoredClaim,
    StoredEvidence,
    StoredPromotion,
)


def _claim() -> StoredClaim:
    return StoredClaim(
        claim_id="c1",
        tenant_id="t1",
        project_id="p1",
        subject_entity_id="file:src/foo.py",
        predicate="line_count",
        object_literal=42,
        source_id="local:src/foo.py",
        evidence_ids=("ev1", "ev2"),
        extraction_method="manual",
        extractor_version="skillgraph-rules/0.1.0",
        checked_at_revision="rev1",
        stale=False,
    )


def _evidence() -> StoredEvidence:
    return StoredEvidence(
        evidence_id="ev1",
        tenant_id="t1",
        project_id="p1",
        kind="manual",
        content={"line": 42},
        source_id="local:src/foo.py",
        observed_at="2026-01-02T00:00:00Z",
    )


def _promotion() -> StoredPromotion:
    return StoredPromotion(
        proposal_id="pr1",
        idempotency_key="idem-1",
        tenant_id="t1",
        source_project="p1",
        target_catalog="software",
        knowledge_ref="kr1",
        payload={"a": 1},
        status="pending",
        attempts=0,
        created_at="2026-01-03T00:00:00Z",
        updated_at="2026-01-03T00:00:00Z",
        published_at=None,
    )


def _budget() -> StoredBudget:
    return StoredBudget(
        tenant_id="t1",
        project_id="p1",
        run_id="r1",
        max_visits=10,
        max_runtime_seconds=300,
        max_events=1000,
    )


class TestToDictRoundtrip:
    """Simetria con los roundtrip que ya existen para los otros 5 DTO."""

    def test_claim_to_dict_preserves_legacy_column_names(self) -> None:
        d = _claim().to_dict()

        assert d["claim_id"] == "c1"
        assert d["subject_entity_id"] == "file:src/foo.py"
        assert d["predicate"] == "line_count"
        # El nombre historico de columna es *_json y el valor va serializado.
        assert d["object_literal_json"] == "42"
        assert json.loads(d["object_literal_json"]) == 42
        # `stale` sale como int, no como bool: es lo que espera la columna.
        assert d["stale"] == 0
        assert isinstance(d["stale"], int)
        assert d["evidence_ids"] == ("ev1", "ev2")

    def test_evidence_to_dict_preserves_legacy_column_names(self) -> None:
        d = _evidence().to_dict()

        assert d["evidence_id"] == "ev1"
        assert d["content_json"] == '{"line": 42}'
        assert json.loads(d["content_json"]) == {"line": 42}
        assert d["observed_at"] == "2026-01-02T00:00:00Z"

    def test_promotion_to_dict_keeps_payload_json_raw(self) -> None:
        d = _promotion().to_dict()

        assert d["proposal_id"] == "pr1"
        assert d["idempotency_key"] == "idem-1"
        assert d["payload_json"] == '{"a": 1}'
        assert json.loads(d["payload_json"]) == {"a": 1}
        assert d["status"] == "pending"
        assert d["published_at"] is None

    def test_budget_to_dict_returns_only_the_three_limits(self) -> None:
        """Comportamiento REAL, que no es el que promete el docstring.

        El docstring de `StoredBudget.to_dict` dice "preservando todas las
        columnas", pero devuelve 3 de las 6: omite `tenant_id`,
        `project_id` y `run_id`. Se fija lo que hace, no lo que dice, y la
        discrepancia se reporta aparte: decidir cual de las dos cosas es
        la correcta cambia el contrato y no es de este workitem.
        """
        d = _budget().to_dict()

        assert d == {"max_visits": 10, "max_runtime_seconds": 300, "max_events": 1000}
        # La identidad no sale: si alguien llegara a esperar las 6 claves,
        # este test lo delata en lugar de dejar que pase por alto.
        assert "run_id" not in d
        assert "tenant_id" not in d
        assert "project_id" not in d

    @pytest.mark.parametrize(
        "factory", [_claim, _evidence, _promotion, _budget], ids=lambda f: f.__name__
    )
    def test_to_dict_is_json_serialisable(self, factory: Any) -> None:
        """La salida tiene que sobrevivir a `json.dumps`: es lo que se emite."""
        json.dumps(factory().to_dict())


class TestDictCompatBranches:
    """`get(key, default)` y el `KeyError` de clave desconocida."""

    @pytest.mark.parametrize("factory", [_claim, _evidence], ids=lambda f: f.__name__)
    def test_get_returns_default_for_unknown_key(self, factory: Any) -> None:
        dto = factory()
        assert dto.get("columna_que_no_existe", "fallback") == "fallback"

    @pytest.mark.parametrize("factory", [_claim, _evidence], ids=lambda f: f.__name__)
    def test_get_returns_the_real_value_for_a_known_key(self, factory: Any) -> None:
        dto = factory()
        assert dto.get("tenant_id") == "t1"

    def test_getitem_raises_key_error_for_unknown_key(self) -> None:
        with pytest.raises(KeyError):
            _claim()["columna_que_no_existe"]
