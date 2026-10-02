"""WI-72: un solo constructor de payload para las propuestas de expansion.

El payload JSON de una propuesta se construia DOS veces, en
`cmd_expansion_propose` y en `cmd_expansion_apply`, con el mismo
contenido y tres divergencias accidentales (nombre del argumento de
`operations`, `encoding` en `write_text`, y el orden de escritura). Es
un contrato en disco con lectores externos (`list`, `show`,
`_scan_proposals_dir`, `_infer_proposal_stage`) y con tests que
construyen el fichero a mano, asi que la duplicacion era un riesgo
silencioso: un escritor podia cambiar sin que el otro se enterara.

La red sujeta el corte por tres vias distintas:

1. **Oraculo diferencial** (comportamiento): los dos comandos, sobre la
   MISMA propuesta, deben escribir payloads identicos, y ambos deben
   coincidir con las 9 claves reconstruidas aqui como literal. Un test
   que solo contara claves no detectaria que un valor cambio.
2. **Estructura** (unificacion): por AST, ninguno de los dos comandos
   puede contener ya el literal. Este es el test que FALLA antes del
   corte; el oraculo pasaria igualmente, porque antes de unificar los
   dos escritores ya coincidian en los valores.
3. **Parametro `overwrite`**: la no-sobrescritura de `apply` y la
   sobrescritura de `propose` se comprueban las dos, porque son
   divergencias INTENCIONALES que el corte debe preservar.

El test de `encoding` cubre REQ-WI72-3, el unico cambio de
comportamiento deliberado: el escritor compartido fija UTF-8 explicito.
"""

from __future__ import annotations

import ast
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from skillgraph.cli.commands import expansion
from skillgraph.cli.commands.expansion import (
    _applied_payload,
    _proposal_payload,
    _write_json,
)

# ---------------------------------------------------------------------------
# Helpers E2E: mismos que tests/test_h4_expansion_cli_slice3.py, copiados a
# proposito para no acoplar este modulo al otro (mismo criterio que el
# docstring de aquel fichero).
# ---------------------------------------------------------------------------


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
    assert _run_cli("project", "create", project, cwd=tmp_path, data_root=data_root).returncode == 0
    return data_root


def _seed_brick(tmp_path: Path, data_root: Path) -> None:
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

# Lint brick para WI-72
""",
        encoding="utf-8",
    )
    assert _run_cli("brick", "demo", str(brick), cwd=tmp_path, data_root=data_root).returncode == 0


def _write_seed_plan(path: Path) -> Path:
    """WorkflowPlan en JSON (formato interno slice-1)."""
    payload: dict[str, Any] = {
        "name": "seed-plan",
        "initial": "root",
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
            for n in ("root", "child")
        ],
        "transitions": [{"source": "root", "outcome": "ok", "target": "child"}],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _write_proposal(path: Path, *, node_name: str = "extra") -> Path:
    payload: dict[str, Any] = {
        "base_revision": "rev-1",
        "problem_observed": "Falta nodo extra.",
        "evidence": [],
        "operations": [
            {
                "op": "add_node",
                "node": {
                    "name": node_name,
                    "kind": "ActionNode",
                    "namespace": "ns-tools",
                    "api_version": "skillgraph.dev/v1alpha1",
                    "resource_revision": 1,
                    "expected_result": f"output of {node_name}",
                    "capabilities": ["lint"],
                    "metadata": {},
                },
            }
        ],
        "new_dependencies": [],
        "capabilities_needed": ["lint"],
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
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _proposals_dir(data_root: Path) -> Path:
    return data_root / "tenants" / "default" / "expansion_proposals"


def _stub_proposal() -> SimpleNamespace:
    """Proposal con exactamente los atributos que consume el constructor."""
    return SimpleNamespace(
        proposal_id="prop-wi72",
        author="test@example.com",
        created_at="2026-09-23T10:00:00Z",
        problem_observed="Falta nodo extra.",
        capabilities_needed=("lint",),
        new_dependencies=(),
        attachment_point="root",
        authorization=SimpleNamespace(mode="manual_signed"),
    )


def _expected_payload(proposal_path: Path) -> dict[str, object]:
    """ORACULO: las 9 claves, reconstruidas aqui como literal.

    Si esta lista se desincroniza con el contrato en disco, el test
    falla; es la unica fuente de verdad sobre QUE se escribe.
    """
    return {
        "proposal_id": "prop-wi72",
        "author": "test@example.com",
        "created_at": "2026-09-23T10:00:00Z",
        "problem_observed": "Falta nodo extra.",
        "operations": str(proposal_path),
        "capabilities_needed": ["lint"],
        "new_dependencies": [],
        "attachment_point": "root",
        "authorization_mode": "manual_signed",
    }


# ---------------------------------------------------------------------------
# 1. Oraculo diferencial: los dos comandos escriben lo mismo
# ---------------------------------------------------------------------------


def test_propose_and_apply_write_identical_payloads(tmp_path: Path) -> None:
    """Sobre la MISMA propuesta, `propose` y `apply` escriben lo mismo.

    Este es el corazon del REQ-WI72-1. Antes de unificar, los dos
    escritores coincidian en los valores por casualidad (el nombre del
    argumento de `operations` era distinto pero su valor no), asi que
    este test PASABA tambien antes del corte. Por eso existe ademas
    `test_both_commands_delegate_to_one_builder`.
    """
    data_root = _init_project(tmp_path)
    _seed_brick(tmp_path, data_root)
    plan_file = _write_seed_plan(tmp_path / "plan.json")
    proposal = _write_proposal(tmp_path / "prop.json")

    applied = _run_cli(
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
    assert applied.returncode == 0, applied.stderr
    pid = applied.stdout.split("OK: ")[1].split(" ")[0]

    from_apply = json.loads((_proposals_dir(data_root) / f"{pid}.json").read_text("utf-8"))

    # Borra el registro y deja que `propose` lo escriba con su propio camino.
    (_proposals_dir(data_root) / f"{pid}.json").unlink()
    proposed = _run_cli(
        "expansion",
        "propose",
        "demo",
        str(proposal),
        cwd=tmp_path,
        data_root=data_root,
    )
    assert proposed.returncode == 0, proposed.stderr

    from_propose = json.loads((_proposals_dir(data_root) / f"{pid}.json").read_text("utf-8"))

    assert from_apply == from_propose, (
        f"propose y apply divergen:\n  apply  ={from_apply}\n  propose={from_propose}"
    )
    # El juego de claves SI se compara contra el oraculo literal. Los
    # valores no: `proposal_id` y `created_at` los genera `propose()` en
    # cada invocacion, asi que aqui solo pueden compararse entre si. La
    # comparacion de VALORES contra el literal es cosa del test
    # unitario de `_proposal_payload`, donde la propuesta es un stub fijo.
    assert set(from_apply) == set(_expected_payload(proposal)), (
        f"claves distintas a las del contrato: {sorted(set(from_apply) ^ set(_expected_payload(proposal)))}"
    )


def test_proposal_payload_matches_the_literal_oracle() -> None:
    """ORACULO de valores: el constructor produce exactamente el literal.

    Este es el test que atrapa un VALOR que cambie (una clave renombrada,
    `list(...)` que se olvide, el mode de authorization equivocado). El
    E2E de arriba no puede hacerlo porque sus valores son generados.
    """
    assert _proposal_payload(_stub_proposal(), "/tmp/prop.json") == _expected_payload(
        Path("/tmp/prop.json")
    )


def test_payload_has_exactly_nine_keys() -> None:
    """El contrato son 9 claves: una de mas o de menos rompe la red."""
    payload = _proposal_payload(_stub_proposal(), "/tmp/prop.json")

    assert set(payload) == {
        "proposal_id",
        "author",
        "created_at",
        "problem_observed",
        "operations",
        "capabilities_needed",
        "new_dependencies",
        "attachment_point",
        "authorization_mode",
    }
    assert len(payload) == 9


# ---------------------------------------------------------------------------
# 2. Estructura: un solo constructor (este es el que falla antes del corte)
# ---------------------------------------------------------------------------

_LITERAL_MARKERS = ("problem_observed", "applied_by", "authorization_mode")


@pytest.mark.parametrize("command", ["cmd_expansion_propose", "cmd_expansion_apply"])
def test_both_commands_delegate_to_one_builder(command: str) -> None:
    """Ninguno de los dos comandos construye ya el literal del payload."""
    source = inspect.getsource(getattr(expansion, command))

    for marker in _LITERAL_MARKERS:
        assert marker not in source, (
            f"{command} vuelve a construir el payload en linea (aparece {marker!r}); "
            "el corte WI-72 esta revertido en este comando"
        )


def _function_node(name: str) -> ast.FunctionDef:
    """Localiza el FunctionDef en el modulo, por AST y no por texto.

    `inspect.cleandoc` dedenta mal el cuerpo de una funcion (calcula el
    margen sin mirar la linea del `def`), asi que parsear el fuente
    dedicado daria IndentationError. Parsear el modulo entero y buscar el
    nodo es lo robusto.
    """
    module_path = Path(inspect.getsourcefile(expansion) or "")
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} no encontrado en {module_path}")


def test_apply_flow_has_no_json_literal() -> None:
    """REQ-WI72-4: el flujo de apply no lleva literales JSON multilinea."""
    dict_literals = [
        n
        for n in ast.walk(_function_node("cmd_expansion_apply"))
        if isinstance(n, ast.Dict) and any(isinstance(k, ast.Constant) for k in n.keys)
    ]
    assert not dict_literals, (
        f"cmd_expansion_apply todavia contiene {len(dict_literals)} dict literal(es) con claves "
        "constantes; el payload debe construirse en los helpers"
    )


def test_new_helpers_are_module_level_private() -> None:
    """Los tres helpers son funciones de modulo, no metodos colgados."""
    for helper in (_proposal_payload, _applied_payload, _write_json):
        assert inspect.isfunction(helper), f"{helper.__name__} deberia ser funcion de modulo"
        assert helper.__name__.startswith("_"), f"{helper.__name__} deberia ser privado"


# ---------------------------------------------------------------------------
# 3. La divergencia INTENCIONAL: overwrite
# ---------------------------------------------------------------------------


def test_apply_does_not_overwrite_existing_record(tmp_path: Path) -> None:
    """REQ-WI72-2 lado apply: un registro existente NO se toca."""
    data_root = _init_project(tmp_path)
    _seed_brick(tmp_path, data_root)
    plan_file = _write_seed_plan(tmp_path / "plan.json")
    proposal = _write_proposal(tmp_path / "prop.json")

    first = _run_cli(
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
    assert first.returncode == 0, first.stderr
    pid = first.stdout.split("OK: ")[1].split(" ")[0]

    record = _proposals_dir(data_root) / f"{pid}.json"
    record.write_text('{"marcado": "por un humano"}', encoding="utf-8")

    second = _run_cli(
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
    assert second.returncode == 0, second.stderr
    assert json.loads(record.read_text("utf-8")) == {"marcado": "por un humano"}, (
        "apply sobrescribio un registro existente; la no-sobrescritura es intencional "
        "y debe preservarse"
    )


def test_propose_overwrites_existing_record(tmp_path: Path) -> None:
    """REQ-WI72-2 lado propose: aqui si sobrescribe. Divergencia deliberada."""
    data_root = _init_project(tmp_path)
    proposal = _write_proposal(tmp_path / "prop.json")

    first = _run_cli(
        "expansion", "propose", "demo", str(proposal), cwd=tmp_path, data_root=data_root
    )
    assert first.returncode == 0, first.stderr
    pid = first.stdout.split("Propuesta ")[1].split(" ")[0]

    record = _proposals_dir(data_root) / f"{pid}.json"
    record.write_text('{"marcado": "por un humano"}', encoding="utf-8")

    second = _run_cli(
        "expansion", "propose", "demo", str(proposal), cwd=tmp_path, data_root=data_root
    )
    assert second.returncode == 0, second.stderr
    assert "marcado" not in json.loads(record.read_text("utf-8")), (
        "propose dejo de sobrescribir; la divergencia con apply es intencional"
    )


def test_write_json_respects_the_overwrite_flag(tmp_path: Path) -> None:
    """El parametro hace exactamente lo que su nombre dice."""
    target = tmp_path / "out.json"

    assert _write_json(target, {"v": 1}, overwrite=True) is True
    assert _write_json(target, {"v": 2}, overwrite=False) is False, (
        "con overwrite=False no deberia haber escrito"
    )
    assert json.loads(target.read_text("utf-8")) == {"v": 1}

    assert _write_json(target, {"v": 3}, overwrite=True) is True
    assert json.loads(target.read_text("utf-8")) == {"v": 3}


def test_write_json_does_not_create_parent_directories(tmp_path: Path) -> None:
    """`_write_json` escribe, no crea directorios: eso lo hacen los comandos.

    El contrato es deliberado. Los dos llamadores hacen
    `proposals_dir.mkdir(parents=True, exist_ok=True)` antes de escribir,
    y meter el mkdir en el escritor esconderia esa responsabilidad.
    """
    nested = tmp_path / "sub" / "deep" / "out.json"

    with pytest.raises(FileNotFoundError):
        _write_json(nested, {"v": 1}, overwrite=True)


# ---------------------------------------------------------------------------
# 4. El marker .applied
# ---------------------------------------------------------------------------


def test_applied_marker_payload_shape() -> None:
    """Las 3 claves del marker, y `applied_at` con forma ISO UTC."""
    payload = _applied_payload(_stub_proposal())

    assert set(payload) == {"proposal_id", "applied_at", "applied_by"}
    assert payload["proposal_id"] == "prop-wi72"
    assert payload["applied_by"] == "expansion-apply-cli"
    assert payload["applied_at"].endswith("+00:00")


def test_apply_still_writes_both_files(tmp_path: Path) -> None:
    """REQ-WI72-6: apply sigue escribiendo el registro y el marker."""
    data_root = _init_project(tmp_path)
    _seed_brick(tmp_path, data_root)
    plan_file = _write_seed_plan(tmp_path / "plan.json")
    proposal = _write_proposal(tmp_path / "prop.json")

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

    proposals_dir = _proposals_dir(data_root)
    record = proposals_dir / f"{pid}.json"
    marker = proposals_dir / f"{pid}.json.applied"
    assert record.is_file()
    assert marker.is_file()

    marker_payload = json.loads(marker.read_text("utf-8"))
    assert marker_payload["proposal_id"] == pid
    assert marker_payload["applied_by"] == "expansion-apply-cli"
    assert "applied_at" in marker_payload

    # El registro NO lleva marca de aplicado: va en el marker, no dentro.
    assert "applied_at" not in json.loads(record.read_text("utf-8"))


# ---------------------------------------------------------------------------
# 5. REQ-WI72-3: encoding explicito
# ---------------------------------------------------------------------------


def test_written_payload_roundtrips_non_ascii(tmp_path: Path) -> None:
    """El payload escrito se relee identico, con acentos y simbolos.

    HALLAZGO que corrige la especificacion: `json.dumps` usa
    `ensure_ascii=True` por defecto, asi que su salida es ASCII puro y
    el `encoding` de `write_text` NO llega a(bytes) a importar. La
    divergencia (3) que la exploracion dio por un bug de locale era
    INERTE. Unificar el `encoding` sigue siendo lo correcto (queda
    fijado por el codigo y no por el entorno, y protege si alguien
    pusiera `ensure_ascii=False`), pero no arregla un defecto observable
    y no se debe presentar como tal.
    """
    proposal = _stub_proposal()
    proposal.author = "ana-ruiz@ejemplo.es"
    proposal.problem_observed = "Falta el nodo: anádelo y revisa el precio (€)"

    target = tmp_path / "payload.json"
    assert _write_json(target, _proposal_payload(proposal, "/tmp/p.json"), overwrite=True) is True

    raw = target.read_bytes()
    # ASCII puro: la serializacion escapa lo no-ASCII, no lo emite crudo.
    assert raw.decode("ascii"), "con ensure_ascii la salida deberia ser ASCII"
    reread = json.loads(raw.decode("utf-8"))
    assert reread["author"] == "ana-ruiz@ejemplo.es"
    assert reread["problem_observed"] == proposal.problem_observed
    assert reread["attachment_point"] == "root"


def test_write_json_uses_indent_and_sorted_keys(tmp_path: Path) -> None:
    """El formato en disco (indent=2, sort_keys) no cambia: es lo que leen list/show."""
    target = tmp_path / "out.json"
    _write_json(target, {"b": 1, "a": 2}, overwrite=True)

    text = target.read_text("utf-8")
    assert text == '{\n  "a": 2,\n  "b": 1\n}', f"formato inesperado: {text!r}"


# ---------------------------------------------------------------------------
# 6. Superficie publica intacta
# ---------------------------------------------------------------------------


def test_module_exports_are_unchanged() -> None:
    """El corte no altera la superficie que el runner importa."""
    assert expansion.cmd_expansion_apply is not None
    assert expansion.cmd_expansion_propose is not None

    from skillgraph.cli import runner

    assert runner.cmd_expansion_apply is expansion.cmd_expansion_apply
