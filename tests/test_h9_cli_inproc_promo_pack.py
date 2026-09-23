"""H9-InProcess-2: cobertura in-process del CLI runner para los comandos
criticos de promocion y pack que faltan tras H9-BSlice1.

Aporta cobertura adicional que pytest-cov SI ve (los tests subprocess de
test_h8_public_paths.py son end-to-end reales, pero pytest-cov no cuenta
el CLI runner que cubren -> su contribucion a la cobertura es 0).

Patron replicado de tests/test_h9_cli_promo_list_inproc.py:
- bootstrap in-process con cmd_init + cmd_project_create.
- siembra via API Storage directa (no via CLI; replica la nota del
  _seed_claim de test_h8_public_paths.py: el CLI no expone comandos
  de creacion de claims porque el subsistema de conocimiento los emite
  en H3).
- invoca cmd_* in-process y assertea rc + stdout/stderr via capsys.

Limitacion documentada:
- `cmd_promotion_reconcile` no se cubre in-process en escenarios con
  failpoint (`os._exit(9)` no es capturable por pytest). Esos caminos
  los cubre subprocess en test_h8_public_paths.py. Aqui cubrimos solo
  la rama nominal.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import pytest

from skillgraph.cli.runner import (
    DEFAULT_TENANT,
    cmd_expansion_show,
    cmd_init,
    cmd_pack_load,
    cmd_project_create,
    cmd_promotion_reconcile,
    cmd_promotion_submit,
)
from skillgraph.knowledge.graph import Claim, Entity, Source
from skillgraph.platform.paths import project_db_path
from skillgraph.platform.storage import Storage

# ---------------------------------------------------------------------------
# Helpers (replican el patron de _seed_claim / _project_db del slice 1)
# ---------------------------------------------------------------------------


def _bootstrap(tmp_path: Path, project: str) -> Path:
    """Inicializa data_root y crea un proyecto. Devuelve el data_root."""
    data_root = tmp_path / "sg-data"
    rc_init = cmd_init(argparse.Namespace(data_root=data_root))
    assert rc_init == 0
    rc_create = cmd_project_create(argparse.Namespace(data_root=data_root, name=project))
    assert rc_create == 0
    return data_root


def _project_db(data_root: Path, project: str) -> Path:
    """Ruta al .sqlite del proyecto (deriva de platform/paths.py)."""
    return project_db_path(data_root, project, tenant=DEFAULT_TENANT)


def _seed_claim(
    data_root: Path,
    project: str,
    claim_id: str = "claim-1",
) -> None:
    """Siembra entity + source + claim en el proyecto (vía API Storage)."""
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
                source_id="src-1",
                kind="local_file",
                content_hash="deadbeef",
                locator={"path": "p.py"},
                git_commit_sha=None,
                git_tree_sha=None,
                working_tree_status=None,
                checked_at=datetime.now(UTC).isoformat(),
                freshness="fresh",
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
                source_id="src-1",
                checked_at_revision="rev-1",
            ),
        )
    finally:
        s.close()


def _ns(
    data_root: Path,
    project: str,
    claim_id: str = "claim-1",
    target: str = "dest",
    proposal_id: str | None = None,
) -> argparse.Namespace:
    """Namespace tipico para cmd_promotion_submit."""
    return argparse.Namespace(
        data_root=data_root,
        project=project,
        claim_id=claim_id,
        target=target,
        proposal_id=proposal_id,
    )


# ---------------------------------------------------------------------------
# Tests de `sg promotion submit`
# ---------------------------------------------------------------------------


class TestPromotionSubmitHappyPath:
    def test_submit_creates_proposal_in_pending(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Submit happy path: rc=0, propuesta registrada en outbox como PENDING."""
        data_root = _bootstrap(tmp_path, project="orig")
        _seed_claim(data_root, "orig")

        rc = cmd_promotion_submit(_ns(data_root, "orig"))
        captured = capsys.readouterr()
        assert rc == 0
        assert "Propuesta registrada" in captured.out
        assert "promo-claim-1" in captured.out
        assert "PENDING" in captured.out

        # Confirmar via API Storage que la propuesta existe.
        db = _project_db(data_root, "orig")
        s = Storage(db)
        try:
            rows = s.list_promotions()
            assert len(rows) == 1
            assert rows[0]["proposal_id"] == "promo-claim-1"
            assert rows[0]["status"] == "PENDING"
        finally:
            s.close()


class TestPromotionSubmitIdempotency:
    def test_second_submit_with_same_claim_returns_conflict(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Submit duplicado: idempotency_key colisiona -> EXIT_DOMAIN (10)."""
        data_root = _bootstrap(tmp_path, project="orig")
        _seed_claim(data_root, "orig")

        rc1 = cmd_promotion_submit(_ns(data_root, "orig"))
        assert rc1 == 0
        capsys.readouterr()  # limpiar

        rc2 = cmd_promotion_submit(_ns(data_root, "orig"))
        captured = capsys.readouterr()
        assert rc2 == 10  # EXIT_DOMAIN
        assert "ERROR" in captured.err
        assert "duplicada" in captured.err.lower() or "identity" in captured.err.lower()


class TestPromotionSubmitErrors:
    def test_unknown_claim_returns_domain_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Claim que no existe en el proyecto -> EXIT_DOMAIN (10)."""
        data_root = _bootstrap(tmp_path, project="orig")
        _seed_claim(data_root, "orig")  # crea claim-1

        rc = cmd_promotion_submit(_ns(data_root, "orig", claim_id="missing"))
        captured = capsys.readouterr()
        assert rc == 10
        assert "claim" in captured.err.lower()
        assert "missing" in captured.err

    def test_unknown_project_returns_not_found(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Proyecto inexistente -> EXIT_PROJECT_NOT_FOUND (4)."""
        data_root = _bootstrap(tmp_path, project="orig")

        rc = cmd_promotion_submit(_ns(data_root, project="nope"))
        captured = capsys.readouterr()
        assert rc == 4
        assert "no existe" in captured.err.lower() or "nope" in captured.err


# ---------------------------------------------------------------------------
# Tests de `sg promotion reconcile` (rama nominal, SIN failpoints)
# ---------------------------------------------------------------------------


class TestPromotionReconcileHappyPath:
    def test_reconcile_empty_outbox_returns_ok(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Reconcile sobre outbox vacio: rc=0, sin trazas confusas."""
        data_root = _bootstrap(tmp_path, project="orig")

        # namespace minimo; target tiene default (= project)
        rc = cmd_promotion_reconcile(
            argparse.Namespace(data_root=data_root, project="orig", target=None)
        )
        captured = capsys.readouterr()
        assert rc == 0
        # No debe haber errores ni traceback.
        assert "Traceback" not in captured.err
        assert "ERROR" not in captured.err

    def test_reconcile_publishes_pending_proposal(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Reconcile aplica propuesta PENDING y la transiciona a PUBLISHED.

        El reconciler acepta 'orig' como source y target (mismo proyecto en
        este test), asi que la propuesta queda publicada en su propio
        proyecto. Lo verificamos via list_promotions.
        """
        data_root = _bootstrap(tmp_path, project="orig")
        _seed_claim(data_root, "orig")
        # Submit primero
        rc_sub = cmd_promotion_submit(_ns(data_root, "orig"))
        assert rc_sub == 0
        capsys.readouterr()

        # Reconcile (sin failpoint, sin crash)
        rc_rec = cmd_promotion_reconcile(
            argparse.Namespace(data_root=data_root, project="orig", target="orig")
        )
        assert rc_rec == 0

        # Verificar via API Storage
        db = _project_db(data_root, "orig")
        s = Storage(db)
        try:
            rows = s.list_promotions()
            assert len(rows) == 1
            assert rows[0]["status"] == "PUBLISHED"
        finally:
            s.close()


# ---------------------------------------------------------------------------
# Tests de `sg pack load` (sembrado in-process con fixture local)
# ---------------------------------------------------------------------------


class TestPackLoadInProcess:
    PACK_PATH = Path(__file__).parent / "fixtures" / "packs" / "narrative-core.md"

    def test_load_valid_pack_persists_types(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Cargar un Domain Pack valido: rc=0, stdout confirma tipos declarados."""
        data_root = _bootstrap(tmp_path, project="u9ip")
        assert self.PACK_PATH.exists(), (
            f"Fixture no encontrada: {self.PACK_PATH}. "
            "Esperada en tests/fixtures/packs/narrative-core.md."
        )

        rc = cmd_pack_load(
            argparse.Namespace(data_root=data_root, project="u9ip", path=self.PACK_PATH)
        )
        captured = capsys.readouterr()
        assert rc == 0
        # Salida menciona los tipos declarados.
        assert "Character" in captured.out or "StoryArc" in captured.out, captured.out

    def test_load_pack_twice_returns_validation_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Cargar el mismo pack dos veces devuelve EXIT_VALIDATION (12).

        El comando no es idempotente por diseno: el Domain Pack ya cargado
        tiene un resource_kind='DomainPack' con el mismo hash; la segunda
        invocacion lo detecta y devuelve un codigo de error explicito.
        Comprobamos que NO produce traceback (es un error controlado,
        no una excepcion).
        """
        data_root = _bootstrap(tmp_path, project="u9ip")
        rc1 = cmd_pack_load(
            argparse.Namespace(data_root=data_root, project="u9ip", path=self.PACK_PATH)
        )
        capsys.readouterr()
        assert rc1 == 0

        rc2 = cmd_pack_load(
            argparse.Namespace(data_root=data_root, project="u9ip", path=self.PACK_PATH)
        )
        captured = capsys.readouterr()
        assert rc2 == 12  # EXIT_VALIDATION
        # La segunda llamada NO debe ser un traceback no controlado.
        assert "Traceback" not in captured.err

    def test_load_pack_for_unknown_project_returns_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Proyecto destino inexistente -> exit code != 0."""
        data_root = _bootstrap(tmp_path, project="u9ip")

        rc = cmd_pack_load(
            argparse.Namespace(
                data_root=data_root,
                project="nope",
                path=self.PACK_PATH,
            )
        )
        assert rc != 0


# ---------------------------------------------------------------------------
# Tests de `sg expansion show` (rama nominal; lee JSONs en disco)
# ---------------------------------------------------------------------------


class TestExpansionShowInProcess:
    """Lee `expansion_proposals/<id>.json` (+ markers) e imprime stage.

    Sembramos el JSON en el formato esperado por _scan_proposals_dir.
    """

    def _seed_proposal(
        self,
        data_root: Path,
        project: str,
        proposal_id: str = "prop-test-1",
    ) -> Path:
        """Crea expansion_proposals/<pid>.json con el formato esperado."""
        import json

        # Localizado via runner.cmd_expansion_show:
        # project_dir.parent.parent / "expansion_proposals"
        # project_dir = Path(project.db_path).parent
        # Como el proyecto vive en <data_root>/tenants/<tenant>/projects/<name>/,
        # expansion_proposals queda en <data_root>/tenants/<tenant>/expansion_proposals.
        proposals_dir = data_root / "tenants" / DEFAULT_TENANT / "expansion_proposals"
        proposals_dir.mkdir(parents=True, exist_ok=True)
        path = proposals_dir / f"{proposal_id}.json"
        path.write_text(
            json.dumps(
                {
                    "proposal_id": proposal_id,
                    "nodes_added": ["extra"],
                    "rationale": "test",
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_show_proposed_proposal_returns_proposed_stage(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Propuesta sin marker => stage='PROPOSED', imprime JSON con stage."""
        data_root = _bootstrap(tmp_path, project="u9ip")
        self._seed_proposal(data_root, "u9ip", "prop-test-1")

        rc = cmd_expansion_show(
            argparse.Namespace(
                data_root=data_root,
                project="u9ip",
                proposal_id="prop-test-1",
            )
        )
        captured = capsys.readouterr()
        assert rc == 0
        assert '"stage": "PROPOSED"' in captured.out
        assert '"proposal_id": "prop-test-1"' in captured.out

    def test_show_applied_proposal_returns_applied_stage(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Si existe el marker `.applied` adyacente => stage='APPLIED'."""
        data_root = _bootstrap(tmp_path, project="u9ip")
        path = self._seed_proposal(data_root, "u9ip", "prop-applied")
        # Crear marker de aplicado.
        marker = path.with_suffix(path.suffix + ".applied")
        marker.touch()

        rc = cmd_expansion_show(
            argparse.Namespace(
                data_root=data_root,
                project="u9ip",
                proposal_id="prop-applied",
            )
        )
        captured = capsys.readouterr()
        assert rc == 0
        assert '"stage": "APPLIED"' in captured.out

    def test_show_unknown_proposal_returns_not_found(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Propuesta inexistente -> EXIT_PROJECT_NOT_FOUND (4)."""
        data_root = _bootstrap(tmp_path, project="u9ip")

        rc = cmd_expansion_show(
            argparse.Namespace(
                data_root=data_root,
                project="u9ip",
                proposal_id="ghost",
            )
        )
        captured = capsys.readouterr()
        assert rc == 4
        assert "no encontrado" in captured.err or "ghost" in captured.err
