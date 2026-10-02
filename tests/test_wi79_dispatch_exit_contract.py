"""WI-79: el contrato "todo handler de la CLI devuelve un int" no lo fijaba NADIE.

Hallazgo de la investigacion retrospectiva (WI-79), sobre la clase de
falso exito que el goal prioriza: una operacion que devuelve OK sin
cumplir su objetivo.

`main()` termina en `sys.exit(main())`. Si un handler de la tabla
`_DISPATCH` devolviera `None` —porque su ultimo `return` se perdio, o
porque alguien escribio `return None` explicito, o porque el cuerpo cae
por el final— entonces `sys.exit(None)` es **exit code 0**: el operador
ve la ejecucion como correcta cuando el comando no cumplio nada. Es el
falso exito mas silencioso que puede tener este CLI, y no habia un
solo test que lo mirara.

Lo que se sabe, con el instrumento por delante:

1. `tests/test_wi57_dispatch_coverage.py` ya camina el arbol del parser y
   afirma que `_DISPATCH` cubre todos los comandos declarados. Eso fija
   la COMPLETITUD de la tabla, no la FORMA de lo que devuelve cada
   handler. Son invariantes distintas y la segunda no existia.
2. Un barrido AST sobre los 31 handlers reales encuentra 0 retornos que
   produzcan None. Pero ese 0 solo vale porque el escaner se valido con
   mutacion en las dos direcciones: con `return None` en
   `cmd_runs_budget` lo marca, sin la mutacion no marca nada.
3. La primera version del escaner era CIEGA justo a este caso: en AST
   `return None` es `Return(value=Constant(None))`, es decir un return
   CON expresion, y el escaner solo buscaba `return` a secas. Un
   resultado negativo de un instrumento ciego no es un resultado.

4. La red inicial (102 tests) NO cubria la rama `except FileNotFoundError`
   de `main`, y la mutacion que convierte su `return
   EXIT_PROJECT_NOT_FOUND` en `return EXIT_OK` se llevo sin que nada la
   notara. El test que la cubre se anadio despues, cuando esa mutacion
   fallo. Ver `test_file_not_found_is_translated_to_project_not_found`.

Por eso esta red no se limita a repetir el barrido: anade el oráculo
CONDUCTUAL, que es el que de verdad importa. `main([...])` se invoca de
verdad y se afirma que devuelve un `int` distinto de cero cuando el
comando falla. Si un handler empieza a devolver None, esto falla aunque
el AST siga verde.

AGENTS.md 1.2 (cada `code` `sg_*` se traduce a exit code) y 6.4 (un test
CLI que verifica el contrato externo: exit code + salida) .
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from skillgraph.cli import runner
from skillgraph.cli.runner import EXIT_BAD_NAME, EXIT_OK, EXIT_USAGE, main

# --- Instrumento: recorrido del AST de un handler ------------------------


def _own_nodes(fn: ast.AST) -> list[ast.AST]:
    """Nodos del cuerpo propio, sin bajar a funciones anidadas.

    Un `return` dentro de un closure o de un comprehension pertenece a
    otra funcion: no puede ser el `return` final de este handler.
    """
    out: list[ast.AST] = []
    stack: list[ast.AST] = list(getattr(fn, "body", []))
    while stack:
        node = stack.pop(0)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        out.append(node)
        stack[0:0] = list(ast.iter_child_nodes(node))
    return out


def _fn_ast(handler: object) -> ast.FunctionDef:
    """AST del handler, resuelto por su fichero real (no por nombre)."""
    fn = inspect.getsourcefile(handler)
    assert fn is not None, f"{handler!r} no tiene fichero fuente"
    tree = ast.parse(Path(fn).read_text(encoding="utf-8"), filename=fn)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == handler.__name__:
            return node
    raise AssertionError(f"no se encontro el AST de {handler!r} en {fn}")


def _returns_none(fn: ast.AST) -> list[int]:
    """Lineas de `return` que producen None.

    Cubre las DOS formas: `return` a secas (value is None) y `return
    None` explicito (value es Constant(None)). La segunda es la que se
    le escapaba al escaner original.
    """
    hits: list[int] = []
    for node in _own_nodes(fn):
        if not isinstance(node, ast.Return):
            continue
        if node.value is None or (
            isinstance(node.value, ast.Constant) and node.value.value is None
        ):
            hits.append(node.lineno)
    return hits


def _terminates(stmt: ast.stmt) -> bool:
    """Terminacion evidente del ultimo stmt de un cuerpo."""
    match stmt:
        case ast.Return() | ast.Raise():
            return True
        case ast.While(test=ast.Constant(value=True)):
            return True
        case ast.If():
            return bool(stmt.orelse) and _terminates(stmt.body[-1]) and _terminates(stmt.orelse[-1])
        case ast.Try():
            return all(_terminates(h.body[-1]) for h in stmt.handlers if h.body) and (
                not stmt.orelse or _terminates(stmt.orelse[-1])
            )
        case ast.With() | ast.For() | ast.AsyncFor() | ast.Match():
            return bool(stmt.body) and _terminates(stmt.body[-1])
        case _:
            return False


# --- Red estatica: la forma de los 31 handlers --------------------------


class TestDispatchReturnContract:
    """Invariante sobre TODOS los handlers de la tabla de dispatch."""

    def test_dispatch_table_is_not_empty(self) -> None:
        """Guarda de ceguera del propio test.

        Si la tabla de dispatch se vacia o se renombra, un barrido que
        "no encuentra nada" seria indistinguible de "no hay nada
        sospechoso". Este test falla en ese caso en vez de dejarlo pasar.
        """
        assert len(runner._DISPATCH) >= 30, f"solo {len(runner._DISPATCH)} handlers en _DISPATCH"
        assert callable(runner.cmd_init), "cmd_init deberia seguir siendo importable"

    @pytest.mark.parametrize("command", sorted(runner._DISPATCH, key=repr))
    def test_handler_is_annotated_int(self, command: str | tuple[str, str]) -> None:
        handler = runner._DISPATCH[command]
        # `from __future__ import annotations` (AGENTS 4.1) deja las
        # anotaciones como cadenas: sin eval_str se compararia el str
        # 'int' contra el tipo int y fallaria siempre.
        ann = inspect.get_annotations(handler, eval_str=True)
        assert ann.get("return") is int, (
            f"{handler.__name__} (dispatch {command!r}) no esta anotado -> int"
        )

    @pytest.mark.parametrize("command", sorted(runner._DISPATCH, key=repr))
    def test_handler_never_returns_none(self, command: str | tuple[str, str]) -> None:
        """Ningun `return` produce None: `sys.exit(None)` seria exit 0."""
        handler = runner._DISPATCH[command]
        hits = _returns_none(_fn_ast(handler))
        assert not hits, (
            f"{handler.__name__} (dispatch {command!r}) devuelve None en linea(s) {hits}"
        )

    @pytest.mark.parametrize("command", sorted(runner._DISPATCH, key=repr))
    def test_handler_body_terminates(self, command: str | tuple[str, str]) -> None:
        """El cuerpo no cae por el final (eso tambien devolveria None)."""
        handler = runner._DISPATCH[command]
        body = _fn_ast(handler).body
        assert body, f"{handler.__name__} (dispatch {command!r}) tiene cuerpo vacio"
        assert _terminates(body[-1]), (
            f"{handler.__name__} (dispatch {command!r}) termina en "
            f"{type(body[-1]).__name__} (linea {body[-1].lineno}): podria caer al final "
            "y devolver None"
        )

    def test_main_is_annotated_int(self) -> None:
        assert inspect.get_annotations(main, eval_str=True).get("return") is int


# --- Red conductual: el oracl que de verdad importa -----------------------


class TestMainReturnsInt:
    """`main` se invoca de verdad. Si devuelve None, el operador ve exit 0."""

    def test_version_returns_exit_ok(self) -> None:
        rc = main(["--version"])
        assert isinstance(rc, int), f"main devolvio {type(rc).__name__}, no int"
        assert rc == EXIT_OK

    def test_no_command_returns_exit_ok(self) -> None:
        rc = main([])
        assert isinstance(rc, int), f"main devolvio {type(rc).__name__}, no int"
        assert rc == EXIT_OK

    def test_unknown_command_returns_usage(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["no-existe"])
        assert isinstance(exc.value.code, int)
        assert exc.value.code != EXIT_OK
        assert "usage" in capsys.readouterr().err.lower()

    def test_argparse_error_is_the_canonical_usage_code(self) -> None:
        """`runs budget` sin `project`/`run_id`: argparse corta antes del handler.

        WI-88 (ADR-0016). Esta prueba consignaba el comportamiento as-built:
        argparse salia con 2 mientras `EXIT_USAGE` era 1, y fijaba el 2 a
        proposito. La consignacion era correcta sobre la contradiccion, pero
        estaba incompleta: 2 no era un numero libre, era `EXIT_BAD_NAME`, que
        `runner.py:131` devuelve vivo. Tres fallos sin relacion —un nombre
        invalido, un comando inexistente y un subcomando sin argumentos—
        devolvian el mismo numero, y un script no podia separarlos.

        Unificar NO era "un fix de test" como decia la nota anterior, sino
        lo que la nota daba por supuesto: que 2 no significaba nada. Ahora
        `EXIT_USAGE` es observable por fin y el 2 significa una sola cosa.
        """
        with pytest.raises(SystemExit) as exc:
            main(["runs", "budget"])
        assert isinstance(exc.value.code, int)
        assert exc.value.code == EXIT_USAGE, (
            "argparse debe salir con EXIT_USAGE; si vuelve a 2, el 2 ha "
            "vuelto a colisionar con EXIT_BAD_NAME y hay que revisar ADR-0016"
        )
        assert exc.value.code != EXIT_BAD_NAME
        assert exc.value.code != EXIT_OK

    def test_failed_subcommand_does_not_report_success(self, tmp_path: Path) -> None:
        """El caso de falso exito por excelencia.

        Un `runs budget` contra un proyecto que no existe NO puede
        devolver 0. Si un handler devolviera None, este test falla.
        """
        data_root = tmp_path / "data"
        rc = main(
            [
                "--data-root",
                str(data_root),
                "runs",
                "budget",
                "no-existe",
                "r1",
            ]
        )
        assert isinstance(rc, int), (
            f"main devolvio {type(rc).__name__} en vez de int: "
            "sys.exit(None) se traduciria a exit code 0 (falso exito)"
        )
        assert rc != EXIT_OK, (
            f"runs budget sobre un proyecto inexistente devolvio {rc}: "
            "el comando fallo pero reporta exito"
        )

    def test_skillgraph_error_is_translated_to_exit_domain(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AGENTS 1.2: un `sg_*` produce exit code, nunca stack trace ni 0.

        Se sustituye `_resolve_handler` y no la entrada de `_DISPATCH`
        porque la tabla es un `MappingProxyType` (inmutable): el fallo de
        un handler se comprueba por la frontera de `main`, que es donde
        ocurre la traduccion.
        """
        from skillgraph.core.errors import NotFoundError

        def _boom(_args: object) -> int:
            raise NotFoundError("no existe")

        monkeypatch.setattr(runner, "_resolve_handler", lambda args: _boom)
        rc = main(["--data-root", str(tmp_path / "data"), "runs", "show", "no-existe", "r1"])

        err = capsys.readouterr().err
        assert isinstance(rc, int), f"main devolvio {type(rc).__name__}, no int"
        assert rc == runner.EXIT_DOMAIN
        assert "sg_not_found" in err, f"el codigo estable no llego a stderr: {err!r}"

    def test_file_not_found_is_translated_to_project_not_found(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """La rama `except FileNotFoundError` de `main` tiene su propio contrato.

        No es la misma rama que el error de dominio: `_open_known_project`
        lanza `FileNotFoundError` cuando el proyecto no existe, y `main`
        lo traduce a `EXIT_PROJECT_NOT_FOUND` (4) en vez de dejar que
        escape como traceback.

        Esta rama estaba sin oraculo: la mutacion que convierte ese
        `return EXIT_PROJECT_NOT_FOUND` en `return EXIT_OK` no la caza
        ningun test de esta red, porque `runs budget` con proyecto
        inexistente no pasa por aqui (resuelve el proyecto antes y
        devuelve su codigo). El fallo se iria a exit 0, y no habia quien
        lo notara.
        """

        def _boom(_args: object) -> int:
            raise FileNotFoundError("proyecto inexistente")

        monkeypatch.setattr(runner, "_resolve_handler", lambda args: _boom)
        rc = main(["--data-root", str(tmp_path / "data"), "runs", "show", "no-existe", "r1"])

        err = capsys.readouterr().err
        assert isinstance(rc, int), f"main devolvio {type(rc).__name__}, no int"
        assert rc == runner.EXIT_PROJECT_NOT_FOUND
        assert rc != EXIT_OK, "un proyecto inexistente no puede reportarse como exito"
        assert "proyecto inexistente" in err, f"el mensaje no llego a stderr: {err!r}"
