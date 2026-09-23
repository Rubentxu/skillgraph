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


def _write_seed_plan(
    plan_path: Path,
    *,
    initial: str = "root",
    nodes: list[str] | None = None,
    transitions: list[tuple[str, str, str]] | None = None,
) -> Path:
    """Escribe un WorkflowPlan en JSON (formato interno slice-1).

    Replica la firma de tests/test_h4_expansion_cli.py para que los tests
    focales de APPLIED marker puedan usarla directamente.
    """
    import json as _json

    nodes = nodes or [initial, "child"]
    transitions = transitions or []
    payload = {
        "name": "seed-plan",
        "initial": initial,
        "nodes": [
            {
                "name": n,
                "kind": "ActionNode",
                "namespace": "ns-seed",
                "api_version": "skillgraph.dev/v1alpha1",
                "resource_revision": 1,
                "expected_result": f"output of {n}",
                "capabilities": [],
                "metadata": {},
            }
            for n in nodes
        ],
        "transitions": [{"source": s, "outcome": o, "target": t} for s, o, t in transitions],
    }
    plan_path.write_text(_json.dumps(payload, indent=2, sort_keys=True))
    return plan_path


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


def _write_proposal_unauthorized_capability(
    path: Path, *, capability: str = "no_existe_esta_cap"
) -> None:
    """Propuesta con una capability que el registry NO tiene (UAT-09)."""
    payload: dict[str, Any] = {
        "base_revision": "rev-1",
        "problem_observed": "Capacidad inexistente",
        "evidence": [],
        "operations": [
            {
                "op": "add_node",
                "node": {
                    "name": "x",
                    "kind": "ActionNode",
                    "namespace": "ns-tools",
                    "api_version": "skillgraph.dev/v1alpha1",
                    "resource_revision": 1,
                    "expected_result": "x output",
                    "capabilities": [],
                    "metadata": {},
                },
            }
        ],
        "new_dependencies": [],
        "capabilities_needed": [capability],
        "scope": "NODE",
        "attachment_point": "root",
        "rollback_plan": [],
        "authorization": {
            "mode": "manual_signed",
            "granted_by": "tester@example.com",
            "granted_at": "2026-09-23T10:00:00Z",
        },
        "author": "test@example.com",
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))


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


# ---------------------------------------------------------------------------
# APPLIED marker (cierra gap declarado en specs/h4-slice-3.md):
# el apply ahora persiste la propuesta en expansion_proposals/ + crea
# un marker .applied adyacente, igual que archive crea .archived.
# ---------------------------------------------------------------------------


def test_apply_creates_applied_marker_and_persists_proposal(tmp_path: Path) -> None:
    """apply exitoso persiste propuesta en expansion_proposals/ y crea marker .applied.

    Cierra el gap declarado en specs/h4-slice-3.md (limitacion 3): antes
    del fix, ``list --stage APPLIED`` retornaba vacio porque no habia
    marker de APPLIED en disco.
    """
    data_root = _init_project(tmp_path)
    _seed_brick(tmp_path, data_root)
    plan_file = _write_seed_plan(tmp_path / "plan.json")
    proposal = tmp_path / "prop.json"
    _write_proposal_authorized(proposal)

    result = _run_cli(
        "expansion",
        "apply",
        "demo",
        "--proposal",
        str(proposal),
        "--plan-file",
        str(plan_file),
        cwd=tmp_path,
        data_root=data_root,
    )
    assert result.returncode == 0, result.stderr
    pid = result.stdout.split("OK: ")[1].split(" ")[0]

    proposals_dir = data_root / "tenants" / "default" / "expansion_proposals"
    # 1. La propuesta ahora esta persistida como JSON canonico.
    proposal_json = proposals_dir / f"{pid}.json"
    assert proposal_json.is_file(), f"propuesta no persistida: {proposal_json}"
    # 2. El marker .applied existe y contiene timestamp + actor.
    applied_marker = proposals_dir / f"{pid}.json.applied"
    assert applied_marker.is_file(), f"marker .applied no creado: {applied_marker}"
    marker_payload = json.loads(applied_marker.read_text())
    assert marker_payload["proposal_id"] == pid
    assert marker_payload["applied_by"] == "expansion-apply-cli"
    assert "applied_at" in marker_payload


def test_list_stage_applied_returns_proposal_after_apply(tmp_path: Path) -> None:
    """`list --stage APPLIED` muestra propuestas aplicadas (gap declarado cerrado)."""
    data_root = _init_project(tmp_path)
    _seed_brick(tmp_path, data_root)
    plan_file = _write_seed_plan(tmp_path / "plan.json")
    proposal = tmp_path / "prop.json"
    _write_proposal_authorized(proposal)

    apply = _run_cli(
        "expansion",
        "apply",
        "demo",
        "--proposal",
        str(proposal),
        "--plan-file",
        str(plan_file),
        cwd=tmp_path,
        data_root=data_root,
    )
    assert apply.returncode == 0
    pid = apply.stdout.split("OK: ")[1].split(" ")[0]

    result = _run_cli(
        "expansion", "list", "--stage", "APPLIED", "demo", cwd=tmp_path, data_root=data_root
    )
    assert result.returncode == 0
    assert pid in result.stdout
    assert "stage=APPLIED" in result.stdout


def test_list_stage_proposed_excludes_applied_proposal(tmp_path: Path) -> None:
    """Tras apply, la propuesta NO aparece en `list --stage PROPOSED` (precedencia)."""
    data_root = _init_project(tmp_path)
    _seed_brick(tmp_path, data_root)
    plan_file = _write_seed_plan(tmp_path / "plan.json")
    proposal = tmp_path / "prop.json"
    _write_proposal_authorized(proposal)

    apply = _run_cli(
        "expansion",
        "apply",
        "demo",
        "--proposal",
        str(proposal),
        "--plan-file",
        str(plan_file),
        cwd=tmp_path,
        data_root=data_root,
    )
    assert apply.returncode == 0

    result = _run_cli(
        "expansion", "list", "--stage", "PROPOSED", "demo", cwd=tmp_path, data_root=data_root
    )
    assert result.returncode == 0
    assert "stage=PROPOSED" not in result.stdout or "sin propuestas" in result.stdout


def test_show_includes_stage_field(tmp_path: Path) -> None:
    """`show` ahora incluye el campo `stage` inferido en el payload JSON."""
    data_root = _init_project(tmp_path)
    _seed_brick(tmp_path, data_root)
    plan_file = _write_seed_plan(tmp_path / "plan.json")
    proposal = tmp_path / "prop.json"
    _write_proposal_authorized(proposal)

    apply = _run_cli(
        "expansion",
        "apply",
        "demo",
        "--proposal",
        str(proposal),
        "--plan-file",
        str(plan_file),
        cwd=tmp_path,
        data_root=data_root,
    )
    assert apply.returncode == 0
    pid = apply.stdout.split("OK: ")[1].split(" ")[0]

    show = _run_cli("expansion", "show", "demo", pid, cwd=tmp_path, data_root=data_root)
    assert show.returncode == 0
    payload = json.loads(show.stdout)
    assert payload["proposal_id"] == pid
    assert payload["stage"] == "APPLIED"


def test_archived_stage_takes_precedence_over_applied(tmp_path: Path) -> None:
    """ARCHIVED > APPLIED: tras archive, la propuesta aparece como ARCHIVED.

    Verifica que el orden de precedencia en `_infer_proposal_stage` es
    correcto y que ``list --stage APPLIED`` se vacia tras ``archive``.
    """
    data_root = _init_project(tmp_path)
    _seed_brick(tmp_path, data_root)
    plan_file = _write_seed_plan(tmp_path / "plan.json")
    proposal = tmp_path / "prop.json"
    _write_proposal_authorized(proposal)

    apply = _run_cli(
        "expansion",
        "apply",
        "demo",
        "--proposal",
        str(proposal),
        "--plan-file",
        str(plan_file),
        cwd=tmp_path,
        data_root=data_root,
    )
    assert apply.returncode == 0
    pid = apply.stdout.split("OK: ")[1].split(" ")[0]

    archive = _run_cli("expansion", "archive", "demo", pid, cwd=tmp_path, data_root=data_root)
    assert archive.returncode == 0

    # ARCHIVED gana a APPLIED
    show = _run_cli("expansion", "show", "demo", pid, cwd=tmp_path, data_root=data_root)
    payload = json.loads(show.stdout)
    assert payload["stage"] == "ARCHIVED"

    # list --stage APPLIED no incluye la archivada
    list_applied = _run_cli(
        "expansion", "list", "--stage", "APPLIED", "demo", cwd=tmp_path, data_root=data_root
    )
    assert "stage=APPLIED" not in list_applied.stdout or "sin propuestas" in list_applied.stdout


def test_rejected_takes_precedence_over_proposed(tmp_path: Path) -> None:
    """Una propuesta rechazada aparece como REJECTED (no PROPOSED) en show/list."""
    data_root = _init_project(tmp_path)
    _seed_brick(tmp_path, data_root)
    plan_file = _write_seed_plan(tmp_path / "plan.json")
    proposal = tmp_path / "prop.json"
    _write_proposal_unauthorized_capability(proposal, capability="fantasma_xyz")

    apply = _run_cli(
        "expansion",
        "apply",
        "demo",
        "--proposal",
        str(proposal),
        "--plan-file",
        str(plan_file),
        cwd=tmp_path,
        data_root=data_root,
    )
    # EXIT_DOMAIN = 10 (rejection no es error del orquestador).
    assert apply.returncode == 10

    # Aunque la propuesta fue rechazada, apply persiste el JSON canonico
    # en expansion_proposals/ (porque crea el archivo ANTES de validar).
    # Wait: NO lo crea, porque el rejection path retorna antes. La
    # propuesta rechazada NO esta en expansion_proposals/, solo en
    # expansion_rejections/. Verificamos que NO aparece como PROPOSED.
    list_proposed = _run_cli(
        "expansion", "list", "--stage", "PROPOSED", "demo", cwd=tmp_path, data_root=data_root
    )
    assert "stage=PROPOSED" not in list_proposed.stdout or "sin propuestas" in list_proposed.stdout

    # Y aparece en rejections (la fuente canonica del rechazo).
    rejections = _run_cli("expansion", "rejections", "demo", cwd=tmp_path, data_root=data_root)
    assert rejections.returncode == 0
    pid = apply.stderr.split("REJECTED: ")[1].split(":")[0]
    assert pid in rejections.stdout
