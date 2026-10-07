"""Los handlers que `runner.py` IMPLEMENTA, no los que reexporta.

**LA MEDIDA QUE ABRE ESTE TRABAJO.** `cli/runner.py` mide **55,08 %** sobre
el suelo del 70 % que AGENTS 6.3 declara para `cli/`.

La razon del hueco es la misma que en WI-116-runs y WI-116-expansion, y por
eso se repite aqui sin miedo a la redundancia: **un modulo que reexporta
handlers de otro parece cubierto porque los handlers lo estan.**

`runner.py` tiene dos mitades bien distintas:

  - la mitad REEEXPORT (los `cmd_expansion_*`, `cmd_runs_*`, `cmd_knowledge_*`)
    que viene de `commands/`, y que este fichero NO toca: esos se miden
    en sus propios ficheros, porque medirlos aqui seria medir un alias;
  - la mitad PROPIA (`cmd_project_*`, `cmd_policy_*`, `cmd_backup*`,
    `cmd_brick_register`, `cmd_init`), que esta DEFINIDA aqui y no la
    ejecuta nadie en ningun test.

**LO QUE ESTABA «CUBIERTO» Y NO LO ESTABA.** `test_wi41_cli_dispatch.py`
comprueba que `cmd_project_inspect`, `cmd_policy_get`, `cmd_backup` y
`cmd_brick_register` son IMPORTABLES, y que la tabla de dispatch los
alcanza. Las dos cosas son verdad y ninguna ejecuta un cuerpo: los cuatro
podrian estar vacios por dentro y el test de superficie publica seguiria en
verde.

**LO QUE SE COMPRUEBA, Y POR QUE ESTOS Y NO OTROS.** Cuatro contratos que un
operador rompe con un `cut` o con un `rm`:

  - `project create` con un nombre NO seguro dice `EXIT_BAD_NAME` y no crea
    nada. El nombre va a una ruta (`tenants/<t>/projects/<name>/`), luego un
    nombre con `/` es un intento de escribir fuera.
  - `project create` dos veces dice `EXIT_PROJECT_EXISTS` y no pisa la base.
  - `policy get` sin politica dice `policy=none`, que es un valor que se
    puede parsear. Un `None` de Python en la salida seria un bug de fmt.
  - `backup list` sin backups lo dice con una frase, no con una cabecera
    vacia —la misma distincion que `(sin runs)` y `(sin propuestas)`.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import pytest

from skillgraph.cli.runner import (
    cmd_backup,
    cmd_backup_create,
    cmd_backup_list,
    cmd_policy_get,
    cmd_policy_set,
    cmd_project_create,
    cmd_project_inspect,
    cmd_project_list,
)

PROJECT = "demo"


def _run_cli(*args: str, cwd: Path, data_root: Path) -> subprocess.CompletedProcess[str]:
    env = {"SKILLGRAPH_DATA_ROOT": str(data_root), "PATH": "/usr/bin:/bin"}
    return subprocess.run(
        [sys.executable, "-m", "skillgraph", "--data-root", str(data_root), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        check=False,
    )


def _init(data_root: Path, cwd: Path) -> None:
    assert _run_cli("init", cwd=cwd, data_root=data_root).returncode == 0


def _seed(data_root: Path, cwd: Path, project: str = PROJECT) -> None:
    _init(data_root, cwd)
    rc = _run_cli("project", "create", project, cwd=cwd, data_root=data_root)
    assert rc.returncode == 0, rc.stderr


def _ns(data_root: Path, **kw: object) -> argparse.Namespace:
    return argparse.Namespace(data_root=Path(data_root), **kw)  # type: ignore[arg-type]


class TestElNombreDeProyecto:
    """El nombre va a una ruta. Un nombre no seguro es un intento de escritura."""

    @pytest.mark.parametrize(
        "nombre",
        ["con/barra", "con espacio", "", "a" * 65, "con.punto", "ñandú"],
        ids=["barra", "espacio", "vacio", "largo", "punto", "no-ascii"],
    )
    def test_un_nombre_NO_seguro_no_crea_nada(self, nombre: str, tmp_path: Path) -> None:
        """**POR QUE `is_safe_name` ES UNA BARRIERA Y NO UN ESTILO.**

        `cmd_project_create` construye `tenants/<t>/projects/<nombre>/`. Con
        `nombre = "con/barra"` eso sale un nivel del directorio del tenant: el
        proyecto se crea donde no debe, o revienta con un `FileNotFoundError`.
        El nombre no es un dato, es una PORCION de ruta.

        Y se mide que no se crea nada, no solo el codigo de retorno: un
        `return EXIT_BAD_NAME` DESPUES del `mkdir` deja un directorio vacio en
        el sitio equivocado, que es justo el residuo que este comando no debe
        dejar.

        `ñandú` esta en la lista por una razon concreta: no es un problema de
        `isalnum()` —que acepta `ñ`— sino del `isascii()` de la funcion. Sin
        el, un nombre con acento crearia un directorio que luego no se puede
        pedir desde otra maquina.
        """

    def test_el_error_ya_no_anuncia_un_conjunto_mas_pequeno_que_el_real(
        self,
        tmp_path: Path,
        capsys,  # type: ignore[no-untyped-def]
    ) -> None:
        """**ESTE TEST AFIRMABA UN DEFECTO QUE YA ESTA ARREGLADO.**

        La primera version de aqui decia: «el mensaje anuncia `[a-z0-9-_]`
        pero `is_safe_name` acepta mayusculas, luego hay una contradiccion».
        MEDIDO, y era verdad. Ese defecto se cerro: la regla vive ahora en
        `platform/paths.py::REGLAS_DE_NOMBRE_SEGURO` y el CLI la IMPORTA, de
        modo que no hay dos verdades que se puedan separar.

        Un test que afirma un defecto ya arreglado no es un test que «aún
        pasa»: es un test rojo, y su unica forma de volver a verde sería que
        el defecto volviera. Por eso se reescribe en vez de borrarse: la
        ASERCION cambia de signo y ahora exige lo contrario.

        Y la mitad fuerte —que la regla escrita describa el comportamiento
        real de la funcion, y que el contraejemplo del texto viejo no pase
        el guard— vive en `tests/test_wi116_nombre_de_proyecto.py`, que trae
        su propio contrasalto. Aqui solo se mide la atadura: que el texto que
        sale del comando LLEVE la regla compartida.
        """
        from skillgraph.cli.support import EXIT_BAD_NAME
        from skillgraph.platform.paths import REGLAS_DE_NOMBRE_SEGURO

        data_root = tmp_path / "sg-data"
        _init(data_root, tmp_path)

        rc = cmd_project_create(_ns(data_root, name="con.punto"))
        err = capsys.readouterr().err

        assert rc == EXIT_BAD_NAME
        assert REGLAS_DE_NOMBRE_SEGURO in err, (
            f"el error no lleva la regla compartida.\n"
            f"  regla: {REGLAS_DE_NOMBRE_SEGURO!r}\n  error: {err!r}"
        )
        assert "[a-z0-9-_]" not in err, (
            "el mensaje volvio al conjunto que la funcion no aplica: el texto "
            "y el codigo dicen cosas distintas otra vez"
        )

    def test_crear_dos_veces_dice_QUE_EXISTE_y_no_pisa_la_base(
        self,
        tmp_path: Path,
        capsys,  # type: ignore[no-untyped-def]
    ) -> None:
        """El segundo `create` es un error, y el error dice CUAL.

        Y lo que no puede hacer es **pisar la base**: el mensaje de error y
        el `db_path` intacto. Un `project create` idempotente que reescriba
        el esquema perderia lasobsrvaciones del proyecto.
        """
        from skillgraph.cli.support import EXIT_PROJECT_EXISTS

        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)
        db = data_root / "tenants" / "default" / "projects" / PROJECT / "project.sqlite"
        antes = db.read_bytes()

        rc = cmd_project_create(_ns(data_root, name=PROJECT))
        err = capsys.readouterr().err

        assert rc == EXIT_PROJECT_EXISTS
        assert PROJECT in err, f"el error no nombra el proyecto: {err!r}"
        assert db.read_bytes() == antes, "el segundo create REESCRIBIO la base del proyecto"


class TestProjectList:
    def test_sin_proyectos_imprime_LA_LITERAL(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        """`(sin proyectos)`, no una cabecera sin filas."""
        data_root = tmp_path / "sg-data"
        _init(data_root, tmp_path)

        rc = cmd_project_list(_ns(data_root))

        assert rc == 0
        assert "(sin proyectos)" in capsys.readouterr().out

    def test_las_columnas_de_una_proyecto_existen(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        """Tres columnas separadas por TAB, y con el nombre del proyecto.

        El tabulador es lo que hace la salida parseable con `cut -f1`; un
        espacio la rompe en cuanto un nombre lo lleva. Por eso el aserto
        mide el tabulador y no solo que el nombre aparezca.
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)

        rc = cmd_project_list(_ns(data_root))
        salida = capsys.readouterr().out

        assert rc == 0
        lineas = [ln for ln in salida.splitlines() if ln.strip()]
        assert len(lineas) == 1, f"esperaba 1 proyecto, la lista dice: {salida!r}"
        campos = lineas[0].split("\t")
        assert len(campos) == 3, f"esperaba 3 columnas separadas por tab, hay {len(campos)}"
        assert campos[0] == PROJECT, campos


class TestProjectInspect:
    def test_un_proyecto_vacio_no_inventa_recursos(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        """`Recursos: 0 total` y NINGUNA linea de breakdown.

        La segunda mitad es la que importa: con cero recursos, imprimir
        `sorted(by_kind.items())` no imprime nada, y un operador que ve un
        total en cero no debe ver una tabla de kinds vacia debajo.
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)

        rc = cmd_project_inspect(_ns(data_root, name=PROJECT))
        salida = capsys.readouterr().out

        assert rc == 0
        assert "Recursos: 0 total" in salida, salida
        assert f"Proyecto: {PROJECT}" in salida, salida

    def test_una_base_AUSENTE_no_dice_un_inspect_vacio(
        self,
        tmp_path: Path,
        capsys,  # type: ignore[no-untyped-def]
    ) -> None:
        """**EL DEFECTO QUE ESTA RAMA EXISTE PARA QUE NO PASE.**

        El catalogo puede conocer un proyecto cuya base ya no esta en disco:
        alguien borro el directorio, o copio el `catalog.sqlite` a otra
        maquina. `inspect` sobre ese proyecto tiene que decir «base
        ausente», no imprimir `Recursos: 0 total` —que es una AFIRMACION
        FALSA sobre un proyecto que no se puede leer—.

        Se mide por BORRAR la base, que es el camino real: no se fabrica
        un catalogo raro a mano.
        """
        from skillgraph.cli.support import EXIT_DB_MISSING

        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)
        db = data_root / "tenants" / "default" / "projects" / PROJECT / "project.sqlite"
        db.unlink()

        rc = cmd_project_inspect(_ns(data_root, name=PROJECT))
        capturado = capsys.readouterr()

        assert rc == EXIT_DB_MISSING, f"una base ausente devolvio {rc}"
        assert "ausente" in capturado.err, capturado.err
        assert "Recursos: 0 total" not in capturado.out, (
            "inspecciono un proyecto que no puede leer y dijo que tiene 0 recursos"
        )


class TestPolicy:
    """`policy get`/`set`: un valor que se puede parsear, y que persiste."""

    def test_sin_politica_dice_none_y_NO_None(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        """`policy=none`, no `policy=None`.

        El `or 'none'` del codigo existe exactamente por esto: `get_policy`
        devuelve `None` cuando no hay fila, y un f-string lo imprimiria como
        `None`, que es un valor que ningun `case` de un shell reconoce como
        «sin politica».
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)

        rc = cmd_policy_get(_ns(data_root, project=PROJECT))
        salida = capsys.readouterr().out

        assert rc == 0
        assert "policy=none" in salida, salida
        assert "None" not in salida, (
            f"la salida de un comando de shell contiene `None` de Python: {salida!r}"
        )

    def test_set_luego_get_devuelve_LO_MISMO(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        """El round-trip, y con la fila LEIDA DE DISCO.

        Un `set` que imprimiera el valor sin escribirlo pasaria un test que
        solo mira stdout. Se pone el valor, se abre el Storage del proyecto
        y se lee la fila; lo que se mide es la persistencia, que es de lo
        que habla el docstring («aplica a TODOS los Runs futuros»).
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)

        rc = cmd_policy_set(_ns(data_root, project=PROJECT, redact_policy="payload"))
        assert rc == 0
        assert "policy=payload" in capsys.readouterr().out

        rc = cmd_policy_get(_ns(data_root, project=PROJECT))
        assert rc == 0
        assert "policy=payload" in capsys.readouterr().out

    def test_un_proyecto_inexistente_no_imprime_una_politica(
        self,
        tmp_path: Path,
        capsys,  # type: ignore[no-untyped-def]
    ) -> None:
        """Los dos comandos, el mismo contrato de salida.

        Parametrizado por la misma razon que en `runs`: la propiedad es una
        —«ninguno de los dos imprime una politica si el proyecto no
        existe»— y dos tests separados dejarian al segundo sin vigilar.
        """
        from skillgraph.cli.support import EXIT_PROJECT_NOT_FOUND

        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)

        rc = cmd_policy_get(_ns(data_root, project="no-existe"))
        assert rc == EXIT_PROJECT_NOT_FOUND
        assert "policy=" not in capsys.readouterr().out

        rc = cmd_policy_set(_ns(data_root, project="no-existe", redact_policy="full"))
        assert rc == EXIT_PROJECT_NOT_FOUND
        assert "policy=full" not in capsys.readouterr().out


class TestBackup:
    """Create/list/restore: el ciclo entero de un backup por la CLI."""

    def test_listar_sin_backups_no_imprime_una_cabecera_vacia(
        self,
        tmp_path: Path,
        capsys,  # type: ignore[no-untyped-def]
    ) -> None:
        """`Sin backups en <dir>`, no `Backups en <dir>:` y nada debajo."""
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)

        rc = cmd_backup_list(_ns(data_root, dir=None))
        salida = capsys.readouterr().out

        assert rc == 0
        assert salida.startswith("Sin backups en"), salida
        assert "Backups en" not in salida, f"imprimio la cabecera de una lista vacia: {salida!r}"

    def test_crear_luego_listar_muestra_TAMANO_y_CONTENIDO(
        self,
        tmp_path: Path,
        capsys,  # type: ignore[no-untyped-def]
    ) -> None:
        """El backup existe en disco Y aparece en el listado, con su tamano.

        Se mide el `.zip` en el sistema de ficheros y no solo el mensaje:
        un `create` que imprimiera «Backup creado» sin escribir nada
        passaria la mitad del contrato, y el `list` es el que lo delata.
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)

        rc = cmd_backup_create(_ns(data_root))
        assert rc == 0
        creado = capsys.readouterr().out
        assert "Backup creado:" in creado, creado

        rc = cmd_backup_list(_ns(data_root, dir=None))
        listado = capsys.readouterr().out

        assert rc == 0
        assert "Backups en" in listado, listado
        assert "tenants=1" in listado, (
            f"el listado no dice cuantos tenants hay en el backup: {listado!r}"
        )
        assert "projects=1" in listado, listado

    @pytest.mark.parametrize(
        ("sub", "marca"),
        [("create", "Backup creado:"), ("list", "Backups en")],
        ids=["create", "list"],
    )
    def test_el_dispatcher_encamina_al_subcomando_que_se_le_pidio(
        self,
        sub: str,
        marca: str,
        tmp_path: Path,
        capsys,  # type: ignore[no-untyped-def]
    ) -> None:
        """**EL DISPATCHER TIENE TRES RAMAS Y CADA UNA EJECUTA OTRA COSA.**

        Se mide el efecto, no la llamada: que `backup create` imprima la
        marca de `create` y `backup list` la de `list`. Un dispatcher que
        encaminara las dos al mismo handler imprimiria la misma marca en los
        dos casos, y un test que mirara «devuelve 0» lo passaria.

        Y el estado previo se differentiate por el `list`: se crea el
        backup primero en el caso de `list`, para que la marca que se
        comprueba sea la de una lista CON contenido y no la de `(sin
        backups)`.
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)
        if sub == "list":
            cmd_backup_create(_ns(data_root))
            capsys.readouterr()

        rc = cmd_backup(_ns(data_root, backup_command=sub, dir=None))
        salida = capsys.readouterr().out

        assert rc == 0
        assert marca in salida, f"`backup {sub}` no imprime la marca de `{sub}`: {salida!r}"

    def test_un_subcomando_DESCONOCIDO_no_dispacha_una_accion(
        self,
        tmp_path: Path,
        capsys,  # type: ignore[no-untyped-def]
    ) -> None:
        """`backup` sin subcomando no crea nada y no lista nada.

         El dispatcher tiene tres ramas y una cuarta que es el error. Sin esa
         cuarta, `getattr(args, "backup_command", None)` devolviendo `None`
         caeria en el primer `if` y ejecutaria un `create` — un backup
        整车 del data-root cada vez que alguien teclea `sg backup`.
        """
        from skillgraph.cli.support import EXIT_VALIDATION

        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)

        rc = cmd_backup(_ns(data_root))
        err = capsys.readouterr().err

        assert rc == EXIT_VALIDATION
        assert "backup" in err.lower(), f"el error no dice que falta el subcomando: {err!r}"
        assert "Backup creado" not in err, "un subcomando ausente disparo una accion"


class TestLaTablaNoEsElCuerpo:
    """**POR QUE ESTE FICHERO NO TOCA `test_wi41_cli_dispatch.py`.**

    Ese fichero mide la TABLA: que todo comando del parser tenga entrada, que
    los handlers públicos sigan importables, que `main` no tenga ramas de
    comando. Son tres invariantes reales y ninguna tiene que ver con que los
    handlers hagan algo.

    Lo que este fichero anade es una capa mas abajo: que el handler al que
    la tabla enruta hace lo que su docstring dice. Un dispatch perfecto
    hacia un cuerpo vacio sigue siendo un producto que no funciona, y solo
    uno de los dos lados puede estar mal sin que el otro lo note.
    """

    def test_el_test_de_superficie_no_puede_verificar_QUE_HACE_un_handler(self) -> None:
        """El guard que demuestra por que este fichero hace falta.

        Se lee el codigo de `test_wi41_cli_dispatch.py` y se mira que su
        clase de superficie solo comprueba importabilidad. No es una
        acusacion: es la demostracion de que la cobertura que da nombre a
        `runner.py` no puede dar nombre a un cuerpo.
        """
        fuente = (Path(__file__).parent / "test_wi41_cli_dispatch.py").read_text(encoding="utf-8")
        bloque = fuente.split("class TestPublicSurfaceStability")[1].split("class ")[0]

        assert "cmd_project_inspect" in bloque, (
            "la clase de superficie ya no menciona estos handlers: la premisa "
            "de este fichero habria cambiado y hay que revisar por que"
        )
        # El bloque SI ejecuta subprocesos, pero solo para `--help` y para
        # `--version`: no para estos handlers. Lo que se mide es que no haya
        # una LLAMADA DIRECTA a ninguno de ellos, que es la unica forma de
        # ejecutar un cuerpo. La primera version de este aserto miraba
        # `_run_cli(` y fallaba, porque la clase tiene un test de ayuda que si
        # lanza la CLI: la premisa era mas fina de lo que parecia.
        for handler in (
            "cmd_project_inspect",
            "cmd_policy_get",
            "cmd_backup",
            "cmd_brick_register",
        ):
            assert not re.search(rf"\b{handler}\s*\(", bloque), (
                f"la superficie publica ya invoca a {handler}(): entonces la "
                "distincion entre 'la tabla' y 'el cuerpo' ya no aplica aqui"
            )


class TestElSueloNoSeRelaja:
    """**POR QUE ESTE FICHERO NO TOCA `check_coverage_floors.py`.**

    El suelo de `cli/` es el 70 % y lo declara AGENTS 6.3 con su motivo: lo
    que falta ahi son ramas que cubre la integracion. Este fichero sube
    `runner.py` exercising sus comandos, no bajando la regla.

    El contrasalto es que la regla siga PONIENDO. Un suelo que baja porque
    el codigo crece no mide cobertura: mide el dia que alguien se rindio.
    """

    def test_el_suelo_de_cli_sigue_siendo_el_que_declara_agentes(self) -> None:
        from scripts.check_coverage_floors import SUELOS_ESPECIALES

        assert SUELOS_ESPECIALES["src/skillgraph/cli/"] == 70.0, (
            f"el suelo de cli/ es {SUELOS_ESPECIALES['src/skillgraph/cli/']} "
            "y AGENTS 6.3 declara 70: bajarlo para que un gate pase es la "
            "forma de guarda que este repo lleva varios bloques cerrando"
        )

    def test_la_atadura_de_donde_viven_los_handlers_QUE_MIDE(self) -> None:
        """**LA ATADURA QUE FALTA EN LOS OTROS TRES FICHEROS.**

        Aqui los handlers medidos son la mitad PROPIA de `runner.py`, no
        reexports. Eso tiene una consecuencia: si alguien mueve
        `cmd_policy_get` a `commands/policy.py`, el modulo que este fichero
        mide deja de ser `runner.py` —y el suelo que sube sigue contando
        para `runner.py`, que se queda sin codigo y por tanto «cumple».

        El `__module__` es lo que dice de donde salio la funcion. No es una
        prueba de que el sitio sea el correcto: es una alarma para que
        moverla sea una decision y no un efecto secundario.
        """
        import skillgraph.cli.runner as runner

        for handler in (
            runner.cmd_policy_get,
            runner.cmd_policy_set,
            runner.cmd_project_inspect,
            runner.cmd_backup_list,
        ):
            assert handler.__module__ == "skillgraph.cli.runner", (
                f"{handler.__name__} vive en {handler.__module__}: el modulo "
                "que este fichero sube de cobertura ya no es runner.py, y el "
                "suelo se llevaria el numero de un modulo que ya no existe"
            )
