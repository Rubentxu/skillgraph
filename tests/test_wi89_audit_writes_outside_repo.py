"""WI-89: la auditoria no escribe dentro del repositorio que audita.

`audits/audit_debt.py` se invoca como subproceso desde la raiz del repo en
`test_audit_debt_smoke.py` y `test_audit_debt_accuracy.py`, y su destino
de escritura era `AUDITS_DIR = pathlib.Path("audits")`, relativo al cwd.
Como `audits/` esta TRACKEADO (63 ficheros; solo `audits/*-audit-bundle.tar.gz`
esta en .gitignore), cada corrida de la suite reescribia un fichero versionado
dentro del repo. Dos modos de fallo, ambos medidos:

  1. el codigo cambio desde la ultima generacion -> el fichero de HOY cambia
     dentro de un directorio trackeado -> `M audits/...`. Fue lo que paso en el
     commit de WI-87 (+50 LoC).
  2. no hay informe para hoy (primera corrida del dia) -> se crea un fichero
     NUEVO sin trackear. Demostrado con fecha 2099-01-01:
     `?? audits/architecture-debt-2099-01-01.md`. Este modo no requiere que
     cambie nada.

La comprobacion de este archivo no es "el arbol queda limpio", sino "el arbol
NO CAMBIA": un operador puede estar trabajando con cambios sin commitear, y en
ese caso el arbol ya esta sucio antes de empezar. Comparar contra el estado
inicial y exigir que siga igual es la unica forma de que la comprobacion sea
util para un desarrollador y no solo para CI.
"""

from __future__ import annotations

import importlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AUDITOR = REPO_ROOT / "audits" / "audit_debt.py"


def _git_status() -> str:
    proc = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    return proc.stdout


def _run_auditor(out_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(AUDITOR), "--out-dir", str(out_dir)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


class TestAuditWritesWhereItIsTold:
    """El destino de la escritura es un parametro, no el cwd."""

    def test_out_dir_argument_is_honoured(self, tmp_path: Path) -> None:
        proc = _run_auditor(tmp_path)
        assert proc.returncode == 0, proc.stderr
        written = list(tmp_path.glob("architecture-debt-*.md"))
        assert written, f"no se escribio informe en {tmp_path}; stdout={proc.stdout!r}"

    def test_printed_path_is_the_written_one(self, tmp_path: Path) -> None:
        """`main()` imprime la ruta que escribio, no una calculada aparte.

        Los tests actuales leen `Path(proc.stdout.strip())` y lo abren. Si el
        stdout y la escritura divergieran, el test abriria un fichero viejo
        y pasaria sin comprobar nada.
        """
        proc = _run_auditor(tmp_path)
        assert proc.returncode == 0, proc.stderr
        printed = Path(proc.stdout.strip())
        assert printed.exists(), f"stdout apunta a {printed}, que no existe"
        assert printed.parent == tmp_path, f"stdout {printed} no esta en {tmp_path}"

    def test_src_root_argument_is_honoured(self, tmp_path: Path) -> None:
        """Se puede auditar un arbol distinto sin cambiar de cwd.

        Elcwd se queda en la RAIZ, donde `src/` real existe, y `--src-root`
        apunta a un arbol de un solo modulo. Si `--src-root` se ignorara, el
        informe describiria el arbol real y no el de juguete: por eso se
        comprueba el recuento de modulos, no solo que el fichero exista.
        """
        fake_src = tmp_path / "src" / "pkg"
        fake_src.mkdir(parents=True)
        (fake_src / "__init__.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        out = tmp_path / "out"
        out.mkdir()

        proc = subprocess.run(
            [
                sys.executable,
                str(AUDITOR),
                "--src-root",
                str(tmp_path / "src"),
                "--out-dir",
                str(out),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        assert proc.returncode == 0, proc.stderr
        report = next(out.glob("architecture-debt-*.md"))
        modules = re.search(r"\*\*(\d+)\*\* modulos Python", report.read_text(encoding="utf-8"))
        assert modules, "no se encontro el recuento de modulos"
        assert int(modules.group(1)) == 1, (
            f"el informe describes {modules.group(1)} modulos: se analizo el "
            "arbol real, luego --src-root se esta ignorando"
        )

    def test_default_behaviour_is_unchanged(self, tmp_path: Path) -> None:
        """Sin `--out-dir`, el destino sigue siendo `audits/` relativo al cwd.

        El contrato por defecto no se mueve: un humano que lance el auditor a
        mano desde la raiz sigue obteniendo el informe en `audits/`. El
        sandbox lleva su propio `src/` porque el default tambien es relativo
        al cwd, y sin el el auditor aborta con FATAL antes de escribir.
        """
        sandbox = tmp_path / "cwd"
        (sandbox / "audits").mkdir(parents=True)
        pkg = sandbox / "src" / "pkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("def f():\n    return 1\n", encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, str(AUDITOR)],
            cwd=sandbox,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        assert proc.returncode == 0, proc.stderr
        assert list((sandbox / "audits").glob("architecture-debt-*.md"))


class TestTheTestHelpersThemselvesWriteOutside:
    """El invariante, apuntando a lo que los tests hacen y no a lo que yo hago.

    Comparar `git status` antes y despues de MI invocacion con `--out-dir`
    no protege de nada: si alguien revierte los helpers y los vuelve a lanzar
    sin sandbox, esa comprobacion sigue verde porque la invocacion del guard
    no es la que se revierte. Estos tests ejecutan los helpers DE VERDAD y
    comprueban a donde apuntan.

    La asercion principal no depende de que el informe este caducado: mira la
    ruta impresa. La comparacion de `git status` se queda como cobertura
    secundaria del caso en que el contenido cambia, que es el modo 1.
    """

    @pytest.mark.parametrize(
        "module_name",
        ["tests.test_audit_debt_smoke", "tests.test_audit_debt_accuracy"],
    )
    def test_helper_writes_outside_the_repository(self, module_name: str) -> None:
        module = importlib.import_module(module_name)
        proc = module._run_audit()
        assert proc.returncode == 0, proc.stderr

        written = Path(proc.stdout.strip()).resolve()
        assert REPO_ROOT.resolve() not in written.parents, (
            f"{module_name}._run_audit() escribio DENTRO del repositorio: {written}. "
            "Ese es el defecto de WI-89; debe pasar --out-dir con un sandbox."
        )

    @pytest.mark.parametrize(
        "module_name",
        ["tests.test_audit_debt_smoke", "tests.test_audit_debt_accuracy"],
    )
    def test_helper_does_not_change_git_status(self, module_name: str) -> None:
        module = importlib.import_module(module_name)
        before = _git_status()
        proc = module._run_audit()
        assert proc.returncode == 0, proc.stderr
        assert _git_status() == before, (
            f"{module_name}._run_audit() cambio el estado del repositorio"
        )

    def test_the_auditor_prints_the_path_it_wrote(self) -> None:
        """stdout y la escritura no pueden divergir.

        Los tests abren `Path(proc.stdout.strip())`. Si stdout apuntara a otro
        sitio, abririan un fichero viejo — o de otro dia — y pasarian sin
        comprobar nada.
        """
        out = Path(tempfile.mkdtemp(prefix="sg-wi89-"))
        proc = _run_auditor(out)
        assert proc.returncode == 0, proc.stderr
        printed = Path(proc.stdout.strip()).resolve()
        assert printed.exists(), f"stdout apunta a {printed}, que no existe"
        assert printed.parent == out.resolve()

    def test_a_fresh_date_does_not_create_a_file_in_the_repo(self, tmp_path: Path) -> None:
        """El segundo modo de fallo: hoy sin informe previo.

        Es el que no requiere que cambie nada. Con el destino por defecto
        relativo al cwd, la primera corrida de cada dia crea un fichero
        `architecture-debt-<hoy>.md` sin trackear en un directorio trackeado.
        """
        audits_dir = REPO_ROOT / "audits"
        before = set(audits_dir.glob("*.md"))

        proc = _run_auditor(tmp_path / "out")
        assert proc.returncode == 0, proc.stderr

        after = set(audits_dir.glob("*.md"))
        assert after == before, (
            f"el auditor creo ficheros dentro de audits/: {sorted(p.name for p in after - before)}"
        )

    def test_importing_the_auditor_creates_no_directory(self, tmp_path: Path) -> None:
        """`AUDITS_DIR.mkdir(exist_ok=True)` estaba en el import.

        Un modulo de auditoria que crea un directorio al ser importado tiene
        un efecto lateral en el `import`, no en su trabajo. Con el destino
        parametrizado, el mkdir pertenece a `main()`.
        """
        sandbox = tmp_path / "cwd"
        sandbox.mkdir()
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import runpy, sys; runpy.run_path({str(AUDITOR)!r}, run_name='not_main')",
            ],
            cwd=sandbox,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        assert not (sandbox / "audits").exists(), (
            "importar el auditor creo 'audits/' en el cwd: el mkdir debe "
            "estar en main(), no a nivel de modulo"
        )


class TestAccuracyTestsStillAnalyseTheRealTree:
    """El arreglo no puede convertir la prueba en una sobre un arbol de juguete.

    `test_audit_debt_accuracy.py` compara la cc medida sobre `_PROJECT_ROOT/src`
    con las cifras citadas en el informe. Si el destino se parametriza pero el
    origen pasara a ser relativo al destino, el test compararia el arbol real
    contra un informe de otro arbol y pasaria sin comprobar nada.
    """

    def test_default_src_root_is_the_real_tree(self, tmp_path: Path) -> None:
        """Sin `--src-root` y con cwd en la raiz, se audita el arbol real.

        El destino es un sandbox: este test no puede ser el que reintroduzca
        el defecto que esta midiendo. La version anterior pasaba
        `--out-dir audits/` — la ruta del repositorio — y escribia ahi.
        """
        proc = subprocess.run(
            [sys.executable, str(AUDITOR), "--out-dir", str(tmp_path / "out")],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        assert proc.returncode == 0, proc.stderr
        report = Path(proc.stdout.strip())
        text = report.read_text(encoding="utf-8")
        m = re.search(r"\*\*(\d+)\*\* modulos Python", text)
        assert m, "no se encontro el recuento de modulos en el informe"
        real = len([p for p in (REPO_ROOT / "src").rglob("*.py") if "__pycache__" not in str(p)])
        assert int(m.group(1)) == real, (
            f"el informe dice {m.group(1)} modulos y el arbol real tiene {real}: "
            "el origen ya no es el arbol real"
        )
