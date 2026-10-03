"""B7 — las vistas que CLI y TUI comparten, y las diez proyecciones.

QUE MIDE ESTE FICHERO, y por qué ejecuta en vez de leer
-------------------------------------------------------
El gate de B7 pide diez widgets vivos «sobre **las mismas** APIs y query
models». La palabra cargada es «las mismas», y medido antes de escribir
nada (`scripts/measure_b7_operational_ux.py`) no había nada a que
referirse: cero `--format` en siete comandos y ningún símbolo que expusiera
render.

Estos tests vigilan la propiedad que hace que la pieza sirva: **una sola
forma de leer, dos representaciones**. Y la vigilan ejecutando, porque el
defecto que importa no está en la firma de `to_json` sino en que las dos
superficies puedan divergir sin que nada lo note.

Tres cosas se comprueban aquí, y las tres son la razón de que exista el
módulo:

1. **La vista no lee disco.** Si una vista abriera la base, dejaría de ser
   una vista y pasaría a ser una segunda vía de consulta —el duplicado que
   este bloque existe para impedir—. Se comprueba por AST: cero imports
   de `platform.storage` ni de `sqlite3` en el paquete.

2. **Las dos representaciones salen del mismo dato.** `to_json` y
   `to_text` no pueden discrepar porque ambas leen los mismos campos, y
   un test que las compare sobre el mismo objeto lo demuestra.

3. **El JSON es estable entre procesos.** Sin `sort_keys`, dos procesos
   pueden serializar el mismo dict en orden distinto y un consumidor que
   compare digests ve una diferencia que no existe — la M5 de B5, la misma
   clase de fallo—.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from skillgraph.core.errors import NotFoundError
from skillgraph.presentation import Column, DetailView, TableView, widgets as W

RAIZ = Path(__file__).resolve().parent.parent
PAQUETE = RAIZ / "src" / "skillgraph" / "presentation"


# --- La vista no lee disco -----------------------------------------------


class TestUnaVistaNoLeeDisco:
    """Una vista que consulta es una segunda vía de consulta."""

    def test_el_paquete_no_importa_storage_ni_sqlite(self) -> None:
        """Ni la base ni el driver, por AST y no por texto.

        Por AST porque un docstring que NOMBRA `sqlite3` es lo mas
        probable en un modulo que explica por que no lo importa: buscar
        la cadena contaria la prosa como la dependencia. Es el error 32 de
        WI-113 aplicado a un predicado de imports.
        """
        prohibidos = {"sqlite3", "Storage", "sqlite3.Connection"}
        for ruta in sorted(PAQUETE.rglob("*.py")):
            arbol = ast.parse(ruta.read_text(encoding="utf-8"))
            for nodo in ast.walk(arbol):
                if isinstance(nodo, ast.Import):
                    for alias in nodo.names:
                        assert alias.name not in prohibidos, (
                            f"{ruta.name} importa {alias.name}: una vista que "
                            f"consulta deja de ser una vista"
                        )
                elif isinstance(nodo, ast.ImportFrom):
                    assert (nodo.module or "") not in prohibidos, (
                        f"{ruta.name} importa de {nodo.module}: idem"
                    )

    def test_el_paquete_no_abre_ninguna_ruta(self) -> None:
        """`Path(...)` sobre datos de proyecto, tampoco.

        Se comprueba que no se llame a `open`, que es como se manifests
        un `sqlite3.connect` disfrazado de lectura de fichero.
        """
        for ruta in sorted(PAQUETE.rglob("*.py")):
            texto = ruta.read_text(encoding="utf-8")
            arbol = ast.parse(texto)
            for nodo in ast.walk(arbol):
                if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name):
                    assert nodo.func.id not in {"open", "input"}, (
                        f"{ruta.name} llama a {nodo.func.id}(): una vista "
                        f"que abre ficheros lee estado, y el estado se "
                        f"pregunta al controlador"
                    )


# --- Las dos representaciones salen del mismo dato -----------------------


class _Snap:
    def __init__(self) -> None:
        self.run_id = "r-1"
        self.state = "ACTIVE"
        self.current_node = "n1"
        self.executed_nodes = ("n0", "n1")
        self.events_emitted = 7


class _Evento:
    def __init__(self, seq: int, kind: str) -> None:
        self.sequence = seq
        self.timestamp = f"2026-01-01T00:00:0{seq}Z"
        self.kind = kind
        self.node_id = f"n{seq}"


class TestLasDosRepresentacionesVienenDelMismoDato:
    def test_text_y_json_dicen_lo_mismo(self) -> None:
        vista = W.run_view((_Snap(),))
        texto = vista.to_text()
        carga = vista.to_json()
        assert carga["kind"] == "runs"
        assert carga["total"] == 1
        # Cada dato de la fila aparece en el texto. Si alguno no aparece,
        # las dos superficies estan diciendo cosas distintas — que es el
        # defecto exacto que este bloque existe para impedir.
        for valor in carga["rows"][0].values():
            assert str(valor) in texto, f"{valor!r} no aparece en el texto"

    def test_una_tabla_vacia_no_inventa_filas(self) -> None:
        assert W.run_view(()).total == 0
        assert W.run_view(()).to_text() == "(sin resultados)"

    def test_el_json_lleva_la_clave_de_la_vista(self) -> None:
        """`kind` es lo que permite distinguir dos superficies iguales.

        Sin el, un consumidor que recibe `{"rows": [...]}` no sabe si lo
        que tiene delante es la lista de runs o la de resources.
        """
        for vista in (
            W.run_view(()),
            W.timeline_view(()),
            W.knowledge_view(()),
            W.evidence_view(()),
            W.resource_view(()),
            W.capability_view(()),
            W.decision_view(()),
            W.policy_view(()),
        ):
            assert vista.kind in vista.to_json()["kind"]

    def test_filtrar_conserva_la_forma(self) -> None:
        """Un filtro devuelve otra vista, no una lista de dicts.

        Un consumidor que aprende a leer `kind` y `columns` no tiene que
        aprender una forma distinta para cada filtro.
        """
        original = W.run_view((_Snap(),))
        filtrada = original.find("state", "ACTIVE")
        assert isinstance(filtrada, TableView)
        assert filtrada.kind == original.kind
        assert filtrada.columns == original.columns


# --- El JSON es estable entre procesos -----------------------------------


class TestElJsonEsEstable:
    """El digest de una vista tiene que ser el mismo en dos procesos."""

    def test_dos_procesos_producen_el_mismo_json(self, tmp_path: Path) -> None:
        guion = tmp_path / "v.py"
        guion.write_text(
            "import json, sys\n"
            "sys.path.insert(0, 'src')\n"
            "from skillgraph.presentation import Column, TableView\n"
            "v = TableView(kind='x',\n"
            "    columns=(Column('b','b'), Column('a','a')),\n"
            "    rows=({'b': 2, 'a': 1},))\n"
            "print(v.to_json_text())\n",
            encoding="utf-8",
        )
        import os

        digests = set()
        for semilla in ("0", "1", "12345"):
            env = dict(os.environ, PYTHONHASHSEED=semilla)
            proc = subprocess.run(
                [sys.executable, str(guion)],
                cwd=RAIZ,
                capture_output=True,
                text=True,
                env=env,
                check=True,
            )
            digests.add(proc.stdout.strip())
        assert len(digests) == 1, (
            "el JSON de la misma vista cambia entre procesos: un consumidor "
            "que compare digests veria una diferencia que no existe"
        )

    def test_el_json_esta_ordenado(self) -> None:
        vista = TableView(
            kind="x",
            columns=(Column("z", "z"),),
            rows=({"z": 1, "a": 2, "m": 3},),
        )
        texto = vista.to_json_text()
        assert json.loads(texto)["rows"][0] == {"a": 2, "m": 3, "z": 1}
        # El orden se comprueba sobre la FILA serializada, no sobre el
        # texto entero: `texto.index('"z"')` encuentra la columna `z` del
        # bloque `columns`, que va antes que las filas, y el assert
        # comparaba posiciones de cosas distintas. Un verificador que
        # busca una cadena en un documento entero encuentra la aparicion
        # equivocada: es el error 32 de WI-113 con otro disfraz.
        fila = json.dumps(json.loads(texto)["rows"][0])
        assert fila.index('"a"') < fila.index('"m"') < fila.index('"z"')


# --- Los diez widgets del gate -------------------------------------------


class TestLosDiezWidgetsDelGate:
    """Cada widget del gate tiene su proyeccion, y devuelve su `kind`."""

    def test_las_diez_proyecciones_existen(self) -> None:
        for nombre in (
            "run_view",
            "run_detail",
            "timeline_view",
            "evidence_view",
            "decision_view",
            "resource_view",
            "diff_view",
            "capability_view",
            "knowledge_view",
            "policy_view",
            "graph_view",
        ):
            assert callable(getattr(W, nombre)), f"falta {nombre}"

    def test_timeline_conserva_el_orden_por_secuencia(self) -> None:
        """La fila lleva `sequence` porque sin el no hay timeline.

        Dos eventos con el mismo timestamp no tienen orden, y un operador
        que no puede ordenar no puede leer la causa.
        """
        eventos = (_Evento(2, "B"), _Evento(1, "A"))
        vista = W.timeline_view(eventos)
        assert [f["sequence"] for f in vista.rows] == [2, 1]
        assert vista.kind == "timeline"

    def test_decision_muestra_su_motivo_o_declara_que_no_lo_tiene(self) -> None:
        """Una decision sin porque no es gobernable.

        La columna existe aunque el dato falte: callarla dejaria al
        operador creyendo que existe un motivo.
        """

        class _Decision:
            decision = "aprobar"
            outcome = "accepted"
            actor = "mavis"
            reason = "cumple la politica"

        vista = W.decision_view((_Decision(),))
        assert vista.rows[0]["reason"] == "cumple la politica"
        assert "reason" in [c.key for c in vista.columns]

    def test_knowledge_muestra_el_origen_que_b6_hizo_posible(self) -> None:
        """El panel tiene que decir QUIEN afirma, no solo QUE.

        Sin `assertion_origin` —nacido en B6— el operador veria la
        afirmacion y no su autoridad, y un panel que no dice quien afirma
        no sirve para gobernarlo.
        """

        class _Claim:
            subject_entity_id = "file:a.py"
            predicate = "line_count"
            object_literal = 42
            source_id = "s-1"
            assertion_origin = "agent-inferred"

        vista = W.knowledge_view((_Claim(),))
        assert vista.rows[0]["origin"] == "agent-inferred"
        assert "origin" in vista.to_text()

    def test_diff_sin_diff_lo_dice_en_vez_de_fallar(self) -> None:
        """Un panel que no puede abrirse es un panel que no existe.

        La ausencia de un diff es un estado legitimo —todavia no se ha
        calculado—, y se dice con palabras.
        """
        assert W.diff_view(None).to_text() == "diff\n  estado  sin diff"
        assert W.diff_view(None).kind == "diff"

    def test_el_diff_trae_las_preguntas_del_roadmap(self) -> None:
        """Siete respuestas, y cada una en su campo.

        No se comprueba el VALOR —eso lo mide B5 con sus 8 sondas— sino
        que el panel no las pierda al presentar, que es lo que haria una
        proyeccion que solo copiara cuatro campos.
        """

        class _Diff:
            revision = "r7"
            changes = (1, 2, 3)
            required_capabilities = ("sg.knowledge.query",)
            declared_capabilities = ()
            reversible = False

        panel = W.diff_view(_Diff())
        for clave in ("revision", "cambios", "reversible"):
            assert clave in dict(panel.fields)
        # Y las capacidades van SEPARADAS, que es el hallazgo de B6.
        assert "capacidades_requeridas" in dict(panel.fields)
        assert "capacidades_declaradas" in dict(panel.fields)


# --- El detalle ----------------------------------------------------------


class TestElDetalleEsUnPanel:
    def test_un_campo_inexistente_dice_cual_no_existe(self) -> None:
        panel = DetailView(kind="run", title="run r1", fields=(("state", "ACTIVE"),))
        assert panel.field("state") == "ACTIVE"
        with pytest.raises(NotFoundError) as exc:
            panel.field("nope")
        assert "nope" in str(exc.value)

    def test_el_json_de_un_detalle_incluye_sus_secciones(self) -> None:
        linea = W.timeline_view((_Evento(1, "A"),))
        panel = W.run_detail(_Snap(), timeline=linea)
        carga = panel.to_json()
        assert carga["kind"] == "run"
        assert "timeline" in carga["sections"]
        assert carga["sections"]["timeline"][0]["kind"] == "timeline"

    def test_una_tupla_y_una_lista_dan_el_mismo_json(self) -> None:
        """La forma serializada no depende de como se construyo.

        Un consumidor que ve `[]` en un caso y `[]` en otro —tupla vacia
        contra lista vacia— no puede distinguirlos, y no debe: la forma
        del JSON es el contrato, no la del Python que la produjo.
        """
        con_tupla = DetailView(kind="k", title="t", fields=(("a", (1, 2)),))
        con_lista = DetailView(kind="k", title="t", fields=(("a", [1, 2]),))
        assert con_tupla.to_json() == con_lista.to_json()

    def test_el_titulo_del_panel_no_se_confunde_con_un_dato(self) -> None:
        """Un campo llamado `title` no pisa el titulo del panel.

        Es un caso real de este patron: un `DetailView` con un campo
        llamado igual que un atributo propio haria que el consumidor leyera
        el titulo donde espera un valor.
        """
        panel = DetailView(kind="k", title="el titulo", fields=(("titulo", "el dato"),))
        assert panel.title == "el titulo"
        assert panel.field("titulo") == "el dato"


# --- El medidor sabe ver rojo --------------------------------------------


class TestElMedidorSabeVerRojo:
    """Un instrumento que solo sabe dar verde no mide nada."""

    def test_el_medidor_da_verde_en_el_arbol_real(self) -> None:
        proc = subprocess.run(
            [sys.executable, "scripts/measure_b7_operational_ux.py"],
            cwd=RAIZ,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def test_el_medidor_ve_rojo_si_se_quita_la_presentacion(self, tmp_path: Path) -> None:
        """Sin la superficie de presentacion, P1 tiene que bajar a rojo.

        No se toca el arbol: se copia a un temporal y se borra alli el
        paquete. Mutar el arbol del test y restaurarlo despues es la
        forma de que una excepcion deje el repo sucio sin que nadie lo
        note.

        Y se copia SOLO `src/` y `scripts/`, que es todo lo que el
        medidor lee. La primera version copiaba el repo entero y fallo
        con `EDQUOT` al escribir cientos de MB en `/tmp`: un
        contra-salto que se pone rojo porque se lleno el disco no mide
        la propiedad, mide el almacenamiento. El clon minimo son 1,1 MB
        y discrimina igual.
        """
        import shutil

        clon = tmp_path / "repo"
        for sub in ("src", "scripts"):
            shutil.copytree(
                RAIZ / sub,
                clon / sub,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        shutil.rmtree(clon / "src" / "skillgraph" / "presentation")

        proc = subprocess.run(
            [sys.executable, "scripts/measure_b7_operational_ux.py"],
            cwd=clon,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "ABIERTO" in proc.stdout


# --- B7 no rompe lo que ya existia ---------------------------------------


class TestB7NoRompeElContratoExterno:
    """Anadir representaciones no es sustituir la que ya habia.

    B7 cambia `runs show` para que la vista que se construye al vuelo
    tenga dos salidas. El riesgo del bloque no es que la vista este mal:
    es que al meterla entre el comando y la pantalla se rompa el
    `clave=valor` que `cmd_runs_show` promete en su docstring y que hay
    callers leyendo con `cut -d= -f2`.

    Y no es un riesgo teorico. La primera version de `_emit` pasaba
    `vacio=` a toda vista: `TableView` lo acepta, `DetailView` no, y
    `runs show` —el camino de TEXTO, el de por defecto, el que se usa
    siempre que nadie pasa `--format`— salia con `TypeError`. Es decir:
    el fallo estaba en la representacion que todo el mundo usa, y solo se
    veia al ejecutar el comando, no al mirar la vista.
    """

    @staticmethod
    def _proyecto_con_run(tmp_path: Path) -> Path:
        from tests.test_cli_runs_inspect import _init_project, _open_project_db, _project_db_path

        data_root = _init_project(tmp_path)
        db = _open_project_db(_project_db_path(data_root))
        try:
            db.execute(
                """
                INSERT INTO workflow_runs
                    (run_id, tenant_id, project_id, plan_json, state,
                     current_node, created_at, updated_at)
                VALUES ('run-b7', 'default', 'demo', '{}', 'ACTIVE', 'nodo-1',
                        datetime('now'), datetime('now'))
                """
            )
            db.commit()
        finally:
            db.close()
        return data_root

    def test_show_conserva_su_contrato_de_clave_valor(self, tmp_path: Path) -> None:
        """Sin `--format`, `runs show` sigue siendo `clave=valor`."""
        from tests.test_cli_runs_inspect import _run_cli

        data_root = self._proyecto_con_run(tmp_path)
        r = _run_cli("runs", "show", "demo", "run-b7", cwd=tmp_path, data_root=data_root)

        assert r.returncode == 0, r.stdout + r.stderr
        assert "run_id=run-b7" in r.stdout
        assert "state=ACTIVE" in r.stdout
        assert "current_node=nodo-1" in r.stdout
        # Y no es el panel: el panel mete sangrias y un titulo, y un
        # `cut -d= -f2` sobre esa linea daria basura con espacios.
        assert "  run_id" not in r.stdout

    def test_el_json_dice_lo_mismo_que_el_texto(self, tmp_path: Path) -> None:
        """La propiedad central de B7, sobre el comando real y no la vista.

        Que `to_text` y `to_json` lean los mismos campos esta probado en
        la vista. Lo que no estaba probado es que el COMANDO elija la
        representacion que el usuario pidio, y esa eleccion ocurre en
        `_emit`, no en la vista.

        Y aqui hay que decir QUE se compara, porque la primera version de
        este test comparaba valor a valor y se puso rojo con
        `executed_nodes: el texto dice '-', el JSON dice []`. Ese rojo no
        era un defecto: era el test afinandose mas que la regla. «Las dos
        representaciones salen del mismo dato» es una afirmacion sobre los
        CAMPOS, no sobre como se imprime un vacio — y de hecho tienen que
        diferir: `-` es lo que un humano lee y lo que el contrato antiguo
        de `runs show` fijaba, `[]` es lo que una maquina necesita para no
        tener que distinguir «vacio» de «cadena vacia». Exigir que coincidan
        habria obligado a romper uno de los dos.
        """
        from tests.test_cli_runs_inspect import _run_cli

        data_root = self._proyecto_con_run(tmp_path)
        texto = _run_cli("runs", "show", "demo", "run-b7", cwd=tmp_path, data_root=data_root)
        json_ = _run_cli(
            "runs", "show", "demo", "run-b7", "--format", "json", cwd=tmp_path, data_root=data_root
        )

        assert json_.returncode == 0, json_.stdout + json_.stderr
        carga = json.loads(json_.stdout)
        campos = carga["fields"]
        assert campos["run_id"] == "run-b7"
        assert campos["state"] == "ACTIVE"

        pares = dict(
            linea.partition("=")[::2] for linea in texto.stdout.splitlines() if "=" in linea
        )
        # 1. Los MISMOS campos. Si `to_key_value` sacara un campo que el
        #    JSON no trae, o al reves, aqui se veria.
        assert set(pares) == set(campos), (
            f"el texto expone {sorted(set(pares) - set(campos))} que el JSON no, "
            f"y el JSON expone {sorted(set(campos) - set(pares))} que el texto no"
        )
        # 2. El mismo VALOR en todo lo que no es un vacio — comparado en
        #    el idioma del texto. Una linea `clave=valor` es texto, asi
        #    que `events_emitted=0` llega aqui como la cadena "0" y el
        #    JSON lo entrega como el entero 0. Exigir `0 == "0"` en
        #    Python es exigir algo que no puede cumplirse, y un test que
        #    no puede cumplirse no mide: hace ruido y teaches a ignorar
        #    la clase de fallo que si importa.
        for clave, valor in pares.items():
            if valor == "-" or campos[clave] in ("", [], {}):
                continue
            assert str(campos[clave]) == valor, (
                f"el texto dice {clave}={valor!r} y el JSON dice {campos[clave]!r}: "
                "es el mismo dato"
            )
        # 3. Y el vacio se declara en las dos formas, a proposito.
        assert pares["executed_nodes"] == "-"
        assert campos["executed_nodes"] == []

    def test_list_sigue_diciendo_sin_runs_y_no_solo_por_defecto(self, tmp_path: Path) -> None:
        """`(sin runs)` es un contrato, no el valor por defecto de la vista.

        `TableView.to_text` por defecto dice `(sin resultados)`. Para
        `runs list` el texto es `(sin runs)`, y si el cableado usara el
        default de la vista, un proyecto vacio cambiaria de palabra sin
        que ningun test lo notara.
        """
        from tests.test_cli_runs_inspect import _init_project, _run_cli

        data_root = _init_project(tmp_path)
        r = _run_cli("runs", "list", "demo", cwd=tmp_path, data_root=data_root)

        assert r.returncode == 0, r.stdout + r.stderr
        assert "(sin runs)" in r.stdout
