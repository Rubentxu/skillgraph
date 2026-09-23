"""Tests de extremo a extremo de la CLI (Etapa 1).

Cubre los UAT 01..03 del blueprint
(external/blueprint-v1/plan/UAT.md):

- UAT-01: SkillGraph NO escribe archivos internos en el proyecto del
  usuario. Aqui simulamos el "proyecto del usuario" con un directorio
  cualquiera y comprobamos que la base y el catalogo se crean FUERA
  de el.

- UAT-02: dos proyectos del mismo tenant mantienen datos aislados: una
  afirmación/registro creado en A no es recuperable desde B.

- UAT-03: un Domain Pack Markdown valido se registra y aparece en
  `project inspect`; un YAML invalido se rechaza antes de activar
  el comportamiento.

Reglas (external/blueprint-v1/plan/ESTRATEGIA-DE-TESTS.md):
- Tests subprocess sobre la CLI instalada por `uv`.
- Aislamiento total por test (data root en tmp_path).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from skillgraph.cli import main

pytestmark = pytest.mark.etapa1


# ---------------------------------------------------------------------------
# Helpers: la CLI se invoca con `python -m skillgraph.cli` para que el
# resolvedor de imports funcione idéntico al del entry point instalado.
# ---------------------------------------------------------------------------


def _run_cli(*args: str, cwd: Path, data_root: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    # Forzar el data root a un directorio temporal; pytest ya aísla tmp_path.
    env["SKILLGRAPH_DATA_ROOT"] = str(data_root)
    # Evitar que la jerarquía de directorios del test contamine el cwd.
    return subprocess.run(
        [sys.executable, "-m", "skillgraph", "--data-root", str(data_root), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        check=False,
    )


def _write_valid_pack(path: Path) -> None:
    path.write_text(
        "---\n"
        "apiVersion: skillgraph.dev/v1alpha1\n"
        "kind: DomainPack\n"
        "metadata:\n"
        "  name: uat-pack\n"
        "  namespace: shared\n"
        "spec:\n"
        "  version: 1.0.0\n"
        "  capabilities:\n"
        "    - name: review\n"
        "      entrypoint: shared.review-root\n"
        "---\n"
        "# UAT pack\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# UAT-01: no contaminacion
# ---------------------------------------------------------------------------


class TestUAT01NoContamination:
    def test_data_lives_outside_user_project(self, tmp_path: Path) -> None:
        user_project = tmp_path / "workspace"
        user_project.mkdir()
        data_root = tmp_path / "skillgraph-data"

        result = _run_cli("init", cwd=user_project, data_root=data_root)
        assert result.returncode == 0, result.stderr

        # El data root contiene el catalogo y directorios de tenant.
        assert (data_root / "catalog.sqlite").exists()
        # El proyecto del usuario NO contiene archivos internos.
        assert not any(user_project.iterdir()), (
            f"SkillGraph escribió dentro del proyecto del usuario: {list(user_project.iterdir())}"
        )


# ---------------------------------------------------------------------------
# UAT-02: aislamiento entre proyectos
# ---------------------------------------------------------------------------


class TestUAT02ProjectIsolation:
    def test_two_projects_do_not_leak_resources(self, tmp_path: Path) -> None:
        data_root = tmp_path / "sg-data"
        # Crear dos proyectos.
        assert (
            _run_cli(
                "project",
                "create",
                "alpha",
                cwd=tmp_path,
                data_root=data_root,
            ).returncode
            == 0
        )
        assert (
            _run_cli(
                "project",
                "create",
                "beta",
                cwd=tmp_path,
                data_root=data_root,
            ).returncode
            == 0
        )

        # Registrar el mismo brick (con mismo nombre y namespace) en cada
        # uno. Si la base estuviera compartida, uno machacaría al otro.
        pack_alpha = tmp_path / "pack-alpha.md"
        _write_valid_pack(pack_alpha)
        r_alpha = _run_cli(
            "brick",
            "alpha",
            str(pack_alpha),
            cwd=tmp_path,
            data_root=data_root,
        )
        assert r_alpha.returncode == 0, r_alpha.stderr

        pack_beta = tmp_path / "pack-beta.md"
        _write_valid_pack(pack_beta)
        r_beta = _run_cli(
            "brick",
            "beta",
            str(pack_beta),
            cwd=tmp_path,
            data_root=data_root,
        )
        assert r_beta.returncode == 0, r_beta.stderr

        # Inspect cada uno: cada uno debe contar 1 brick propio.
        out_alpha = _run_cli(
            "project",
            "inspect",
            "alpha",
            cwd=tmp_path,
            data_root=data_root,
        )
        out_beta = _run_cli(
            "project",
            "inspect",
            "beta",
            cwd=tmp_path,
            data_root=data_root,
        )
        assert "Recursos: 1 total" in out_alpha.stdout
        assert "DomainPack: 1" in out_alpha.stdout
        assert "Recursos: 1 total" in out_beta.stdout
        assert "DomainPack: 1" in out_beta.stdout


# ---------------------------------------------------------------------------
# UAT-03: brick declarativo
# ---------------------------------------------------------------------------


class TestUAT03BrickDeclarative:
    def test_invalid_yaml_rejected_before_activation(self, tmp_path: Path) -> None:
        data_root = tmp_path / "sg-data"
        assert (
            _run_cli(
                "project",
                "create",
                "proj",
                cwd=tmp_path,
                data_root=data_root,
            ).returncode
            == 0
        )
        bad = tmp_path / "bad.md"
        bad.write_text(
            "---\n"
            "apiVersion: skillgraph.dev/v1alpha1\n"
            "kind: DecisionNode\n"
            "metadata:\n"
            "  namespace: software\n"
            # Falta name => parse error.
            "spec:\n"
            "  ctx_recipe_ref: software.imp\n"
            "  outcomes:\n"
            "    - name: ONLY\n"
            "      next: x\n"
            "---\n"
            "# bad\n",
            encoding="utf-8",
        )
        r = _run_cli(
            "brick",
            "proj",
            str(bad),
            cwd=tmp_path,
            data_root=data_root,
        )
        assert r.returncode != 0
        assert "metadata.name" in r.stderr

    def test_unknown_kind_rejected_before_activation(self, tmp_path: Path) -> None:
        data_root = tmp_path / "sg-data"
        assert (
            _run_cli(
                "project",
                "create",
                "proj",
                cwd=tmp_path,
                data_root=data_root,
            ).returncode
            == 0
        )
        alien = tmp_path / "alien.md"
        alien.write_text(
            "---\n"
            "apiVersion: skillgraph.dev/v1alpha1\n"
            "kind: AlienConcept\n"
            "metadata:\n"
            "  name: foo\n"
            "  namespace: software\n"
            "spec:\n"
            "  whatever: 1\n"
            "---\n"
            "# alien\n",
            encoding="utf-8",
        )
        r = _run_cli(
            "brick",
            "proj",
            str(alien),
            cwd=tmp_path,
            data_root=data_root,
        )
        assert r.returncode != 0
        assert "sg_unknown_kind" in r.stderr

    def test_valid_pack_appears_in_inspect(self, tmp_path: Path) -> None:
        data_root = tmp_path / "sg-data"
        assert (
            _run_cli(
                "project",
                "create",
                "proj",
                cwd=tmp_path,
                data_root=data_root,
            ).returncode
            == 0
        )
        ok_md = tmp_path / "ok.md"
        _write_valid_pack(ok_md)
        r = _run_cli(
            "brick",
            "proj",
            str(ok_md),
            cwd=tmp_path,
            data_root=data_root,
        )
        assert r.returncode == 0, r.stderr
        # Listado
        listed = _run_cli(
            "project",
            "list",
            cwd=tmp_path,
            data_root=data_root,
        )
        assert "proj" in listed.stdout
        # Inspección
        ins = _run_cli(
            "project",
            "inspect",
            "proj",
            cwd=tmp_path,
            data_root=data_root,
        )
        assert ins.returncode == 0, ins.stderr
        assert "DomainPack: 1" in ins.stdout


# ---------------------------------------------------------------------------
# Smoke tests del propio main(), sin subprocess (defensa en profundidad)
# ---------------------------------------------------------------------------


class TestCliEntryPoint:
    def test_main_version_flag_prints_version(self, capsys) -> None:
        rc = main(["--version"])
        assert rc == 0
        out = capsys.readouterr().out
        assert out.startswith("skillgraph ")

    def test_main_no_command_prints_help(self, capsys) -> None:
        rc = main([])
        assert rc == 0
        out = capsys.readouterr().out
        assert "SkillGraph:" in out
        assert "init" in out
        assert "project" in out

    def test_main_returns_2_for_invalid_name(self, tmp_path, capsys) -> None:
        rc = main(
            [
                "--data-root",
                str(tmp_path / "sg-data"),
                "project",
                "create",
                "Nombre Con Espacios",
            ]
        )
        assert rc == 2
        err = capsys.readouterr().err
        assert "inválido" in err

    def test_main_returns_3_when_project_already_exists(self, tmp_path, capsys) -> None:
        rc1 = main(
            [
                "--data-root",
                str(tmp_path / "sg-data"),
                "project",
                "create",
                "alpha",
            ]
        )
        assert rc1 == 0
        rc2 = main(
            [
                "--data-root",
                str(tmp_path / "sg-data"),
                "project",
                "create",
                "alpha",
            ]
        )
        assert rc2 == 3
        err = capsys.readouterr().err
        assert "ya existe" in err


def test_uats_can_be_loaded_as_documentation(tmp_path: Path) -> None:
    """Comprueba que los UAT-01..03 del blueprint son visibles y se
    pueden citar como documentacion viva desde el repo."""
    uat_doc = (
        Path(__file__).resolve().parent.parent / "external" / "blueprint-v1" / "plan" / "UAT.md"
    )
    if not uat_doc.exists():  # pragma: no cover
        pytest.skip("blueprint no versionado en el repo")
    text = uat_doc.read_text(encoding="utf-8")
    for tag in ("UAT-01", "UAT-02", "UAT-03"):
        assert tag in text, f"falta {tag} en el blueprint"
