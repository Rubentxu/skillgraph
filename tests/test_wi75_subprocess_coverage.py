"""WI-75 — la cobertura mide el CLI ejecutado por SUBPROCESO.

Contexto (por que este fichero existe)
--------------------------------------
La suite ejercita la frontera CLI casi siempre por subproceso
(`sys.executable -m skillgraph ...` con `cwd=tmp_path`). Medido el
2026-10-02 con `pytest --cov=skillgraph.cli`, el CLI total daba 65.86 %
— por DEBAJO del contrato de AGENTS.md §6.3 (>=70 %) — y parecia deuda de
tests: expansion.py 40 %, runs.py 37 %, pack.py 46 %.

Era ceguera del instrumento. Con la receta de `scripts/coverage.sh`
(hook .pth + `parallel = true` + `data_file` ABSOLUTO) el mismo codigo
mide 94 %, y `cmd_expansion_apply` —la funcion que WI-72 partio en 73
LoC— aparece con cobertura real, no con un 0 % que solo contaba ramas
de error.

Estos tests fijan los dos ingredientes que se pueden perder en silencio:

1. `test_subprocess_cli_coverage_is_recorded` — end-to-end. Un
   subproceso real de la CLI, lanzado con la receta, debe dejar datos y
   tras combinar, `cli/commands/expansion.py` debe salir con sentencias
   ejecutadas. Si el hook .pth desaparece del venv, o si el subproceso
   deja de heredar la variable, este test falla.

2. `test_coverage_script_pins_the_three_ingredients` — el contrato
   escrito. Sin `parallel = true` el ultimo proceso pisa a los demas
   (el "last-writer-wins" que WI-57 midio); sin `data_file` absoluto los
   subprocesos escriben dentro del tmp de pytest y pytest lo borra. Un
   "simplificar" cualquiera de los dos devuelve la medicion a 0 % sin
   que nada falle, asi que se fija a nivel de script.

No se usan mocks: subproceso real, disco real, venv real.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
COVERAGE_SCRIPT = REPO_ROOT / "scripts" / "coverage.sh"


def _write_recipe(tmp_path: Path) -> Path:
    """Escribe una config de coverage equivalente a la de `scripts/coverage.sh`.

    `data_file` es ABSOLUTO y vive dentro de tmp_path: los subprocesos se
    lanzan con `cwd=tmp_path`, asi que un path relativo resolveria ahi y
    pytest lo borraria (el bug que midio WI-75).
    """
    rc = tmp_path / "covrc"
    rc.write_text(
        "[run]\n"
        "branch = true\n"
        "source = skillgraph\n"
        "parallel = true\n"
        "sigterm = true\n"
        f"data_file = {tmp_path / '.coverage'}\n"
        "\n"
        "[report]\n"
        "fail_under = 0\n",
        encoding="utf-8",
    )
    return rc


@pytest.mark.slow
def test_subprocess_cli_coverage_is_recorded(tmp_path: Path) -> None:
    """Un subproceso real de la CLI debe quedar cubierto, no invisible."""
    import coverage

    rc = _write_recipe(tmp_path)
    data_root = tmp_path / "sg-data"

    env = {**os.environ, "COVERAGE_PROCESS_START": str(rc)}
    target = "src/skillgraph/cli/commands/expansion.py"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "skillgraph",
            "--data-root",
            str(data_root),
            "init",
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, f"init fallo: rc={proc.returncode}\n{proc.stderr}"

    # 1) El subproceso DEJO datos de cobertura (ficheros paralelos).
    parallel = sorted(tmp_path.glob(".coverage.*"))
    assert parallel, (
        "el subproceso no dejo datos de cobertura: o falta el hook .pth "
        "que llama a coverage.process_startup(), o COVERAGE_PROCESS_START "
        "no llego al subproceso"
    )

    # 2) Tras combinar, el modulo de comandos del CLI tiene sentencias
    #    ejecutadas: esto es justo lo que antes marcaba 0 %.
    combined = subprocess.run(
        [sys.executable, "-m", "coverage", "combine", "--rcfile", str(rc), str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert combined.returncode == 0, f"combine fallo: {combined.stderr}"

    cov = coverage.Coverage(data_file=str(tmp_path / ".coverage"), config_file=False)
    cov.load()
    # analysis2 devuelve una 5-tupla:
    # (fichero, sentencias, excluidas, sin_cubrir, texto_legible).
    name, executed, _excluded, missing, _text = cov.analysis2(target)

    assert name.endswith("expansion.py"), f"analizo otro fichero: {name}"
    assert len(executed) > 0, "expansion.py no tiene sentencias que medir"
    assert len(missing) < len(executed), (
        f"expansion.py quedo al 0 % incluso combinando los datos del "
        f"subproceso ({len(missing)}/{len(executed)} sin cubrir): la "
        f"instrumentacion de subproceso volvio a romperse"
    )


def test_coverage_script_pins_the_three_ingredients() -> None:
    """El script debe seguir fijando los tres ingredientes de la receta.

    Fijarlos aqui evita el modo de fallo mas caro: una receta que "funciona"
    en la maquina de quien la escribio y mide 0 % en cualquier otra.
    """
    assert COVERAGE_SCRIPT.is_file(), f"falta {COVERAGE_SCRIPT}"
    assert os.access(COVERAGE_SCRIPT, os.X_OK), f"{COVERAGE_SCRIPT} no es ejecutable"

    body = COVERAGE_SCRIPT.read_text(encoding="utf-8")

    # Se asienta sobre el CODIGO, no sobre el fichero entero: los tres
    # ingredientes estan mencionados tambien en la cabecera comentada, y
    # una asercion sobre el cuerpo completo se satisfacia con el comentario
    # mientras la config dizia `parallel = false` (mutacion no cazada,
    # 2026-10-02).
    code = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("#"))

    # (1) hook .pth auto-instalado: el de a1_coverage.pth estaba colado a
    #     mano en el venv y no estaba declarado en pyproject/uv.lock.
    #     Se comprueban las DOS mitades: escribir el hook e idempotencia
    #     (reutilizar el que ya exista). Sin el `if`, el script duplicaria
    #     process_startup en cada venv que ya trajera uno.
    assert "process_startup" in code, "el script debe crear el hook .pth si falta"
    assert "grep -lqs" in code, (
        "el script debe comprobar si ya existe un hook .pth antes de crear "
        "otro (si no, duplica process_startup en un venv que ya tenga uno)"
    )
    # (2) parallel: sin el, last-writer-wins entre procesos.
    assert "parallel = true" in code, "falta parallel = true en la config"
    # (3) data_file absoluto: con cwd=tmp_path uno relativo se pierde.
    assert "data_file = $REPO_ROOT/.coverage.parallel" in code, (
        "el data_file debe ser absoluto; con uno relativo los datos de los "
        "subprocesos caen en el tmp de pytest y se borran"
    )
    assert "COVERAGE_PROCESS_START" in code, "falta exportar COVERAGE_PROCESS_START"

    # (4) pytest-cov mide el PRINCIPAL y el hook los SUBPROCESOS, ambos al
    #     mismo data_file. Medido 2026-10-02: correr `pytest` a pelo
    #     (solo el hook) daba 60 % en la suite completa — expansion.py 82 %
    #     pero runtime/locks.py 35 %, porque el perfil del proceso principal
    #     se perdia. Sin --cov/--cov-config, la receta vuelve a perderlo.
    assert "--cov=skillgraph" in code, (
        "el proceso principal debe medirlo pytest-cov; con `pytest` a pelo "
        "su perfil se pierde y la suite completa cae al 60 %"
    )
    assert "--cov-config=" in code, (
        "pytest-cov debe leer la MISMA config que el hook (data_file "
        "compartido), si no los dos miden en ficheros distintos"
    )
