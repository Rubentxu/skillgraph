"""La medicion que abre B36 — un guard que no puede pasar por la puerta que vigila.

`tests/test_wi116_suelos_de_cobertura.py::TestElHarnessNoBorraTrabajo` afirma que
el arbol de trabajo no tiene nada sin commitear entre `src/` y `scripts/`: corre
`git status --porcelain -- src scripts` y exige vacio.

El hook de pre-commit corre `pytest -q` SOBRE LOS FICHEROS STAGEAD. Luego, en
todo commit que toque `src/` o `scripts/` y ademas stagee ese test, el guard ve
stageado justo lo que se va a commitear, y se pone rojo.

Cada ronda mide una parte y NO afirma nada que no medido: si un numero no sale
de aqui, no va a la evidencia. Nada de listas escritas a mano — el conjunto se
deriva del arbol.

Ejecutar:  uv run python scripts/measure_b36_commit_gate.py
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys
import tempfile
from collections.abc import Iterator

RAIZ = pathlib.Path(__file__).resolve().parent.parent
TESTS = RAIZ / "tests"
SCRIPTS = RAIZ / "scripts"
HOOK = RAIZ / "scripts" / "hooks" / "pre-commit"

#: El test que mira el estado del arbol. NO es una lista de "sitios donde lo
#: vimos": sale del arbol, buscando el test que consulta `git status`.
GUARD = "test_el_arbol_no_tiene_nada_sin_commitear_entre_scripts_y_src"

#: Subcomandos de git que devuelven ficheros a otro estado y por tanto pueden
#: destruir trabajo no commitado. Se reconocen por la PALABRA que se invoca,
#: no por una lista de ficheros donde lo vimos.
PALABRAS_DESTRUCTIVAS = frozenset({"checkout", "restore", "reset", "clean", "stash"})

#: El binario que hace que una lista de argumentos sea una llamada a git.
BINARIOS_GIT = frozenset({"git"})

#: Directorios cuyo `.py` NO es codigo de este repo. Ver la nota de `modulos`:
#: sin esto el derivado conta dulwich y urllib3.
EXCLUIDOS = frozenset(
    {"__pycache__", "node_modules", "site-packages", "external", ".pipelinek", ".venv"}
)

if not (RAIZ / ".git").exists():
    # MEDIDO, y por casi pasa: este instrumento, ejecutado desde /tmp, midi
    # `0` harnesses, `0` commits y `(el guard no esta en el arbol)` — y todo
    # era verdad, porque estaba mirando `/`. Una medicion que reporta cero sin
    # quejarse es indistinguible de una que mide. Este abort avisa.
    raise SystemExit(
        f"RAIZ no es el repositorio: {RAIZ}\n"
        "Este script vive en scripts/ y deriva la raiz de donde esta. "
        "Ejecutalo desde scripts/, no desde /tmp."
    )


def modulos(raiz: pathlib.Path) -> Iterator[pathlib.Path]:
    """Todo `.py` bajo `raiz`, en orden estable, menos lo que NO es codigo de este repo.

    **MEDIDO, Y LA PRIMERA VERSION DE ESTA FUNCION MENTIA.** Sin el filtro,
    recorrer el arbol entero devolvia 34 falsos positivos:
    `.pipelinek/wi99_bundle/skillgraph-*.venv/lib/python3.13/site-packages/dulwich/...`
    y `urllib3` — que no son codigo de este repo sino codigo de terceros, y
    ademas una COPIA VENDORIZADA del propio repo dentro de un bundle. Un guard
    derivado de ahi no vigila nada: mide la biblioteca de otro.
    """
    return sorted(
        p
        for p in raiz.rglob("*.py")
        if not any(parte in EXCLUIDOS or parte == "__pycache__" for parte in p.parts)
    )


def fichero_del_guard() -> pathlib.Path | None:
    """El fichero que REALMENTE define el test, derivado por AST."""
    for candidato in modulos(TESTS):
        try:
            arbol = ast.parse(candidato.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.FunctionDef) and nodo.name == GUARD:
                return candidato
    return None


def llama_a_palabra(fichero: pathlib.Path, palabras: frozenset[str]) -> list[tuple[int, str]]:
    """Lineas donde el script LLAMA a `git <destructivo>` como COMANDO.

    **MEDIDO, Y LA PRIMERA VERSION DE ESTE RASTREO MENTIA.** Buscaba la palabra
    suelta dentro de cualquier literal, luego contaba como llamada ESTO:

        print("RONDA 2 — QUE ESTADO DESTRUYE `git checkout --`")

    que es PROSA, y ademas la prosa de este mismo fichero. Un docstring que
    explica el comando no lo ejecuta. Es la **quinta** vez que sale este
    defecto en el repo — el guard de B15, el de WI-92, el de B34 con su sonda
    M10, y las dos primeras versiones de hoy — y por eso aqui se exige la FORMA:
    una lista de argumentos donde el binario de git va seguido del verbo.

    `subprocess.run(["git", "checkout", "--", "x"])` cuenta.
    `print("... git checkout ...")` no.
    """
    try:
        arbol = ast.parse(fichero.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    hallados: list[tuple[int, str]] = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call) or not nodo.args:
            continue
        lista = nodo.args[0]
        if not isinstance(lista, (ast.List, ast.Tuple)):
            continue
        elementos = [
            e.value for e in lista.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)
        ]
        if not (BINARIOS_GIT & set(elementos)):
            continue
        for indice, palabra in enumerate(elementos):
            if palabra in palabras and any(b in BINARIOS_GIT for b in elementos[:indice]):
                hallados.append((nodo.lineno, " ".join(elementos[: indice + 1])))
                break
    return hallados


def git(*args: str, cwd: pathlib.Path) -> str:
    proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=False)
    return proc.stdout


def sep(titulo: str) -> None:
    print()
    print(titulo)


def repo_de_prueba(destino: pathlib.Path) -> pathlib.Path:
    raiz = destino / "repo"
    (raiz / "src").mkdir(parents=True)
    (raiz / "src" / "a.py").write_text("uno\n", encoding="utf-8")
    git("init", "-q", cwd=raiz)
    git("config", "user.email", "p@p", cwd=raiz)
    git("config", "user.name", "p", cwd=raiz)
    git("add", "-A", cwd=raiz)
    git("commit", "-qm", "base", cwd=raiz)
    return raiz


def ronda_1() -> None:
    """¿Que ve el guard cuando alguien commitea?"""
    sep("RONDA 1 — QUE VE EL GUARD")
    with tempfile.TemporaryDirectory() as tmp:
        raiz = repo_de_prueba(pathlib.Path(tmp))
        print(
            f"    arbol limpio                     -> {git('status', '--porcelain', '--', 'src', cwd=raiz).strip()!r}"
        )
        (raiz / "src" / "a.py").write_text("uno-bis\n", encoding="utf-8")
        git("add", "src/a.py", cwd=raiz)
        print(
            f"    cambio STAGEADO (lo de un commit) -> {git('status', '--porcelain', '--', 'src', cwd=raiz).strip()!r}"
        )
        git("reset", "-q", "HEAD", "src/a.py", cwd=raiz)
        print(
            f"    cambio SIN stagear               -> {git('status', '--porcelain', '--', 'src', cwd=raiz).strip()!r}"
        )


def ronda_2() -> None:
    """¿Cual de los dos estados es el peligroso de verdad?"""
    sep("RONDA 2 — QUE ESTADO DESTRUYE `git checkout --`")
    with tempfile.TemporaryDirectory() as tmp:
        raiz = repo_de_prueba(pathlib.Path(tmp))
        (raiz / "src" / "a.py").write_text("sin stagear\n", encoding="utf-8")
        git("checkout", "--", "src", cwd=raiz)
        print(
            f"    SIN stagear + checkout -> {(raiz / 'src' / 'a.py').read_text(encoding='utf-8').strip()!r}  DESTRUIDO"
        )
        (raiz / "src" / "a.py").write_text("stageado\n", encoding="utf-8")
        git("add", "src/a.py", cwd=raiz)
        git("checkout", "--", "src", cwd=raiz)
        print(
            f"    STAGEADO     + checkout -> {(raiz / 'src' / 'a.py').read_text(encoding='utf-8').strip()!r}  sobrevive"
        )


def ronda_3() -> None:
    """¿Quien queda vigilado: los instrumentos o el operador?"""
    sep("RONDA 3 — DONDE VIVE EL RIESGO DE VERDAD")
    for etiqueta, raiz in (("scripts/", SCRIPTS), ("todo el repo", RAIZ)):
        modulos_ = [p for p in modulos(raiz) if p.suffix == ".py"]
        con = [(p, h) for p in modulos_ if (h := llama_a_palabra(p, PALABRAS_DESTRUCTIVAS))]
        print(f"    {etiqueta:<14} .py:{len(modulos_):<4} con git destructivo: {len(con)}")
        for fichero, hallados in con:
            for num, llamada in hallados:
                print(f"      {fichero.relative_to(RAIZ)}:{num}  {llamada}")
    print(
        "    OJO con la segunda cifra: `tests/` construye repos TEMPORALES para\n"
        "    probar que una sonda restaura bien. Un guard derivado de TODO el repo\n"
        "    las contaria de mas, y ese falso positivo es el que decide el alcance.\n"
    )


def ronda_4() -> None:
    """¿Cuantos commits del repo han cruzado las dos puertas?"""
    sep("RONDA 4 — EL CRUCE, CONTADO SOBRE EL HISTORIAL")
    guard = fichero_del_guard()
    if guard is None:
        print("    (el guard no esta en el arbol)")
        return
    relativo = guard.relative_to(RAIZ).as_posix()
    print(f"    el guard vive en                 : {relativo}")

    commits = [c for c in git("rev-list", "HEAD", cwd=RAIZ).split() if c]
    con_py = tocan_codigo = 0
    cruzan: list[str] = []
    for commit in commits:
        ficheros = git("show", "--name-only", "--format=", commit, cwd=RAIZ).splitlines()
        py = [f for f in ficheros if f.endswith(".py")]
        if not py:
            continue
        con_py += 1
        toca = any(f.startswith(("src/", "scripts/")) for f in py)
        tocan_codigo += toca
        if toca and relativo in py:
            cruzan.append(commit)

    print(f"    commits del repo                   : {len(commits)}")
    print(f"    commits con .py stageado            : {con_py}")
    print(f"    commits que tocan src/ o scripts/  : {tocan_codigo}")
    print(f"    commits que CRUZAN las dos puertas : {len(cruzan)}")
    for commit in cruzan[:5]:
        print(f"      {git('log', '-1', '--format=%h %s', commit, cwd=RAIZ).strip()}")


def ronda_5() -> None:
    """¿Que apaga de verdad el bypass que el hook ofrece?"""
    sep("RONDA 5 — QUE SE APAGA CON HOOK_SKIP_TESTS=1")
    if not HOOK.exists():
        print("    (no hay scripts/hooks/pre-commit)")
        return
    lineas = HOOK.read_text(encoding="utf-8").splitlines()
    # **MEDIDO, Y LA PRIMERA VERSION DE ESTO MENTIA.** Filtraba las etapas que
    # redirigen su salida (`and ">" not in linea`), y eso excluia JUSTO la etapa
    # que se apaga: `pytest -q $STAGED_PY >"$PYTEST_LOG"`. La ronda decia
    # «se apagan 0, siguen corriendo 2», que es exactamente lo contrario de lo
    # que hace el hook. Un instrumento que se contradice con el fichero que
    # mide no mide: hay que mirarlo antes de escribir el veredicto.
    etapas = [
        (i + 1, linea.strip()) for i, linea in enumerate(lineas) if "run_in_toolchain run " in linea
    ]

    # El rango de la condicion se DERIVA: se busca el `if` que consulta la
    # variable y su `fi` pareja por sangria. No se escribe el rango a mano.
    rango: tuple[int, int] | None = None
    for i, linea in enumerate(lineas):
        if "HOOK_SKIP_TESTS" in linea and linea.strip().startswith("if "):
            sangria = len(linea) - len(linea.lstrip())
            for j in range(i + 1, len(lineas)):
                if (
                    lineas[j].strip() == "fi"
                    and len(lineas[j]) - len(lineas[j].lstrip()) == sangria
                ):
                    rango = (i + 1, j + 1)
                    break
            break

    print(f"    etapas que ejecutan la toolchain   : {len(etapas)}")
    dentro = fuera = 0
    for num, etapa in etapas:
        if rango and rango[0] < num < rango[1]:
            dentro += 1
            veredicto = "SE APAGA con HOOK_SKIP_TESTS=1"
        else:
            fuera += 1
            veredicto = "corre SIEMPRE"
        print(f"      {num:>3}  {etapa}  ->  {veredicto}")
    print(f"    rango de la condicion              : {rango}")
    print(f"    se apagan {dentro}, siguen corriendo {fuera}")


def main() -> None:
    print("B36 — un guard que no puede pasar por la puerta que vigila")
    print(f"raiz: {RAIZ}   python: {sys.version.split()[0]}")
    ronda_1()
    ronda_2()
    ronda_3()
    ronda_4()
    ronda_5()
    print()
    print("CONCLUSION, y es una eleccion con dos respuestas posibles:")
    print("  (A) corregir el ALCANCE del guard: que no mire lo que ya esta en el")
    print("      indice, que es lo unico que un `git checkout --` no puede tocar;")
    print("  (B) SUSTITUIRLO por una guarda derivada del arbol que diga que ningun")
    print("      instrumento puede ejecutar git destructivo.")
    print("Miden cosas distintas. La que se puede decidir con sondas es (B);")
    print("(A) se decide leyendo el codigo del guard y la ronda 2.")


if __name__ == "__main__":
    main()
