"""B37 — el hook tiene que DECIR si ha medido.

**MEDIDO AL ABRIR EL BLOQUE, con `scripts/measure_b37_smoke_subset.py`** sobre
los 1163 commits del repo:

    551  no stagean `.py`       -> el smoke no lanza pytest
    252  stagean solo codigo   -> `pytest -q src/...` colecta cero, rc=5, y el
                                   hook sigue como si hubiera medido
    264  stagean un solo test  -> corre ese y nada mas, sin decirlo

**803 de 1163 commits — el 69 % — pasaron por el hook sin ejecutar un test.**

Y el defecto no es que el smoke no corra: es que **su silencio es
indistinguible de un paso**. `scripts/hooks/pre-commit` tiene la forma

    if [ -n "$STAGED_PY" ] && [ "${HOOK_SKIP_TESTS:-0}" != "1" ]; then
        ...smoke...
    fi

    echo "[pre-commit] OK"

y de los TRES caminos por los que puede pasar —smoke corrido, `HOOK_SKIP_TESTS=1`,
y nada stageado— **solo el primero anuncia algo**. Los otros dos imprimen un
`OK` idéntico al de un commit que sí se midió.

**POR QUE ESTE TEST EJECUTA EL HOOK Y NO LO LEE.** Un guard que buscara una
cadena en el fichero aprobaría con la rama movida dentro del `if`, que es
exactamente donde estaba el defecto. Lo que se mide es lo que el operador
**VE**: se ejecuta el hook real, sin modificar, en un repo de pruebas, y se mira
lo que imprime.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
HOOK = RAIZ / "scripts" / "hooks" / "pre-commit"

#: Los tres binarios que el hook invoca por `run_in_toolchain`. El stub
#: responde y sale con 0: aqui no se mide si ruff pasa, se mide QUE DICE EL HOOK
#: sobre los tests, y un binario real haria que el test dependiera de tener
#: ruff, mise y un venv en el entorno de quien lo corre.
BINS_QUE_SE_ESTUPEAN = ("mise", "ruff", "uv")

STUB = "#!/bin/sh\nexit 0\n"


def _repo_con_hook(tmp_path: Path) -> Path:
    """Un repo git minimo con el hook REAL instalado y PATH sin herramientas.

    El hook se copia sin tocar: si aqui se modificara una linea, el test
    mediria el hook del test y no el del repo.
    """
    repo = tmp_path / "repo"
    (repo / "scripts" / "hooks").mkdir(parents=True)
    shutil.copy(HOOK, repo / "scripts" / "hooks" / "pre-commit")

    binarios = tmp_path / "bin"
    binarios.mkdir()
    for nombre in BINS_QUE_SE_ESTUPEAN:
        ruta = binarios / nombre
        ruta.write_text(STUB, encoding="utf-8")
        ruta.chmod(0o755)

    for cmd in (
        ["init", "-q"],
        ["config", "user.email", "b37@b37.invalid"],
        ["config", "user.name", "b37"],
    ):
        subprocess.run(["git", *cmd], cwd=repo, check=True, capture_output=True)
    return repo


def _stagear(repo: Path, *rutas: str) -> None:
    for ruta in rutas:
        destino = repo / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text("x = 1\n", encoding="utf-8")
    if rutas:
        subprocess.run(["git", "add", *rutas], cwd=repo, check=True, capture_output=True)


def _correr(repo: Path, tmp_path: Path, **entorno: str) -> str:
    # El PATH se ANTEPONE, no se sustituye: MEDIDO, la primera version lo
    # reemplazo entero y `subprocess` no encontro ni el `sh` que lanza el hook.
    # Anteponer basta para que los stubs ganen a las herramientas reales, que
    # es justo lo que hace el hook con `command -v mise`.
    binarios = str(tmp_path / "bin")
    r = subprocess.run(
        ["sh", "scripts/hooks/pre-commit"],
        cwd=repo,
        env={**os.environ, "PATH": f"{binarios}{os.pathsep}{os.environ['PATH']}", **entorno},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    return r.stdout + r.stderr


def _dice_que_no_ha_medido(salida: str) -> bool:
    """El hook dice que no ha medido, y no lo disimula con un OK."""
    return "tests:" in salida and "NINGUNO" in salida


def test_sin_ficheros_py_stageados_dice_que_no_ha_medido(tmp_path: Path) -> None:
    """**EL CASO DE LOS 551 COMMITS.** El hook pasa en silencio y parece verde.

    Con un `doc-only` el hook no tiene nada que correr, y eso es correcto: es
    un filtro, no una certificacion. Lo que no puede es terminar con un `OK`
    que se lee igual que el de un commit que si se midio.
    """
    repo = _repo_con_hook(tmp_path)
    _stagear(repo, "LEEME.md")

    salida = _correr(repo, tmp_path)

    assert _dice_que_no_ha_medido(salida), (
        "el hook paso sin decir que no habia nada que medir. Su salida:\n" + salida
    )


def test_con_bypass_dice_que_los_tests_se_omitieron(tmp_path: Path) -> None:
    """**EL SEGUNDO CAMINO SILENCIOSO.** Con `HOOK_SKIP_TESTS=1` no se corre nada.

    Es un bypass legitimo —el propio hook lo ofrece— pero offered no es lo mismo
    que visible: quien lea despues tiene que poder ver que el commit salio sin
    que se ejecutara un solo test.
    """
    repo = _repo_con_hook(tmp_path)
    _stagear(repo, "tests/test_algo.py")

    salida = _correr(repo, tmp_path, HOOK_SKIP_TESTS="1")

    assert "OMITIDOS" in salida, (
        "el hook paso en silencio con HOOK_SKIP_TESTS=1. Su salida:\n" + salida
    )


def test_con_smoke_corriendo_lo_dice_tambien(tmp_path: Path) -> None:
    """El camino que ya llevaba su anuncio, y que no debe perderlo.

    Es el contrasalto del contrasalto: si el arreglo se aplicase borrando el
    anuncio viejo en vez de anadir el nuevo, este test se pondria rojo.
    """
    repo = _repo_con_hook(tmp_path)
    _stagear(repo, "tests/test_algo.py")

    salida = _correr(repo, tmp_path)

    assert "smoke" in salida, f"el camino que corre tests dejo de anunciarlo:\n{salida}"
    assert "tests:" in salida, (
        f"el hook no cerro diciendo que ha medido, y el lector no puede "
        f"distinguirlo del camino silencioso:\n{salida}"
    )


def test_el_ok_cierra_despues_de_declarar_los_tests(tmp_path: Path) -> None:
    """**EL ORDEN, QUE TAMBIEN ES LA PROPIEDAD.**

    Decir «no he medido» por debajo de un `OK` no arregla nada: quien lee el
    scroll ve primero el `OK` —que es la senal de que todo fue bien— y la nota
    queda dos lineas mas abajo, ya fuera de la lectura. Un hook que declara al
    final de su salida lo que hizo es el que convierte el `OK` en algo
    distinguible; uno que declara antes vuelve a indistinguishable el `OK` de
    un commit medido de uno que no lo fue.

    Por eso este test mira las DOS ULTIMAS lineas, y no busca la cadena
    `tests:` por el output: una busqueda por el output no distingue «la
    declaracion precedes al OK» de «la declaracion va detras».
    """
    repo = _repo_con_hook(tmp_path)
    _stagear(repo, "LEEME.md")

    lineas = [linea for linea in _correr(repo, tmp_path).splitlines() if linea.strip()]

    assert lineas[-1] == "[pre-commit] OK", (
        f"la ultima linea del hook tiene que ser su OK, no otra cosa: {lineas[-1]!r}\n"
        + "\n".join(lineas)
    )
    assert lineas[-2].startswith("[pre-commit] tests:"), (
        "la declaracion sobre los tests tiene que ir pegada al OK, no antes de "
        f"la pantalla se llene de otra cosa: {lineas[-2]!r}\n" + "\n".join(lineas)
    )


def test_todos_los_caminos_dicen_algo_sobre_los_tests(tmp_path: Path) -> None:
    """**LA PROPIEDAD, Y NO UN CASO.**

    Tres entradas distintas —nada stageado, bypass, smoke— y las TRES tienen que
    decir algo sobre los tests. Es la forma de que anadir un cuarto camino al
    hook no vuelva a pasar en silencio sin que nada lo note.
    """
    casos = {
        "nada stageado": ((), {}),
        "bypass": (("tests/test_algo.py",), {"HOOK_SKIP_TESTS": "1"}),
        "smoke": (("tests/test_algo.py",), {}),
    }
    for nombre, (rutas, entorno) in casos.items():
        limpio = tmp_path / nombre.replace(" ", "_")
        limpio.mkdir()
        repo = _repo_con_hook(limpio)
        _stagear(repo, *rutas)
        salida = _correr(repo, limpio, **entorno)
        assert "tests:" in salida, (
            f"el camino «{nombre}» termina sin decir nada sobre los tests. "
            f"Un hook que se calla en un camino es un hook que parece verde "
            f"en ese camino.\n{salida}"
        )
