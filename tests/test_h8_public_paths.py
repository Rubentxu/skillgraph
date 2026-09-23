"""H8: recorridos públicos E2E para UAT-12 (pack load) y UAT-13 (promoción).

Estos tests certifican por la INTERFAZ PÚBLICA (CLI via subprocess), no
por las APIs Python. Complementan (no sustituyen) los tests de
test_h6_multiproposito.py y test_h7_promocion.py, que cubren las
bibliotecas subyacentes.

Failpoints: SKILLGRAPH_FAILPOINT_PROMOTION (ver cmd_promotion_reconcile).
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

PACK = Path(__file__).parent / "fixtures" / "packs" / "narrative-core.md"


def _sg(
    data_root: Path, *argv: str, env_extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Ejecuta la CLI como proceso aparte (recorrido de usuario real)."""
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "skillgraph", "--data-root", str(data_root), *argv],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
        env=env,
        timeout=60,
    )


def _dest_counts(dest_db: Path, claim_id: str) -> tuple[int, int, int]:
    db = sqlite3.connect(dest_db)
    try:
        claim = db.execute("SELECT COUNT(*) FROM claims WHERE claim_id=?", (claim_id,)).fetchone()[
            0
        ]
        entity = db.execute("SELECT COUNT(*) FROM entities WHERE entity_id='ent-1'").fetchone()[0]
        source = db.execute("SELECT COUNT(*) FROM sources WHERE source_id='src-1'").fetchone()[0]
    finally:
        db.close()
    return claim, entity, source


# ---------------------------------------------------------------------------
# UAT-12 ruta pública: sg pack load -> sg brick -> nueva invocación valida
# ---------------------------------------------------------------------------


class TestUat12PublicPath:
    def test_pack_load_brick_register_and_revalidate_across_processes(self, tmp_path: Path) -> None:
        """Cargar pack -> registrar brick de tipo nuevo -> terminar proceso
        -> nueva invocación CLI -> el brick sigue válido y consultable."""
        data_root = tmp_path / "data"
        assert _sg(data_root, "init").returncode == 0
        assert _sg(data_root, "project", "create", "u12").returncode == 0

        # 1. Cargar el Domain Pack.
        r = _sg(data_root, "pack", "load", "u12", str(PACK))
        assert r.returncode == 0, r.stderr
        assert "Character, StoryArc" in r.stdout

        # 2. Registrar un Character válido (proceso aparte: el tipo vive
        #    porque se re-declara desde el pack persistido, no en memoria).
        char = tmp_path / "frodo.md"
        char.write_text(
            "---\n"
            "apiVersion: skillgraph.dev/v1alpha1\n"
            "kind: Character\n"
            "metadata:\n  name: frodo\n  namespace: shared\n"
            "spec:\n  name: Frodo\n  archetype: heroe\n"
            "---\n\n# Frodo\n",
            encoding="utf-8",
        )
        r = _sg(data_root, "brick", "u12", str(char))
        assert r.returncode == 0, r.stderr
        assert "Character/shared/frodo" in r.stdout

        # 3. Tercer proceso: el brick persistido es consultable y el
        #    pack sigue en el proyecto (aislamiento y persistencia).
        r = _sg(data_root, "project", "inspect", "u12")
        assert r.returncode == 0, r.stderr
        # El Character registrado y el DomainPack persistido figuran.
        assert "Character: 1" in r.stdout
        assert "DomainPack: 1" in r.stdout

    def test_pack_load_rejects_brick_missing_required_field(self, tmp_path: Path) -> None:
        """El validador declarativo del pack se aplica por CLI: un
        Character sin `archetype` (required) es rechazado (exit 12)."""
        data_root = tmp_path / "data"
        assert _sg(data_root, "init").returncode == 0
        assert _sg(data_root, "project", "create", "u12b").returncode == 0
        assert _sg(data_root, "pack", "load", "u12b", str(PACK)).returncode == 0

        bad = tmp_path / "bad.md"
        bad.write_text(
            "---\n"
            "apiVersion: skillgraph.dev/v1alpha1\n"
            "kind: Character\n"
            "metadata:\n  name: bad\n  namespace: shared\n"
            "spec:\n  name: Bad\n"
            "---\n\n# bad\n",
            encoding="utf-8",
        )
        r = _sg(data_root, "brick", "u12b", str(bad))
        assert r.returncode == 12
        assert "archetype" in r.stderr

    def test_pack_load_unknown_kind_rejected_without_pack(self, tmp_path: Path) -> None:
        """Sin pack cargado, un Character es UnknownKind (el tipo NO está
        en el núcleo: extensión sin modificar el núcleo, verificación
        inversa del mismo contrato)."""
        data_root = tmp_path / "data"
        assert _sg(data_root, "init").returncode == 0
        assert _sg(data_root, "project", "create", "u12c").returncode == 0

        char = tmp_path / "x.md"
        char.write_text(
            "---\n"
            "apiVersion: skillgraph.dev/v1alpha1\n"
            "kind: Character\n"
            "metadata:\n  name: x\n  namespace: shared\n"
            "spec:\n  name: X\n  archetype: y\n"
            "---\n\n# x\n",
            encoding="utf-8",
        )
        r = _sg(data_root, "brick", "u12c", str(char))
        assert r.returncode == 12
        assert "UnknownKind" in r.stderr or "unknown" in r.stderr.lower()


# ---------------------------------------------------------------------------
# UAT-13 ruta pública: submit -> (crash) -> reconcile -> sin duplicados
# ---------------------------------------------------------------------------


def _seed_claim(data_root: Path, project: str, claim_id: str) -> None:
    """Siembra entity+source+claim en el proyecto origen (via API porque
    no hay comando de creación de claims: el CLI promociona los que
    produce el subsistema de conocimiento H3)."""
    code = f"""
from skillgraph.platform.storage import Storage
from skillgraph.knowledge.graph import Claim, Entity, Source
from datetime import UTC, datetime
db = {str(data_root / "tenants" / "default" / "projects" / project / "project.sqlite")!r}
s = Storage(db)
s.upsert_entity(tenant_id='default', project_id={project!r},
                entity=Entity(entity_id='ent-1', kind='module', stable_key='pkg.mod'))
s.register_source(tenant_id='default', project_id={project!r},
                  source=Source(source_id='src-1', kind='local_file',
                                content_hash='deadbeef', locator={{'path': 'p.py'}},
                                git_commit_sha=None, git_tree_sha=None,
                                working_tree_status=None,
                                checked_at=datetime.now(UTC).isoformat(),
                                freshness='fresh'))
s.record_claim(tenant_id='default', project_id={project!r},
               claim=Claim(claim_id={claim_id!r}, subject_entity_id='ent-1',
                           predicate='line_count', object_literal=42,
                           source_id='src-1', checked_at_revision='rev-1'))
s.close()
"""
    r = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr


class TestUat13PublicPath:
    def test_promotion_submit_reconcile_publishes_once(self, tmp_path: Path) -> None:
        data_root = tmp_path / "data"
        assert _sg(data_root, "init").returncode == 0
        assert _sg(data_root, "project", "create", "orig").returncode == 0
        assert _sg(data_root, "project", "create", "dest").returncode == 0
        _seed_claim(data_root, "orig", "claim-1")

        # Submit duplicado: idempotencia por idempotency_key.
        assert _sg(data_root, "promotion", "submit", "orig", "claim-1", "dest").returncode == 0
        r = _sg(data_root, "promotion", "submit", "orig", "claim-1", "dest")
        assert r.returncode == 10  # EXIT_DOMAIN: duplicado detectado
        assert "duplicad" in r.stderr.lower()

        # Reconcile publica exactamente una vez.
        r = _sg(data_root, "promotion", "reconcile", "orig", "--target", "dest")
        assert r.returncode == 0, r.stderr
        assert "PUBLISHED" in r.stdout

        dest_db = data_root / "tenants" / "default" / "projects" / "dest" / "project.sqlite"
        claim, entity, source = _dest_counts(dest_db, "claim-1")
        assert (claim, entity, source) == (1, 1, 1)

        # Re-reconcile: nada pendiente, sin duplicados.
        r = _sg(data_root, "promotion", "reconcile", "orig", "--target", "dest")
        assert r.returncode == 0
        assert _dest_counts(dest_db, "claim-1") == (1, 1, 1)

    def test_promotion_survives_mid_apply_crash_without_duplicates(self, tmp_path: Path) -> None:
        """CASO CRÍTICO UAT-13 por CLI: crash a mitad del apply (failpoint
        os._exit(9) con outbox IN_PROGRESS) -> reanudación completa sin
        duplicar ni perder la propuesta."""
        data_root = tmp_path / "data"
        assert _sg(data_root, "init").returncode == 0
        assert _sg(data_root, "project", "create", "orig").returncode == 0
        assert _sg(data_root, "project", "create", "dest").returncode == 0
        _seed_claim(data_root, "orig", "claim-crash")

        assert _sg(data_root, "promotion", "submit", "orig", "claim-crash", "dest").returncode == 0

        # CRASH: el proceso muere con os._exit(9) tras marcar IN_PROGRESS.
        r = _sg(
            data_root,
            "promotion",
            "reconcile",
            "orig",
            "--target",
            "dest",
            env_extra={"SKILLGRAPH_FAILPOINT_PROMOTION": "mid_apply"},
        )
        assert r.returncode == 9, f"esperado crash exit 9, rc={r.returncode}"
        assert "FAILPOINT: mid_apply" in r.stderr

        # Estado post-crash: outbox IN_PROGRESS, claim NO aplicado aún.
        orig_db = data_root / "tenants" / "default" / "projects" / "orig" / "project.sqlite"
        dest_db = data_root / "tenants" / "default" / "projects" / "dest" / "project.sqlite"
        db = sqlite3.connect(orig_db)
        try:
            st = db.execute(
                "SELECT status FROM promotion_outbox WHERE proposal_id='promo-claim-crash'"
            ).fetchone()[0]
        finally:
            db.close()
        assert st == "IN_PROGRESS"
        assert _dest_counts(dest_db, "claim-crash") == (0, 0, 0)

        # REANUDACIÓN: reconcile normal completa la operación.
        r = _sg(data_root, "promotion", "reconcile", "orig", "--target", "dest")
        assert r.returncode == 0, r.stderr
        assert "PUBLISHED" in r.stdout

        # Sin duplicados tras reanudar.
        assert _dest_counts(dest_db, "claim-crash") == (1, 1, 1)

        # Y un reconcile adicional sigue sin duplicar.
        r = _sg(data_root, "promotion", "reconcile", "orig", "--target", "dest")
        assert r.returncode == 0
        assert _dest_counts(dest_db, "claim-crash") == (1, 1, 1)
