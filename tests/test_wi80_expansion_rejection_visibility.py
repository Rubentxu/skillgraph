"""WI-80: un rechazo ilegible degradaba a `PROPOSED` sin avisar. **CORREGIDO.**

Investigacion retrospectiva, senal "fallbacks silenciosos" del goal.

Barrido mecanico de los 66 handlers de excepcion de `src/`
(`.pipelinek/wi80_scan_silent_handlers.py`): 59 con cuerpo efectivo, 0
`pass`, 0 vacios, y **7 cuyo unico cuerpo es `continue`**. Todos son
"tolerancia a datos corruptos" y todos estan documentados. Dos merecen
juicio:

1. `_load_registry` (expansion.py:109) se salta un resource con
   `spec_json` ilegible. El registry alimenta I3/I4 de
   `graph_expansion.py:341`, que preguntan "la capability EXISTE en el
   registry". Un registry incompleto hace que la comprobacion FALLE
   (I3) en vez de pasar: **fail-closed, correcto**. Hipotesis retirada.

2. `_collect_rejection_ids` (expansion.py:86) se saltaba un
   `expansion_rejections/*.json` ilegible. Este era el hallazgo, y era
   real.

El precedente del propio repo es explicito. `knowledge/git_source.py:365`:

    "Antes devolvia `{}` ante cualquier fallo, y ese `{}` viaja dentro del
     Source.locator. Un repo roto, o no-repo, se convertia asi en un
     Source que afirma 'no hay cambios pendientes': un dato plausible y
     falso, que es peor que un error."

Y `governance/backups.py:358`:

    "Backup corrupto o sin manifest: lo ignoramos en `list`, pero NO lo
     borramos (preservar evidencia para el operador)."

Los dos degradan el dato corrupto. Pero los dos son HONESTOS: `None` y
"no aparece en la lista" son afirmaciones que el operador puede
interpretar. Aqui la degradacion era peor: un rechazo ilegible se
convertia en la afirmacion contraria — "esta propuesta NO esta
rechazada" — y `list` la imprimia como `stage=PROPOSED` sin una linea de
aviso. Un operador que filtra por `--stage REJECTED` no la ve, y un
operador que lea la lista concluye que hay una propuesta pendiente que en
realidad ya fue rechazada con evidencia persistida.

ALCANCE MEDIDO, no supuesto:

- El registry de rechazos NO gobierna la aplicacion. `cmd_expansion_apply`
  no consulta `_collect_rejection_ids`; re-aplicar una propuesta rechazada
  la re-valida contra el plan. Por tanto NO era un falso exito de
  escritura: nada se aplicaba dos veces por esta via. El alcance real
  era de **visualizacion**: `cmd_expansion_list` y `cmd_expansion_show`.

POR QUE NO SE CORRIGIO EN SU DIA, Y POR QUE SI AHORA. La red original
fijaba el comportamiento REAL a proposito (`test_caso_corrupto_muestra_
proposed_y_no_avisa`) y la consigna era "arreglarlo exige tocar el test
a proposito". Motivo: cambiar la salida de `expansion list` se leyo como
cambio de contrato externo (AGENTS 6.4). Ese criterio era erroneo, y la
razon es que confundio **cambiar un contrato** con **corregir una
afirmacion falsa**: el contrato de `--stage REJECTED` no es "oculta las
rechazadas cuyo fichero esta roto", y ningun consumidor razonable
depende de que `stage=PROPOSED` se imprima para algo que si fue
rechazado. La correccion hace el contrato MAS HONESTO, no menos.

EL FIX. `record_rejection` escribe siempre `<proposal_id>.json`
(`graph_expansion.py:618`), asi que el stem del fichero ES el
proposal_id por construccion. `_collect_rejection_ids` deja de saltarse
el fichero: usa el stem, y ademas lo reporta en `unreadable` para que
`list`/`show` avisen en stderr. Sin ese aviso, la correccion habria
sustituido una mentira silenciosa por otra mas pequena: decir REJECTED
como si la evidencia estuviera sana.

QUE HACE ESTA RED: fija el contrato YA CORREGIDO, con el caso base
(REJECTED legible) al lado del caso degradado (REJECTED por nombre de
fichero + aviso), para que la diferencia sea visible y no un misterio.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from skillgraph.cli.commands.expansion import _collect_rejection_ids, _infer_proposal_stage


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


def _seed_brick(tmp_path: Path, data_root: Path, *, project: str = "demo") -> None:
    """Brick minimo con capabilities={'lint'} (formato Markdown + YAML)."""
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

# Lint brick para WI-80
""",
        encoding="utf-8",
    )
    rc = _run_cli("brick", project, str(brick), cwd=tmp_path, data_root=data_root).returncode
    assert rc == 0, f"brick register fallo: {rc}"


def _write_seed_plan(path: Path, *, initial: str = "root") -> None:
    """WorkflowPlan en JSON (formato interno slice-1)."""
    nodes = [initial, "child"]
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
        "transitions": [],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_proposal(path: Path, *, capability: str) -> None:
    payload: dict[str, Any] = {
        "base_revision": "rev-1",
        "problem_observed": "Falta nodo extra.",
        "evidence": [],
        "operations": [
            {
                "op": "add_node",
                "node": {
                    "name": "extra",
                    "kind": "ActionNode",
                    "namespace": "ns-tools",
                    "api_version": "skillgraph.dev/v1alpha1",
                    "resource_revision": 1,
                    "expected_result": "output of extra",
                    "capabilities": [capability],
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
            "granted_by": "t@example.com",
            "granted_at": "2026-10-02T10:00:00Z",
        },
        "author": "test@example.com",
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _escenario_rechazada(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Monta propuesta registrada + rechazo persistido.

    Hace falta `propose` ANTES de `apply`: `apply` no persiste la
    propuesta en `expansion_proposals/`, solo la evidencia del rechazo,
    asi que sin el registro previo `expansion list` no ve nada.
    """
    data_root = _init_project(tmp_path)
    _seed_brick(tmp_path, data_root)
    project_dir = data_root / "tenants" / "default" / "projects" / "demo"
    plan_file = project_dir / "plan.json"
    _write_seed_plan(plan_file)

    proposal = tmp_path / "prop.json"
    _write_proposal(proposal, capability="no_existe_esta_cap")

    proposed = _run_cli(
        "expansion", "propose", "demo", str(proposal), cwd=tmp_path, data_root=data_root
    )
    assert proposed.returncode == 0, f"propose fallo: {proposed.stderr}"

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
    assert applied.returncode == 10, (
        f"se esperaba REJECTED (10), vino {applied.returncode}\n"
        f"stdout={applied.stdout}\nstderr={applied.stderr}"
    )

    rejections = project_dir / "expansion_rejections"
    files = sorted(rejections.glob("*.json"))
    assert files, (
        f"no se persistio evidencia de rechazo\nstderr={applied.stderr}\n"
        f"proposals={sorted((project_dir.parent.parent / 'expansion_proposals').glob('*'))}"
    )
    return data_root, rejections, files[0]


# --- Red 1: el comportamiento por debajo del CLI -------------------------


class TestCollectRejectionIds:
    def test_legible_devuelve_el_id(self, tmp_path: Path) -> None:
        _data_root, rejections, _f = _escenario_rechazada(tmp_path)
        scan = _collect_rejection_ids(rejections)
        assert len(scan.ids) == 1, f"se esperaba 1 rechazo legible, vino {scan.ids}"
        assert scan.unreadable == (), (
            f"una evidencia legible no puede estar damaged: {scan.unreadable}"
        )

    def test_ilegible_conserva_el_id_por_nombre(self, tmp_path: Path) -> None:
        """WI-80: un rechazo truncado NO se pierde, y se reporta como ilegible.

        `record_rejection` escribe siempre `<proposal_id>.json`
        (`graph_expansion.py:618`), asi que el stem ES el proposal_id. No
        es una heuristica: es la convencion de escritura leida al reves.
        """
        _data_root, rejections, f = _escenario_rechazada(tmp_path)
        expected = f.stem
        f.write_text(f.read_text()[:20], encoding="utf-8")  # JSON truncado
        with pytest.raises(json.JSONDecodeError):
            json.loads(f.read_text())  # el fichero esta roto de verdad

        scan = _collect_rejection_ids(rejections)
        assert expected in scan.ids, (
            f"el rechazo ilegible se perdio: {expected!r} no esta en {scan.ids}. "
            f"Degradarlo a 'no rechazado' es una afirmacion falsa (WI-80)"
        )
        assert scan.unreadable == (f,), f"debe reportarse como ilegible: {scan.unreadable}"

    def test_ilegible_ya_no_cambia_el_stage_inferido(self, tmp_path: Path) -> None:
        """Con ello, la propuesta sigue siendo REJECTED, no PROPOSED."""
        _data_root, rejections, f = _escenario_rechazada(tmp_path)
        proposal_id = json.loads(f.read_text())["proposal_id"]
        prop_path = tmp_path / "prop.json"

        antes = _infer_proposal_stage(
            prop_path, proposal_id, _collect_rejection_ids(rejections).ids
        )
        assert antes == "REJECTED"

        f.write_text(f.read_text()[:20], encoding="utf-8")
        despues = _infer_proposal_stage(
            prop_path, proposal_id, _collect_rejection_ids(rejections).ids
        )
        assert despues == "REJECTED", (
            f"una corrupcion del fichero no puede convertir una propuesta rechazada "
            f"en PROPOSED: {despues}"
        )

    def test_json_valido_sin_proposal_id_tambien_se_recupera(self, tmp_path: Path) -> None:
        """JSON bien formado pero sin `proposal_id`: mismo nombre, misma regla."""
        _data_root, rejections, f = _escenario_rechazada(tmp_path)
        f.write_text(json.dumps({"reason": "I3"}), encoding="utf-8")

        scan = _collect_rejection_ids(rejections)
        assert f.stem in scan.ids
        assert scan.unreadable == (f,)


# --- Red 2: el contrato externo (exit code + salida) ---------------------


class TestExpansionListUnderCorruptRejection:
    def test_caso_base_muestra_rejected(self, tmp_path: Path) -> None:
        data_root, _rejections, _f = _escenario_rechazada(tmp_path)
        out = _run_cli("expansion", "list", "demo", cwd=tmp_path, data_root=data_root)
        assert out.returncode == 0, out.stderr
        assert "stage=REJECTED" in out.stdout

    def test_caso_corrupto_sigue_diciendo_rejected_y_avisa(self, tmp_path: Path) -> None:
        """WI-80: la corrupcion no puede cambiar lo que el producto afirma.

        Antes de esta correccion, `expansion list` salia con 0 y decia
        `stage=PROPOSED` para una propuesta que SI fue rechazada, sin
        ninguna linea de aviso. Ahora dice `REJECTED` —que es la verdad—
        y ademas avisa en stderr de que la evidencia esta ilegible, para
        que el operador sepa que la conclusion viene del nombre del
        fichero y no de su cuerpo.
        """
        data_root, rejections, f = _escenario_rechazada(tmp_path)
        f.write_text(f.read_text()[:20], encoding="utf-8")

        out = _run_cli("expansion", "list", "demo", cwd=tmp_path, data_root=data_root)
        assert out.returncode == 0, out.stderr
        assert "stage=REJECTED" in out.stdout, out.stdout
        assert "stage=PROPOSED" not in out.stdout, out.stdout
        # El fichero roto sigue en disco: la evidencia NO se borra.
        assert f.is_file(), "la evidencia del rechazo debe preservarse"
        assert rejections.is_dir()
        # Y el operador se entera de que la lectura fallo.
        assert "ilegible" in out.stderr.lower(), (
            f"sin aviso en stderr, el operador no puede distinguir una "
            f"evidencia sana de una danada:\n{out.stderr}"
        )

    def test_evidencia_sana_no_avisa(self, tmp_path: Path) -> None:
        """El aviso es por lectura fallida, no por presencia de rechazos.

        Si `expansion list` gritara en cada rechazo, el aviso dejaria de
        informar: seria ruido, y el ruido es lo que hace que nadie lea
        los avisos.
        """
        data_root, _rejections, _f = _escenario_rechazada(tmp_path)
        out = _run_cli("expansion", "list", "demo", cwd=tmp_path, data_root=data_root)
        assert out.returncode == 0, out.stderr
        assert "ilegible" not in out.stderr.lower(), f"aviso espurio:\n{out.stderr}"

    def test_filtrar_por_rejected_la_sigue_listando(self, tmp_path: Path) -> None:
        """La consecuencia operativa que se corrigio: el filtro la conserva."""
        data_root, _rejections, f = _escenario_rechazada(tmp_path)
        f.write_text(f.read_text()[:20], encoding="utf-8")

        out = _run_cli(
            "expansion", "list", "demo", "--stage", "REJECTED", cwd=tmp_path, data_root=data_root
        )
        assert out.returncode == 0, out.stderr
        assert "stage=REJECTED" in out.stdout, (
            f"una propuesta rechazada sigue desapareciendo del filtro por la "
            f"corrupcion del fichero:\n{out.stdout}"
        )
        assert "sin propuestas en stage=REJECTED" not in out.stdout
