"""WI-109: el `code` `sg_*` debe ser la clave con la que la CLI traduce a exit code.

AGENTS.md 1.2, tercera viñeta, dice literalmente:

    "Cada excepcion lleva un `code` estable (`sg_*`) usado por la CLI para
     traducir a exit codes."

La medicion (`.pipelinek/wi109_measure.py`, `wi109_exp.py`) encontro tres
cosas distintas, y este fichero vigila las tres:

  1. La traduccion NO EXISTIA. `runner.main` hacia
     `except SkillGraphError -> return EXIT_DOMAIN` (10) para todo, y el
     `code` solo se imprimia. EXIT_PARSE y EXIT_VALIDATION se alcanzaban
     por `except ParseError` explicito en el sitio de la llamada: la
     decision la tomaba el TIPO, no el `code`.

  2. `knowledge compile` con una recipe JSON malformada escapaba como
     Traceback con rc=1 de Python, porque `json.loads(args.recipe)` esta
     FUERA del `try` y `JSONDecodeError` no es `SkillGraphError`.

  3. Dos `code` no identificaban un error: `sg_error` lo compartian tres
     clases y `sg_invalid_expansion` dos. Un `code` compartido no puede
     mapear a un exit code distinto, asi que la traduccion no se podia
     construir encima de el.

Este guard mira el COMPORTAMIENTO (que rc sale, que se imprime), no una
copia de la verdad. Un guard que compara contra su propia copia de la
tabla no vigila nada: la tabla es la que se somete a prueba aqui.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SRC = RAIZ / "src" / "skillgraph"

# Los codigos que la CLI puede emitir y su exit code. Es una copia DEL
# contrato externo, no del mecanismo: el mecanismo se prueba debajo.
# Si esta tabla queda vieja, el guard falla aqui, que es lo que se quiere.


# ---------------------------------------------------------------------------
# 1. La traduccion existe y es PURA
# ---------------------------------------------------------------------------


def test_la_traduccion_existe_y_es_una_funcion() -> None:
    """`exit_para` debe existir en el modulo hoja de exit codes.

    Vive en `exit_codes.py` y no en `runner.py` a proposito: ADR-0016
    movio los codigos a un modulo SIN IMPORTS para que `parser.py` pueda
    consumir el contrato sin arrastrar `Storage`, `pack_loader` y demas.
    Una traduccion que viviera en `runner.py` seria inalcanzable desde
    ahi, y volveria a colisionar con el 2 de `argparse`.
    """
    from skillgraph.cli import exit_codes

    assert hasattr(exit_codes, "exit_para"), (
        "exit_codes.py debe exponer `exit_para`: es la traduccion que 1.2 promete"
    )


def test_la_traduccion_es_pura_sobre_el_code() -> None:
    """La traduccion depende SOLO del `code`, no de la clase ni del estado.

    Es la propiedad que hace que el `code` sea la clave: dos errores con el
    mismo `code` tienen el mismo exit code, y uno solo puede ser la clave
    de una tabla si la funcion no mira nada mas.
    """
    from skillgraph.cli.exit_codes import exit_para

    class _Falso:
        def __init__(self, code: str) -> None:
            self.code = code

    a = exit_para(_Falso("sg_parse"))
    b = exit_para(_Falso("sg_parse"))
    assert a == b, "la traduccion no puede depender del estado de la excepcion"


def test_la_traduccion_no_puede_depender_de_la_clase() -> None:
    """Dos clases DISTINTAS con el mismo `code` dan el mismo exit code.

    Esta es la propiedad que hace imposible el defecto medido en M4: si la
    traduccion mirase la clase, dos clases que comparten `code` podrian
    salir distinto, y entonces el `code` no seria la clave.
    """
    from skillgraph.cli.exit_codes import exit_para

    class _A:
        code = "sg_error"

    class _B:
        code = "sg_error"

    assert exit_para(_A()) == exit_para(_B())


# ---------------------------------------------------------------------------
# 2. Los codes que la traduccion necesita, uno a uno
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "esperado"),
    [
        ("sg_parse", 11),
        ("sg_validation", 12),
    ],
)
def test_cada_code_mapea_a_su_exit_code(code: str, esperado: int) -> None:
    """`sg_parse`->11 y `sg_validation`->12, que es el contrato documentado.

    Estos son los dos casos que la medicion comprobo que el runner
    resolvia por TIPO y no por `code`. Ahora los resuelve el `code`.
    """
    from skillgraph.cli.exit_codes import exit_para

    class _Falso:
        pass

    exc = _Falso()
    exc.code = code
    assert exit_para(exc) == esperado


def test_un_code_desconocido_cae_en_el_catch_all_de_dominio() -> None:
    """Un `code` que la tabla no conoce devuelve EXIT_DOMAIN, no 0.

    Que caiga en 10 y no en 0 importa: un exit code 0 significa exito, y
    un error de dominio que sale con 0 es peor que uno que sale con 10.
    """
    from skillgraph.cli import exit_codes

    class _Falso:
        code = "sg_code_del_futuro"

    assert exit_codes.exit_para(_Falso()) == exit_codes.EXIT_DOMAIN


def test_una_excepcion_sin_code_no_revienta_la_traduccion() -> None:
    """Una excepcion sin atributo `code` tambien cae en EXIT_DOMAIN.

    `main()` captura `FileNotFoundError`, que no tiene `code`. La
    traduccion tiene que sobrevivir a eso sin lanzar AttributeError: un
    fallo al traducir un fallo es el peor de los dos mundos.
    """
    from skillgraph.cli import exit_codes

    assert exit_codes.exit_para(FileNotFoundError("no existe")) == exit_codes.EXIT_DOMAIN


# ---------------------------------------------------------------------------
# 3. La traduccion esta cableada donde se usa
# ---------------------------------------------------------------------------


def test_main_usa_la_traduccion_y_no_el_catch_all_a_pelo() -> None:
    """`main()` debe delegar en `exit_para`, no devolver EXIT_DOMAIN a pelo.

    Sin esto la traduccion existiria pero nadie la usaria, que es
    exactamente el estado en que estaba la regla antes de WI-109: el
    `code` existia, era unico casi todo, y no traducia nada.

    Se mira el AST y no el texto: buscar la cadena `return EXIT_DOMAIN`
    encuentra la del COMENTARIO que explica por que se sustituyo, que es
    precisamente el falso positivo que hizo inutilizable la primera
    version de este test. La propiedad es «no hay un return con ese
    valor», y el AST es donde se expresa (AGENTS.md 6.2).
    """
    ruta = SRC / "cli" / "runner.py"
    arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
    cuerpo_main = next(
        n for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef) and n.name == "main"
    )

    usa_traduccion = any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "exit_para"
        for n in ast.walk(cuerpo_main)
    )
    assert usa_traduccion, "main() debe llamar a exit_para(exc)"

    # Ningun `return` de main() puede devolver EXIT_DOMAIN por la via
    # del catch-all: debe pasar por exit_para.
    returns_directos = [
        n
        for n in ast.walk(cuerpo_main)
        if isinstance(n, ast.Return)
        and n.value is not None
        and ast.unparse(n.value) == "EXIT_DOMAIN"
    ]
    assert not returns_directos, (
        f"main() sigue devolviendo EXIT_DOMAIN a pelo en la linea "
        f"{returns_directos[0].lineno if returns_directos else '?'}: "
        "la traduccion no esta cableada."
    )


# ---------------------------------------------------------------------------
# 4. El defecto observable: recipe malformada sale con traceback
# ---------------------------------------------------------------------------


def _cli(args: list[str], data_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "skillgraph", "--data-root", str(data_root), *args],
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.fixture
def proyecto(tmp_path: Path) -> str:
    """Proyecto real en un data root aislado, para no tocar el del operador."""
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "skillgraph",
            "--data-root",
            str(tmp_path),
            "project",
            "create",
            "wi109",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stderr
    return "wi109"


def test_recipe_json_malformada_no_escapa_como_traceback(tmp_path: Path, proyecto: str) -> None:
    """C1: entrada de usuario malformada sale con codigo de dominio, no con traceback.

    Antes de WI-109 esto devolvia rc=1 con el Traceback completo de
    `json.JSONDecodeError` impreso en stderr, porque `json.loads` estaba
    fuera del `try` y `JSONDecodeError` no es `SkillGraphError`.
    """
    r = _cli(["knowledge", "compile", proyecto, '{"obligatory": ['], tmp_path)

    assert "Traceback" not in r.stderr, (
        f"un error de entrada de usuario no puede salir como Traceback.\n{r.stderr}"
    )
    assert r.returncode != 1 or "usage:" not in r.stderr, (
        f"rc=1 es el codigo de error de uso, no de dominio.\n{r.stderr}"
    )


def test_recipe_json_malformada_reporta_el_code_del_error(tmp_path: Path, proyecto: str) -> None:
    """El mensaje nombra el `code` que produjo el fallo, como los demas.

    `main()` imprime `ERROR (<code>): <mensaje>`. Si la conversion no
    produce un `SkillGraphError` con `code`, el usuario no tiene ningun
    identificador estable con el que buscar el problema.
    """
    r = _cli(["knowledge", "compile", proyecto, '{"obligatory": ['], tmp_path)
    assert "ERROR (sg_" in r.stderr, (
        f"el error de dominio debe reportar su code.\nstdout={r.stdout!r}\nstderr={r.stderr!r}"
    )


def test_recipe_valida_sigue_funcionando(tmp_path: Path, proyecto: str) -> None:
    """El arreglo no rompe el camino bueno.

    Un guard que solo mira el camino de error puede pasar mientras todo
    lo demas esta roto. Este test mira que la entrada valida sigue
    dando el mismo comportamiento.
    """
    r = _cli(["knowledge", "compile", proyecto, "src-inexistente"], tmp_path)
    # La receta es valida: el fallo, si lo hay, es de dominio y no de parseo.
    assert "Traceback" not in r.stderr, r.stderr


# ---------------------------------------------------------------------------
# 5. La propiedad estructural: ningun parseo de entrada sin proteccion
# ---------------------------------------------------------------------------


def _parseos_de_json_en_cli() -> list[tuple[Path, int, str]]:
    """Localiza los `json.loads(...)` que hay en `src/skillgraph/cli/`.

    El `filename` se pasa por palabra clave a proposito: el segundo
    parametro posicional de `ast.parse` es `filename`, y pasarlo
    posicionalmente hace que el nombre de un fichero sea el codigo a
    parsear. Falla de forma ruidosa, que es mejor que en silencio.
    """
    hallazgos: list[tuple[Path, int, str]] = []
    for p in sorted((SRC / "cli").rglob("*.py")):
        arbol = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        for nodo in ast.walk(arbol):
            if (
                isinstance(nodo, ast.Call)
                and isinstance(nodo.func, ast.Attribute)
                and nodo.func.attr == "loads"
                and isinstance(nodo.func.value, ast.Name)
                and nodo.func.value.id in {"json", "_json"}
            ):
                hallazgos.append((p, nodo.lineno, ast.unparse(nodo.args[0]) if nodo.args else ""))
    return hallazgos


def test_hay_parseos_de_json_que_este_guard_vigila() -> None:
    """Contraejemplo del propio guard: si no viera nada, pasaria en verde.

    Sin esta asercion, un guard que degrada a "no encuentra nada" es
    indistinguible de un guard que funciona. Un guard que solo sabe pasar
    no esta probado (AGENTS.md 6.2).
    """
    hallazgos = _parseos_de_json_en_cli()
    assert len(hallazgos) >= 2, (
        f"el guard deberia ver al menos 2 parseos de json en la CLI, ve {len(hallazgos)}. "
        "Si esto falla, el AST cambio y el guard ha dejado de medir."
    )


def test_todo_parseo_de_entrada_de_usuario_esta_protegido() -> None:
    """C4 (parte estructural): cada `json.loads` de la CLI esta dentro de un `try`.

    De los parseos que hay hoy, los que ya tenian `try` se dejan como
    estan; los que no, son el defecto. Este test falla si alguien anade
    un `json.loads` nuevo fuera de proteccion.
    """
    desprotegidos: list[str] = []
    for p in sorted((SRC / "cli").rglob("*.py")):
        arbol = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        # Recorrer FUNCIONES: un parseo a nivel de modulo tampoco vale.
        for fn in [n for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef)]:
            try_visitados: set[int] = set()
            for stmt in fn.body:
                for sub in ast.walk(stmt):
                    if isinstance(sub, ast.Try):
                        for hijo in ast.walk(sub):
                            try_visitados.add(id(hijo))
            for stmt in fn.body:
                for sub in ast.walk(stmt):
                    if (
                        isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Attribute)
                        and sub.func.attr == "loads"
                        and isinstance(sub.func.value, ast.Name)
                        and sub.func.value.id in {"json", "_json"}
                    ):
                        # Solo los que leen ENTRADA (args.* o un parametro),
                        # no los que leen un fichero ya persistido.
                        txt = ast.unparse(sub.args[0]) if sub.args else ""
                        es_entrada = "args." in txt or "plan_path" in txt or "args" in txt
                        if es_entrada and id(sub) not in try_visitados:
                            rel = p.relative_to(RAIZ)
                            desprotegidos.append(f"{rel}:{sub.lineno}  json.loads({txt})")

    assert not desprotegidos, (
        "parseo de entrada de usuario sin `try`:\n  "
        + "\n  ".join(desprotegidos)
        + "\nUn JSON malformado debe salir con codigo de dominio, no como Traceback."
    )


# ---------------------------------------------------------------------------
# 6. La regla dice COMO se comprueba
# ---------------------------------------------------------------------------


def test_la_regla_dice_como_se_comprueba() -> None:
    """`AGENTS.md 1.2` debe decir donde vive el guard, como hizo 6.2.

    Una regla que no dice como se comprueba es la que produce los
    workitems WI-107 a WI-109: nadie la mira porque nadie sabe que
    mirarla es un trabajo automatizable.
    """
    texto = (RAIZ / "AGENTS.md").read_text(encoding="utf-8")
    seccion = texto.split("### 1.2", 1)[1].split("### 1.3", 1)[0]
    assert "test_wi109" in seccion, (
        "1.2 debe nombrar el fichero de tests que la vigila, como hace 6.2 con 6.3"
    )


# ---------------------------------------------------------------------------
# 7. C3: el `code` identifica un error (M4 de la medicion)
# ---------------------------------------------------------------------------


def _clases_de_error_de_dominio() -> dict[str, type[Exception]]:
    """Todas las clases `SkillGraphError` alcanzables, por import real.

    Se importa el paquete entero en vez de leer el AST: la propiedad que
    importa es la del `code` EFECTIVO, que es el que ve el usuario, y ese
    sale de la jerarquia de clases, no del texto fuente.
    """
    import importlib
    import inspect
    import pkgutil

    import skillgraph
    from skillgraph.core.errors import SkillGraphError

    clases: dict[str, type[Exception]] = {}
    for nombre in pkgutil.walk_packages(skillgraph.__path__, "skillgraph."):
        try:
            mod = importlib.import_module(nombre.name)
        except Exception:
            continue
        for _n, obj in vars(mod).items():
            if (
                inspect.isclass(obj)
                and issubclass(obj, SkillGraphError)
                and obj.__module__.startswith("skillgraph")
            ):
                clases[obj.__qualname__] = obj
    return clases


def test_la_medida_no_ve_ninguna_clase() -> None:
    """Contraejemplo del contador: si no viera clases, los otros tests de
    la seccion pasarian en verde sin comprobar nada.
    """
    clases = _clases_de_error_de_dominio()
    assert len(clases) >= 25, (
        f"se esperaban >=25 clases de error de dominio, hay {len(clases)}. "
        "Si esto falla, el import del paquete cambio y el guard dejo de medir."
    )


def test_cada_error_de_dominio_declara_su_propio_code() -> None:
    """Ninguna clase de §1.2 hereda el `code` de su padre.

    M4 de la medicion: `sg_error` lo compartian tres clases y
    `sg_invalid_expansion` dos. Un `code` heredado no identifica el
    error, que es justo la mitad del contrato de 1.2.
    """
    sin_code = [
        nombre
        for nombre, cls in _clases_de_error_de_dominio().items()
        if "code" not in cls.__dict__
    ]
    assert not sin_code, "clases de dominio sin `code` propio (lo heredan):\n  " + "\n  ".join(
        sorted(sin_code)
    )


def test_ningun_code_comparte_clase() -> None:
    """C3: cada `code` pertenece a una sola clase de error.

    Esta es la propiedad que hace construible la traduccion: si dos
    errores comparten `code`, no pueden salir con exit codes distintos,
    y entonces el `code` deja de ser la clave.
    """
    from collections import defaultdict

    por_code: dict[str, list[str]] = defaultdict(list)
    for nombre, cls in _clases_de_error_de_dominio().items():
        por_code[cls.code].append(nombre)

    compartidos = {c: ns for c, ns in por_code.items() if len(ns) > 1}
    assert not compartidos, "codes que no identifican un error:\n" + "\n".join(
        f"  {c!r} -> {sorted(ns)}" for c, ns in sorted(compartidos.items())
    )


def test_todo_code_empieza_por_sg() -> None:
    """El prefijo `sg_` es parte del contrato (§1.2) y de la convencion."""
    malos = [
        f"{nombre} -> {cls.code!r}"
        for nombre, cls in _clases_de_error_de_dominio().items()
        if not cls.code.startswith("sg_")
    ]
    assert not malos, "codes sin prefijo sg_:\n  " + "\n  ".join(sorted(malos))


def test_la_medida_de_colisiones_detecta_el_defecto() -> None:
    """La comprobacion anterior debe FALLAR si se reintroduce una colision.

    Sin esto, `test_ningun_code_comparte_clase` pasaria igual de verde
    con la tabla de `por_code` rota. Un guard que solo sabe pasar no
    esta probado.
    """
    from collections import defaultdict

    por_code: dict[str, list[str]] = defaultdict(list)
    for nombre, cls in _clases_de_error_de_dominio().items():
        por_code[cls.code].append(nombre)

    # Dos clases que hoy NO comparten code, unidas a proposito.
    clases = _clases_de_error_de_dominio()
    pares = [(a, b) for a in clases for b in clases if a < b and clases[a].code != clases[b].code]
    assert pares, "el universo de clases es demasiado pequeno para la contraejemplo"

    a, b = pares[0]
    inyectado: dict[str, list[str]] = defaultdict(list, {k: list(v) for k, v in por_code.items()})
    inyectado[clases[a].code] = [a, b]
    compartidos = {c: ns for c, ns in inyectado.items() if len(ns) > 1}
    assert compartidos, (
        "la comprobacion de colisiones no degrada: con dos clases de code "
        f"distinto ({a!r}, {b!r}) unidas, deberia detectar la colision y no la detecta"
    )
