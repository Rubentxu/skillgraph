"""Tests del modulo runtime.redaction (Etapa 7 / S5)."""

from __future__ import annotations

import pytest

from skillgraph.core.errors import ValidationError
from skillgraph.runtime.redaction import (
    REDACTED_MARKER,
    RedactionPolicy,
    redact_payload,
    validate_policy,
)


class TestValidatePolicy:
    """Validacion de la smart constructor `validate_policy`."""

    def test_validate_policy_accepts_known_policies(self) -> None:
        """validate_policy acepta las 4 politicas canonicas."""
        for p in ("none", "metadata", "payload", "full"):
            result = validate_policy(p)
            assert result == p
            assert isinstance(result, str)

    def test_validate_policy_rejects_unknown(self) -> None:
        """validate_policy lanza ValidationError para politicas invalidas."""
        with pytest.raises(ValidationError):
            validate_policy("mask")
        with pytest.raises(ValidationError):
            validate_policy("")
        with pytest.raises(ValidationError):
            validate_policy("NONE")  # case-sensitive


class TestRedactNone:
    """`policy='none'` debe ser passthrough (compat con versiones previas)."""

    def test_none_returns_shallow_copy(self) -> None:
        """`none` devuelve copia superficial sin modificar valores."""
        original = {"api_key": "sk-123", "value": 42}
        out = redact_payload(original, "none")
        assert out == original
        assert out is not original  # copia, no alias

    def test_none_does_not_redact_secret(self) -> None:
        """`none` permite que secretos pasen intactos."""
        original = {"token": "abc123"}
        out = redact_payload(original, "none")
        assert out["token"] == "abc123"


class TestRedactMetadata:
    """`policy='metadata'`: conserva claves, redacta valores."""

    def test_metadata_redacts_all_values(self) -> None:
        """`metadata` reemplaza TODOS los valores por REDACTED."""
        original = {"api_key": "sk-123", "user": "alice", "count": 5}
        out = redact_payload(original, "metadata")
        assert set(out.keys()) == set(original.keys())
        assert all(v == REDACTED_MARKER for v in out.values())

    def test_metadata_preserves_nested_dict_keys(self) -> None:
        """`metadata` aplana a 1 nivel: las claves del nivel superior se
        mantienen, los valores (incluso si son dicts) se redactan."""
        original = {"outer": {"inner": "secret"}}
        out = redact_payload(original, "metadata")
        # El valor anidado se reemplaza por el marcador (no se preserva
        # la estructura).
        assert out == {"outer": REDACTED_MARKER}


class TestRedactFull:
    """`policy='full'`: descarta TODO el payload."""

    def test_full_returns_empty_dict(self) -> None:
        """`full` devuelve {} independientemente del contenido."""
        original = {"a": 1, "b": "secret", "c": [1, 2, 3]}
        out = redact_payload(original, "full")
        assert out == {}

    def test_full_on_empty_payload(self) -> None:
        """`full` sobre payload vacio devuelve {}."""
        out = redact_payload({}, "full")
        assert out == {}


class TestRedactPayload:
    """`policy='payload'`: redaccion recursiva."""

    def test_payload_redacts_scalars_but_preserves_collections(self) -> None:
        """`payload` redacta escalares y conserva la forma de colecciones."""
        original = {
            "name": "alice",
            "api_key": "sk-123",
            "tags": ["urgent", "internal"],
            "meta": {"created_at": "2026-01-01", "owner": "bob"},
        }
        out = redact_payload(original, "payload")
        # Escalares redactados.
        assert out["name"] == REDACTED_MARKER
        assert out["api_key"] == REDACTED_MARKER
        # Colecciones conservadas (forma), contenido redactado.
        assert out["tags"] == [REDACTED_MARKER, REDACTED_MARKER]
        assert out["meta"] == {
            "created_at": REDACTED_MARKER,
            "owner": REDACTED_MARKER,
        }

    def test_payload_redacts_nested_dict_deeply(self) -> None:
        """`payload` recursa en dicts anidados a cualquier profundidad."""
        original = {"a": {"b": {"c": "secret"}}}
        out = redact_payload(original, "payload")
        assert out == {"a": {"b": {"c": REDACTED_MARKER}}}

    def test_payload_preserves_tuples_immutably(self) -> None:
        """`payload` convierte tuplas en tuplas (no listas)."""
        original = {"k": ("a", "b")}
        out = redact_payload(original, "payload")
        assert out["k"] == (REDACTED_MARKER, REDACTED_MARKER)
        assert isinstance(out["k"], tuple)


class TestRedactionPurity:
    """Invariantes funcionales: pureza, no mutacion del input."""

    def test_redact_does_not_mutate_input(self) -> None:
        """Ninguna politica muta el payload original."""
        original = {
            "api_key": "sk-123",
            "nested": {"secret": "value"},
            "list": [1, 2, 3],
        }
        snapshot = {
            "api_key": "sk-123",
            "nested": {"secret": "value"},
            "list": [1, 2, 3],
        }
        for policy in ("none", "metadata", "payload", "full"):
            redact_payload(original, policy)
            assert original == snapshot, f"policy={policy} muto el input"

    def test_redact_is_deterministic(self) -> None:
        """Misma entrada + misma politica -> misma salida."""
        original = {"a": 1, "b": {"c": 2}}
        for policy in ("metadata", "payload", "full"):
            out1 = redact_payload(original, policy)  # type: ignore[arg-type]
            out2 = redact_payload(original, policy)  # type: ignore[arg-type]
            assert out1 == out2


class TestRedactionTypeAnnotation:
    """Sanity: el tipo RedactionPolicy existe y cubre 4 valores."""

    def test_redaction_policy_is_literal(self) -> None:
        """`RedactionPolicy` es un Literal cerrado (compile-time check)."""
        # Esto verifica la exportacion del simbolo. El checking real es
        # estatico (mypy/pyright).
        assert RedactionPolicy is not None


class TestStoragePolicyPersistence:
    """Storage.get_policy / upsert_policy round-trip (S5 Etapa 7).

    Estos tests usan Storage directamente (sin EventLog) para
    verificar la capa de persistencia aislada.
    """

    def test_get_policy_returns_none_when_absent(self, tmp_path) -> None:
        """Tenant sin politica configurada -> get_policy devuelve None."""
        from skillgraph.platform.storage import Storage

        s = Storage(tmp_path / "project.sqlite")
        result = s.get_policy(tenant_id="acme")
        assert result is None

    def test_upsert_then_get_policy_round_trip(self, tmp_path) -> None:
        """upsert + get preserva la politica configurada."""
        from skillgraph.platform.storage import Storage

        s = Storage(tmp_path / "project.sqlite")
        s.upsert_policy(tenant_id="acme", policy="payload")
        assert s.get_policy(tenant_id="acme") == "payload"
        s.upsert_policy(tenant_id="acme", policy="full")
        assert s.get_policy(tenant_id="acme") == "full"

    def test_upsert_is_idempotent(self, tmp_path) -> None:
        """upsert idempotente: 2 llamadas con mismo tenant y policy = 1 fila."""
        from skillgraph.platform.storage import Storage

        s = Storage(tmp_path / "project.sqlite")
        for _ in range(3):
            s.upsert_policy(tenant_id="acme", policy="metadata")
        assert s.get_policy(tenant_id="acme") == "metadata"


class TestEventLogRedaction:
    """Integracion EventLog + policy_resolver (S5 Etapa 7)."""

    def test_eventlog_redacts_payload_when_resolver_returns_metadata(self, tmp_path) -> None:
        """Resolver explicito 'metadata': claves conservadas, valores [REDACTED]."""
        import json as _json

        from skillgraph.runtime.engine import EventBuilder, EventLog

        log = EventLog(
            _open_conn(tmp_path),
            policy_resolver=lambda _tenant: "metadata",
        )
        eb = EventBuilder(tenant_id="t", project_id="p", correlation_id="c")
        ev = eb.run_created(run_id="r", initial_node="a")
        log.append(ev)
        conn = log._conn  # type: ignore[attr-defined]
        row = conn.execute(
            "SELECT payload_json FROM runtime_events WHERE event_id = ?",
            (ev.event_id,),
        ).fetchone()
        persisted = _json.loads(row["payload_json"])
        # metadata: claves conservadas, valores [REDACTED].
        assert all(v == REDACTED_MARKER for v in persisted.values()), persisted

    def test_eventlog_passes_through_by_default(self, tmp_path) -> None:
        """Sin resolver -> default 'none': payload integro en disco."""
        import json as _json

        from skillgraph.runtime.engine import EventBuilder, EventLog

        log = EventLog(_open_conn(tmp_path), policy_resolver=None)
        eb = EventBuilder(tenant_id="t", project_id="p", correlation_id="c")
        ev = eb.run_created(run_id="r", initial_node="a")
        log.append(ev)
        conn = log._conn  # type: ignore[attr-defined]
        row = conn.execute(
            "SELECT payload_json FROM runtime_events WHERE event_id = ?",
            (ev.event_id,),
        ).fetchone()
        persisted = _json.loads(row["payload_json"])
        # Default 'none' = payload integro (compat pre-S5).
        assert persisted.get("initial_node") == "a"

    def test_eventlog_redacts_with_policy_payload(self, tmp_path) -> None:
        """policy='payload' redacta recursivamente."""
        import json as _json

        from skillgraph.runtime.engine import EventBuilder, EventLog

        log = EventLog(
            _open_conn(tmp_path),
            policy_resolver=lambda _tenant: "payload",
        )
        eb = EventBuilder(tenant_id="t", project_id="p", correlation_id="c")
        ev = eb.node_started(run_id="r", node_execution_id="ne-1")
        log.append(ev)
        conn = log._conn  # type: ignore[attr-defined]
        row = conn.execute(
            "SELECT payload_json FROM runtime_events WHERE event_id = ?",
            (ev.event_id,),
        ).fetchone()
        persisted = _json.loads(row["payload_json"])
        # Todos los valores escalares del payload deberian ser REDACTED.
        for v in persisted.values():
            if isinstance(v, str):
                assert v == REDACTED_MARKER

    def test_eventlog_passes_through_with_policy_none(self, tmp_path) -> None:
        """Resolver explicito 'none' -> passthrough (compat con pre-S5)."""
        import json as _json

        from skillgraph.runtime.engine import EventBuilder, EventLog

        log = EventLog(
            _open_conn(tmp_path),
            policy_resolver=lambda _tenant: "none",
        )
        eb = EventBuilder(tenant_id="t", project_id="p", correlation_id="c")
        ev = eb.run_created(run_id="r", initial_node="a")
        log.append(ev)
        conn = log._conn  # type: ignore[attr-defined]
        row = conn.execute(
            "SELECT payload_json FROM runtime_events WHERE event_id = ?",
            (ev.event_id,),
        ).fetchone()
        persisted = _json.loads(row["payload_json"])
        # Con policy=none, los valores se preservan.
        assert "initial_node" in persisted
        assert persisted["initial_node"] == "a"


def _open_conn(tmp_path) -> object:
    """Helper: abre una conexion SQLite con row_factory=Row."""
    import sqlite3 as _sqlite3

    conn = _sqlite3.connect(str(tmp_path / "redaction_test.sqlite"))
    conn.row_factory = _sqlite3.Row
    return conn
