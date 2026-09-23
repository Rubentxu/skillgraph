"""H9-InProcess-3: cobertura in-process del CLI runner para comandos
de conocimiento y registro de bricks.

Replica el patron de tests/test_h9_cli_inproc_promo_pack.py (H9-InProcess-2).
Mismo setup in-process; foco en los comandos que quedan sin cobertura:
- sg knowledge stale
- sg knowledge invalidate
- sg brick register

El resto (compile, trace, refresh, run) queda pendiente en deuda;
no se incluyen aqui porque son mas complejos o requieren subprocess
(failpoint en run) y harian este slice mas grande de lo razonable.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from skillgraph.cli.runner import (
    DEFAULT_TENANT,
    cmd_brick_register,
    cmd_init,
    cmd_knowledge_invalidate,
    cmd_knowledge_stale,
    cmd_project_create,
)
from skillgraph.knowledge.graph import Claim, Entity, Source
from skillgraph.platform.paths import project_db_path
from skillgraph.platform.storage import Storage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bootstrap(tmp_path: Path, project: str) -> Path:
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
                object_literal=42,
                source_id=source_id,
                checked_at_revision="rev-1",
            ),
        )
    finally:
        s.close()


# ---------------------------------------------------------------------------
# Tests de `sg knowledge stale`
# ---------------------------------------------------------------------------


class TestKnowledgeStale:
    def test_empty_knowledge_returns_zero_count(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Sin claims -> mensaje 'stale claims (0):' y rc=0."""
        data_root = _bootstrap(tmp_path, project="k1")
        rc = cmd_knowledge_stale(argparse.Namespace(data_root=data_root, project="k1"))
        captured = capsys.readouterr()
        assert rc == 0
        assert "stale claims (0)" in captured.out

    def test_fresh_claim_not_listed_as_stale(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Claim con source 'fresh' NO aparece (smoke caso 2 verificado)."""
        data_root = _bootstrap(tmp_path, project="k1")
        _seed_source_and_claim(data_root, "k1", freshness="fresh")

        rc = cmd_knowledge_stale(argparse.Namespace(data_root=data_root, project="k1"))
        captured = capsys.readouterr()
        assert rc == 0
        assert "stale claims (0)" in captured.out
        assert "claim-1" not in captured.out

    def test_stale_claim_listed_after_invalidation(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Tras invalidar un source, list_stale lo incluye (smoke caso 5)."""
        data_root = _bootstrap(tmp_path, project="k1")
        _seed_source_and_claim(data_root, "k1", source_id="src-i", claim_id="c-i")

        # Invalidate el source primero (establece el camino correcto).
        rc_inv = cmd_knowledge_invalidate(
            argparse.Namespace(data_root=data_root, project="k1", source="src-i", max_hops=3)
        )
        assert rc_inv == 0
        capsys.readouterr()

        rc = cmd_knowledge_stale(argparse.Namespace(data_root=data_root, project="k1"))
        captured = capsys.readouterr()
        assert rc == 0
        assert "stale claims (1)" in captured.out
        assert "c-i" in captured.out


# ---------------------------------------------------------------------------
# Tests de `sg knowledge invalidate`
# ---------------------------------------------------------------------------


class TestKnowledgeInvalidate:
    def test_invalidate_raises_for_unknown_source(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Source desconocido lanza UnknownSourceError (smoke caso 3).

        El wrapper cli NO captura la excepcion todavia: la propaga. Esto es
        un bug menor de UX (mejor devolver rc != 0 con mensaje); mientras
        tanto, documentamos el comportamiento real.
        """
        from skillgraph.core.errors import UnknownSourceError

        data_root = _bootstrap(tmp_path, project="k1")
        with pytest.raises(UnknownSourceError):
            cmd_knowledge_invalidate(
                argparse.Namespace(data_root=data_root, project="k1", source="ghost", max_hops=3)
            )

    def test_invalidate_for_known_source_invalidates_claim(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Con un claim asociado a la source, lo invalida (smoke caso 4)."""
        data_root = _bootstrap(tmp_path, project="k1")
        _seed_source_and_claim(data_root, "k1", source_id="src-i", claim_id="c-i")

        rc = cmd_knowledge_invalidate(
            argparse.Namespace(data_root=data_root, project="k1", source="src-i", max_hops=3)
        )
        captured = capsys.readouterr()
        assert rc == 0
        assert "invalidated" in captured.out
        assert "c-i" in captured.out


# ---------------------------------------------------------------------------
# Tests de `sg brick register`
# ---------------------------------------------------------------------------

# Brick minimo valido (cumple el formato esperado por el parser/registry).
_BRICK_MIN = """---
apiVersion: skillgraph.dev/v1alpha1
kind: ActionNode
metadata:
  name: brick-min
  namespace: ns-tools
spec:
  capabilities:
    - lint
  inputs:
    - name: target
      type: core.EntityRef
      required: true
  transitions:
    SUCCEEDED: done
    FAILED: failed
---

# Brick minimo para H9-InProcess-3.
"""


class TestBrickRegister:
    def test_register_valid_brick_persists_resource(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        data_root = _bootstrap(tmp_path, project="k1")
        brick = tmp_path / "brick.md"
        brick.write_text(_BRICK_MIN, encoding="utf-8")

        rc = cmd_brick_register(argparse.Namespace(data_root=data_root, project="k1", path=brick))
        captured = capsys.readouterr()
        assert rc == 0
        assert "Brick registrado" in captured.out
        assert "ActionNode/ns-tools/brick-min" in captured.out

    def test_register_invalid_brick_returns_parse_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Brick con YAML malformado -> EXIT_PARSE (11)."""
        data_root = _bootstrap(tmp_path, project="k1")
        brick = tmp_path / "bad.md"
        brick.write_text("---\nEsto NO es YAML valido: : :\n", encoding="utf-8")

        rc = cmd_brick_register(argparse.Namespace(data_root=data_root, project="k1", path=brick))
        assert rc == 11  # EXIT_PARSE
        captured = capsys.readouterr()
        assert "ERROR" in captured.err

    def test_register_unknown_project_returns_not_found(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Proyecto destino inexistente -> exit code != 0."""
        data_root = _bootstrap(tmp_path, project="k1")
        brick = tmp_path / "any.md"
        brick.write_text(_BRICK_MIN, encoding="utf-8")

        rc = cmd_brick_register(argparse.Namespace(data_root=data_root, project="nope", path=brick))
        assert rc != 0


# ---------------------------------------------------------------------------
# Acceptance path real: binario publico contra los 3 comandos cubiertos.
# El CLI runner envuelve main() en try/except SkillGraphError -> EXIT_DOMAIN;
# estos tests ejercitan la ruta publica completa (subprocess) para confirmar
# que el contrato externo (exit codes tipados) se cumple.
# ---------------------------------------------------------------------------


def _sg(data_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Ejecuta el binario publico en un data_root aislado."""
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(data_root.parent / "xdg")
    env["SKILLGRAPH_DATA_ROOT"] = str(data_root)
    return subprocess.run(
        [sys.executable, "-m", "skillgraph", "--data-root", str(data_root), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=60,
    )


class TestAcceptancePathKnowledgeAndBrick:
    def test_knowledge_invalidate_ghost_returns_exit_domain(
        self,
        tmp_path: Path,
    ) -> None:
        """Public CLI: source inexistente -> rc=10 (EXIT_DOMAIN)."""
        data_root = tmp_path / "sg-data"
        assert _sg(data_root, "init").returncode == 0
        assert _sg(data_root, "project", "create", "k1").returncode == 0

        r = _sg(data_root, "knowledge", "invalidate", "--source", "ghost", "k1")
        assert r.returncode == 10  # EXIT_DOMAIN
        assert "unknown_source" in r.stderr.lower() or "ghost" in r.stderr

    def test_knowledge_stale_empty_returns_ok(self, tmp_path: Path) -> None:
        """Public CLI: knowledge stale en outbox vacio -> rc=0."""
        data_root = tmp_path / "sg-data"
        assert _sg(data_root, "init").returncode == 0
        assert _sg(data_root, "project", "create", "k1").returncode == 0

        r = _sg(data_root, "knowledge", "stale", "k1")
        assert r.returncode == 0
        assert "stale claims (0)" in r.stdout

    def test_brick_register_valid_persists(self, tmp_path: Path) -> None:
        """Public CLI: brick valido -> rc=0, persistencia confirma."""
        data_root = tmp_path / "sg-data"
        assert _sg(data_root, "init").returncode == 0
        assert _sg(data_root, "project", "create", "k1").returncode == 0

        brick = tmp_path / "brick.md"
        brick.write_text(_BRICK_MIN, encoding="utf-8")

        r = _sg(data_root, "brick", "k1", str(brick))
        assert r.returncode == 0
        assert "Brick registrado" in r.stdout
        assert "ActionNode/ns-tools/brick-min" in r.stdout
