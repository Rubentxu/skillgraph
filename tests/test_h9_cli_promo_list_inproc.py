"""H9 slice B: tests in-process del CLI runner para `sg promotion list`.

Cierra la limitacion declarada en README/CHANGELOG: "Cobertura 1st-person
del CLI (in-process)". Los tests de test_h8_public_paths.py invocan la CLI
como subproceso (recorrido de usuario real, sirve para UAT). Este archivo
cubre el adaptador CLI in-process, que pytest-cov SI ve.

Convenciones: bootstrap minimo in-process (cmd_init + cmd_project_create),
captura de stdout via capsys de pytest. Sin mocks.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from skillgraph.cli.runner import (
    cmd_init,
    cmd_project_create,
    cmd_promotion_list,
)
from skillgraph.platform.storage import Storage


def _bootstrap(tmp_path: Path, project: str) -> Path:
    """Inicializa data_root y crea un proyecto (ambos in-process).

    Devuelve el data_root. El nombre de proyecto es seguro (`[a-z0-9-_]+`).
    Las funciones del runner esperan `data_root: Path` (no str), asi que
    pasamos `Path` directamente al Namespace.
    """
    data_root = tmp_path / "sg-data"
    rc_init = cmd_init(argparse.Namespace(data_root=data_root))
    assert rc_init == 0
    rc_create = cmd_project_create(argparse.Namespace(data_root=data_root, name=project))
    assert rc_create == 0
    return data_root


def _project_db(data_root: Path, project: str) -> Path:
    """Ruta al .sqlite del proyecto dentro del data_root.

    Sigue la estructura interna de platform/paths.py; se deriva en lugar de
    hardcodear para que cualquier cambio futuro de layout no rompa este test
    sin un aviso explicito.
    """
    from skillgraph.cli.runner import DEFAULT_TENANT
    from skillgraph.platform.paths import project_db_path

    return project_db_path(data_root, project, tenant=DEFAULT_TENANT)


# ---------------------------------------------------------------------------
# Tests in-process del adaptador CLI (pytest-cov los ve)
# ---------------------------------------------------------------------------


class TestPromotionListEmpty:
    def test_empty_outbox_prints_marker_and_returns_ok(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        data_root = _bootstrap(tmp_path, project="u9b")
        rc = cmd_promotion_list(
            argparse.Namespace(data_root=data_root, project="u9b", pending=False)
        )
        out = capsys.readouterr().out
        assert rc == 0
        assert "(sin propuestas)" in out


class TestPromotionListAll:
    def test_list_all_shows_published_and_pending(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        data_root = _bootstrap(tmp_path, project="u9b")
        db_path = _project_db(data_root, "u9b")
        # Sembramos el outbox directamente via API Storage.
        s = Storage(db_path)
        try:
            s.register_promotion(
                proposal_id="p1",
                idempotency_key="k1",
                tenant_id="t1",
                source_project="src",
                target_catalog="tgt",
                knowledge_ref="c1",
                payload={"k": 1},
            )
            s.register_promotion(
                proposal_id="p2",
                idempotency_key="k2",
                tenant_id="t1",
                source_project="src",
                target_catalog="tgt",
                knowledge_ref="c2",
                payload={"k": 2},
            )
            s.mark_promotion_in_progress("p1")
            s.mark_promotion_published("p1")
        finally:
            s.close()

        rc = cmd_promotion_list(
            argparse.Namespace(data_root=data_root, project="u9b", pending=False)
        )
        out = capsys.readouterr().out
        assert rc == 0
        # Ambas propuestas visibles (PUBLISHED y PENDING).
        assert "p1" in out
        assert "p2" in out
        assert "PUBLISHED" in out
        assert "PENDING" in out


class TestPromotionListPendingOnly:
    def test_pending_flag_excludes_published(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        data_root = _bootstrap(tmp_path, project="u9b")
        db_path = _project_db(data_root, "u9b")
        s = Storage(db_path)
        try:
            s.register_promotion(
                proposal_id="p1",
                idempotency_key="k1",
                tenant_id="t1",
                source_project="src",
                target_catalog="tgt",
                knowledge_ref="c1",
                payload={"k": 1},
            )
            s.register_promotion(
                proposal_id="p2",
                idempotency_key="k2",
                tenant_id="t1",
                source_project="src",
                target_catalog="tgt",
                knowledge_ref="c2",
                payload={"k": 2},
            )
            s.mark_promotion_in_progress("p1")
            s.mark_promotion_published("p1")
        finally:
            s.close()

        rc = cmd_promotion_list(
            argparse.Namespace(data_root=data_root, project="u9b", pending=True)
        )
        out = capsys.readouterr().out
        assert rc == 0
        # Solo p2 PENDING; p1 PUBLISHED queda fuera.
        assert "p2" in out
        assert "p1" not in out


class TestPromotionListUnknownProject:
    def test_unknown_project_returns_error_code(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Proyecto inexistente: cmd retorna codigo != 0 y NO imprime propuestas."""
        data_root = _bootstrap(tmp_path, project="u9b")
        rc = cmd_promotion_list(
            argparse.Namespace(data_root=data_root, project="nope", pending=False)
        )
        assert rc != 0
        # No debe imprimir "(sin propuestas)" porque ni siquiera encontro el proyecto.
        out = capsys.readouterr().out
        assert "(sin propuestas)" not in out


class TestPromotionListInvariant:
    """Garantiza que el comando NO accede a storage._conn directamente.

    Cualquier acceso a atributos privados del Storage desde este modulo es
    un code smell. Lo verificamos con un grep simbolico en el codigo.
    """

    def test_no_storage_private_attr_access_in_promotion_list(self) -> None:
        import inspect

        from skillgraph.cli import runner

        src = inspect.getsource(runner.cmd_promotion_list)
        assert "storage._conn" not in src, (
            "cmd_promotion_list no debe acceder a atributos privados de Storage; "
            "usa la API publica (Storage.list_promotions / list_pending_promotions)."
        )
        assert "_json" not in src, (
            "cmd_promotion_list no debe serializar/deserializar JSON manualmente."
        )
