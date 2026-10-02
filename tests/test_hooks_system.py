"""Tests para el sistema de git hooks del proyecto.

WI-100: siete de estos tests buscaban **cadenas** en el contenido del hook
pre-push («pytest» esta, «HOOK_SKIP_PUSH_TESTS» esta, «run_in_toolchain»
esta). Con cadenas asi, el hook anterior pasaba: ejecutaba `pytest -q` a
pelado con el instrumento que no ve los subprocesos, y sus propios tests
lo confirmaban.

Lo que sustituye a cada uno comprueba la PROPIEDAD, y dos de ellos
**ejecutan** el hook sobre un repo de prueba con un `scripts/ci.sh` stub
que falla si se invoca. Es la primera vez que este fichero comprueba
comportamiento y no forma: hasta aqui, «el hook menciona el bypass» era
indistinguible de «el bypass funciona».

Los parsers viven en `scripts/check_ci_recipe_parity.py` y no aqui. El
invariante C4 depende de ellos, y duplicarlos entre el guard y su test es
la forma de que dejen de contar lo mismo sin que nada lo note (WI-98).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK_PATH = REPO_ROOT / "scripts" / "hooks" / "pre-commit"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import check_ci_recipe_parity as _par  # noqa: E402

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


def _hook_pre_push() -> str:
    return PRE_PUSH_HOOK_PATH.read_text(encoding="utf-8")


def _repo_de_prueba(tmp_path: Path, ci_sh: str) -> Path:
    """Un repo git minimo con el hook instalado y un `ci.sh` estejado.

    El hook real, sin modificar, en un repo que no es el de desarrollo: por
    eso se puede ejecutar sin tocar nada. El `ci.sh` decides el resultado,
    asi que el test mide COMO el hook consulta a su delegado, no si el
    delegado funciona — eso lo mide el otro test.
    """
    repo = tmp_path / "repo"
    (repo / "scripts" / "hooks").mkdir(parents=True)
    (repo / "scripts" / "ci.sh").write_text(ci_sh, encoding="utf-8")
    shutil.copy(PRE_PUSH_HOOK_PATH, repo / "scripts" / "hooks" / "pre-push")
    (repo / "un-fichero").write_text("x", encoding="utf-8")
    for cmd in (
        ["init", "-q"],
        ["config", "user.email", "hook@test.invalid"],
        ["config", "user.name", "hook test"],
        ["add", "-A"],
        ["commit", "-qm", "inicial"],
    ):
        subprocess.run(["git", *cmd], cwd=repo, check=True, capture_output=True)
    return repo


class TestPrePushHookDelega:
    """El pre-push pide la receta; no la tiene.

    MEDIDO en WI-100: el hook corria `pytest -q` a pelo, o sea la MISMA
    suite con un instrumento distinto y menos informacion. Con el mismo
    `.coverage.rc` y el mismo commit, unica variable el hook `.pth`:

        modulo                pre-push    coverage.sh    delta
        cli/commands/runs.py     39 %         88 %          -49
        cli/runner.py            55 %         79 %          -24
        cli/support.py           69 %         86 %          -17

    `cli/support.py` mide 69 %, y el suelo que declara el propio
    AGENTS.md 6.3 para la CLI es 70 %. El gate mas cercano al push podia
    dar VERDE un paquete que no cumplia el suelo declarado. Ademas no
    ejecutaba ninguno de los cuatro contratos exigibles.

    Los tres primeros tests ya existian y se quedan: existen, son
    ejecutables, tienen shebang. Los demas miraban la cadena.
    """

    def test_hook_exists(self) -> None:
        assert PRE_PUSH_HOOK_PATH.exists(), f"Hook no encontrado: {PRE_PUSH_HOOK_PATH}"

    def test_hook_is_executable(self) -> None:
        import stat

        mode = PRE_PUSH_HOOK_PATH.stat().st_mode
        assert mode & stat.S_IXUSR, f"Hook no ejecutable: {PRE_PUSH_HOOK_PATH}"

    def test_hook_has_shebang(self) -> None:
        first_line = _hook_pre_push().splitlines()[0]
        assert first_line.startswith("#!"), f"Hook sin shebang: {first_line!r}"
        assert "sh" in first_line or "bash" in first_line, (
            f"Shebang no apunta a shell: {first_line!r}"
        )

    def test_el_hook_delega_en_el_dueno_de_la_receta(self) -> None:
        """Invoca `scripts/ci.sh`, que es quien sabe llegar a `.pipeline.kts`.

        Y no se busca `.pipeline.kts` en el hook: el hook no lo menciona, y
        no deberia. La propiedad es la DELEGACION, y su ruta es el owner's.
        Duplicar el comando canonico en el hook crearia un segundo dueno de
        la misma regla, que es exactamente lo que `AGENTS.md` («CI Local
        Obligatorio») prohibe.
        """
        assert "scripts/ci.sh" in _par.rutas_de_script(_hook_pre_push(), "#"), (
            "El pre-push no invoca scripts/ci.sh. Sin esa indireccion nadie "
            "resuelve mise trust ni .pipelinek/, y el hook se convierte en "
            "una receta mas con un instrumento distinto"
        )

    def test_el_hook_no_tiene_receta_propia(self) -> None:
        """La mitad de la que se esperaba: no ejecuta pytest, lo pide.

        La version anterior ejecutaba `pytest -q`; por eso
        `test_hook_enforces_pytest` («pytest» esta en el contenido) pasaba
        y el hook era una cuarta receta. Ahora esa asercion seria la
        equaciona del defecto.
        """
        assert not _par.ejecuta_pytest(_hook_pre_push()), (
            "El pre-push ejecuta pytest. Si lo ejecuta, tiene su propia "
            "receta y su veredicto se mide con un instrumento distinto al "
            "de la receta canonica"
        )

    def test_el_bypass_salta_la_verificacion_de_verdad(self, tmp_path: Path) -> None:
        """«HOOK_SKIP_PUSH_TESTS» esta en el contenido: eso no es un bypass.

        Ejecuta el hook real sobre un repo de prueba cuyo `ci.sh` falla. Si
        el bypass no funciona, el hook sale != 0 y este test cae. Antes solo
        se comprobaba que la variable aparecia en el texto, cosa que un
        comentario satisface igual.
        """
        repo = _repo_de_prueba(tmp_path, "#!/bin/sh\necho STUB-EJECUTADO\nexit 9\n")
        r = subprocess.run(
            ["sh", "scripts/hooks/pre-push"],
            cwd=repo,
            env={**os.environ, "HOOK_SKIP_PUSH_TESTS": "1"},
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert r.returncode == 0, r.stdout + r.stderr
        assert "STUB-EJECUTADO" not in r.stdout, (
            "Con el bypass puesto, el hook ejecuto la verificacion. El "
            "bypass se declara en la cabecera pero no hace nada"
        )

    def test_el_hook_aborta_cuando_el_dueno_falla(self, tmp_path: Path) -> None:
        """La otra mitad: sin bypass, un fallo del delegado ES un push abortado.

        Es la propiedad que justifica el tempfile sin pipe. Con
        `sh scripts/ci.sh | tail -30`, el exit code seria el de `tail` — que
        es 0 — y el hook daria verde con la receta en rojo. La trampa la
        documenta `.pipeline.kts`, el `pre-commit` y el propio hook.
        """
        repo = _repo_de_prueba(tmp_path, "#!/bin/sh\necho STUB-EJECUTADO\nexit 9\n")
        r = subprocess.run(
            ["sh", "scripts/hooks/pre-push"],
            cwd=repo,
            env={**os.environ, "HOOK_SKIP_PUSH_TESTS": "0"},
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert r.returncode != 0, (
            "El hook dio verde con el delegado en rojo. O el exit code se "
            "perdio por un pipe, o el error no se propaga"
        )
        assert "STUB-EJECUTADO" in r.stdout, (
            "El hook ni siquiera llego a invocar a su delegado. Con "
            f"HOOK_SKIP_PUSH_TESTS=0 deberia haberlo hecho:\n{r.stdout}"
        )

    def test_la_invocacion_del_dueno_no_trae_pipe(self) -> None:
        """El rc de un pipe es el de su ultimo comando, no el del que importa.

        `tail` sale 0 siempre. Un pipe entre el hook y su delegado
        convertiria «la receta fallo» en «el push pasa», y ningun test que
        mire el texto lo notaria.
        """
        ordenes = [o for o in _par.logicas_de(_hook_pre_push(), "#") if "scripts/ci.sh" in o]
        assert ordenes, "el hook no invoca a scripts/ci.sh"
        con_pipe = [o for o in ordenes if "|" in o]
        assert not con_pipe, (
            f"La invocacion del delegado va con pipe: el exit code seria el "
            f"de tail (0) y el hook daria verde con la receta en rojo: {con_pipe}"
        )

    def test_el_hook_se_situa_en_la_raiz_antes_de_verificar(self) -> None:
        """Sin esto, `scripts/ci.sh` no se encuentra y el fallo no explica nada.

        git ejecuta los hooks con el cwd en la raiz en un push normal, pero
        eso no esta garantizado cuando el hook corre desde otro worktree. El
        fallo que produce sin esto es «no such file», que no dice nada de la
        causa.
        """
        ordenes = _par.logicas_de(_hook_pre_push(), "#")
        assert any("rev-parse --show-toplevel" in o for o in ordenes), (
            "El hook no resuelve la raiz del repo antes de invocar a su "
            "delegado; dependeria del cwd con el que git lo lance"
        )

    def test_el_prefijo_de_log_se_usa(self) -> None:
        """Convencion de logs, no propiedad de comportamiento: se queda como cadena.

        Se declara explicitamente la excepcion, porque un guard tiene que
        saber cuando mira texto a proposito. Aqui no hay forma de que un
        prefijo mal puesto cambie lo que el hook acepta o rechaza.
        """
        assert "[pre-push]" in _hook_pre_push(), "Hook sin prefijo [pre-push] en logs"


class TestPreCommitHookFiltraDeVerdad:
    """El smoke que decia ser, y no era.

    MEDIDO en WI-100: el hook seleccionaba los `.py` staged y **no se los
    pasaba** a pytest. Ejecutaba `pytest -q` a secas, o sea la suite
    entera:

        anunciado   "smoke, N files staged",  ~10 s
        real        2636 tests,               124.29 s

    El selector existia; la instruccion no. Y ningun test lo noto, porque
    buscaban «pytest» en el contenido — y el hook SI tiene `pytest`.
    """

    def test_los_ficheros_staged_llegan_a_pytest(self) -> None:
        """La propiedad: pytest recibe paths. Sin paths no hay smoke.

        Con `"$STAGED_PY"` entrecomillado, pytest recibiria UN argumento con
        todos los paths pegados y no correria nada: el hook pasaria en
        verde sin haber ejecutado un test. Por eso la comprobacion mira la
        orden de verdad y no si la variable aparece en el texto.
        """
        ordenes = [
            o
            for o in _par.logicas_de(HOOK_PATH.read_text(encoding="utf-8"), "#")
            if _par._INVOCA_PYTEST.search(o)
        ]
        assert ordenes, "el pre-commit no lanza pytest"
        con_paths = [o for o in ordenes if _par.filtra_por_ficheros(o)]
        assert con_paths, (
            "El pre-commit lanza pytest SIN pasarle los ficheros staged: "
            f"eso es la suite entera, no un smoke. Ordenes: {ordenes}"
        )
        quoted = [o for o in ordenes if '"$STAGED_PY"' in o or "'$STAGED_PY'" in o]
        assert not quoted, (
            f"STAGED_PY va entrecomillado: pytest recibiria un solo argumento "
            f"con todos los paths pegados y no correria nada: {quoted}"
        )

    def test_el_pre_commit_ya_no_es_un_verdicto_sobre_el_repo(self) -> None:
        """Por eso queda fuera de C4 sin necesitar una lista de excepciones.

        C4 mide «pytest sobre el repo entero». Este hook filtra, asi que no
        emite veredicto sobre el repo: emite sobre lo que alguien tiene a
        medio escribir. El veredicto lo dan el pre-push y la receta.
        """
        contenido = HOOK_PATH.read_text(encoding="utf-8")
        assert _par.ejecuta_pytest(contenido)
        assert _par.filtra_por_ficheros(contenido), (
            "El pre-commit dejo de filtrar: si corre pytest sobre el repo "
            "entero, es una receta mas con un instrumento distinto, y vuelve "
            "a ser un veredicto que no es el de la receta canonica"
        )

    def test_el_smoke_es_rapido_por_diseno_no_por_suerte(self, tmp_path: Path) -> None:
        """Un filtro que tarda 124 s no es un filtro: nadie lo espera.

        Mide un smoke sobre dos modulos triviales en `tmp_path`, NO sobre
        ficheros del repo. La primera version de este test usaba
        `tests/test_hooks_system.py`, y resulto ser un bucle: el smoke
        corria un fichero que contiene el test del smoke, que volvia a
        correr el smoke. No era solo un test lento — era un hook que, al
        tocar su propio fichero de tests, se llama a si mismo.

        El coste medido con ficheros reales fue de 0.83 s frente a los
        124.29 s de la suite entera.
        """
        import time

        modulos = []
        for i in range(2):
            f = tmp_path / f"mod_{i}.py"
            f.write_text("def test_verdad() -> None:\n    assert True\n", encoding="utf-8")
            modulos.append(str(f))

        inicio = time.monotonic()
        r = subprocess.run(
            ["mise", "exec", "--", "uv", "run", "pytest", "-q", "-p", "no:cacheprovider", *modulos],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        elapsed = time.monotonic() - inicio
        assert r.returncode == 0, r.stdout[-3000:]
        assert elapsed < 60, (
            f"El smoke tardo {elapsed:.1f}s sobre 2 modulos. La suite entera "
            "tardaba 124.29 s: eso no es un smoke, es la receta anterior "
            "repetida con otro nombre"
        )


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
        pasos = _par.pasos_ejecutables(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
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
