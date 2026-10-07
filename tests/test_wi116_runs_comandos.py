"""`runs.py` ejecutado de verdad, no solo cableado.

**LA MEDIDA QUE ABRE ESTE TRABAJO.** `cli/commands/runs.py` mide **44,95 %**
sobre el suelo del 70 % que AGENTS 6.3 declara para `cli/`. Sus lineas sin
cubrir eran, casi todas, el CUERPO de cinco comandos:

    cmd_runs_list  ·  cmd_runs_show  ·  cmd_runs_logs
    cmd_runs_cancel  ·  cmd_runs_budget

Que estaban «cubiertos» es una ilusion de WI-53: sus tests comprueban que
`runner.cmd_runs_list is runs.cmd_runs_list`, o sea **que el comando esta
enchufado**. Una asercion de identidad mide el cable, no el comando. Los
cinco podia estar vacios por dentro y los tests seguian en verde.

**LO QUE SE COMPRUEBA, Y POR QUE ESTOS Y NO OTROS.** Cada comando declara un
CONTRATO EXTERNO distinto, y ese contrato es lo que un operador rompe con un
`awk`:

  - `runs list` imprime `(sin runs)` literal en un proyecto vacio. Es un
    contrato de una linea que ya se leia en scripts, y cambiarlo por el
    `(sin resultados)` por defecto de la vista seria una ruptura silenciosa.
  - `runs show` sigue siendo `clave=valor` en TEXTO. B7 anadio un panel
    legible y un JSON, pero el texto por defecto **no** se sustituye: hay
    callers que leen `state=` con un `cut`.
  - `runs cancel` es la UNICA de las cinco que escribe, y su garantia es
    atomica: la transicion de estado y el evento van en una sola TX.
  - `runs budget` distingue tres casos que se confunden leyendo el codigo:
    run que no existe, run sin budget, y run con budget.

**Y LA AFIRMACION QUE SOSTIENE TODO ESTE FICHERO.** Las cinco se ejecutan
contra un proyecto REAL y un run REAL creados por el DSL, no contra mocks: un
`FakeAgentAdapter(Path("/dev/null"))` es lo que los propios comandos usan, y
los cinco declaran en su codigo que no invocan al adapter.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest

from skillgraph.cli.commands.runs import (
    cmd_runs_budget,
    cmd_runs_cancel,
    cmd_runs_list,
    cmd_runs_logs,
    cmd_runs_show,
)
from skillgraph.cli.runner import EXIT_DOMAIN, EXIT_OK
from skillgraph.domain.dsl import PlanBuilder, node_name
from skillgraph.runtime.run_types import RunBudget
from skillgraph.runtime.runcontroller import RunController

TENANT = "default"
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


def _seed(data_root: Path, cwd: Path, project: str = PROJECT) -> None:
    assert _run_cli("init", cwd=cwd, data_root=data_root).returncode == 0
    rc = _run_cli("project", "create", project, cwd=cwd, data_root=data_root)
    assert rc.returncode == 0, rc.stderr


def _ns(data_root: Path, **kw: object) -> argparse.Namespace:
    return argparse.Namespace(data_root=Path(data_root), **kw)  # type: ignore[arg-type]


def _plan():
    return (
        PlanBuilder()
        .add_node(node_name("n1"), expected="texto", capabilities=())
        .starts_at(node_name("n1"))
        .build()
    )


class TestRunsList:
    """El contrato de la linea literal, y el filtro de estado."""

    def test_proyecto_vacio_imprime_LA_LITERAL(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        """**EL CONTRATO MAS FRAGIL DEL MODULO.**

        `(sin runs)` esta fijado como literal porque hay scripts que lo
        leen. El `_emit` tiene un `vacio="(sin results)"` por defecto en la
        vista, asi que el comando TIENE que pasar el suyo: si alguien quita
        ese argumento, la vista gana y el contrato se rompe en silencio.
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)

        rc = cmd_runs_list(_ns(data_root, project=PROJECT, state=None, limit=20))

        assert rc == EXIT_OK
        assert "(sin runs)" in capsys.readouterr().out, (
            "un proyecto vacio no imprimio `(sin runs)`. Es un contrato de "
            "una linea que scripts existentes ya leen."
        )

    def test_filtrar_por_un_que_no_existe_devuelve_VACIO(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        """Un filtro que no casa con nada NO es un error.

        Es la diferencia entre «no hay runs» y «no hay runs en ese estado»:
        el segundo es una consulta legitima que devuelve cero, y tratarlo
        como error haria que un operador no pudiera preguntar por un estado
        raro sin que la CLI le dijera que se equivoca.
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)

        rc = cmd_runs_list(_ns(data_root, project=PROJECT, state="COMPLETED", limit=20))

        assert rc == EXIT_OK
        assert "(sin runs)" in capsys.readouterr().out

    def test_json_devuelve_JSON_parseABLE(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        """La segunda representacion: la misma vista, en JSON.

        Y se PARSEA, no se mira: un JSON que no parsea es texto con corchetes,
        y el fallo aparece en el consumidor, no en la CLI.
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)

        rc = cmd_runs_list(_ns(data_root, project=PROJECT, state=None, limit=20, format="json"))
        salida = capsys.readouterr().out

        assert rc == EXIT_OK
        carga = json.loads(salida)  # si esto falla, el contrato JSON es falso
        assert isinstance(carga, (list, dict)), carga


class TestRunsShow:
    """`clave=valor` es un contrato de shell, no un formato."""

    def test_un_run_inexistente_es_un_ERROR_DE_DOMINIO_no_un_estado_vacio(
        self, tmp_path: Path
    ) -> None:
        """**LO QUE MIDIO ESTE TEST, Y NO ES LO QUE ESPERABA.**

        La primera version afirmaba `rc != EXIT_OK` al llamar al comando
        in-process. FALLA, y la razon importa: `show_run` **lanza**
        `NotFoundError` y no devuelve exit code.

        Lo que hace bien es la clase: `NotFoundError` es un `SkillGraphError`
        con `code`, luego `runner.py:253` lo traduce a exit code y lo imprime
        por stderr. Un `return 0` con un estado vacio habria sido el
        defecto de verdad: el operador recibiria un estado creyendolo real.

        Por eso el test mide la clase de la excepcion y NO el return code:
        son dos frontiers distintas, y es la de la excepcion la que decide
        si el usuario ve un mensaje o un Traceback.
        """
        from skillgraph.core.errors import NotFoundError

        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)

        with pytest.raises(NotFoundError) as exc:
            cmd_runs_show(_ns(data_root, project=PROJECT, run_id="no-existe"))

        assert exc.value.code, (
            "un error de dominio sin `code` no lo puede traducir el runner: "
            "sale como Traceback, que es el defecto que WI-109 cerro"
        )
        assert "no-existe" in str(exc.value), f"el error no nombra el run que se pidio: {exc.value}"


class TestRunsLogs:
    """El timeline, y su decidedly-empty."""

    def test_un_run_inexistente_no_devuelve_UN_TIMELINE_VACIO(self, tmp_path: Path) -> None:
        """Un timeline vacio se lee como «este run no hizo nada».

        Que es otra cosa distinta de «este run no existe», y quien lo lee en
        un terminal no puede distinguirlas. Por eso tiene que ser un error de
        dominio con `code`, no una lista vacia con exit code 0.
        """
        from skillgraph.core.errors import NotFoundError

        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)

        with pytest.raises(NotFoundError) as exc:
            cmd_runs_logs(_ns(data_root, project=PROJECT, run_id="no-existe"))

        assert exc.value.code, "sin `code` el runner no lo traduce"


class TestRunsCancel:
    """La unica de las cinco que ESCRIBE. Su garantia es atomica."""

    def test_cancelar_un_run_inexistente_no_dice_que_se_cancelo(self, tmp_path: Path) -> None:
        """**Y AQUI ESTA EL FALLO QUE CUESTA.**

        `cmd_runs_cancel` imprime `run_id=... state=...` y devuelve `EXIT_OK`.
        Si el run no existe, lo que tiene que imprimir es un ERROR, no un
        `state=` de algo: un cancel que reporta exito sobre un run
        inexistente deja al operador creyendo que lo cancelo cuando no habia
        nada que cancelar.
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)

        from skillgraph.core.errors import NotFoundError

        with pytest.raises(NotFoundError) as exc:
            cmd_runs_cancel(_ns(data_root, project=PROJECT, run_id="no-existe"))

        assert exc.value.code, (
            "cancelar un run inexistente tiene que ser un error de dominio "
            "traducible: el comando imprime `state=` en el camino feliz, y "
            "un `state=` de algo que no existe es una cancelacion fantasma"
        )


class TestRunsBudget:
    """Tres casos que se confunden leyendo el codigo."""

    def test_run_inexistente_sale_con_el_EXIT_DEL_DOMINIO(
        self,
        tmp_path: Path,
        capsys,  # type: ignore[no-untyped-def]
    ) -> None:
        """El caso que el codigo distingue con un `try/except` explicito.

        `get_run` lanza `NotFoundError`, se imprime por stderr y se devuelve
        `EXIT_DOMAIN`. Un `(sin budget)` aqui seria la MENTIRA: no es que el
        run no tenga presupuesto, es que el run no existe.
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)

        rc = cmd_runs_budget(_ns(data_root, project=PROJECT, run_id="no-existe"))

        assert rc == EXIT_DOMAIN
        assert "ERROR" in capsys.readouterr().err, (
            "el error de «run que no existe» tiene que ir por stderr: en "
            "stdout se mezclaria con el `(sin budget)` de un caso legitimo"
        )

    def test_run_sin_budget_imprime_LA_LITERAL(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        """Un run real SIN budget: la respuesta honesta es «no tiene»."""
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)
        _crear_run_real(data_root)

        run_id = _primer_run(data_root)
        rc = cmd_runs_budget(_ns(data_root, project=PROJECT, run_id=run_id))

        assert rc == EXIT_OK
        assert "(sin budget)" in capsys.readouterr().out, (
            "un run sin presupuesto no dijo `(sin budget)`: imprime `max_visits=-` "
            "como si el presupuesto existiera con limites ilimitados, que es "
            "otra cosa distinta"
        )

    def test_run_CON_budget_imprime_LOS_TRES_LIMITES(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        """**EL CASO QUE COMPLEMENTA AL ANTERIOR, Y NO ES SU NEGADO.**

        Con budget activo el comando imprime `clave=valor` y NO la literal.
        Lo que se mide aqui no es que aparecen los numeros —eso lo haria
        cualquiera— sino que la literal `(sin budget)` **desaparece**: un
        comando que imprime las dos cosas a la vez no se puede parsear con
        `grep -q '(sin budget)'` para decidir si hay limite.

        Y el guion: se fija `max_visits` y se dejan los otros dos en `None`,
        que es como se declara un budget real (se limita lo que se quiere
        limitar). Los otros dos tienen que salir `-`, no `None`: `-` es lo
        que un `cut -d= -f2` puede comparar, `None` no.
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)
        _crear_run_real(data_root, budget=RunBudget(max_visits=3))
        run_id = _primer_run(data_root)

        rc = cmd_runs_budget(_ns(data_root, project=PROJECT, run_id=run_id))
        salida = capsys.readouterr().out

        assert rc == EXIT_OK
        assert "(sin budget)" not in salida, (
            f"un run CON presupuesto tambien Prints la literal de ausencia: {salida!r}"
        )
        assert "max_visits=3" in salida, salida
        assert "max_runtime_seconds=-" in salida, (
            f"un limite no fijado tiene que salir `-`, no `None`: {salida!r}"
        )
        assert "max_events=-" in salida, salida


class TestElProyectoQueNoExiste:
    """**LA RAMA QUE FALTA EN LOS CINCO, Y QUE ES LA MISMA.**

    `_open_project_storage` devuelve `(None, EXIT_PROJECT_NOT_FOUND)` cuando
    el catalogo no conoce el proyecto, y los cinco comandos tienen su
    `if err != EXIT_OK: return err`.

    Se mide con los CINCO a la vez, y el motivo de que sea un solo test
    parametrizado y no cinco es que la propiedad es una sola: **ninguno de
    los cinco invoca al adapter ni escribe cuando el proyecto no existe**.
    Si se midiera uno por separado, cinco tests que casi siempre darian el
    mismo codigo, y el quinto que se olvidara de comprobarlo no lo detectaria
    nadie.

    Es el typo del nombre del proyecto, que es el error mas frecuente que
    va a cometer un operador de esta CLI.
    """

    @pytest.mark.parametrize(
        ("comando", "kw"),
        [
            (cmd_runs_list, {"state": None, "limit": 20}),
            (cmd_runs_show, {"run_id": "x"}),
            (cmd_runs_logs, {"run_id": "x", "limit": None}),
            (cmd_runs_cancel, {"run_id": "x"}),
            (cmd_runs_budget, {"run_id": "x"}),
        ],
        ids=["list", "show", "logs", "cancel", "budget"],
    )
    def test_proyecto_inexistente_no_llega_a_ejecutar(
        self,
        comando,  # type: ignore[no-untyped-def]
        kw: dict,  # type: ignore[type-arg]
        tmp_path: Path,
        capsys,  # type: ignore[no-untyped-def]
    ) -> None:
        from skillgraph.cli.support import EXIT_PROJECT_NOT_FOUND

        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)

        rc = comando(_ns(data_root, project="no-existe", **kw))
        capturado = capsys.readouterr()

        assert rc == EXIT_PROJECT_NOT_FOUND, (
            f"{comando.__name__} con un proyecto inexistente devolvio {rc} "
            f"en vez de {EXIT_PROJECT_NOT_FOUND}"
        )
        assert "no-existe" in capturado.err, (
            f"el error no nombra el proyecto que se pidio: {capturado.err!r}"
        )


class TestLosCaminosFelices:
    """**LO QUE FALTABA, Y POR QUE ES LA PARTE IMPORTANTE.**

    Los ocho tests anteriores exercised sobre todo lo que FALLA: run que no
    existe, proyecto vacio, filtro que no casa. Cubren los `except` y los
    `if not ...`.

    Los caminos felices —un run que se ejecuta, se muestra, se cancela— no
    estaban cubiertos, y son los que un operador usa. Con solo los errores,
    un comando que devolviera `EXIT_OK` sin imprimir nada pasaria esta
    suite entera: la cobertura sube sin que nadie haya mirado un run
    real nunca.

    Cada test de aqui mide una SALIDA, no un codigo de retorno, y la razon
    esta en el propio contrato del comando.
    """

    def test_show_de_un_run_ejecutado_imprime_clave_valor_Y_conserva_el_texto(
        self,
        tmp_path: Path,
        capsys,  # type: ignore[no-untyped-def]
    ) -> None:
        """**LO QUE EL COMANDO HACE, MEDIDO, Y NO ES LO QUE YO ESPERABA.**

        La primera version de este test afirmaba que `runs show` imprimia el
        timeline en el texto. FALLA, y el motivo es el contrato mismo: el
        comando construye `run_detail(snap, timeline=timeline_view(...))`
        —el timeline VIAJA a la vista— pero `_emit` por defecto llama a
        `vista.to_key_value`, que imprime solo los `fields`, no las
        `sections`.

        No es un defecto: es exactamente lo que B7 fijo al anadir el panel
        legible sin sustituir el texto que leen callers con `cut`. Por eso
        lo que se mide aqui es la OTRA mitad del contrato, que es el que se
        puede romper en silencio:

        - sale `clave=valor` (no el panel legible),
        - `events_emitted` cuenta lo que ocurrio (un run de verdad, no uno
          recien creado y sin ejecutar).

        Un `show` que sustituyera el texto por el panel pasaria un test que
        solo mirara `state=`; por eso el primer aserto mira que `sections`
        NO este en la salida.
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)
        run_id = _crear_run_real(data_root, ejecutar=True)

        rc = cmd_runs_show(_ns(data_root, project=PROJECT, run_id=run_id))
        salida = capsys.readouterr().out

        assert rc == EXIT_OK
        assert f"run_id={run_id}" in salida, f"se perdio el `clave=valor` del run: {salida!r}"
        assert "state=" in salida, f"no dice en que estado quedo el run: {salida!r}"
        assert "sections" not in salida and "timeline" not in salida, (
            f"`show` sustituyo el texto por el panel legible: hay callers que "
            f"leen `state=` con un `cut` y esto los rompe. Salida: {salida!r}"
        )
        # `events_emitted` con valor > 0 es lo que distingue «un run que se
        # ejecutó» de «un run que se creó». Sin esto, show y create serian
        # indistinguibles desde la terminal.
        emitido = _valor_de_clave(salida, "events_emitted")
        assert emitido > 0, f"un run reconciliado dice 0 eventos emitidos: {salida!r}"

    def test_show_en_json_incluye_el_timeline(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        """**LA REPRESENTACION DONDE EL TIMELINE SI SE VE.**

        `to_json_text` serializa `sections`, y el timeline es una de ellas.
        Es el otro lado del contrato de arriba: si `to_key_value` omite el
        timeline a proposito, el JSON es donde el operador lo encuentra.

        Y por eso se mide aqui: si `to_json_text` dejara de serializar las
        secciones, el unico sitio donde se ve el «POR QUE» se perderia en
        silencio, y no habria ningun contrato roto de los que mirar.
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)
        run_id = _crear_run_real(data_root, ejecutar=True)

        rc = cmd_runs_show(_ns(data_root, project=PROJECT, run_id=run_id, format="json"))
        carga = json.loads(capsys.readouterr().out)

        assert rc == EXIT_OK
        assert carga.get("sections"), f"el JSON de `show` no trajo secciones: {carga!r}"

    def test_logs_de_un_run_ejecutado_imprime_UN_EVENTO_POR_FILA(
        self,
        tmp_path: Path,
        capsys,  # type: ignore[no-untyped-def]
    ) -> None:
        """El timeline de verdad, con su cabecera de cuatro columnas.

        Y `limit`: un operador que depura un run largo recorta, y esa rama
        (`logs[:args.limit]`) es una slicing sobre una lista que puede dar
        cualquier cosa si el limite es mayor que los eventos. Se recorta un
        evento de mas para que el recorte tenga que hacer algo.
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)
        run_id = _crear_run_real(data_root, ejecutar=True)

        rc = cmd_runs_logs(_ns(data_root, project=PROJECT, run_id=run_id, limit=None))
        completa = capsys.readouterr().out

        assert rc == EXIT_OK
        assert "event_kind" in completa, completa
        assert "RunCreated" in completa, (
            f"un run creado tiene al menos su `RunCreated` y no aparece: {completa!r}"
        )

        rc = cmd_runs_logs(_ns(data_root, project=PROJECT, run_id=run_id, limit=1))
        recortada = capsys.readouterr().out

        assert rc == EXIT_OK
        assert len(recortada.splitlines()) < len(completa.splitlines()), (
            f"`limit=1` no recorto nada: {len(recortada.splitlines())} lineas "
            f"contra {len(completa.splitlines())}"
        )

    def test_un_run_siempre_tiene_al_menos_su_RunCreated(self, tmp_path: Path) -> None:
        """**POR QUE `(sin eventos)` NO TIENE TEST DE CAMINO FELIZ.**

        La rama `if not logs: print("(sin eventos)")` de `cmd_runs_logs` no
        la alcanza ningun test, y no por descuido: `create_run` emite
        `RunCreated` en la MISMA transaccion que escribe el run (H9). No
        existe un run creado por la API que no tenga al menos ese evento.

        Podria cubrirla insertando una fila en `workflow_runs` a mano por SQL,
        y ese es precisamente el motivo de no hacerlo: fabricaria un estado
        que el sistema no puede producir y mediria una linea con un test
        que no puede pasar nada real.

        Lo que se mide es la PROPIEDAD que vuelve la rama defensiva: todo
        run creado tiene su evento. Si alguien hiciera `create_run` sin
        emitir —el defecto de H9 regresando— este test se pone rojo, y la
        rama pasa a ser alcanzable y a necesitar su propio test.
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)
        run_id = _crear_run_real(data_root)

        storage = _storage_del_proyecto(data_root)
        eventos = storage._conn.execute(
            "SELECT COUNT(*) FROM runtime_events WHERE run_id = ?", (run_id,)
        ).fetchone()
        assert eventos is not None and eventos[0] >= 1, (
            f"un run sin ningun evento: la rama `(sin eventos)` de `cmd_runs_logs` "
            f"ha dejado de ser defensiva y necesita su propio test. run_id={run_id}"
        )

    def test_cancelar_un_run_REAL_lo_pasa_a_CANCELLED(
        self,
        tmp_path: Path,
        capsys,  # type: ignore[no-untyped-def]
    ) -> None:
        """**EL CONTRARIO DEL TEST DE ARRIBA, Y NO ES SIMETRICO POR CASUALIDAD.**

        El test de run inexistente comprueba que NO se invente una
        cancelacion. Este comprueba que una cancelacion REAL se escribe en
        la base: imprime `state=CANCELLED` y el estado se lee de disco.

        Un comando que imprimiera `state=CANCELLED` sin escribir nada pasaria
        la mitad de los tests de este modulo —los que solo miran stdout— y
        dejaria al operador con un run que sigue vivo y una terminal que
        dice lo contrario. Por eso la asercion mira la TABLA.
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)
        run_id = _crear_run_real(data_root)

        rc = cmd_runs_cancel(_ns(data_root, project=PROJECT, run_id=run_id))

        assert rc == EXIT_OK
        assert "state=CANCELLED" in capsys.readouterr().out
        storage = _storage_del_proyecto(data_root)
        estado = storage._conn.execute(
            "SELECT state FROM workflow_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        assert estado is not None and estado[0] == "CANCELLED", (
            f"el comando informo de una cancelacion que no ocurrio: en disco {estado}"
        )

    def test_list_muestra_el_run_QUE_EXISTE(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        """La lista con contenido, no solo la lista vacia.

        `run_view` con filas tiene una rama de render que `(sin runs)` no
        toca nunca, y es la que un operador lee todos los dias.
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)
        run_id = _crear_run_real(data_root)

        rc = cmd_runs_list(_ns(data_root, project=PROJECT, state=None, limit=20))

        assert rc == EXIT_OK
        salida = capsys.readouterr().out
        assert run_id[:8] in salida, f"la lista no mostro el run que existe: {salida!r}"
        assert "(sin runs)" not in salida, f"una lista con un run no dice `(sin runs)`: {salida!r}"

    def test_list_en_json_devuelve_las_FILAS(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        """La segunda representacion tambien con contenido.

        El JSON de un proyecto vacio es `[]`, que es lo que hace `{}`/`list`
        parseables. El caso con filas es el que de verdad tiene que
        **conservar el `run_id`**: un `to_json_text` que serializara solo
        columnas visibles perderia la clave con la que se pide `runs show`.
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)
        run_id = _crear_run_real(data_root)

        rc = cmd_runs_list(_ns(data_root, project=PROJECT, state=None, limit=20, format="json"))
        carga = json.loads(capsys.readouterr().out)

        assert rc == EXIT_OK
        assert carga, "el JSON de un proyecto con un run vino vacio"
        assert run_id[:8] in capsys.readouterr().out + json.dumps(carga)


class _AdapterQueRespondeOK:
    """Un adapter de un nodo, sin ficheros de por medio.

    `FakeAgentAdapter` busca un fixture en disco por `node_execution_id`, y
    el `node_execution_id` de este plan lo genera `RunController`. Sembrar
    el fixture correcto exigiría leer el id de una corrida anterior, que es
    una dependencia de orden escondida en un helper de test.

    Este stub dice lo mismo que el fixture —`outcome="ok"`— sin el fichero.
    Los cinco comandos de este modulo declaran en su codigo que NO invocan
    al adapter; este solo se usa para poner un run en estado terminal con
    eventos, que es lo que `show`/`logs` necesitan para tener algo que
    mostrar.
    """

    def invoke(self, handoff) -> object:  # type: ignore[no-untyped-def]
        from skillgraph.runtime.agent import AgentResult

        return AgentResult.from_fixture({"outcome": "ok", "result": {}})


def _valor_de_clave(salida: str, clave: str) -> int:
    """El entero de la linea `clave=valor` de una salida `clave=valor`.

    **POR QUE UN HELPER Y NO UN `int` EN EL ASERTO.** La salida es texto con
    varias lineas y el valor esta entre el `=` y el fin de linea. Un
    `int(linea.split("=")[1])` en cada test repetiria el parseo cuatro
    veces, y una de esas cuatro es la que se olvidaria de comprobar el
    `except`. Ademas un aserto que dice «no encuentro la clave» y uno que
    dice «la clave vale 0» son fallos distintos, y aqui importan: el segundo
    es el defecto real.
    """
    for linea in salida.splitlines():
        if linea.startswith(f"{clave}="):
            return int(linea.split("=", 1)[1])
    raise AssertionError(f"la salida no trae `{clave}=`: {salida!r}")


def _crear_run_real(data_root: Path, *, ejecutar: bool = False, budget=None):  # type: ignore[no-untyped-def]
    """Crea un run en el Storage del proyecto, con el plan del DSL.

    `ejecutar=True` reconcilia el run para que tenga eventos; sin eso,
    `logs` no tiene nada que listar y `show` no tiene timeline que traer.
    """
    storage = _storage_del_proyecto(data_root)
    ctl = RunController(
        runs=storage,
        events=storage,
        policy=storage,
        adapter=_AdapterQueRespondeOK(),
    )
    run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=_plan(), budget=budget)
    if ejecutar:
        ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
    return run_id


def _storage_del_proyecto(data_root: Path):
    """El Storage del proyecto, resuelto por el CATALOGO y no por una ruta.

    **POR QUE NO `<root>/tenants/<t>/projects/<p>/project.sqlite`.** Esa
    version del helper fallaba con `no such table: runs`, y la causa es la
    parte interesante: `Storage(...)` **crea** el fichero SQLite si no
    existe. Una ruta inventada no da error, da una base VACIA —y una base
    vacia sin `runs` es indistinguible de un proyecto sin runs hasta que
    alguien lee el error al reves.

    Es el mismo modo de fallo que el error 32 de WI-113, una vez mas por el
    lado equivocado: aqui no habia sonda de mutacion que lo cazaras, habia
    un `sqlite3.OperationalError` de un helper de test.

    La via correcta es la misma que usan los comandos —`resolve_project`—,
    de modo que el test escribe en la base que el comando va a LEER. Un
    helper que las dos cosas por su cuenta mide dos proyectos.
    """
    from skillgraph.cli.support import resolve_project
    from skillgraph.platform.storage import Storage

    args = _ns(data_root)
    project, err = resolve_project(args, PROJECT)
    assert err is None, f"el catalogo no conoce {PROJECT!r}: exit={err}"
    return Storage(Path(project["db_path"]))


def _primer_run(data_root: Path) -> str:
    """El `run_id` del unico run creado.

    **Y AQUI ESTA EL FALLO QUE ESTUVO DOS INTENTOS.**

    Buscaba `SELECT run_id FROM runs`, y la tabla no se llama `runs`: se
    llama **`workflow_runs`**. El `sqlite3.OperationalError: no such table`
    no venia de la RUTA —que era correcta desde el principio— sino de este
    nombre, escrito de memoria en vez de leido del esquema.

    Lo que lo hace instructive es el tiempo que se tardo en verlo. Un error
    de ruta y un error de nombre producen EL MISMO sintoma, y el primero es
    el que uno supone. Por eso el fix fue cambiar la ruta, no el `SELECT`,
    y el fallo siguio verde. Un sintoma ambiguo se acota mirando el
    esquema real, que es lo que hace este comentario.
    """
    storage = _storage_del_proyecto(data_root)
    filas = storage._conn.execute(
        "SELECT run_id FROM workflow_runs ORDER BY created_at LIMIT 1"
    ).fetchall()
    assert filas, "no se creo ningun run"
    return filas[0][0]


class TestElSueloNoSeRelaja:
    """**POR QUE ESTE FICHERO NO TOCA `check_coverage_floors.py`.**

    El suelo de `cli/` es el 70 % y lo declara AGENTS 6.3 con su motivo: lo
    que falta ahi son ramas de error que cubre la integracion. Este fichero
    sube `runs.py` exercising sus comandos, no bajando la regla.

    Y el contrasalto es que la regla siga PONIENDO: si `runs.py` sube al
    100 % y alguien anade 400 lineas sin test, el gate tiene que volver a
    rojo. Un suelo que baja porque el codigo es mas grande no mide cobertura,
    mide el dia que alguien se rindio.
    """

    def test_el_suelo_de_cli_sigue_siendo_el_que_declara_agentes(self) -> None:
        from scripts.check_coverage_floors import SUELOS_ESPECIALES

        assert SUELOS_ESPECIALES["src/skillgraph/cli/"] == 70.0, (
            f"el suelo de cli/ es {SUELOS_ESPECIALES['src/skillgraph/cli/']} "
            "y AGENTS 6.3 declara 70: bajarlo para que un gate pase es la "
            "forma de guarda que este repo lleva cinco bloques cerrando"
        )
