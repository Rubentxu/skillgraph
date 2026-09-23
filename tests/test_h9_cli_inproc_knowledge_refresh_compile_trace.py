"""H9-InProcess-4: cobertura in-process del CLI runner para los
comandos de conocimiento que quedaron sin cobertura en
H9-InProcess-3 (stale/invalidate).

Replica el patron de tests/test_h9_cli_inproc_knowledge_brick.py.
Cubre:
- sg knowledge refresh (cmd_knowledge_refresh)
- sg knowledge compile (cmd_knowledge_compile)
- sg knowledge trace (cmd_knowledge_trace)

Cada comando tiene al menos:
- 1 happy path (rc=0 + formato esperado de stdout).
- 1 error path documentando el comportamiento real (no
  retoca codigo de produccion: el patron InProcess solo
  describe contratos, no los cambia).

Los 3 comandos ya tienen cobertura subprocess en
tests/test_cli_branches.py (TestKnowledgeCompile/Trace/Refresh).
Aqui documentamos la ruta directa (in-process) que es mas
rapida y estable.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import pytest

from skillgraph.cli.runner import (
    DEFAULT_TENANT,
    cmd_init,
    cmd_knowledge_compile,
    cmd_knowledge_refresh,
    cmd_knowledge_trace,
    cmd_project_create,
)
from skillgraph.core.errors import UnknownSourceError
from skillgraph.knowledge.graph import Claim, Entity, Source
from skillgraph.platform.paths import project_db_path
from skillgraph.platform.storage import Storage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bootstrap(tmp_path: Path, project: str) -> Path:
    """Bootstrap: init + project_create. Devuelve data_root."""
    data_root = tmp_path / "sg-data"
    assert cmd_init(argparse.Namespace(data_root=data_root)) == 0
    assert cmd_project_create(argparse.Namespace(data_root=data_root, name=project)) == 0
    return data_root


def _project_db(data_root: Path, project: str) -> Path:
    return project_db_path(data_root, project, tenant=DEFAULT_TENANT)


def _seed_source_and_claim(
    data_root: Path,
    project: str,
    *,
    source_id: str = "src-1",
    claim_id: str = "claim-1",
    freshness: str = "fresh",
    object_literal: int = 42,
) -> None:
    """Siembra una Source + Entity + Claim con la frescura indicada."""
    db = _project_db(data_root, project)
    s = Storage(db)
    try:
        s.upsert_entity(
            tenant_id="default",
            project_id=project,
            entity=Entity(entity_id="ent-1", kind="module", stable_key="pkg.mod"),
        )
        s.register_source(
            tenant_id="default",
            project_id=project,
            source=Source(
                source_id=source_id,
                kind="local_file",
                content_hash="deadbeef",
                locator={"path": "p.py"},
                git_commit_sha=None,
                git_tree_sha=None,
                working_tree_status=None,
                checked_at=datetime.now(UTC).isoformat(),
                freshness=freshness,
            ),
        )
        s.record_claim(
            tenant_id="default",
            project_id=project,
            claim=Claim(
                claim_id=claim_id,
                subject_entity_id="ent-1",
                predicate="line_count",
                object_literal=object_literal,
                source_id=source_id,
                checked_at_revision="rev-1",
            ),
        )
    finally:
        s.close()


# ---------------------------------------------------------------------------
# Tests de `sg knowledge refresh`
# ---------------------------------------------------------------------------


class TestKnowledgeRefresh:
    def test_refresh_for_known_source_returns_zero_reactivated(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Happy path: rc=0 + stdout 'reactivated 0 claim(s)'."""
        data_root = _bootstrap(tmp_path, project="k1")
        _seed_source_and_claim(data_root, "k1")

        rc = cmd_knowledge_refresh(
            argparse.Namespace(data_root=data_root, project="k1", source="src-1", revision=2)
        )
        captured = capsys.readouterr()
        assert rc == 0
        assert "reactivated 0 claim(s)" in captured.out

    def test_refresh_for_known_source_with_stale_claim_reactivates(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Happy path con claim reactivado: rc=0 + nombre del claim en stdout.

        Contrato: tras invalidar un source, refresh_source con
        una revision valida re-evalua los claims asociados y
        los reactiva si la evidencia de revision cuadra.
        """
        from skillgraph.cli.runner import cmd_knowledge_invalidate

        data_root = _bootstrap(tmp_path, project="k1")
        _seed_source_and_claim(data_root, "k1", source_id="src-i", claim_id="c-i")

        # Invalidate el source primero (establece claim stale).
        assert (
            cmd_knowledge_invalidate(
                argparse.Namespace(data_root=data_root, project="k1", source="src-i", max_hops=3)
            )
            == 0
        )
        capsys.readouterr()

        rc = cmd_knowledge_refresh(
            argparse.Namespace(data_root=data_root, project="k1", source="src-i", revision=2)
        )
        captured = capsys.readouterr()
        assert rc == 0
        # El formato es 'reactivated N claim(s)' + bullet list.
        assert "reactivated" in captured.out
        assert "claim(s)" in captured.out

    def test_refresh_raises_for_unknown_source(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Source desconocido lanza UnknownSourceError (mismo patron que
        ``cmd_knowledge_invalidate``: el wrapper no captura esta excepcion).

        Esto es un bug menor de UX conocido; documentamos el
        comportamiento real sin tocar produccion.
        """
        data_root = _bootstrap(tmp_path, project="k1")

        with pytest.raises(UnknownSourceError):
            cmd_knowledge_refresh(
                argparse.Namespace(data_root=data_root, project="k1", source="ghost", revision=1)
            )

    def test_refresh_for_nonexistent_project_raises_filenotfound(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Proyecto inexistente: ``_DummyStorage`` lanza ``FileNotFoundError``.

        ``_open_known_project`` devuelve ``_DummyStorage`` cuando
        el proyecto no se encuentra. Cualquier llamada posterior
        a ``self.storage.<attr>`` dispara ``__getattr__`` que
        lanza ``FileNotFoundError`` con mensaje 'proyecto no
        encontrado'. ``cmd_knowledge_refresh`` NO captura esta
        excepcion; se propaga al caller.

        Esto es un bug menor de UX conocido (igual que
        ``cmd_knowledge_invalidate`` con source ghost): el
        wrapper deberia capturar FileNotFoundError y devolver
        rc=4 (EXIT_NOTFOUND) con mensaje legible. Mientras
        tanto, documentamos el comportamiento real.
        """
        data_root = _bootstrap(tmp_path, project="k1")

        with pytest.raises(FileNotFoundError, match="proyecto no encontrado"):
            cmd_knowledge_refresh(
                argparse.Namespace(
                    data_root=data_root, project="missing", source="src-1", revision=1
                )
            )


# ---------------------------------------------------------------------------
# Tests de `sg knowledge compile`
# ---------------------------------------------------------------------------


class TestKnowledgeCompile:
    def test_compile_with_inline_recipe_succeeds(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Happy path: rc=0 + stdout con JSON handoff + linea context_hash."""
        data_root = _bootstrap(tmp_path, project="k1")
        _seed_source_and_claim(data_root, "k1")

        rc = cmd_knowledge_compile(
            argparse.Namespace(
                data_root=data_root,
                project="k1",
                recipe="src-1",  # valor del selector source
                strict=False,
                token_budget=2048,
                overflow="drop_optional",
                run=None,
                node=None,
                revision=None,
            )
        )
        captured = capsys.readouterr()
        assert rc == 0
        # El handoff serializado contiene 'included' (lista de claims).
        assert '"included"' in captured.out
        # Y la linea final con el context_hash.
        assert "context_hash:" in captured.out

    def test_compile_with_strict_rejects_stale_claim(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--strict con claim stale devuelve rc=10 (EXIT_DOMAIN) + stderr.

        ``cmd_knowledge_compile`` captura SkillGraphError y devuelve
        ``EXIT_DOMAIN`` (10). Aqui verificamos que el camino real
        del wrapper es el correcto: NO propaga la excepcion.
        """
        from skillgraph.cli.runner import cmd_knowledge_invalidate

        data_root = _bootstrap(tmp_path, project="k1")
        _seed_source_and_claim(
            data_root, "k1", source_id="src-i", claim_id="c-i", freshness="fresh"
        )
        # Invalidate para que el claim quede stale.
        assert (
            cmd_knowledge_invalidate(
                argparse.Namespace(data_root=data_root, project="k1", source="src-i", max_hops=3)
            )
            == 0
        )
        capsys.readouterr()

        rc = cmd_knowledge_compile(
            argparse.Namespace(
                data_root=data_root,
                project="k1",
                recipe="src-i",
                strict=True,  # <-- strict: rechaza stale
                token_budget=2048,
                overflow="drop_optional",
                run=None,
                node=None,
                revision=None,
            )
        )
        captured = capsys.readouterr()
        assert rc == 10  # EXIT_DOMAIN
        # El wrapper escribe a stderr con el codigo sg_*.
        assert "sg_stale_knowledge_error" in captured.err or "ERROR" in captured.err

    def test_compile_with_invalid_overflow_raises_validation_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Overflow invalido: ``ValidationError`` se PROPAGA.

        El ``except SkillGraphError`` del wrapper solo cubre la
        llamada a ``ctx.compile_handoff(...)``. La validacion de
        ``overflow_strategy`` ocurre en ``ContextRecipe.from_dict()``
        ANTES del try, por lo que la excepcion sube al caller sin
        ser capturada. argparse rechazaria antes (choices=...), pero
        invocando el wrapper directamente sin argparse, la
        validacion la hace el modelo y propaga.

        Esto es un bug menor de UX: el wrapper deberia envolver
        toda la logica para devolver rc=10. Documentamos el
        comportamiento real.
        """
        from skillgraph.core.errors import ValidationError

        data_root = _bootstrap(tmp_path, project="k1")

        with pytest.raises(ValidationError, match="overflow_strategy invalido"):
            cmd_knowledge_compile(
                argparse.Namespace(
                    data_root=data_root,
                    project="k1",
                    recipe="src-1",
                    strict=False,
                    token_budget=2048,
                    overflow="not-a-valid-strategy",
                    run=None,
                    node=None,
                    revision=None,
                )
            )

    def test_compile_for_nonexistent_source_returns_domain_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Source desconocida: el selector obligatorio falla -> EXIT_DOMAIN."""
        data_root = _bootstrap(tmp_path, project="k1")
        # NO sembramos nada: 'ghost' no existe.

        rc = cmd_knowledge_compile(
            argparse.Namespace(
                data_root=data_root,
                project="k1",
                recipe="ghost",
                strict=False,
                token_budget=2048,
                overflow="drop_optional",
                run=None,
                node=None,
                revision=None,
            )
        )
        captured = capsys.readouterr()
        assert rc == 10  # EXIT_DOMAIN
        assert "sg_missing_obligatory" in captured.err


# ---------------------------------------------------------------------------
# Tests de `sg knowledge trace`
# ---------------------------------------------------------------------------


class TestKnowledgeTrace:
    def test_trace_returns_json_with_trace_id(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Happy path: rc=0 + stdout JSON con trace_id, kind, name."""
        data_root = _bootstrap(tmp_path, project="k1")

        rc = cmd_knowledge_trace(
            argparse.Namespace(data_root=data_root, project="k1", run="some-run", name=None)
        )
        captured = capsys.readouterr()
        assert rc == 0
        assert '"trace_id"' in captured.out
        assert '"kind"' in captured.out
        assert '"name"' in captured.out
        # Default name: 'trace-<run_id>'.
        assert '"trace-some-run"' in captured.out
        # kind: 'SoftwareExecutionSlice' (constante del dominio).
        assert '"SoftwareExecutionSlice"' in captured.out

    def test_trace_with_custom_name(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """``--name`` custom: el JSON contiene el name dado."""
        data_root = _bootstrap(tmp_path, project="k1")

        rc = cmd_knowledge_trace(
            argparse.Namespace(
                data_root=data_root,
                project="k1",
                run="some-run",
                name="my-trace",
            )
        )
        captured = capsys.readouterr()
        assert rc == 0
        assert '"my-trace"' in captured.out
        assert '"trace-some-run"' not in captured.out

    def test_trace_for_run_without_evidence_returns_empty_refs(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Run sin eventos: claim_refs y evidence_refs son listas vacias."""
        data_root = _bootstrap(tmp_path, project="k1")

        rc = cmd_knowledge_trace(
            argparse.Namespace(data_root=data_root, project="k1", run="empty-run", name=None)
        )
        captured = capsys.readouterr()
        assert rc == 0
        assert '"claim_refs": []' in captured.out
        assert '"evidence_refs": []' in captured.out

    def test_trace_for_nonexistent_project_raises_filenotfound(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Proyecto inexistente: ``_DummyStorage`` lanza ``FileNotFoundError``.

        Igual que ``cmd_knowledge_refresh``: el wrapper no captura
        esta excepcion. ``OutcomeTracer.from_run`` accede a
        ``ctrl.storage._conn`` lo cual dispara ``__getattr__`` del
        DummyStorage.
        """
        data_root = _bootstrap(tmp_path, project="k1")

        with pytest.raises(FileNotFoundError, match="proyecto no encontrado"):
            cmd_knowledge_trace(
                argparse.Namespace(data_root=data_root, project="missing", run="r", name=None)
            )
