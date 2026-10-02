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

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK_PATH = REPO_ROOT / "scripts" / "hooks" / "pre-commit"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from check_ci_recipe_parity import pasos_ejecutables as _pasos_ejecutables  # noqa: E402

# El parser de `run:` vive en `scripts/check_ci_recipe_parity.py` y no aqui.
# El invariante C1 depende de el, y duplicarlo entre el guard y su test es
# la forma de que dejen de contar lo mismo sin que nada lo note (WI-98).


PRE_PUSH_HOOK_PATH = REPO_ROOT / "scripts" / "hooks" / "pre-push"
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

    def test_installer_copies_all_hooks(self, tmp_path: Path) -> None:
        """El installer debe iterar sobre TODOS los hooks en scripts/hooks/.

        Hoy usa un glob (`for hook in "$SOURCE_DIR"/*`), asi que ya copia
        todos. Este test crea un repo temporal con multiples hooks y verifica
        que el installer los copia todos sin hardcodear nombres.

        Importante: el hook pre-push NO debe quedar excluido por error.
        """
        import shutil
        import subprocess

        # 1. Crear repo temporal con git init
        fake_repo = tmp_path / "fake_repo"
        fake_repo.mkdir()
        subprocess.run(
            ["git", "init", "--initial-branch=main"],
            cwd=fake_repo,
            check=True,
            capture_output=True,
        )

        # 2. Crear scripts/hooks con 2 hooks (pre-commit + pre-push)
        hooks_src = fake_repo / "scripts" / "hooks"
        hooks_src.mkdir(parents=True)
        (hooks_src / "pre-commit").write_text("#!/bin/sh\necho pre-commit\n")
        (hooks_src / "pre-push").write_text("#!/bin/sh\necho pre-push\n")

        # 3. Instalar el installer real apuntando al fake repo
        # Truco: el installer usa git rev-parse para detectar root, asi que
        # basta con ejecutarlo desde fake_repo. Pero el installer vive en el
        # repo real, asi que copiamos el installer al fake_repo temporalmente.
        installer_copy = fake_repo / "install-hooks.sh"
        shutil.copy(INSTALLER_PATH, installer_copy)

        # 4. Ejecutar installer
        result = subprocess.run(
            ["bash", str(installer_copy)],
            cwd=fake_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Installer fallo: stdout={result.stdout!r} stderr={result.stderr!r}"
        )

        # 5. Verificar que AMBOS hooks se copiaron a .git/hooks/
        git_hooks_dir = fake_repo / ".git" / "hooks"
        assert (git_hooks_dir / "pre-commit").exists(), "pre-commit no copiado"
        assert (git_hooks_dir / "pre-push").exists(), "pre-push no copiado por installer"

        # 6. Verificar que ambos son ejecutables
        import stat

        for name in ("pre-commit", "pre-push"):
            mode = (git_hooks_dir / name).stat().st_mode
            assert mode & stat.S_IXUSR, f"{name} no ejecutable tras installer"


class TestPrePushHook:
    """El hook pre-push ejecuta la suite completa de pytest antes del push.

    Defensa en profundidad 3 capas:
      1. Pre-commit (lint + format + smoke pytest)  [ya implementado]
      2. CI workflow (lint + format + full pytest)  [ya implementado]
      3. Pre-push (suite completa de pytest)         [este test]
    """

    def test_hook_exists(self) -> None:
        assert PRE_PUSH_HOOK_PATH.exists(), f"Hook no encontrado: {PRE_PUSH_HOOK_PATH}"

    def test_hook_is_executable(self) -> None:
        """El hook debe tener bit +x (stat S_IXUSR).

        El install-hooks.sh debe re-aplicar chmod +x al copiar al directorio
        .git/hooks/ (que no se commitea).
        """
        import stat

        mode = PRE_PUSH_HOOK_PATH.stat().st_mode
        assert mode & stat.S_IXUSR, f"Hook no ejecutable: {PRE_PUSH_HOOK_PATH}"

    def test_hook_has_shebang(self) -> None:
        first_line = PRE_PUSH_HOOK_PATH.read_text(encoding="utf-8").splitlines()[0]
        assert first_line.startswith("#!"), f"Hook sin shebang: {first_line!r}"
        assert "sh" in first_line or "bash" in first_line, (
            f"Shebang no apunta a shell: {first_line!r}"
        )

    def test_hook_enforces_pytest(self) -> None:
        """El hook debe ejecutar pytest para validar la suite antes del push."""
        content = PRE_PUSH_HOOK_PATH.read_text(encoding="utf-8")
        assert "pytest" in content, "Hook no ejecuta pytest"

    def test_hook_uses_toolchain_dispatcher(self) -> None:
        """El hook debe usar el dispatcher run_in_toolchain (mise/uv) para coherencia con pre-commit."""
        content = PRE_PUSH_HOOK_PATH.read_text(encoding="utf-8")
        assert "run_in_toolchain" in content or "mise exec" in content, (
            "Hook no usa toolchain dispatcher (mise/uv)"
        )

    def test_hook_provides_bypass_for_experimental_branches(self) -> None:
        """El hook debe permitir bypass via env var HOOK_SKIP_PUSH_TESTS.

        Casos de uso legitimos:
          - Push de rama experimental sin tests listos
          - CI config / docs-only changes en worktree de otro dev
          - Smoke test de hooks system sin esperar 190s
        """
        content = PRE_PUSH_HOOK_PATH.read_text(encoding="utf-8")
        assert "HOOK_SKIP_PUSH_TESTS" in content, (
            "Hook sin mecanismo de bypass HOOK_SKIP_PUSH_TESTS"
        )

    def test_hook_uses_consistent_log_prefix(self) -> None:
        """El hook debe usar prefijo [pre-push] para identificarse en logs."""
        content = PRE_PUSH_HOOK_PATH.read_text(encoding="utf-8")
        assert "[pre-push]" in content, "Hook sin prefijo [pre-push] en logs"

    def test_hook_documents_purpose(self) -> None:
        """El header debe explicar por qué existe el hook (que problema evita)."""
        content = PRE_PUSH_HOOK_PATH.read_text(encoding="utf-8")
        # El header debe contener palabras clave de proposito
        header_lines = "\n".join(content.splitlines()[:15])
        assert "push" in header_lines.lower(), "Hook no documenta relacion con push"
        assert "pytest" in header_lines.lower() or "test" in header_lines.lower(), (
            "Hook no documenta relacion con pytest"
        )

    def test_hook_cleans_up_tempfile_on_exit(self) -> None:
        """El hook debe limpiar el tempfile en EXIT (cubre exito, fallo, SIGTERM/SIGINT).

        Sin trap, un Ctrl-C durante pytest (3min) dejaria un tempfile huerfano
        en /tmp. El trap EXIT garantiza limpieza en cualquier camino de salida.
        """
        content = PRE_PUSH_HOOK_PATH.read_text(encoding="utf-8")
        # El trap debe estar en el bloque donde se crea el tempfile (_log="$(mktemp)")
        assert "trap" in content, "Hook sin trap para limpieza"
        # Verifica que el trap referencia EXIT (cubre todos los caminos de salida)
        assert "trap '" in content and "EXIT" in content, (
            "Hook sin trap EXIT para cubrir exito/fallo/signal"
        )
        # El trap debe limpiar $_log (el tempfile)
        assert "rm -f" in content and '_log"' in content, "Trap no limpia $_log"


class TestCIWorkflow:
    """El workflow GH ejecuta los gates.

    WI-98: nueve de estos tests buscaban **cadenas** en `ci.yml`
    («lint» en el contenido, «pytest» en el contenido). Un guard que busca
    una cadena comprueba que la cadena exista, no la propiedad: el workflow
    anterior 执行 `mise run lint` y `pytest --cov` y por eso pasaban, siendo
    una reejecución parcial de la receta canónica que se quedaba sin
    los tres contratos exigibles.

    Lo que queda son las propiedades que no se deducen de la receta
    canonica: los triggers, el toolchain, el cache y el artefacto de
    cobertura. Que el remoto ejecute lint, format y los tests ya no lo
    vigila este fichero: lo vigila
    `tests/test_wi98_ci_recipe_parity.py`, y lo hace por la via que importa.
    """

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

    def test_workflow_invokes_the_canonical_recipe(self) -> None:
        """La receta, por su NOMBRE.

        Es la propiedad que sustituye a las cuatro pruebas de cadenas que
        havia antes (lint, format, pytest y la de instrumentacion). Buscar
        el nombre del script es lo unico que distingue «ejecuta lo mismo»
        de «ejecuta algo parecido»; y si el remoto dejara de invocarla, la
        regla de AGENTS.md («el runner remoto debe invocar el mismo
        .pipeline.kts») seria falsa otra vez.
        """
        content = CI_WORKFLOW_PATH.read_text(encoding="utf-8")
        assert ".pipeline.kts" in content, (
            "Workflow sin la receta canonica. AGENTS.md declara que el runner "
            "remoto DEBE invocar el mismo .pipeline.kts; si esto falla, o el "
            "workflow cambio de receta o la regla hay que revisarla — no las dos"
        )

    def test_workflow_passes_rerun_to_the_canonical_recipe(self) -> None:
        """`--rerun` no es opcional: sin el el motor cachea el veredicto.

        Medido en AGENTS.md: un run cuyo script no ha cambiado termina en
        SUCCESS sin ejecutar un solo step. Un remoto que invoca la receta
        SIN `--rerun` es un remoto verde que no verifica nada.
        """
        content = CI_WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "--rerun" in content, (
            "El remoto invoca la receta canonica sin --rerun: pipelinek "
            "cachea el veredicto por cacheKey de compilacion y devuelve "
            "SUCCESS sin ejecutar un step"
        )

    def test_workflow_gives_mise_a_token_for_the_github_backend(self) -> None:
        """`mise.toml` fija pipelinek como backend `github:`, no del registro.

        Sin token, `jdx/mise-action` no puede bajarlo y `mise exec --
        pipelinek` resuelve el shim de asdf, que es OTRO binario con la
        misma ruta de nombre. Es el mismo problema que `mise.toml`
        documenta en local, y aqui se manifestaria como «funciona, pero no
        es el que crees».
        """
        content = CI_WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "github_token" in content, (
            "El workflow instala un backend `github:` sin token; pipelinek "
            "no se bajara y se ejecutara otro binario"
        )

    def test_workflow_uses_uv_cache(self) -> None:
        """El workflow debe cachear ~/.cache/uv para reducir tiempo de CI."""
        content = CI_WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "actions/cache" in content, "Workflow sin actions/cache para uv"
        assert "uv.lock" in content, (
            "Cache key debe incluir hash de uv.lock para invalidar al cambiar deps"
        )
        assert "UV_CACHE_DIR" in content, "Workflow sin UV_CACHE_DIR env var"

    def test_workflow_uploads_coverage_artifact(self) -> None:
        """El workflow debe subir coverage.xml como artifact.

        Esta capacidad se conserva al pasar a la receta canonica, pero
        cambiando el ORIGEN del dato: se exporta del `.coverage`
        combinado e instrumentado que deja la receta, no de un `pytest
        --cov` a pelo que mediria la mitad.
        """
        content = CI_WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "upload-artifact" in content, "Workflow sin upload-artifact para coverage"
        assert "coverage.xml" in content, "Artifact no incluye coverage.xml"
        assert "coverage xml" in content, (
            "coverage.xml se sube pero no se genera: falta exportar el "
            "informe. O se mudo de paso y nadie lo nota, o se rompió"
        )

    def test_workflow_does_not_reimplement_the_recipe(self) -> None:
        """El remoto no vuelve a medir lo que la receta ya midió.

        Es la diferencia entre apoyarse en la instrumentación correcta y
        volver a medir a mano con el instrumento que ya se sabe ciego.

        Mira **los pasos ejecutables**, no el fichero entero: la primera
        versión de este test buscaba la cadena en todo el contenido y
        fallaba porque el `ci.yml` la menciona en un comentario que explica
        por qué no debe usarse. Buscar una cadena en un fichero del que se
        habla de la cadena es buscar en el sitio equivocado — que es
        exactamente la clase de guard que este bloque viene a cerrar.
        """
        pasos = _pasos_ejecutables(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
        assert not any("pytest --cov" in paso for paso in pasos), (
            "El workflow vuelve a medir con `pytest --cov` a pelo: sin el "
            "hook .pth de scripts/coverage.sh el CLI ejecutado por "
            "subproceso no se ve. Medido: 39 % en cli/commands/runs.py "
            f"frente a 87.96 % de la instrumentada. Pasos: {pasos}"
        )


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
