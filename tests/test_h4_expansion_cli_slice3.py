"""E2E subprocess para H4 slice-3: CLI list/show/archive.

Cubre:
- `sg expansion list <project>` lista propuestas registradas.
- `sg expansion list --stage X` filtra por stage.
- `sg expansion show <project> <id>` imprime JSON.
- `sg expansion archive <project> <id>` crea marker ARCHIVED.
- Idempotencia de archive.
- show/archive con proposal_id inexistente retorna EXIT_PROJECT_NOT_FOUND.

Helpers E2E (run_cli, init_project, write_proposal_authorized) copiados
intencionalmente desde test_h4_expansion_cli.py. Duplicacion explicita
para evitar acoplamiento entre modulos de test. Si este patron crece,
refactor a conftest_slice3.py en slice-4.

Aislamiento total por test (data_root en tmp_path).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Helpers E2E (copiados de test_h4_expansion_cli.py; ver docstring modulo)
# ---------------------------------------------------------------------------


def _run_cli(*args: str, cwd: Path, data_root: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["SKILLGRAPH_DATA_ROOT"] = str(data_root)
    return subprocess.run(
        [sys.executable, "-m", "skillgraph.cli", "--data-root", str(data_root), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        check=False,
    )


def _init_project(tmp_path: Path, project: str = "demo") -> Path:
    data_root = tmp_path / "sg-data"
    assert _run_cli("init", cwd=tmp_path, data_root=data_root).returncode == 0
    rc = _run_cli("project", "create", project, cwd=tmp_path, data_root=data_root).returncode
    assert rc == 0, f"project create fallo: {rc}"
    return data_root


def _seed_brick(tmp_path: Path, data_root: Path, *, project: str = "demo") -> None:
    """Brick minimo con capability 'lint' para que el plan lo encuentre."""
    brick = tmp_path / "lint-brick.md"
    brick.write_text(
        """---
apiVersion: skillgraph.dev/v1alpha1
kind: ActionNode

metadata:
  name: lint-brick
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

# Lint brick para H4 slice-3
""",
        encoding="utf-8",
    )
    rc = _run_cli("brick", project, str(brick), cwd=tmp_path, data_root=data_root).returncode
    assert rc == 0, f"brick register fallo: {rc}"


def _write_proposal_authorized(
    path: Path,
    *,
    add_node_name: str = "extra",
    capability: str = "lint",
    attachment: str = "root",
    authorization_mode: str = "manual_signed",
    granted_by: str | None = "tester@example.com",
    granted_at: str | None = "2026-09-23T10:00:00Z",
) -> None:
    payload: dict[str, Any] = {
        "base_revision": "rev-1",
        "problem_observed": "Falta nodo extra para slice-3.",
        "evidence": [],
        "operations": [
            {
                "op": "add_node",
                "node": {
                    "name": add_node_name,
                    "kind": "ActionNode",
                    "namespace": "ns-tools",
                    "api_version": "skillgraph.dev/v1alpha1",
                    "resource_revision": 1,
                    "expected_result": f"output of {add_node_name}",
                    "capabilities": [capability],
                    "metadata": {},
                },
            }
        ],
        "new_dependencies": [],
        "capabilities_needed": [capability],
        "scope": "NODE",
        "attachment_point": attachment,
        "rollback_plan": [],
        "authorization": {"mode": authorization_mode},
        "author": "test@example.com",
    }
    if granted_by is not None:
        payload["authorization"]["granted_by"] = granted_by
    if granted_at is not None:
        payload["authorization"]["granted_at"] = granted_at
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))


def _proposals_dir(data_root: Path, project: str = "demo") -> Path:
    return data_root / "tenants" / "default" / "expansion_proposals"


# ---------------------------------------------------------------------------
# Tests E2E
# ---------------------------------------------------------------------------


def test_list_empty_when_no_proposals(tmp_path: Path) -> None:
    """`sg expansion list` sin propuestas imprime '(sin propuestas)'."""
    data_root = _init_project(tmp_path)
    result = _run_cli("expansion", "list", "demo", cwd=tmp_path, data_root=data_root)
    assert result.returncode == 0
    assert "(sin propuestas)" in result.stdout


def test_list_shows_registered_proposal(tmp_path: Path) -> None:
    """Tras `sg expansion propose`, `list` muestra la propuesta."""
    data_root = _init_project(tmp_path)
    _seed_brick(tmp_path, data_root)

    proposal = tmp_path / "proposal.json"
    _write_proposal_authorized(proposal)
    propose = _run_cli(
        "expansion",
        "propose",
        "demo",
        str(proposal),
        cwd=tmp_path,
        data_root=data_root,
    )
    assert propose.returncode == 0, propose.stderr

    result = _run_cli("expansion", "list", "demo", cwd=tmp_path, data_root=data_root)
    assert result.returncode == 0
    assert "stage=PROPOSED" in result.stdout


def test_list_filters_by_stage(tmp_path: Path) -> None:
    """`sg expansion list --stage PROPOSED` filtra correctamente."""
    data_root = _init_project(tmp_path)
    _seed_brick(tmp_path, data_root)

    proposal = tmp_path / "proposal.json"
    _write_proposal_authorized(proposal)
    _run_cli(
        "expansion",
        "propose",
        "demo",
        str(proposal),
        cwd=tmp_path,
        data_root=data_root,
    )

    # Filtrar por PROPOSED: debe mostrar
    result = _run_cli(
        "expansion",
        "list",
        "demo",
        "--stage",
        "PROPOSED",
        cwd=tmp_path,
        data_root=data_root,
    )
    assert result.returncode == 0
    assert "stage=PROPOSED" in result.stdout

    # Filtrar por ARCHIVED: no debe mostrar
    result2 = _run_cli(
        "expansion",
        "list",
        "demo",
        "--stage",
        "ARCHIVED",
        cwd=tmp_path,
        data_root=data_root,
    )
    assert result2.returncode == 0
    assert "(sin propuestas en stage=ARCHIVED)" in result2.stdout


def test_show_prints_proposal_json(tmp_path: Path) -> None:
    """`sg expansion show <id>` imprime el proposal JSON completo."""
    data_root = _init_project(tmp_path)
    _seed_brick(tmp_path, data_root)

    proposal = tmp_path / "proposal.json"
    _write_proposal_authorized(proposal)
    propose_result = _run_cli(
        "expansion",
        "propose",
        "demo",
        str(proposal),
        cwd=tmp_path,
        data_root=data_root,
    )
    assert propose_result.returncode == 0

    # Extraer proposal_id del output de propose
    # Format esperado: "Propuesta <id> registrada en <path>"
    out = propose_result.stdout
    # Capturar el id entre "Propuesta " y " registrada"
    marker = "Propuesta "
    idx = out.find(marker)
    assert idx >= 0, f"no encontre 'Propuesta' en output: {out!r}"
    pid = out[idx + len(marker) :].split(" ")[0]

    result = _run_cli(
        "expansion",
        "show",
        "demo",
        pid,
        cwd=tmp_path,
        data_root=data_root,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["proposal_id"] == pid
    assert payload["author"] == "test@example.com"
    assert payload["authorization_mode"] == "manual_signed"


def test_show_unknown_id_returns_not_found(tmp_path: Path) -> None:
    """`sg expansion show <unknown>` retorna EXIT_PROJECT_NOT_FOUND (4)."""
    data_root = _init_project(tmp_path)
    result = _run_cli(
        "expansion",
        "show",
        "demo",
        "prop-nonexistent",
        cwd=tmp_path,
        data_root=data_root,
    )
    assert result.returncode == 4  # EXIT_PROJECT_NOT_FOUND
    assert "no encontrado" in result.stderr


def test_archive_marks_proposal_archived(tmp_path: Path) -> None:
    """`sg expansion archive <id>` crea marker file ARCHIVED."""
    data_root = _init_project(tmp_path)
    _seed_brick(tmp_path, data_root)

    proposal = tmp_path / "proposal.json"
    _write_proposal_authorized(proposal)
    propose_result = _run_cli(
        "expansion",
        "propose",
        "demo",
        str(proposal),
        cwd=tmp_path,
        data_root=data_root,
    )
    assert propose_result.returncode == 0

    pid = propose_result.stdout.split("Propuesta ")[1].split(" ")[0]

    # Archive
    arch = _run_cli(
        "expansion",
        "archive",
        "demo",
        pid,
        cwd=tmp_path,
        data_root=data_root,
    )
    assert arch.returncode == 0, arch.stderr
    assert "Archived" in arch.stdout

    # Verificar marker file
    proposals_dir = _proposals_dir(data_root)
    marker = proposals_dir / f"{pid}.json.archived"
    assert marker.is_file()


def test_archive_reflected_in_list_as_archived_stage(tmp_path: Path) -> None:
    """Tras archive, `list` muestra la propuesta como stage=ARCHIVED."""
    data_root = _init_project(tmp_path)
    _seed_brick(tmp_path, data_root)

    proposal = tmp_path / "proposal.json"
    _write_proposal_authorized(proposal)
    propose_result = _run_cli(
        "expansion",
        "propose",
        "demo",
        str(proposal),
        cwd=tmp_path,
        data_root=data_root,
    )
    assert propose_result.returncode == 0
    pid = propose_result.stdout.split("Propuesta ")[1].split(" ")[0]

    _run_cli(
        "expansion",
        "archive",
        "demo",
        pid,
        cwd=tmp_path,
        data_root=data_root,
    )

    result = _run_cli(
        "expansion",
        "list",
        "demo",
        "--stage",
        "ARCHIVED",
        cwd=tmp_path,
        data_root=data_root,
    )
    assert result.returncode == 0
    assert "stage=ARCHIVED" in result.stdout
    assert pid in result.stdout


def test_archive_is_idempotent(tmp_path: Path) -> None:
    """Archivar dos veces la misma propuesta no falla (idempotente)."""
    data_root = _init_project(tmp_path)
    _seed_brick(tmp_path, data_root)

    proposal = tmp_path / "proposal.json"
    _write_proposal_authorized(proposal)
    propose_result = _run_cli(
        "expansion",
        "propose",
        "demo",
        str(proposal),
        cwd=tmp_path,
        data_root=data_root,
    )
    assert propose_result.returncode == 0
    pid = propose_result.stdout.split("Propuesta ")[1].split(" ")[0]

    # Archive 1
    r1 = _run_cli(
        "expansion",
        "archive",
        "demo",
        pid,
        cwd=tmp_path,
        data_root=data_root,
    )
    assert r1.returncode == 0

    # Archive 2 (idempotente)
    r2 = _run_cli(
        "expansion",
        "archive",
        "demo",
        pid,
        cwd=tmp_path,
        data_root=data_root,
    )
    assert r2.returncode == 0, r2.stderr


def test_archive_unknown_id_returns_not_found(tmp_path: Path) -> None:
    """`sg expansion archive <unknown>` retorna EXIT_PROJECT_NOT_FOUND."""
    data_root = _init_project(tmp_path)
    result = _run_cli(
        "expansion",
        "archive",
        "demo",
        "prop-nonexistent",
        cwd=tmp_path,
        data_root=data_root,
    )
    assert result.returncode == 4  # EXIT_PROJECT_NOT_FOUND
    assert "no encontrado" in result.stderr
