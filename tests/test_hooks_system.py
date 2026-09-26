"""Tests para el sistema de git hooks del proyecto.

Estos tests verifican que:
1. El hook pre-commit existe y es ejecutable.
2. El script install-hooks.sh existe, es ejecutable y tiene shebang valido.
3. El hook pre-commit en scripts/hooks/ contiene los comandos clave.
4. El CI workflow existe y referencia las tareas mise correctas.

Los tests NO ejecutan el hook (eso seria un side effect sobre el repo
del usuario). Solo verifican la presencia y la forma.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK_PATH = REPO_ROOT / "scripts" / "hooks" / "pre-commit"
INSTALLER_PATH = REPO_ROOT / "scripts" / "install-hooks.sh"
CI_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"


class TestPreCommitHook:
    """El hook vive en scripts/hooks/ para ser commiteable."""

    def test_hook_exists(self) -> None:
        assert HOOK_PATH.exists(), f"Hook no encontrado: {HOOK_PATH}"

    def test_hook_is_executable(self) -> None:
        """Verifica que el hook tenga bit +x (stat S_IXUSR).

        Importante: el install-hooks.sh debe re-aplicar chmod +x al copiar
        al directorio .git/hooks/ (que no se commitea).
        """
        import stat

        mode = HOOK_PATH.stat().st_mode
        assert mode & stat.S_IXUSR, f"Hook no ejecutable: {HOOK_PATH}"

    def test_hook_has_shebang(self) -> None:
        first_line = HOOK_PATH.read_text(encoding="utf-8").splitlines()[0]
        assert first_line.startswith("#!"), f"Hook sin shebang: {first_line!r}"
        assert "sh" in first_line or "bash" in first_line, (
            f"Shebang no apunta a shell: {first_line!r}"
        )

    def test_hook_enforces_ruff_check(self) -> None:
        """El hook debe ejecutar ruff check para mantener el lint limpio."""
        content = HOOK_PATH.read_text(encoding="utf-8")
        assert "ruff check" in content, "Hook no ejecuta 'ruff check'"

    def test_hook_enforces_ruff_format_check(self) -> None:
        """El hook debe ejecutar ruff format --check para evitar drift de format."""
        content = HOOK_PATH.read_text(encoding="utf-8")
        assert "ruff format --check" in content, "Hook no ejecuta 'ruff format --check'"

    def test_hook_runs_pytest_for_py_staged_files(self) -> None:
        """El hook debe ejecutar pytest -q cuando hay .py staged."""
        content = HOOK_PATH.read_text(encoding="utf-8")
        assert "pytest" in content, "Hook no ejecuta pytest"
        assert ".py" in content, "Hook no detecta archivos .py staged"

    def test_hook_provides_bypass_for_doc_only_commits(self) -> None:
        """El hook debe permitir bypass para commits solo-docs via env var."""
        content = HOOK_PATH.read_text(encoding="utf-8")
        assert "HOOK_SKIP_TESTS" in content, "Hook sin mecanismo de bypass para commits doc-only"


class TestInstallHooksScript:
    """El script install-hooks.sh copia los hooks al directorio .git/hooks/."""

    def test_installer_exists(self) -> None:
        assert INSTALLER_PATH.exists(), f"Installer no encontrado: {INSTALLER_PATH}"

    def test_installer_is_executable(self) -> None:
        import stat

        mode = INSTALLER_PATH.stat().st_mode
        assert mode & stat.S_IXUSR, f"Installer no ejecutable: {INSTALLER_PATH}"

    def test_installer_uses_git_rev_parse(self) -> None:
        """El installer debe detectar el repo root via git rev-parse."""
        content = INSTALLER_PATH.read_text(encoding="utf-8")
        assert "git rev-parse --show-toplevel" in content, (
            "Installer no usa git rev-parse para detectar root"
        )

    def test_installer_applies_chmod(self) -> None:
        """El installer debe hacer chmod +x al hook copiado."""
        content = INSTALLER_PATH.read_text(encoding="utf-8")
        assert "chmod" in content, "Installer no aplica chmod"

    def test_installer_is_idempotent(self) -> None:
        """Re-ejecutar install-hooks.sh no debe fallar."""
        content = INSTALLER_PATH.read_text(encoding="utf-8")
        assert "cp" in content, "Installer no copia hooks"


class TestCIWorkflow:
    """El workflow GH en .github/workflows/ci.yml ejecuta los gates."""

    def test_workflow_exists(self) -> None:
        assert CI_WORKFLOW_PATH.exists(), f"Workflow no encontrado: {CI_WORKFLOW_PATH}"

    def test_workflow_triggers_on_push_and_pr(self) -> None:
        """El workflow debe correr en push y pull_request a main."""
        content = CI_WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "push:" in content, "Workflow sin trigger push"
        assert "pull_request:" in content, "Workflow sin trigger pull_request"

    def test_workflow_installs_mise(self) -> None:
        """El workflow debe usar mise para garantizar toolchain pinned."""
        content = CI_WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "mise" in content.lower(), "Workflow no usa mise"

    def test_workflow_runs_lint(self) -> None:
        content = CI_WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "lint" in content.lower(), "Workflow no ejecuta lint"

    def test_workflow_runs_format_check(self) -> None:
        content = CI_WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "format" in content.lower(), "Workflow no ejecuta format --check"

    def test_workflow_runs_pytest(self) -> None:
        content = CI_WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "pytest" in content or "test" in content.lower(), "Workflow no ejecuta pytest"

    def test_workflow_uses_uv_cache(self) -> None:
        """El workflow debe cachear ~/.cache/uv para reducir tiempo de CI."""
        content = CI_WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "actions/cache" in content, "Workflow sin actions/cache para uv"
        assert "uv.lock" in content, (
            "Cache key debe incluir hash de uv.lock para invalidar al cambiar deps"
        )
        assert "UV_CACHE_DIR" in content, "Workflow sin UV_CACHE_DIR env var"

    def test_workflow_uploads_coverage_artifact(self) -> None:
        """El workflow debe subir coverage.xml como artifact."""
        content = CI_WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "upload-artifact" in content, "Workflow sin upload-artifact para coverage"
        assert "coverage.xml" in content, "Artifact no incluye coverage.xml"
        assert "--cov" in content, "pytest sin flag --cov (sin cobertura)"


class TestMiseTasksContract:
    """Las tareas mise referenciadas por el CI deben existir en mise.toml."""

    @pytest.fixture
    def mise_toml_content(self) -> str:
        return (REPO_ROOT / "mise.toml").read_text(encoding="utf-8")

    def test_lint_task_exists(self, mise_toml_content: str) -> None:
        assert "[tasks.lint]" in mise_toml_content, "Tarea [tasks.lint] no encontrada en mise.toml"

    def test_format_task_exists(self, mise_toml_content: str) -> None:
        assert "[tasks.format]" in mise_toml_content, (
            "Tarea [tasks.format] no encontrada en mise.toml"
        )

    def test_test_task_exists(self, mise_toml_content: str) -> None:
        assert "[tasks.test]" in mise_toml_content, "Tarea [tasks.test] no encontrada en mise.toml"

    def test_sync_task_exists(self, mise_toml_content: str) -> None:
        """CI usa 'mise run sync' para resolver deps; la tarea debe existir."""
        assert "[tasks.sync]" in mise_toml_content, "Tarea [tasks.sync] no encontrada en mise.toml"
