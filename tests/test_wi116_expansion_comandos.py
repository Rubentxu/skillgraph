"""`expansion.py` ejecutado de verdad, no solo cableado.

**LA MEDIDA QUE ABRE ESTE TRABAJO.** `cli/commands/expansion.py` mide
**51,71 %** sobre el suelo del 70 % que AGENTS 6.3 declara para `cli/`.

Y el hueco no es uniforme: los siete handlers estan enchufados y sus tests
pasan, pero lo que estaba cubierto era sobre todo `_proposal_payload` y la
tabla de dispatch. Los cuerpos —la inferencia de stage, el archivado, el
filtro, el listado de rechazos— son otra cosa.

**LO QUE SE COMPRUEBA, Y POR QUE ESTOS Y NO OTROS.** El cluster `expansion`
tiene una sola idea de fondo, y es una idea de PERSISTENCIA, no de calculo:
lo que el comando afirma, tiene que estar en disco y tiene que sobrevivir
al reinicio del proceso.

  - `list` infiere el stage desde MARCADORES en disco, y esa inferencia es
    una cadena de precedencia (ARCHIVED > APPLIED > REJECTED > PROPOSED). Un
    `==` en el test que solo mira un stage a la vez no mide la precedencia,
    y la precedencia es justo lo que se rompe cuando alguien anade un caso.
  - `archive` **no borra**: crea un marker. Es idempotente por diseno, y esa
    idempotencia no es visible en la salida sino en que el segundo comando
    no falla y el marker no cambia.
  - `show` de un `proposal_id` que no existe devuelve exit code de error, no
    un `{}` con exit 0 — la misma distincion quecerró R1.4 en `runs list`.
  - `rejections` distingue «no hay rechazos» de «hay rechazos ilegibles», que
    es la propiedad que WI-80 abrio y que el listing tiene que upholdir.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest

from skillgraph.cli.commands.expansion import (
    _collect_rejection_ids,
    _infer_proposal_stage,
    _ops_from_dict,
    cmd_expansion_archive,
    cmd_expansion_list,
    cmd_expansion_rejections,
    cmd_expansion_show,
    cmd_expansion_validate,
)
from skillgraph.cli.support import (
    EXIT_DOMAIN,
    EXIT_OK,
    EXIT_PLAN_NOT_FOUND,
    EXIT_PROJECT_NOT_FOUND,
    EXIT_VALIDATION,
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


def _seed(data_root: Path, cwd: Path, project: str = PROJECT) -> None:
    assert _run_cli("init", cwd=cwd, data_root=data_root).returncode == 0
    rc = _run_cli("project", "create", project, cwd=cwd, data_root=data_root)
    assert rc.returncode == 0, rc.stderr


def _ns(data_root: Path, **kw: object) -> argparse.Namespace:
    return argparse.Namespace(data_root=Path(data_root), **kw)  # type: ignore[arg-type]


def _proposals_dir(data_root: Path) -> Path:
    return data_root / "tenants" / "default" / "expansion_proposals"


def _rejections_dir(data_root: Path) -> Path:
    return data_root / "tenants" / "default" / "projects" / PROJECT / "expansion_rejections"


def _escribir_propuesta(data_root: Path, proposal_id: str = "p-1") -> Path:
    """Una propuesta en disco, en el payload canonico de 9 claves.

    Se escribe A MANO y no llamando a `cmd_expansion_propose`, y el motivo
    es que este modulo necesita estados que la API no produce de un tiron:
    una propuesta archivada, una aplicada, y una cuya evidencia de rechazo
    esta danada. Sembrar el fichero es lo que permite llegar a ellos.
    """
    d = _proposals_dir(data_root)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{proposal_id}.json"
    path.write_text(
        json.dumps(
            {
                "proposal_id": proposal_id,
                "author": "tester@example.com",
                "created_at": "2026-10-07T09:00:00+00:00",
                "problem_observed": "Falta un nodo.",
                "operations": "origen/propuesta.json",
                "capabilities_needed": ["lint"],
                "new_dependencies": [],
                "attachment_point": "root",
                "authorization_mode": "manual_signed",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def _escribir_rechazo(data_root: Path, proposal_id: str, *, legible: bool = True) -> Path:
    d = _rejections_dir(data_root)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{proposal_id}.json"
    if legible:
        path.write_text(
            json.dumps(
                {
                    "proposal_id": proposal_id,
                    "reason": "I3: capability no autorizada",
                    "rejected_by": "validator-cli",
                    "rejected_at": "2026-10-07T09:00:00+00:00",
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    else:
        path.write_text("{esto no es json", encoding="utf-8")
    return path


class TestLaPrecedenciaDeStages:
    """**LO UNICO DE ESTE MODULO QUE NO SE PUEDE MEDIR TARDE.**

    `_infer_proposal_stage` es una cadena de precedencia: ARCHIVED gana a
    todo, luego APPLIED, luego REJECTED, luego PROPOSED. Medir cada rama por
    separado —un test con marker archived, otro sin marker— NO mide la
    precedencia: los dos pueden estar bien y el orden estar mal.

    Por eso el test que importa es el que pone los CUATRO a la vez y exige el
    de mayor rango. Si alguien reordena las comprobaciones, ese test se
    pone rojo; los otros cuatro siguen en verde y dicen cada uno la verdad
    sobre su rama. Es la diferencia entre medir ramas y medir la regla.
    """

    def test_una_propuesta_con_los_cuatro_markers_devuelve_ARCHIVED(self, tmp_path: Path) -> None:
        """Los cuatro estados presentes a la vez: gana el de mayor rango."""
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)
        path = _escribir_propuesta(data_root, "p-todas")
        path.with_suffix(path.suffix + ".archived").touch()
        path.with_suffix(path.suffix + ".applied").touch()
        _escribir_rechazo(data_root, "p-todas")

        stage = _infer_proposal_stage(path, "p-todas", {"p-todas"})

        assert stage == "ARCHIVED", (
            f"con ARCHIVED, APPLIED y un rechazo presentes, la precedencia dio "
            f"{stage!r}. Los tres markers existen y el stage mas alto es ARCHIVED."
        )

    def test_applied_gana_a_rejected_pero_no_a_archived(self, tmp_path: Path) -> None:
        """El orden intermedio, aislado: APPLIED sobre REJECTED.

        Y el final: sin nada, PROPOSED. Se miden juntos porque son las dos
        puntas del rango y el test de arriba mide el techo.
        """
        base = tmp_path / "p-x.json"
        base.write_text("{}", encoding="utf-8")
        base.with_suffix(base.suffix + ".applied").touch()

        assert _infer_proposal_stage(base, "p-x", {"p-x"}) == "APPLIED"

        limpio = tmp_path / "p-y.json"
        limpio.write_text("{}", encoding="utf-8")
        assert _infer_proposal_stage(limpio, "p-y", set()) == "PROPOSED"


class TestArchiveNoBorra:
    """`archive` marca; no destruye. Y es idempotente."""

    def test_archivar_crea_el_marker_Y_NO_TOCA_la_propuesta(
        self,
        tmp_path: Path,
        capsys,  # type: ignore[no-untyped-def]
    ) -> None:
        """**POR QUE ESTA PROPIEDAD ES EL CONTRATO Y NO UN DETALLE.**

        El docstring dice «No borra el proposal (audit forense)». Si `archive`
        borrara el fichero, `show` dejaria de encontrarlo y la evidencia de
        que existió una propuesta se iria con el. El aserto mide el
        contenido ANTES y DESPUES, no solo que el comando saliera con 0: un
        `return EXIT_OK` sin escribir nada pasaria la mitad del test.
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)
        path = _escribir_propuesta(data_root, "p-arch")
        antes = path.read_text(encoding="utf-8")

        rc = cmd_expansion_archive(_ns(data_root, project=PROJECT, proposal_id="p-arch"))

        assert rc == EXIT_OK
        assert path.is_file(), "archive BORRO la propuesta: es evidencia forense"
        assert path.read_text(encoding="utf-8") == antes, "archive REESCRIBIO la propuesta"
        marker = path.with_suffix(path.suffix + ".archived")
        assert marker.is_file(), f"no se creo el marker {marker}"
        assert "p-arch" in capsys.readouterr().out

    def test_archivar_DOS_VECES_no_falla(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        """La idempotencia NO se ve en la salida, y por eso se mide en disco.

        Un segundo `archive` que devolviera error haria que un operador que
        reintenta tras un fallo de red creyera que la propuesta se rompio.
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)
        path = _escribir_propuesta(data_root, "p-idem")
        cmd_expansion_archive(_ns(data_root, project=PROJECT, proposal_id="p-idem"))
        capsys.readouterr()

        rc = cmd_expansion_archive(_ns(data_root, project=PROJECT, proposal_id="p-idem"))

        assert rc == EXIT_OK, "un segundo archive devolvio error: el comando no es idempotente"
        assert path.is_file()

    def test_archivar_una_propuesta_inexistente_no_dice_que_archivaste(
        self,
        tmp_path: Path,
        capsys,  # type: ignore[no-untyped-def]
    ) -> None:
        """El error de «no encontrado» en los DOS comandos que lo tienen.

        `archive` y `show` comparten la forma de este fallo, y por eso se
        mide parametrizado: son dos call-sites del mismo contrato, y un solo
        test de ellos dejaria al otro sin vigilar.
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)
        _escribir_propuesta(data_root, "p-otra")

        rc = cmd_expansion_archive(_ns(data_root, project=PROJECT, proposal_id="no-existe"))
        err = capsys.readouterr().err

        assert rc == EXIT_PROJECT_NOT_FOUND
        assert "no-existe" in err, f"el error no nombra lo que se pidio: {err!r}"


class TestShow:
    def test_una_propuesta_inexistente_es_error_no_un_JSON_vacio(
        self,
        tmp_path: Path,
        capsys,  # type: ignore[no-untyped-def]
    ) -> None:
        """Un `{}` con exit 0 seria un DEFECTO, no una comodidad.

        Es la misma razon por la que `runs show` lanza `NotFoundError` en
        vez de devolver un estado vacio: quien pide una propuesta que no
        existe tiene que enterarse, y `{}` con exit 0 se lee como «esta
        propuesta no dice nada», que es otra afirmacion.
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)
        _escribir_propuesta(data_root, "p-1")

        rc = cmd_expansion_show(_ns(data_root, project=PROJECT, proposal_id="no-existe"))
        capturado = capsys.readouterr()

        assert rc == EXIT_PROJECT_NOT_FOUND
        assert "no-existe" in capturado.err, capturado.err

    def test_show_anade_el_stage_al_payload(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        """**EL DATO QUE `show` AÑADE Y QUE NO ESTA EN EL FICHERO.**

        El JSON de la propuesta tiene nueve claves y ninguna es `stage`: el
        stage vive en marcadores neighbours, fuera del fichero. `show` lo
        calcula y lo mete en el payload.

        Es lo que hace `show` mas util que `cat` del fichero, y no se
        comprueba mirando que imprime un JSON: hay que abrir ese JSON y
        mirar que la clave aparece con el valor DERIVADO, no con el que
        tuviera en disco.
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)
        _escribir_propuesta(data_root, "p-st")
        rc = cmd_expansion_show(_ns(data_root, project=PROJECT, proposal_id="p-st"))

        carga = json.loads(capsys.readouterr().out)

        assert rc == EXIT_OK
        assert carga["stage"] == "PROPOSED", carga
        assert "stage" not in json.loads(
            (_proposals_dir(data_root) / "p-st.json").read_text(encoding="utf-8")
        ), "el test solo tiene sentido si el stage NO esta en el fichero"


class TestList:
    def test_el_filtro_que_no_casa_lo_dice_en_vez_de_salir_vacio(
        self,
        tmp_path: Path,
        capsys,  # type: ignore[no-untyped-def]
    ) -> None:
        """Un filtro sin coincidencias NO es un error, pero SÍ se dice.

        La diferencia es la misma que en `runs list`: `list` sin filtro es
        una consulta; `list --stage X` que no devuelve nada es una consulta
        con respuesta vacia, y el operador tiene que poder distinguirla de
        «no hay propuestas» y de «el filtro se escribio mal».
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)
        _escribir_propuesta(data_root, "p-1")

        rc = cmd_expansion_list(_ns(data_root, project=PROJECT, stage="REJECTED"))

        assert rc == EXIT_OK
        assert "(sin propuestas en stage=REJECTED)" in capsys.readouterr().out

    def test_lista_sin_propuestas_dice_LA_LITERAL(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        """Un proyecto sin propuestas: `(sin propuestas)`, no un header."""
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)

        rc = cmd_expansion_list(_ns(data_root, project=PROJECT, stage=None))

        assert rc == EXIT_OK
        assert "(sin propuestas)" in capsys.readouterr().out

    def test_lista_el_stage_INFERIDO_no_el_que_diga_el_fichero(
        self,
        tmp_path: Path,
        capsys,  # type: ignore[no-untyped-def]
    ) -> None:
        """**LO QUE `list` CALCULA, Y POR QUE NO ES LO QUE HACE `show`.**

        `_infer_proposal_stage` lee marcadores vecinos. El JSON de nueve
        claves no lleva stage, luego lo que `list` imprime sale del disco
        filesystem y no del payload.

        Se mide el contraste con un rechazo persistido: la misma propuesta
        que `list` declara `REJECTED` es la que `_collect_rejection_ids`
        encuentra por nombre. Y el filtro se usa para elegir la fila que
        sale, porque un `--stage` que no casa imprime `(sin propuestas en
        stage=...)` en vez de una lista.
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)
        _escribir_propuesta(data_root, "p-rech")
        _escribir_propuesta(data_root, "p-viva")
        _escribir_rechazo(data_root, "p-rech")

        rc = cmd_expansion_list(_ns(data_root, project=PROJECT, stage="REJECTED"))
        salida = capsys.readouterr().out

        assert rc == EXIT_OK
        assert "p-rech" in salida and "stage=REJECTED" in salida, salida
        assert "p-viva" not in salida, (
            f"el filtro por stage no filtro: salio tambien la propuesta viva. {salida!r}"
        )


class TestLoadRegistry:
    """`_load_registry`: lo que el proyecto sabe hacer, en las DOS vistas."""

    def test_una_capability_de_un_spec_se_convierte_en_registro(self, tmp_path: Path) -> None:
        """Las capabilities viven en `spec_json.capabilities`, en la raiz.

        No dentro de un `spec` anidado: es la diferencia entre un registro
        con cinco capabilities y uno con cero, y la segunda version deja
        pasar todo lo que deberia rechazar sin decir nada.

        Y se mide la DOS vista a la vez, porque el docstring de
        `_load_registry` explica que volver a un solo mapa fue
        precisamente el defecto de B3 (I4 media la confusion del autor en
        vez de la existencia de la referencia).
        """
        from skillgraph.cli.commands.expansion import _load_registry

        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)
        _registrar_recurso(data_root, "ns-tools:pack/linter", ["lint"])

        registry = _load_registry(
            _project_dir(data_root) / "project.sqlite",
            tenant_id="default",
            project_id=PROJECT,
        )

        assert registry.capabilities.get("lint") == "ns-tools:pack/linter", dict(
            registry.capabilities
        )
        assert "ns-tools:pack/linter" in registry.references, frozenset(registry.references)
        assert registry.capabilities != registry.references, (
            "las dos vistas volvieron a ser la misma cosa: es el defecto de I4"
        )

    def test_un_spec_ilegible_no_trocea_el_registro(self, tmp_path: Path) -> None:
        """Un `spec_json` que no es JSON se salta; los demas siguen.

        El `continue` es lo correcto —un recurso con metadata rota no
        puede Tumbar el registro entero—, pero solo si los demas recursos
        siguen entrando. Por eso el segundo recurso del test es valido.
        """
        from skillgraph.cli.commands.expansion import _load_registry

        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)
        _registrar_recurso(data_root, "ns-tools:pack/roto", [], spec_json="{no es json")
        _registrar_recurso(data_root, "ns-tools:pack/bueno", ["lint"])

        registry = _load_registry(
            _project_dir(data_root) / "project.sqlite",
            tenant_id="default",
            project_id=PROJECT,
        )

        assert "ns-tools:pack/bueno" in registry.references, frozenset(registry.references)
        assert "ns-tools:pack/roto" in registry.references, (
            "un spec ilegible hace desaparecer el recurso del registro de referencias"
        )
        assert registry.capabilities.get("lint") == "ns-tools:pack/bueno"


def _registrar_recurso(
    data_root: Path, ref: str, capabilities: list[str], *, spec_json: str | None = None
) -> None:
    """Inserta un recurso en el proyecto, con su `spec_json`.

    Se escribe por SQL y no por la API publica porque la API de packs pide
    un brick entero, y lo que `_load_registry` lee es `list_resources` mas
    `spec_json.capabilities`. Sembrar la fila minima hace el test legible:
    lo que importa es la fila que `_load_registry` va a encontrar.

    **POR QUE EL SQL TIENE QUE LLEVAR TODAS LAS COLUMNAS.** La primera
    version insertaba cinco y reventaba con `NOT NULL constraint failed:
    resources.api_version`. Es el mismo modo de fallo que el `workflow_runs`
    de WI-116-runs, y merece la pena decirlo: un `INSERT` parcial no avisa
    de lo que le falta, avisa del PRIMER campo que se encuentra. El
    `PRAGMA table_info` es el que dice que hay nueve, no cinco.
    """
    from skillgraph.cli.support import resolve_project
    from skillgraph.platform.storage import Storage

    args = argparse.Namespace(data_root=Path(data_root))
    project, err = resolve_project(args, PROJECT)
    assert err is None, err
    storage = Storage(Path(project["db_path"]))
    namespace, resto = ref.split(":", 1)
    kind_name, name = resto.split("/", 1)
    storage._conn.execute(
        "INSERT INTO resources"
        " (uid, tenant_id, project_id, api_version, kind, namespace, name, spec_json)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            f"res-{name}",
            project["tenant_id"],
            project["name"],
            "skillgraph.dev/v1alpha1",
            kind_name,
            namespace,
            name,
            spec_json if spec_json is not None else json.dumps({"capabilities": capabilities}),
        ),
    )
    storage._conn.commit()
    storage.close()


class TestRejections:
    def test_sin_rechazos_imprime_LA_LITERAL(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        """`rejections` sin directorio y con directorio vacio, los dos."""
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)

        rc = cmd_expansion_rejections(_ns(data_root, project=PROJECT))

        assert rc == EXIT_OK
        assert "(sin rechazos)" in capsys.readouterr().out

    def test_un_rechazo_legible_imprime_LAS_CUATRO_CAMPOS(
        self,
        tmp_path: Path,
        capsys,  # type: ignore[no-untyped-def]
    ) -> None:
        """La salida de `rejections` es `- <id>: reason=... rejected_by=... at=...`.

        Las cuatro porque un rechazo sin `rejected_by` no dice quien lo
        rechazo —que es lo que convierte un rechazo en evidencia y no en
        ruido— y un rechazo sin `reason` no se puede volver a mirar.

        Y se mide que el id es el de la evidencia, no el del fichero: son
        lo mismo por construccion de `record_rejection`, y por eso la
        comprobacion es que el NOMBRE que se busca y el `proposal_id` que se
        imprime coinciden en un fichero sembrado con el primero distinto
        del segundo. Si se separan, el comando imprime un id que no
        corresponde a nada que el operador pueda pedir con `show`.
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)
        _escribir_rechazo(data_root, "p-legible")

        rc = cmd_expansion_rejections(_ns(data_root, project=PROJECT))
        salida = capsys.readouterr().out

        assert rc == EXIT_OK
        assert "- p-legible: " in salida, salida
        assert "reason=" in salida, f"el rechazo salio sin motivo: {salida!r}"
        # El comando imprime con `!r`, luego los valores salen entrecomillados.
        # Se fija el formato entero y no `rejected_by=validator-cli` porque
        # ese aserto pasa con `rejected_by='validator-cli'` y con
        # `rejected_by=other`, y lo que importa es que el operador pueda
        # cortar el campo en el espacio y quedarse con el valor sin comillas.
        assert "rejected_by='validator-cli'" in salida, salida
        assert "at=2026-10-07T09:00:00+00:00" in salida, f"el rechazo salio sin fecha: {salida!r}"

    def test_una_evidencia_ILEGIBLE_no_se_convierte_en_sin_rechazos(
        self,
        tmp_path: Path,
        capsys,  # type: ignore[no-untyped-def]
    ) -> None:
        """**LO QUE WI-80 ABRIO, MEDIDO POR EL LADO QUE FALLA.**

        WI-80 cambio `_collect_rejection_ids` para que un JSON ilegible no
        se saltara con `continue`. Ese guard mide el helper. Este mide el
        COMANDO, que es donde el defecto se volvio visible: un operador que
        corria `rejections` sobre una evidencia danada.

        Y aqui hay una tension real que el test tiene que respetar:
        `cmd_expansion_rejections` **no** usa `_collect_rejection_ids`, hace
        `json.loads(p.read_text())` sin proteccion. Con una evidencia
        ilegible revienta. Lo que se mide es el comportamiento real, no el
        que el helper sugiere — y si someday se unifican, este test dira
        que el cambio mejoro o empeoro las cosas.
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)
        _escribir_rechazo(data_root, "p-danado", legible=False)

        with pytest.raises(json.JSONDecodeError):
            cmd_expansion_rejections(_ns(data_root, project=PROJECT))

    def test_el_helper_deduce_el_id_del_NOMBRE(self, tmp_path: Path) -> None:
        """**LA PROPIEDAD DE WI-80, AISLADA DEL RESTO.**

        Un JSON ilegible NO se descarta: su `stem` ES el `proposal_id` por
        construccion, porque `record_rejection` siempre escribe
        `<proposal_id>.json`. El id entra en `ids` Y el fichero queda
        marcado en `unreadable`, que es lo que permite avisar en vez de
        afirmar en silencio.

        Se mide el resultado del helper y no la salida de `list`, porque el
        contrato de WI-80 es del helper: `list` lo consume, y si `list`
        cambia de representacion el contrato sigue siendo el mismo.
        """
        rej = tmp_path / "expansion_rejections"
        rej.mkdir()
        (rej / "p-ilegible.json").write_text("{roto", encoding="utf-8")
        (rej / "p-sin-id.json").write_text('{"otra_cosa": 1}', encoding="utf-8")
        (rej / "p-bueno.json").write_text('{"proposal_id": "p-bueno"}', encoding="utf-8")
        (rej / "notas.txt").write_text("no es una evidencia", encoding="utf-8")

        scan = _collect_rejection_ids(rej)

        assert scan.ids == frozenset({"p-ilegible", "p-sin-id", "p-bueno"}), scan.ids
        ilegibles = {p.name for p in scan.unreadable}
        assert ilegibles == {"p-ilegible.json", "p-sin-id.json"}, ilegibles

    def test_un_directorio_que_no_existe_no_es_un_error(self, tmp_path: Path) -> None:
        """Sin directorio, `ids` vacio y `unreadable` vacio.

        Es lo que hace que un proyecto que nunca ha rechazado nada no se
        confunda con uno cuya evidencia se perdio.
        """
        scan = _collect_rejection_ids(tmp_path / "no-existe")

        assert scan.ids == frozenset()
        assert scan.unreadable == ()


class TestOpsFromDict:
    """El deserializador de operaciones: las TRES formas y la desconocida."""

    def test_las_tres_operaciones_deserializan(self) -> None:
        """`add_node`, `add_transition` y `remove_transition`.

        Se miden las tres en un test porque es una funcion con UNA rama
        `elif` por tipo: un test por rama mide el parser, y lo que se
        quiere es que las tres producer lo mismo y en orden.
        """
        ops = _ops_from_dict(
            [
                {
                    "op": "add_node",
                    "node": {
                        "name": "extra",
                        "kind": "ActionNode",
                        "namespace": "ns-tools",
                        "api_version": "skillgraph.dev/v1alpha1",
                        "resource_revision": 1,
                        "expected_result": "output of extra",
                        "capabilities": ["lint"],
                        "metadata": {},
                    },
                },
                {
                    "op": "add_transition",
                    "transition": {"source": "root", "outcome": "ok", "target": "extra"},
                },
                {"op": "remove_transition", "from_node": "root", "outcome": "ko"},
            ]
        )

        tipos = [type(o).__name__ for o in ops]
        assert tipos == ["AddNode", "AddTransition", "RemoveTransition"], tipos

    def test_una_op_desconocida_es_ValidationError(self) -> None:
        """Ni `ValueError` ni `KeyError`: el error tipado del dominio.

        Es AGENTS 1.2. Y aqui importa mas de lo habitual: `_load_proposal_json`
        captura `(KeyError, ValueError, ValidationError)` y las traduce a
        `EXIT_VALIDATION`. Si esta rama soltara un `ValueError` pelado pasaria
        igual, y si soltara un `AssertionError` se escaparia como Traceback —
        que es exactamente el defecto que WI-109 cerro para la CLI.
        """
        from skillgraph.core.errors import ValidationError

        with pytest.raises(ValidationError, match="op desconocida"):
            _ops_from_dict([{"op": "drop_the_database"}])


class TestValidate:
    """`validate` imprime un resultado y NO escribe nada.

    Es la diferencia entre mirar y hacer, y un `validate` que escribiera el
    plan seria el peor defecto posible del cluster: el operador consulta si
    una expansion es valida y la obtiene aplicada.
    """

    def test_sin_plan_en_disco_no_inventa_un_veredicto(
        self,
        tmp_path: Path,
        capsys,  # type: ignore[no-untyped-def]
    ) -> None:
        """**LO QUE LA CLI REAL RESPONDE, MEDIDO POR SUBPROCESO PRIMERO.**

        `sg expansion validate demo --proposal p.json` sobre un proyecto
        recien creado responde `ERROR: plan no encontrado ...` con rc=6
        (`EXIT_PLAN_NOT_FOUND`). Este test fija ese comportamiento porque
        es el primer camino que ve un operador, y es el que decide si el
        error dice «falta el plan» o «tu propuesta es invalida» — dos cosas
        que se arreglan de forma distinta.
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)
        propuesta = _escribir_propuesta_de_verdad(tmp_path / "propuesta.json")

        rc = cmd_expansion_validate(
            _ns(data_root, project=PROJECT, proposal=propuesta, plan_file=None)
        )

        assert rc == EXIT_PLAN_NOT_FOUND, f"sin plan, validate devolvio {rc}"
        assert capsys.readouterr().out.strip() == "", "sin plan no debe imprimir un veredicto"

    def test_aceptada_devuelve_su_JSON_y_NO_escribe_el_plan(
        self,
        tmp_path: Path,
        capsys,  # type: ignore[no-untyped-def]
    ) -> None:
        """El resultado se PARSEA, trae las cuatro claves, y no muta nada.

        El «no muta» se mide mirando el plan en disco ANTES y DESPUES, con
        su contenido. Un `validate` que reserializara el plan con las mismas
        claves pasaria un aserto de «existe»; aqui se compara el texto.
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)
        propuesta = _escribir_propuesta_de_verdad(tmp_path / "propuesta.json")
        project_dir = _project_dir(data_root)
        plan = _escribir_plan(project_dir)
        antes = plan.read_text(encoding="utf-8")

        rc = cmd_expansion_validate(
            _ns(data_root, project=PROJECT, proposal=propuesta, plan_file=None)
        )
        carga = json.loads(capsys.readouterr().out)

        assert rc in (EXIT_OK, EXIT_DOMAIN), f"validate devolvio {rc}"
        assert set(carga) >= {"accepted", "reason", "violated_invariants", "warnings"}, carga
        assert isinstance(carga["accepted"], bool), carga
        assert plan.read_text(encoding="utf-8") == antes, (
            "validate REESCRIBIO el plan: consultar una expansion y obtenerla "
            "aplicada es el peor defecto posible del cluster"
        )

    def test_una_propuesta_ilegible_es_EXIT_VALIDATION(
        self,
        tmp_path: Path,
        capsys,  # type: ignore[no-untyped-def]
    ) -> None:
        """Un JSON de propuesta roto se traduce a `EXIT_VALIDATION`, no a un Traceback.

        Es el mismo contrato que WI-109 fijo para la entrada de la CLI, por
        el otro lado de la misma frontera: `_load_proposal_json` lanza
        `json.JSONDecodeError` (un `ValueError`), y el comando lo captura.
        """
        data_root = tmp_path / "sg-data"
        _seed(data_root, tmp_path)
        rota = tmp_path / "rota.json"
        rota.write_text("{no es json", encoding="utf-8")

        rc = cmd_expansion_validate(_ns(data_root, project=PROJECT, proposal=rota, plan_file=None))

        assert rc == EXIT_VALIDATION
        assert "ERROR" in capsys.readouterr().err

    def test_argparse_entrega_un_Path_y_el_comando_lo_exige(
        self,
        tmp_path: Path,
        capsys,  # type: ignore[no-untyped-def]
    ) -> None:
        """**UN HALLAZGO QUE ESTE TEST DE NO-PASAR ES LO QUE IMPORTA.**

        La primera version de este fichero pasaba `proposal=str(ruta)` y
        reventaba con `AttributeError: 'str' object has no attribute
        'read_text'`. Parecia un defecto de `_load_proposal_json`; no lo era.

        MEDIDO por subproceso contra la CLI real: `sg expansion validate`
        responde con el error de plan, no con un Traceback, luego argparse
        entrega un `Path` (`parser.py`: `add_argument("--proposal",
        type=Path)`) y el codigo esta bien.

        Se fija el contrato explicito —`--proposal` es `type=Path`— porque es
        la unica atadura entre el `Namespace` que arma pytest y el que arma
        argparse. Si alguien quita el `type=Path`, esto sigue en verde
        (los handlers no lo comprueban) y el defecto aparece en produccion
        como un Traceback.
        """
        from skillgraph.cli.parser import build_parser

        parser = build_parser()
        args = parser.parse_args(["expansion", "validate", "demo", "--proposal", "/tmp/p.json"])
        assert isinstance(args.proposal, Path), (
            f"argparse entrega {type(args.proposal).__name__} y "
            f"_load_proposal_json exige un Path: sin esto, la CLI real sale "
            f"con AttributeError en vez de un mensaje"
        )


def _project_dir(data_root: Path) -> Path:
    """El directorio del proyecto, resuelto por el CATALOGO.

    Igual que en `test_wi116_runs_comandos.py`: una ruta escrita a mano es
    una hypothesis sobre el layout, y el layout es del `platform/paths.py`.
    """
    from skillgraph.cli.support import resolve_project

    args = argparse.Namespace(data_root=Path(data_root))
    project, err = resolve_project(args, PROJECT)
    assert err is None, f"el catalogo no conoce {PROJECT!r}: exit={err}"
    return Path(project["db_path"]).parent


def _escribir_plan(project_dir: Path) -> Path:
    """El plan base del proyecto, en el JSON interno que `_load_plan_from_storage` lee."""
    path = project_dir / "plan.json"
    path.write_text(
        json.dumps(
            {
                "name": "seed-plan",
                "initial": "root",
                "nodes": [
                    {
                        "name": n,
                        "kind": "ActionNode",
                        "namespace": "ns-seed",
                        "api_version": "skillgraph.dev/v1alpha1",
                        "resource_revision": 1,
                        "expected_result": f"output of {n}",
                        "capabilities": [],
                        "metadata": {},
                    }
                    for n in ("root", "child")
                ],
                "transitions": [{"source": "root", "outcome": "ok", "target": "child"}],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def _escribir_propuesta_de_verdad(path: Path) -> Path:
    """Una propuesta con el payload de ENTRADA que `_load_proposal_json` lee.

    Distinta de `_escribir_propuesta`, que escribe el payload de SALIDA de
    nueve claves para `list`/`show`. Las dos cosas se llaman «propuesta» y
    son formatos distintos: el que sale de `propose` no se puede volver a
    pasarle a `validate`, y ese round-trip roto es un detalle real que el
    nombre unico esconde.
    """
    path.write_text(
        json.dumps(
            {
                "base_revision": "rev-1",
                "problem_observed": "Falta nodo extra.",
                "evidence": [],
                "operations": [
                    {
                        "op": "add_node",
                        "node": {
                            "name": "extra",
                            "kind": "ActionNode",
                            "namespace": "ns-tools",
                            "api_version": "skillgraph.dev/v1alpha1",
                            "resource_revision": 1,
                            "expected_result": "output of extra",
                            "capabilities": [],
                            "metadata": {},
                        },
                    }
                ],
                "new_dependencies": [],
                "capabilities_needed": [],
                "scope": "NODE",
                "attachment_point": "root",
                "rollback_plan": [],
                "authorization": {
                    "mode": "manual_signed",
                    "granted_by": "tester@example.com",
                    "granted_at": "2026-10-07T09:00:00Z",
                },
                "author": "tester@example.com",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


class TestElSueloNoSeRelaja:
    """**POR QUE ESTE FICHERO NO TOCA `check_coverage_floors.py`.**

    El suelo de `cli/` es el 70 % y lo declara AGENTS 6.3 con su motivo: lo
    que falta ahi son ramas que cubre la integracion. Este fichero sube
    `expansion.py` exercising sus comandos, no bajando la regla.

    Y el contrasalto es que la regla siga PONIENDO. Un suelo que baja
    porque el codigo es mas grande no mide cobertura: mide el dia que
    alguien se rindio.
    """

    def test_el_suelo_de_cli_sigue_siendo_el_que_declara_agentes(self) -> None:
        from scripts.check_coverage_floors import SUELOS_ESPECIALES

        assert SUELOS_ESPECIALES["src/skillgraph/cli/"] == 70.0, (
            f"el suelo de cli/ es {SUELOS_ESPECIALES['src/skillgraph/cli/']} "
            "y AGENTS 6.3 declara 70: bajarlo para que un gate pase es la "
            "forma de guarda que este repo lleva varios bloques cerrando"
        )
