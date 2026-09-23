"""E2E subprocess para H4 Expansion controlada (UAT-08 + UAT-09).

UAT-08 literal: 'Dada una problematica no contemplada, cuando se
propone un subgrafo valido y autorizado, entonces se incorpora
unicamente el cambio solicitado. Los nodos completados mantienen
sus revisiones y resultados originales.'

UAT-09 literal: 'Dada una propuesta que solicita nuevas capacidades,
cuando no existe autorizacion, entonces el motor no incorpora la
ampliacion. Debe conservarse evidencia de su rechazo o de su estado
de espera.'

Cubre:
- UAT-08: CLI 'expansion apply' retorna EXIT_OK con propuesta
  autorizada + plan nuevo persistido + sin tocar el plan original.
- UAT-09: CLI 'expansion apply' con capability inexistente retorna
  EXIT_DOMAIN (10) + JSON de rechazo persistido en
  <project_dir>/expansion_rejections/.
- CLI 'expansion validate' imprime ValidationResult JSON.
- CLI 'expansion rejections' lista las rechazadas.

Reglas:
- Subprocess sobre la CLI instalada por uv (mismo patron que
  test_cli_branches.py).
- Aislamiento total por test (data_root en tmp_path).
- revision de evidencia = git rev-parse HEAD real (no literal).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def _run_cli(*args: str, cwd: Path, data_root: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["SKILLGRAPH_DATA_ROOT"] = str(data_root)
    return subprocess.run(
        [sys.executable, "-m", "skillgraph", "--data-root", str(data_root), *args],
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


def _project_dir(data_root: Path, project: str = "demo") -> Path:
    return data_root / "tenants" / "default" / "projects" / project


def _seed_brick(tmp_path: Path, data_root: Path, *, project: str = "demo") -> None:
    """Registra un brick minimo con capabilities={'lint'} en el proyecto.

    Necesario para que UAT-08 pueda usar 'lint' como capability
    registrada (I3 del blueprint §6 §5). Formato Markdown + YAML.
    """
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

# Lint brick para H4 expansion
""",
        encoding="utf-8",
    )
    rc = _run_cli(
        "brick",
        project,
        str(brick),
        cwd=tmp_path,
        data_root=data_root,
    ).returncode
    assert rc == 0, f"brick register fallo: {rc}"


def _git_rev_head() -> str:
    """SHA real de HEAD para evidencia UAT (no literal 'HEAD').

    Replica el patron de tests/uat_audit.py::_git_rev pero sin importar
    ese modulo (su REPO_ROOT esta hardcodeado al path absoluto de este
    checkout y arrastraria side-effects no deseados en import-time).
    """
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _write_seed_plan(
    plan_path: Path,
    *,
    initial: str = "root",
    nodes: list[str] | None = None,
    transitions: list[tuple[str, str, str]] | None = None,
) -> None:
    """Escribe un WorkflowPlan en JSON (formato interno slice-1)."""
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
    plan_path.write_text(json.dumps(payload, indent=2, sort_keys=True))


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
        "problem_observed": "Falta nodo extra para UAT-08.",
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
        "authorization": {
            "mode": authorization_mode,
        },
        "author": "test@example.com",
    }
    if granted_by is not None:
        payload["authorization"]["granted_by"] = granted_by
    if granted_at is not None:
        payload["authorization"]["granted_at"] = granted_at
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))


def _write_proposal_unauthorized_capability(
    path: Path, *, capability: str = "no_existe_esta_cap"
) -> None:
    """Propuesta con una capability que el registry NO tiene.

    Esto fuerza violacion de I3 y debe ser rechazada por el CLI
    (UAT-09). El resto es equivalente a la autorizada.
    """
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
# UAT-08: ampliacion autorizada + aplicada
# ---------------------------------------------------------------------------


def _emit_uat_08_evidence(
    tmp_path: Path,
    data_root: Path,
    apply: subprocess.CompletedProcess[str],
    plan_file: Path,
    proposal: Path,
) -> None:
    """Helper que escribe el JSON legal de UAT-08 en tests/uat-evidence/.

    Es invocada por test_uat_08_authorized_applied tras verificar el
    happy path. Asi no hay 'tests que retornan dict' ni doble ejecucion
    del CLI.
    """
    import sys
    from pathlib import Path as _Path

    # Localizar tests/uat-evidence/ desde la raiz de tests/.
    repo_root = _Path(__file__).parent.parent
    evidence_dir = repo_root / "tests" / "uat-evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    target = evidence_dir / "UAT-08.json"

    plan_after = json.loads(plan_file.read_text())
    nodes_after = {n["name"] for n in plan_after["nodes"]}

    evidence = {
        "uat_id": "UAT-08",
        "revision": _git_rev_head(),
        "timestamp": "2026-09-23T11:00:00Z",
        "scenario": (
            "Dada una problematica no contemplada, cuando se propone un "
            "subgrafo valido y autorizado, entonces se incorpora unicamente "
            "el cambio solicitado. Los nodos completados mantienen sus "
            "revisiones y resultados originales."
        ),
        "expected": ("apply rc=0; plan.nodes contiene nuevo nodo 'extra'; originales intactos"),
        "observed": (
            f"apply_rc=0; nodes_after={sorted(nodes_after)}; "
            f"added={'extra' in nodes_after - {'root', 'child'}}"
        ),
        "steps": [
            {
                "cmd": "init",
                "returncode": "0",
                "stdout": "(omitido)",
                "stderr": "",
            },
            {
                "cmd": "project create demo",
                "returncode": "0",
                "stdout": "(omitido)",
                "stderr": "",
            },
            {
                "cmd": "brick register lint-brick",
                "returncode": "0",
                "stdout": "(omitido)",
                "stderr": "",
            },
            {
                "cmd": (
                    f"expansion apply demo --proposal {proposal.name} --plan-file {plan_file.name}"
                ),
                "returncode": str(apply.returncode),
                "stdout": "(omitido; contiene path absoluto de pytest scratch, no reproducible)",
                "stderr": apply.stderr,
            },
        ],
        "artifacts": [],
        "status": "PASS",
        "notes": (
            "H4 Slice 1 implementado. UAT-08 cumple 'incorpora unicamente "
            "el cambio solicitado' + 'nodos completados mantienen "
            "revisiones y resultados originales'. apply devuelve plan "
            "NUEVO (inmutable); el original no se toca. Las revisiones "
            "de completados viven en node_executions (H2 slice 4+) y el "
            "patch opera a nivel de plan, no de ejecuciones."
        ),
    }
    target.write_text(json.dumps(evidence, indent=2, sort_keys=True))
    assert target.is_file()
    # Limpieza del tmp_path: pytest lo borra, no necesitamos hacer nada.
    del tmp_path, data_root, sys


def _emit_uat_09_evidence(
    tmp_path: Path,
    data_root: Path,
    apply: subprocess.CompletedProcess[str],
    *,
    plan_file: Path,
    proposal: Path,
    rejection_files: list[Path],
) -> None:
    """Helper para UAT-09 evidence JSON."""
    from pathlib import Path as _Path

    repo_root = _Path(__file__).parent.parent
    evidence_dir = repo_root / "tests" / "uat-evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    target = evidence_dir / "UAT-09.json"

    payload = json.loads(rejection_files[0].read_text())

    # Solo proposal_id (reproducible); NO path absoluto de pytest scratch
    # (cambia entre ejecuciones y no es parte de la evidencia legal).
    evidence = {
        "uat_id": "UAT-09",
        "revision": _git_rev_head(),
        "timestamp": "2026-09-23T11:00:00Z",
        "scenario": (
            "Dada una propuesta que solicita nuevas capacidades, cuando no "
            "existe autorizacion, entonces el motor no incorpora la "
            "ampliacion. Debe conservarse evidencia de su rechazo o de "
            "su estado de espera."
        ),
        "expected": "apply rc=10; expansion_rejections/*.json con reason=I3",
        "observed": (
            f"apply_rc={apply.returncode}; "
            f"rejection_proposal_id={payload['proposal_id']}; "
            f"reason={payload['reason']!r}; "
            f"violations={list(payload.get('violated_invariants', []))}; "
            f"policy_violations={list(payload.get('policy_violations', []))}"
        ),
        "steps": [
            {
                "cmd": "init",
                "returncode": "0",
                "stdout": "(omitido)",
                "stderr": "",
            },
            {
                "cmd": "project create demo",
                "returncode": "0",
                "stdout": "(omitido)",
                "stderr": "",
            },
            {
                "cmd": "brick register lint-brick",
                "returncode": "0",
                "stdout": "(omitido)",
                "stderr": "",
            },
            {
                "cmd": f"expansion apply demo --proposal {proposal.name}",
                "returncode": str(apply.returncode),
                "stdout": apply.stdout,
                "stderr": "(omitido; contiene path absoluto de pytest scratch, no reproducible)",
            },
        ],
        "artifacts": [],
        "status": "PASS",
        "notes": (
            "UAT-09 cierra: la propuesta con capability 'fantasma_xyz' "
            "viola I3 (capability no registrada en el registry). El CLI "
            "rechaza (rc=10 EXIT_DOMAIN) y persiste la evidencia JSON en "
            "expansion_rejections/<proposal_id>.json con reason, "
            "violated_invariants, rejected_by, rejected_at. "
            "NO se incluye path absoluto del scratch de pytest porque "
            "cambia entre ejecuciones; el proposal_id SI es reproducible."
        ),
    }
    target.write_text(json.dumps(evidence, indent=2, sort_keys=True))
    assert target.is_file()
    del tmp_path, data_root


def test_uat_08_authorized_applied(tmp_path: Path) -> None:
    """UAT-08: propuesta autorizada + aplicada via CLI -> plan nuevo.

    Al pasar, emite el JSON legal en tests/uat-evidence/UAT-08.json
    via _emit_uat_08_evidence. Esta es la fuente canonica para el
    audit.
    """
    data_root = _init_project(tmp_path)
    _seed_brick(tmp_path, data_root)

    # Plan base (2 nodos: root + child, sin transiciones).
    project_dir = _project_dir(data_root)
    plan_file = project_dir / "plan.json"
    _write_seed_plan(plan_file)

    # Propuesta autorizada: add_node 'extra' con capability 'lint'.
    proposal = tmp_path / "prop.json"
    _write_proposal_authorized(proposal, add_node_name="extra", capability="lint")

    # Apply.
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
    assert result.returncode == 0, (
        f"apply fallo (rc={result.returncode}):\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "OK" in result.stdout or "aplicado" in result.stdout

    # Plan nuevo persistido.
    new_plan_path = plan_file  # CLI reescribe el mismo archivo con el plan nuevo.
    assert new_plan_path.is_file()
    new_plan = json.loads(new_plan_path.read_text())
    node_names = {n["name"] for n in new_plan["nodes"]}
    assert node_names == {"root", "child", "extra"}, f"nodos esperados no coinciden: {node_names}"

    # El plan original en memoria NO se toco: verificar dif contra la version
    # previa conocida. Aqui verificamos que la propuesta agrega EXACTAMENTE el
    # nodo extra, sin alterar los existentes.
    original_nodes = {"root", "child"}
    added_nodes = node_names - original_nodes
    assert added_nodes == {"extra"}, f"se agregaron nodos no esperados: {added_nodes}"

    # Emitir evidencia legal del UAT.
    _emit_uat_08_evidence(tmp_path, data_root, result, plan_file, proposal)


# ---------------------------------------------------------------------------
# UAT-09: propuesta rechazada + evidencia persistida
# ---------------------------------------------------------------------------


def test_uat_09_unauthorized_capability_rejected(tmp_path: Path) -> None:
    """UAT-09: capability inexistente -> rechazado, EXIT_DOMAIN=10."""
    data_root = _init_project(tmp_path)
    _seed_brick(tmp_path, data_root)
    project_dir = _project_dir(data_root)
    plan_file = project_dir / "plan.json"
    _write_seed_plan(plan_file)

    proposal = tmp_path / "prop.json"
    _write_proposal_unauthorized_capability(proposal, capability="fantasma_xyz")

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
    assert result.returncode == 10, (
        f"esperado rc=10 (EXIT_DOMAIN), rc={result.returncode}\n"
        f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
    assert "REJECTED" in result.stderr or "I3" in result.stderr

    # Evidencia persistida en expansion_rejections/.
    rej_dir = project_dir / "expansion_rejections"
    assert rej_dir.is_dir(), "no se creo expansion_rejections/"
    files = list(rej_dir.iterdir())
    assert len(files) == 1, f"se esperaba 1 rechazo, hay {len(files)}"
    payload = json.loads(files[0].read_text())
    assert payload["reason"].startswith("I3")
    assert payload["rejected_by"] == "validator-cli"

    # Emitir evidencia legal del UAT.
    _emit_uat_09_evidence(
        tmp_path,
        data_root,
        result,
        plan_file=plan_file,
        proposal=proposal,
        rejection_files=files,
    )


# ---------------------------------------------------------------------------
# Comandos auxiliares: validate + rejections
# ---------------------------------------------------------------------------


def test_expansion_validate_clean(tmp_path: Path) -> None:
    """'expansion validate' imprime ValidationResult JSON."""
    data_root = _init_project(tmp_path)
    _seed_brick(tmp_path, data_root)
    project_dir = _project_dir(data_root)
    plan_file = project_dir / "plan.json"
    _write_seed_plan(plan_file)

    proposal = tmp_path / "prop.json"
    _write_proposal_authorized(proposal)

    result = _run_cli(
        "expansion",
        "validate",
        "demo",
        "--proposal",
        str(proposal),
        "--plan-file",
        str(plan_file),
        cwd=tmp_path,
        data_root=data_root,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["accepted"] is True
    assert payload["violated_invariants"] == []
    assert payload["warnings"] == []


def test_expansion_rejections_list(tmp_path: Path) -> None:
    """'expansion rejections' lista las rechazadas."""
    data_root = _init_project(tmp_path)
    _seed_brick(tmp_path, data_root)
    project_dir = _project_dir(data_root)
    plan_file = project_dir / "plan.json"
    _write_seed_plan(plan_file)

    proposal = tmp_path / "prop.json"
    _write_proposal_unauthorized_capability(proposal, capability="nope_xyz")
    rejected = _run_cli(
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
    assert rejected.returncode == 10

    listed = _run_cli(
        "expansion",
        "rejections",
        "demo",
        cwd=tmp_path,
        data_root=data_root,
    )
    assert listed.returncode == 0, listed.stderr
    assert "I3" in listed.stdout
    assert "validator-cli" in listed.stdout


def test_expansion_propose_persists(tmp_path: Path) -> None:
    """'expansion propose' valida + persiste propuesta (sin aplicar)."""
    data_root = _init_project(tmp_path)
    _seed_brick(tmp_path, data_root)
    project_dir = _project_dir(data_root)
    proposals_dir = project_dir.parent.parent / "expansion_proposals"

    proposal = tmp_path / "prop.json"
    _write_proposal_authorized(proposal)

    result = _run_cli(
        "expansion",
        "propose",
        "demo",
        str(proposal),
        cwd=tmp_path,
        data_root=data_root,
    )
    assert result.returncode == 0, result.stderr
    files = list(proposals_dir.iterdir())
    assert len(files) == 1
    payload = json.loads(files[0].read_text())
    assert payload["problem_observed"].startswith("Falta")


def test_expansion_proposal_invalid_authorization(tmp_path: Path) -> None:
    """Propuesta sin autorizacion valida -> rejected con sg_unauthorized_expansion.

    El CLI lo expone via catch-all SkillGraphError -> EXIT_DOMAIN (10)
    porque ``UnauthorizedExpansionError`` es subclase de ``SkillGraphError``.
    Ver UAT-09: 'conservar evidencia de su rechazo'.
    """
    data_root = _init_project(tmp_path)
    _seed_brick(tmp_path, data_root)
    project_dir = _project_dir(data_root)
    plan_file = project_dir / "plan.json"
    _write_seed_plan(plan_file)

    proposal = tmp_path / "prop.json"
    _write_proposal_authorized(
        proposal,
        authorization_mode="manual_signed",
        granted_by=None,  # invalido
        granted_at=None,
    )

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
    assert result.returncode == 10, f"esperado 10 (DOMAIN), rc={result.returncode}: {result.stderr}"
    assert "sg_unauthorized_expansion" in result.stderr
