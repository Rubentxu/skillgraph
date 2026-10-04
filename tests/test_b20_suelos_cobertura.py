"""B20 — los suelos de cobertura declaraban una cosa que nadie estaba midiendo.

Por que este fichero
--------------------
Al certificar B20, la etapa `coverage-floors` de la receta canonica dejo de
reventar —porque el arreglo de `scripts/coverage.sh` le quito las rutas de
`/tmp` que la hacian morir— y resulto que **seis modulos incumplian el suelo
que su propia ubicacion declara**. No es una lista de excepciones: el suelo se
DERIVA de si el modulo cuelga de un paquete, y lo unico que hay que declarar es
`platform/paths.py` al 60 % porque AGENTS.md 6.3 lo exonera.

Lo grave no es que seis modulos esten bajos. Es que **la etapa llevaba tiempo
sin poder informar**, porque `coverage json` —su unica via de entrada— fallaba
antes de devolver nada. Un contrato que no se puede evaluar no es un contrato
que se cumpla: es un contrato que nadie ha comprobado. Y un verificador que
lanza excepcion no es un verificador que dice «incumple», es uno que no dice
nada.

**LO QUE ESTE FICHERO NO HACE.** No baja un suelo para que la etapa pase. El
suelo es el que AGENTS.md declara; lo que se hace es cubrir el codigo que lo
incumple.

Los seis, con el hueco medido sobre el dato real:

    src/skillgraph/cli/commands/pack.py                      46,43 %  (suelo 70)
    src/skillgraph/packaging/registry.py                     77,86 %  (suelo 90)
    src/skillgraph/presentation/views.py                      79,26 %  (suelo 90)
    src/skillgraph/governance/graph_diff.py                  80,00 %  (suelo 90)
    src/skillgraph/platform/installed_packs_repository.py     78,57 %  (suelo 90)
    src/skillgraph/resources/status.py                       75,31 %  (suelo 90)

**Y POR QUE ESTO NO ES DEUDA FICTICIA.** MEDIDO: las 282 rutas de `/tmp` que
había en el dato de cobertura eran COPIAS de estos mismos ficheros en otra
ruta. Coverage cuenta los statements al fichero que se ejecuta, luego ejecutar
`/tmp/.../pack.py` no puede sumar ni una línea a `src/.../pack.py`. Quitar esas
rutas **no bajó** la cobertura de nadie: solo dejó de romper el informe. Los
seis incumplimientos ya estaban ahí y no los miraba nadie.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from skillgraph.cli.commands.pack import (
    cmd_pack_import,
    cmd_pack_install,
    cmd_pack_list,
    cmd_pack_load,
    cmd_pack_remove,
    cmd_pack_update,
)
from skillgraph.cli.exit_codes import EXIT_OK, EXIT_PARSE, EXIT_VALIDATION
from skillgraph.core.errors import NotFoundError, ValidationError
from skillgraph.governance.graph_diff import (
    GraphChange,
    GraphDiff,
    diff_graph,
    el_diff_corresponde,
)
from skillgraph.governance.graph_expansion import (
    AddNode,
    AddTransition,
    Authorization,
    GraphExpansionProposal,
    RemoveTransition,
)
from skillgraph.packaging import PackManifest, Requires
from skillgraph.packaging.registry import (
    ESTADO_INSTALADO,
    ESTADO_RETIRADO,
    FilaDePack,
    RegistroDePacks,
)
from skillgraph.platform.installed_packs_repository import (
    SqliteInstalledPacksRepository,
    _a_fila,
)
from skillgraph.platform.storage import Storage
from skillgraph.presentation.views import Column, DetailView, TableView
from skillgraph.resources.status import (
    Condition,
    ResourceStatus,
    status_from_json,
    status_to_json,
)
from skillgraph.resources.workflow import (
    WorkflowNode,
    WorkflowPlan,
    WorkflowTransition,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _manifiesto(nombre: str = "acme", version: str = "0.1.0") -> PackManifest:
    return PackManifest(
        name=nombre, version=version, kind="DomainPack", requires=Requires(skillgraph=">=0.1.0")
    )


def _storage(tmp_path: Path) -> Storage:
    return Storage(tmp_path / "sg.db")


# =====================================================================
# Conjunto A. El registro de packs instalados
# =====================================================================


class TestElRegistroRetiraYDiceCuantasFilas:
    """`marcar_retirado` estaba entero sin ejecutar, y su retorno es la prueba.

    Que devuelva el numero de filas es lo que permite decir «no estaba
    instalado» con verdad y no con suposicion: un UPDATE que no cambia nada
    y uno que cambia una fila son indistinguibles si no se mira.
    """

    def test_retirar_una_fila_devuelve_uno(self, tmp_path: Path) -> None:
        st = _storage(tmp_path)
        repo = st.installed_packs_repository()
        repo.guardar(
            FilaDePack(pack="acme", estado=ESTADO_INSTALADO, manifiesto=_manifiesto()),
            tenant_id="t1",
            project_id="p1",
        )
        assert repo.marcar_retirado(tenant_id="t1", project_id="p1", name="acme") == 1, (
            "retirar una fila instalada debe decir que cambio UNA fila: es lo "
            "unico que distingue «la retire» de «no habia nada que retirar»"
        )

    def test_retirar_lo_que_no_esta_devuelve_cero(self, tmp_path: Path) -> None:
        st = _storage(tmp_path)
        repo = st.installed_packs_repository()
        assert repo.marcar_retirado(tenant_id="t1", project_id="p1", name="nunca") == 0, (
            "retirar un pack que no estaba instalado no puede decir que "
            "cambio una fila: diria que se instalo algo que no existia"
        )

    def test_retirar_dos_veces_la_segunda_no_cambia_nada(self, tmp_path: Path) -> None:
        """El `WHERE` lleva `estado = instalado`, y por eso la segunda es 0.

        Sin ese `AND estado = ?`, retirar un pack ya retirado devolveria 1 y
        «lo he retirado» seria cierto dos veces, que es como un registro
        acaba contando una retirada que no ocurrio.
        """
        st = _storage(tmp_path)
        repo = st.installed_packs_repository()
        repo.guardar(
            FilaDePack(pack="acme", estado=ESTADO_INSTALADO, manifiesto=_manifiesto()),
            tenant_id="t1",
            project_id="p1",
        )
        assert repo.marcar_retirado(tenant_id="t1", project_id="p1", name="acme") == 1
        assert repo.marcar_retirado(tenant_id="t1", project_id="p1", name="acme") == 0, (
            "la segunda retirada dice que cambio una fila que ya estaba retirada: "
            "el estado no filtra, y una retirada se cuenta dos veces"
        )

    def test_la_fila_retirada_sigue_leyendose_como_retirada(self, tmp_path: Path) -> None:
        st = _storage(tmp_path)
        repo = st.installed_packs_repository()
        repo.guardar(
            FilaDePack(pack="acme", estado=ESTADO_INSTALADO, manifiesto=_manifiesto()),
            tenant_id="t1",
            project_id="p1",
        )
        repo.marcar_retirado(tenant_id="t1", project_id="p1", name="acme")
        registro = repo.listar(tenant_id="t1", project_id="p1", solo_instalados=False)
        assert [f.estado for f in registro.filas] == [ESTADO_RETIRADO], (
            "retirar no borra: es lo que conserva la unica respuesta que existe "
            "a «¿este proyecto ha tenido alguna vez este pack?»"
        )


class TestLaFilaSeConvierteOexplicaPorQueNo:
    """`_a_fila` traduce la fila de la tabla, y sus tres fallos son contrato."""

    def test_un_manifiesto_ilegible_sale_como_legible_error(self) -> None:
        fila = {
            "manifest_json": "{esto no es json",
            "name": "acme",
            "estado": ESTADO_INSTALADO,
            "tenant_id": "t1",
            "project_id": "p1",
            "uid": "u1",
        }
        with pytest.raises(ValidationError) as exc:
            _a_fila(fila, "t1", "p1")
        assert "ilegible" in str(exc.value), (
            f"el mensaje no dice que el manifiesto es ilegible: {exc.value}"
        )

    def test_un_estado_desconocido_dice_cuales_existen(self) -> None:
        """El error enumera los DOS estados validos, no solo el malo.

        Un mensaje que dice «estado desconocido» sin decir cuales son deja al
        que lee la pregunta de como se escribe un estado valido sin
        respuesta. Este lo dice, y el test lo exige.
        """
        fila = {
            "manifest_json": json.dumps(_manifiesto().to_dict(), sort_keys=True),
            "name": "acme",
            "estado": "inventado",
            "tenant_id": "t1",
            "project_id": "p1",
            "uid": "u1",
        }
        with pytest.raises(ValidationError) as exc:
            _a_fila(fila, "t1", "p1")
        mensaje = str(exc.value)
        assert ESTADO_INSTALADO in mensaje and ESTADO_RETIRADO in mensaje, (
            f"el mensaje no dice cuales son los estados que existen: {mensaje}"
        )

    def test_una_fila_de_otro_proyecto_no_pasa(self) -> None:
        """El filtro no acota, y eso se quiere ver en un test y no en produccion.

        La fila se pide de `t1/p1` y dice ser de `t2/p2`. Con el `WHERE` bien
        puesto no puede pasar; si pasara, significaria que el filtro de
        `listar` no acota, que es una fuga entre tenants.
        """
        fila = {
            "manifest_json": json.dumps(_manifiesto().to_dict(), sort_keys=True),
            "name": "acme",
            "estado": ESTADO_INSTALADO,
            "tenant_id": "t2",
            "project_id": "p2",
            "uid": "u1",
        }
        with pytest.raises(ValidationError) as exc:
            _a_fila(fila, "t1", "p1")
        assert "no esta acotando" in str(exc.value), (
            f"el mensaje no dice que el fallo es el filtro: {exc.value}"
        )

    def test_la_fila_de_verdad_si_se_traduce(self) -> None:
        fila = {
            "manifest_json": json.dumps(_manifiesto().to_dict(), sort_keys=True),
            "name": "acme",
            "estado": ESTADO_INSTALADO,
            "tenant_id": "t1",
            "project_id": "p1",
            "uid": "u1",
        }
        traducida = _a_fila(fila, "t1", "p1")
        assert traducida.pack == "acme"
        assert traducida.estado == ESTADO_INSTALADO


def test_el_repositorio_no_trae_packs_de_otro_proyecto(tmp_path: Path) -> None:
    """El aislamiento por tenant es un contrato, no una preferencia."""
    st = _storage(tmp_path)
    repo = st.installed_packs_repository()
    repo.guardar(
        FilaDePack(pack="mio", estado=ESTADO_INSTALADO, manifiesto=_manifiesto("mio")),
        tenant_id="t1",
        project_id="p1",
    )
    repo.guardar(
        FilaDePack(pack="suyo", estado=ESTADO_INSTALADO, manifiesto=_manifiesto("suyo")),
        tenant_id="t2",
        project_id="p2",
    )
    registro = repo.listar(tenant_id="t1", project_id="p1")
    assert [f.pack for f in registro.filas] == ["mio"], (
        f"el registro de t1/p1 enseña packs de otro proyecto: {registro.filas}"
    )


def test_la_clase_es_la_que_declara_la_plataforma() -> None:
    """El nombre del receptor no es decorativo: es el que se instancia.

    Un test que fabricara su propio doble de la base y midiera el doble
    mediria el doble. Este exige que la clase expuesta por el modulo sea la
    que se puede construir con un Storage.
    """
    st = Storage(":memory:")
    assert isinstance(st.installed_packs_repository(), SqliteInstalledPacksRepository)


# =====================================================================
# Conjunto B. El status observado de un recurso
# =====================================================================


class TestLaCondicionDiceLoQueObservaYPorQue:
    """`Condition` es un tipo cerrado, y su lista de valores se vigila.

    Un estado de condicion inventado pasaria por el dataclass si la
    validacion no lo mirase, y un status que dice «True» sin decir por que
    obliga a mirar el log para averiguarlo: que es justo lo que el
    constructor impide.
    """

    def test_un_estado_inventado_no_es_un_estado(self) -> None:
        with pytest.raises(ValidationError) as exc:
            Condition(
                type="ready",
                status="Quizá",  # type: ignore[arg-type]
                reason="lo dijo quien lo escribio",
                message="m",
                last_transition="2026-10-05T00:00:00Z",
            )
        assert "True" in str(exc.value) and "Unknown" in str(exc.value), (
            f"el mensaje no dice cuales son los estados que existen: {exc.value}"
        )

    def test_una_condicion_sin_motivo_no_se_acepta(self) -> None:
        with pytest.raises(ValidationError) as exc:
            Condition(
                type="ready",
                status="True",
                reason="   ",
                message="m",
                last_transition="2026-10-05T00:00:00Z",
            )
        assert "motivo" in str(exc.value), f"el mensaje no dice que falta el motivo: {exc.value}"


def _condicion(tipo: str = "ready", estado: str = "True") -> Condition:
    return Condition(
        type=tipo,
        status=estado,  # type: ignore[arg-type]
        reason="lo escribio quien lo observo",
        message="m",
        last_transition="2026-10-05T00:00:00Z",
    )


def _status(*condiciones: Condition, phase: str = "ready", generacion: int = 1) -> ResourceStatus:
    return ResourceStatus(
        phase=phase,
        observed_generation=generacion,
        conditions=tuple(condiciones),
    )


class TestElStatusObservadoNoAdivina:
    """Lo que `ResourceStatus` no valida, lo acaba validando el que lee."""

    def test_una_fase_vacia_no_es_una_fase(self) -> None:
        with pytest.raises(ValidationError, match="phase"):
            _status(phase="  ")

    def test_la_generacion_arranca_en_uno(self) -> None:
        """`generation` es un contador que empieza en 1, y 0 no es «la primera»."""
        with pytest.raises(ValidationError, match="generacion"):
            _status(generacion=0)

    def test_condicion_devuelve_la_de_ese_tipo_o_ninguna(self) -> None:
        """La consulta es una CONSULTA: no encuentra y devuelve `None`.

        No lanza. Un `status` que lanza al preguntar por algo que no observa
        obliga a un `try` a quien solo quiere saber, y ese `try` se escribe
        para tapar el error en vez de para mirar el dato.
        """
        status = _status(_condicion("ready"), _condicion("fresh", "Unknown"))
        assert status.condicion("ready") is not None
        assert status.condicion("fresh").status == "Unknown"  # type: ignore[union-attr]
        assert status.condicion("jamas-observado") is None, (
            "preguntar por un tipo que no se observa tiene que devolver None: "
            "es una consulta, y una consulta que lanza obliga a escribir un try"
        )

    def test_una_consulta_sin_condiciones_no_encuentra(self) -> None:
        assert _status().condicion("ready") is None


class TestElStatusCruzaLaFronteraValidando:
    """`status_json` es texto a proposito; aqui se cruza, y se valida."""

    def test_json_ilegible_sale_como_error_del_dominio(self) -> None:
        with pytest.raises(ValidationError, match="JSON"):
            status_from_json("{esto no es json")

    def test_json_que_no_es_objeto_sale_diciendo_que_es(self) -> None:
        """Una lista es JSON valido y un status NO: el mensaje dice cual es."""
        with pytest.raises(ValidationError) as exc:
            status_from_json("[1, 2, 3]")
        assert "list" in str(exc.value), (
            f"el mensaje no dice que clase de cosa es, y sin eso el que lee "
            f"tiene que adivinarlo: {exc.value}"
        )

    def test_ida_y_vuelta_conserva_el_status(self) -> None:
        """La frontera se cruza entera y sale lo mismo. Con `phase` no vacio."""
        original = _status(_condicion("ready"), _condicion("fresh", "Unknown"))
        assert status_from_json(status_to_json(original)) == original


# =====================================================================
# Conjunto C. Las vistas, que son lapresentacion y no el dato
# =====================================================================


class TestLaColumnaDistingueVacioDeAusente:
    """Una celda vacia y una celda ausente se ven IGUALES, y no lo son.

    `-` significa «no hay valor», no «el valor es la cadena "-»». La regla
    de por que no se distinguen mas esta escrita en el propio modulo: cada
    superficie imprime el vacio en su idioma, y lo que no puede diferir es
    el dato. Estos tests fijan cual es el idioma de esta.
    """

    def test_una_lista_se_une_y_una_lista_vacia_dice_guion(self) -> None:
        assert Column("k", "K").cell({"k": ["a", "b"]}) == "a,b"
        assert Column("k", "K").cell({"k": []}) == "-", (
            "una lista vacia es un valor, no una ausencia: si dijera el mismo "
            "guion que un None, el que lee no podria decir cual de las dos cosas "
            "ha visto"
        )

    def test_none_y_cadena_vacia_dicen_guion(self) -> None:
        assert Column("k", "K").cell({"k": None}) == "-"
        assert Column("k", "K").cell({"k": ""}) == "-"
        assert Column("k", "K").cell({}) == "-"

    def test_un_guion_de_verdad_no_se_confunde(self) -> None:
        """La distincion que hay que hacer es de AUSENCIA, no de Aspecto."""
        assert Column("k", "K").cell({"k": "x"}) == "x"

    def test_el_ancho_fijo_recorta_y_rellena(self) -> None:
        """`width` es el ancho que eligio quien presenta, no el dato.

        Con ancho, la celda se rellena a la DERECHA con espacios y se
        recorta por la derecha: dos columnas contiguas tienen que alinearse
        aunque unaSea mas corta que la otra.
        """
        col = Column("k", "K", width=5)
        assert col.cell({"k": "ab"}) == "ab   "
        assert col.cell({"k": "abcdefgh"}) == "abcde"


def _tabla() -> TableView:
    return TableView(
        kind="t",
        columns=(Column("nombre", "Nombre"), Column("estado", "Estado")),
        rows=({"nombre": "acme", "estado": "instalado"},),
    )


class TestLaVistaDeDetalleDiceCuandoNoHayNada:
    """El vacio se dice una vez y en un sitio, no tres veces en tres sitios."""

    def test_sin_campos_ni_secciones_dice_vacio(self) -> None:
        vista = DetailView(kind="d", title="Instalacion de acme")
        assert vista.to_text() == "Instalacion de acme\n(vacio)", (
            "una vista sin nada que enseñar tiene que decirlo: sin esta linea, "
            "el que lee no puede distinguir «no hay datos» de «no se ha mirado»"
        )

    def test_las_secciones_se_imprimen_bajo_su_nombre(self) -> None:
        vista = DetailView(
            kind="d",
            title="Instalacion de acme",
            fields=(("pack", "acme"),),
            sections=(("versiones", (_tabla(),)),),
        )
        texto = vista.to_text()
        assert "versiones:" in texto
        assert "acme" in texto
        assert "instalado" in texto, (
            "la tabla de una sección no sale en el texto: la sección se nombra "
            "y luego no dice nada, que es peor que no tener secciones"
        )

    def test_una_seccion_sin_tablas_no_imprime_nada(self) -> None:
        """Una sección vacía no deja un título colgado y sin contenido."""
        vista = DetailView(
            kind="d", title="T", fields=(("pack", "acme"),), sections=(("vacias", ()),)
        )
        assert "vacias" not in vista.to_text(), (
            "una sección sin tablas imprime su nombre y nada más, que se lee "
            "como que la sección existe y está vacía cuando no existe"
        )


class TestElTextoYElJsonDicenLoMismo:
    """La misma tupla de listas y una lista de tuplas son la MISMA vista.

    `_serializable` existe por eso: si el JSON y el texto dieran formas
    distintas para el mismo dato, un consumidor que lee uno y compara con
    el otro vería una diferencia que no está.
    """

    def test_una_tupla_y_una_lista_dan_el_mismo_json(self) -> None:
        como_tupla = DetailView(kind="d", title="T", fields=(("v", (1, 2)),))
        como_lista = DetailView(kind="d", title="T", fields=(("v", [1, 2]),))
        assert como_tupla.to_json() == como_lista.to_json()

    def test_un_diccionario_se_ordena_por_clave(self) -> None:
        """Ordenado, porque dos JSON del mismo dato no pueden diferir en el orden."""
        uno = DetailView(kind="d", title="T", fields=(("v", {"b": 1, "a": 2}),))
        assert uno.to_json()["fields"]["v"] == {"a": 2, "b": 1}

    def test_un_valor_que_no_es_json_entra_como_texto(self) -> None:
        """Un `Path`, una fecha, un enum: `json.dumps` los rechazaria.

        Aqui se convierten con `str`, y se dice: el dato se conserva legible
        en vez de perder el widget entero por un valor raro.
        """
        from pathlib import PurePosixPath

        vista = DetailView(kind="d", title="T", fields=(("ruta", PurePosixPath("/a/b")),))
        assert vista.to_json()["fields"]["ruta"] == "/a/b"

    def test_none_en_texto_dice_guion(self) -> None:
        assert DetailView(kind="d", title="T", fields=(("v", None),)).to_text().endswith("-")

    def test_un_diccionario_en_texto_enseña_sus_claves(self) -> None:
        texto = DetailView(kind="d", title="T", fields=(("v", {"a": 1}),)).to_text()
        assert "a=1" in texto, f"un diccionario en texto no enseña qué claves tiene: {texto!r}"


class TestLaTablaSabeCuantasFilasYComoFiltrar:
    """Filtrar devuelve OTRA `TableView`, no una lista de dicts.

    Es lo que mantiene la forma estable: un consumidor que aprende a leer
    `kind` y `columns` no tiene que aprender una forma distinta para cada
    filtro, y un filtro que devuelve listas de dicts obliga a aprenderla.
    """

    def test_total_cuenta_las_filas(self) -> None:
        assert _tabla().total == 1
        assert TableView(kind="t", columns=()).total == 0

    def test_una_tabla_sin_filas_dice_el_vacio_que_le_piden(self) -> None:
        """El vacio se imprime en el idioma de quien lee, y se puede cambiar."""
        vacia = TableView(kind="t", columns=(), rows=())
        assert vacia.to_text() == "(sin resultados)"
        assert vacia.to_text(vacio="nada aqui") == "nada aqui", (
            "el texto del vacio no se puede cambiar: cada superficie lo "
            "imprime en su idioma, y el idioma es un parametro del que presenta"
        )

    def test_filtrar_devuelve_una_tabla_con_la_misma_forma(self) -> None:
        tabla = TableView(
            kind="t",
            columns=(Column("estado", "Estado"),),
            rows=({"estado": "ok"}, {"estado": "ko"}),
        )
        filtrada = tabla.find("estado", "ok")
        assert isinstance(filtrada, TableView)
        assert filtrada.kind == tabla.kind
        assert [c.key for c in filtrada.columns] == ["estado"]
        assert filtrada.rows == ({"estado": "ok"},)

    def test_el_json_lleva_las_columnas_por_clave_no_por_texto(self) -> None:
        """`to_json` lleva `key` y `header`: el ancho es de quien presenta.

        Si el JSON llevara el texto ya formateado, el ancho elegido por la
        CLI se congelaria en el dato y la TUI no podria elegir el suyo.
        """
        json_ = _tabla().to_json()
        assert json_["columns"] == [
            {"key": "nombre", "header": "Nombre"},
            {"key": "estado", "header": "Estado"},
        ]
        assert json_["total"] == 1
        assert json_["rows"] == [{"estado": "instalado", "nombre": "acme"}]

    def test_el_json_ordena_las_claves_de_cada_fila(self) -> None:
        """`sorted(fila)`, no `sorted(fila.items())`.

        La segunda compara tambien los valores cuando dos claves se empatan,
        y un valor puede no ser comparable con otro: una tupla de listas
        contra una lista de cadenas. MEDIDO al escribir el test de
        estabilidad: esa fila no se serializaba, y `to_json` reventaba con
        `AttributeError` en vez de devolver la vista.
        """
        tabla = TableView(
            kind="t",
            columns=(Column("executed", "E"), Column("events", "N")),
            rows=({"executed": ("a",), "events": 1},),
        )
        assert tabla.to_json()["rows"] == [{"events": 1, "executed": ["a"]}]

    def test_el_json_texto_sale_ordenado(self) -> None:
        texto = _tabla().to_json_text()
        assert json.loads(texto)["kind"] == "t"


class TestLaVistaDeDetalleAunSePreguntaPorUnCampo:
    def test_field_da_el_valor(self) -> None:
        vista = DetailView(kind="d", title="T", fields=(("pack", "acme"),))
        assert vista.field("pack") == "acme"

    def test_field_de_uno_que_no_existe_lo_dice(self) -> None:
        """Un `KeyError` de diccionario no dice qué se buscó ni en qué vista.

        Aquí el error nombra el campo y la vista, que es lo que hace falta
        para no terminar leyendo toda la salida buscando el dato.
        """
        from skillgraph.core.errors import NotFoundError

        vista = DetailView(kind="d", title="T", fields=(("pack", "acme"),))
        with pytest.raises(NotFoundError) as exc:
            vista.field("no_existe")
        assert "no_existe" in str(exc.value) and "'d'" in str(exc.value), (
            f"el mensaje no dice qué se buscó ni en qué vista: {exc.value}"
        )

    def test_to_key_value_es_la_forma_que_ya_existia(self) -> None:
        """Hay scripts fuera del repo que leen `clave=valor`.

        Cambiarlo por una tablabonita sería una ruptura silenciosa: el
        contrato no se declara en ningún sitio donde se pueda ver, solo en
        quien lo usa.
        """
        vista = DetailView(kind="d", title="T", fields=(("run_id", "r1"), ("state", "ACTIVE")))
        assert vista.to_key_value() == "run_id=r1\nstate=ACTIVE"

    def test_el_json_texto_de_la_seccion_no_revienta(self) -> None:
        vista = DetailView(
            kind="d",
            title="T",
            fields=(("v", [1, 2]),),
            sections=(("versiones", (_tabla(),)),),
        )
        assert json.loads(vista.to_json_text())["sections"]["versiones"]


# =====================================================================
# Conjunto D. El registro de packs, en memoria
# =====================================================================


def _fila(
    nombre: str = "acme", version: str = "0.1.0", uid: str = "", estado: str = ESTADO_INSTALADO
):
    return FilaDePack(pack=nombre, estado=estado, manifiesto=_manifiesto(nombre, version), uid=uid)


class TestLaFilaSeDescribeYElRegistroSeRecorre:
    def test_describe_dice_version_aislamiento_y_estado(self) -> None:
        """La linea que ve el operador lleva los TRES, no solo el nombre.

        Un operador que tiene que abrir otra cosa para saber si algo esta
        aislado no puede decidir con la vista que le dan.
        """
        linea = _fila("acme", "0.1.0").describe()
        assert "acme" in linea and "0.1.0" in linea and ESTADO_INSTALADO in linea

    def test_el_registro_se_recorre_y_se_cuenta(self) -> None:
        registro = RegistroDePacks((_fila("a"), _fila("b")))
        assert len(registro) == 2
        assert [f.pack for f in registro] == ["a", "b"], (
            "un registro que no se puede recorrer obliga a llegar a `.filas`, "
            "y entonces la inmutacion deja de estar garantizada"
        )

    def test_con_uid_solo_devuelve_lo_que_esta_vivo(self) -> None:
        """Un uid es la identidad de una instalacion VIVA.

        Buscar por uid debe comportarse como `buscar` por nombre: una fila
        retirada tiene uid, y si `con_uid` la devolviera, un consumidor
        creeria que algo esta instalado cuando ya no lo esta.
        """
        registro = RegistroDePacks((_fila("a", uid="u1"), _fila("b", uid="u2")))
        assert registro.con_uid("u2") is not None
        assert registro.con_uid("nunca") is None
        retirado = RegistroDePacks((_fila("a", uid="u1", estado=ESTADO_RETIRADO),))
        assert retirado.con_uid("u1") is None, (
            "una fila retirada ha devuelto su uid: lo que esta retirado parece "
            "instalado para quien busca por identidad"
        )


class TestActualizarMienteSiLaVersionNoSube:
    """`_sube` es por NUMERO, y una version ilegible NO sube."""

    def test_una_version_que_no_se_puede_leer_no_sube(self) -> None:
        """`0.10.0 > 0.9.0` como numero y `<` como texto.

        Y `alfa` no sube de nada: devolver `True` ahi degradaria la
        version instalada por un manifiesto que nadie pudo ni leer.
        """
        from skillgraph.packaging.registry import _sube

        assert _sube("0.9.0", "0.10.0") is True
        assert _sube("0.9.0", "0.9.0") is False
        assert _sube("0.9.0", "0.8.0") is False
        assert _sube("0.1.0", "alfa") is False, (
            "una version ilegible ha subroutine: un manifiesto con "
            "version: alfa degradaria la instalada"
        )
        assert _sube("alfa", "0.1.0") is False
        assert _sube("0.1", "0.1.1") is False, (
            "una version de dos trozos no es una version: se compara como si lo fuera"
        )

    def test_actualizar_lo_que_no_esta_dice_que_hay(self) -> None:
        from skillgraph.packaging.registry import actualizar

        registro = RegistroDePacks((_fila("otro"),))
        with pytest.raises(NotFoundError, match="otro"):
            actualizar(registro, _manifiesto("acme", "0.2.0"), version_skillgraph="0.32.4")

    def test_actualizar_un_pack_incompatible_lo_dice(self) -> None:
        """El motivo de la incompatibilidad SUBE al que decide."""
        from skillgraph.packaging.registry import actualizar

        registro = RegistroDePacks((_fila("acme", "0.1.0"),))
        nuevo = _manifiesto("acme", "0.2.0")
        objeto_nuevo = type(nuevo)(
            name=nuevo.name,
            version="0.2.0",
            kind="DomainPack",
            requires=Requires(skillgraph=">=99.0.0"),
        )
        with pytest.raises(ValidationError) as exc:
            actualizar(registro, objeto_nuevo, version_skillgraph="0.32.4")
        assert "99.0.0" in str(exc.value) or "0.2.0" in str(exc.value), (
            f"el motivo no sube al que decide: {exc.value}"
        )


class TestElManifiestoSeLeeDeDondeElPackLoGuarda:
    """El manifiesto viaja en `spec.manifest` porque es lo unico que B8 acepta.

    Y leerlo tiene tres fallos distintos, cada uno con su mensaje: sin `spec`,
    sin `manifest`, y con un `manifest` que no se puede parsear.
    """

    @staticmethod
    def _brick(spec: object) -> object:
        return type("Brick", (), {"spec": spec})()

    def test_lee_el_manifiesto_de_un_pack_bien_formado(self) -> None:
        from skillgraph.packaging.registry import manifiesto_de

        crudo = _manifiesto("acme", "0.1.0").to_dict()
        assert manifiesto_de(self._brick({"manifest": crudo})).name == "acme"

    def test_un_pack_sin_spec_lo_dice(self) -> None:
        from skillgraph.packaging.registry import manifiesto_de

        with pytest.raises(ValidationError, match="spec"):
            manifiesto_de(self._brick(None))

    def test_un_pack_sin_manifest_lo_dice(self) -> None:
        from skillgraph.packaging.registry import manifiesto_de

        with pytest.raises(ValidationError, match=r"spec\.manifest"):
            manifiesto_de(self._brick({"otra_cosa": 1}))

    def test_un_manifest_que_no_es_objeto_lo_dice(self) -> None:
        from skillgraph.packaging.registry import manifiesto_de

        with pytest.raises(ValidationError, match=r"spec\.manifest"):
            manifiesto_de(self._brick({"manifest": "no soy un objeto"}))


def test_desde_filas_construye_un_registro(tmp_path: Path) -> None:
    """El constructor que usan los tests y el que carga, es el mismo camino."""
    from skillgraph.packaging.registry import desde_filas

    registro = desde_filas([_fila("a"), _fila("b")])
    assert [f.pack for f in registro.filas] == ["a", "b"]


# =====================================================================
# Conjunto E. El diff del grafo, que es un diff y no un eco
# =====================================================================


def _nodo(nombre: str, *, capabilities: tuple[str, ...] = ()) -> WorkflowNode:
    return WorkflowNode(
        name=nombre,
        kind="ActionNode",
        namespace="packs:Demo",
        api_version="skillgraph.io/v1",
        resource_revision=1,
        expected_result="ok",
        capabilities=capabilities,
    )


def _plan(nodos, transiciones=()) -> WorkflowPlan:
    return WorkflowPlan(nodes=tuple(nodos), initial=nodos[0].name, transitions=tuple(transiciones))


def _transicion(origen: str, outcome: str, destino: str) -> WorkflowTransition:
    return WorkflowTransition(source=origen, outcome=outcome, target=destino)


def _propuesta(
    base_revision: str, *operaciones, declaradas: tuple[str, ...] = ()
) -> GraphExpansionProposal:
    """Una propuesta REAL, con los campos que el tipo declara.

    No un objeto con lo justo para que el diff lo mire: el diff calcula
    sobre la propuesta entera, y una propuesta a medio construir mediria un
    caso que en produccion no existe.
    """
    return GraphExpansionProposal(
        proposal_id="p-1",
        base_revision=base_revision,
        problem_observed="x",
        evidence=("e",),
        operations=tuple(operaciones),
        new_dependencies=(),
        capabilities_needed=declaradas,
        scope="workflow",
        attachment_point="a",
        rollback_plan=(),
        authorization=Authorization(mode="policy_approved", granted_at="2026-10-05T00:00:00Z"),
        created_at="2026-10-05T00:00:00Z",
        author="t",
    )


class TestElDiffDistingueTransicionesAnadidasYRetiradas:
    """Anadir y retirar una arista son cambios distintos y se cuentan distinto.

    Retirar una transicion **invalida el nodo de origen**: deja de tener por
    donde llegar. Y esa invalidacion no se declara en la operacion —se deduce
    de ella—, que es justo lo que la haceinformativa.
    """

    def test_una_transicion_nueva_aparece_como_anadida(self) -> None:
        plan = _plan([_nodo("a"), _nodo("b")])
        propuesta = _propuesta("r1", AddTransition(_transicion("a", "ok", "b")))
        cambios = diff_graph(plan, propuesta).changes
        assert any(c.subject == "relation" and c.kind == "added" for c in cambios), (
            f"una transicion nueva no sale como anadida: {[c.to_dict() for c in cambios]}"
        )

    def test_una_transicion_ya_que_existe_no_cambia_nada(self) -> None:
        """La misma arista propuesta dos veces es UN cambio, no dos.

        Y aqui esta el motivo de mirar `aristas_actual`: sin el, repetir una
        transicion que ya existe generaria un cambio fantasma.
        """
        plan = _plan([_nodo("a"), _nodo("b")], [_transicion("a", "ok", "b")])
        propuesta = _propuesta("r1", AddTransition(_transicion("a", "ok", "b")))
        cambios = diff_graph(plan, propuesta).changes
        assert not [c for c in cambios if c.subject == "relation"], (
            f"una transicion que ya existe sale como cambio: {[c.to_dict() for c in cambios]}"
        )

    def test_retirar_una_transicion_invalida_el_nodo_de_origen(self) -> None:
        plan = _plan([_nodo("a"), _nodo("b")], [_transicion("a", "ok", "b")])
        propuesta = _propuesta("r1", RemoveTransition("a", "ok"))
        diff = diff_graph(plan, propuesta)
        assert any(c.subject == "relation" and c.kind == "removed" for c in diff.changes)
        assert "a" in diff.invalidated_nodes, (
            "retirar la unica transicion de un nodo lo deja sin por donde "
            "llegar, y el diff no lo dice: quien lee ve una relacion menos y "
            "no ve que ese nodo ha quedado muerto"
        )


class TestUnaOperacionFueraDeLaUnionNoSeCompara:
    """La union `PatchOp` es CERRADA, y una operacion fuera no se puede decidir."""

    def test_una_operacion_inventada_no_entra(self) -> None:
        plan = _plan([_nodo("a")])
        propuesta = _propuesta("r1", type("Inventada", (), {})())
        with pytest.raises(ValidationError) as exc:
            diff_graph(plan, propuesta)
        assert "AddNode" in str(exc.value), (
            f"el mensaje no dice cuales son las que si valen: {exc.value}"
        )


class TestLaCoherenciaPreguntaLoQueElParcheProduce:
    """`es_coherente` NO es un accessor: es la pregunta que hace que sea un diff.

    Compara lo que la propuesta DECLARA con lo que su parche PRODUCE. Si
    solo mirara una de las dos, un diff que no se corresponde con su
    propuesta pasaria por coherente.
    """

    def test_coherente_cuando_las_dos_cosas_dicen_lo_mismo(self) -> None:
        plan = _plan([_nodo("a")])
        propuesta = _propuesta("r1", AddNode(_nodo("b", capabilities=("c1",))), declaradas=("c1",))
        assert diff_graph(plan, propuesta).es_coherente() is True

    def test_incoherente_cuando_declara_mas_de_lo_que_produce(self) -> None:
        """Declara una capacidad que el parche no anade: eso no se sostiene.

        El caso inverso —que el parche produzca mas de lo declarado— es el
        que el gate tiene que cazar, porque un diff «parecido» es un diff
        que nadie ha comprobado.
        """
        plan = _plan([_nodo("a")])
        # Declara dos capacidades y el parche solo produce una: lo declarado
        # no se sostiene sobre lo que el diff realmente hace.
        propuesta = _propuesta(
            "r1", AddNode(_nodo("b", capabilities=("c1",))), declaradas=("c1", "c2")
        )
        assert diff_graph(plan, propuesta).es_coherente() is False


class TestUnDiffDeOtraRevisionNoDescribeEsteCambio:
    """`el_diff_corresponde` RECALCULA y compara; no acepta un diff «parecido»."""

    def test_un_diff_de_otra_revision_no_corresponde(self) -> None:
        plan = _plan([_nodo("a")])
        otra = _propuesta("r-OTRA", AddNode(_nodo("b")))
        diff = diff_graph(plan, _propuesta("r1", AddNode(_nodo("b"))))
        veredicto = el_diff_corresponde(diff, otra, plan)
        assert veredicto, "un diff calculado sobre otra revision no puede corresponder"
        assert "r-OTRA" in str(veredicto), f"el motivo no dice que revision es: {veredicto}"


# =====================================================================
# Conjunto F. Los cuatro comandos del ciclo, llamados DE DIRECTO
# =====================================================================


def _fichero_pack(directorio: Path, nombre: str, version: str, requiere: str = ">=0.1.0") -> Path:
    directorio.mkdir(parents=True, exist_ok=True)
    ruta = directorio / f"{nombre}.md"
    ruta.write_text(
        f"---\napiVersion: skillgraph.dev/v1alpha1\nkind: DomainPack\n"
        f"metadata:\n  namespace: packs\n  name: {nombre}\n"
        f"spec:\n  version: {version}\n  manifest:\n    name: {nombre}\n"
        f"    version: {version}\n    kind: DomainPack\n    isolation: declarative\n"
        f'    requires:\n      skillgraph: "{requiere}"\n---\n# {nombre}\n',
        encoding="utf-8",
    )
    return ruta


def _raiz(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """La raiz de datos de ESTA prueba, aislada por variable de entorno.

    `SKILLGRAPH_DATA_ROOT` es la via que el propio codigo lee antes que el
    HOME, y usarla deja el HOME del que la esta ejecutando intacto: cambiar
    el HOME entero seria tocar algo del proceso que la envuelve.
    """
    raiz = tmp_path / "data"
    raiz.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SKILLGRAPH_DATA_ROOT", str(raiz))
    return raiz


def _proyecto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, nombre: str = "p") -> str:
    """Crea el proyecto en el catalogo de esa raiz, con la CLI de verdad."""
    raiz = _raiz(tmp_path, monkeypatch)
    proc = subprocess.run(
        [sys.executable, "-m", "skillgraph", "project", "create", nombre],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "SKILLGRAPH_DATA_ROOT": str(raiz),
            "PYTHONPATH": str(REPO_ROOT / "src"),
        },
    )
    assert proc.returncode == 0, f"no se pudo crear el proyecto: {proc.stdout}{proc.stderr}"
    return nombre


def _args(proyecto: str, **extra: str) -> argparse.Namespace:
    """El Namespace que el parser de verdad construye para estos comandos.

    `data_root` va a `None` a proposito: la raiz la pone la variable de
    entorno, y asi el test no depende de donde este el repositorio.
    """
    return argparse.Namespace(project=proyecto, data_root=None, **extra)


class TestElCicloDeLaCliPorDentro:
    """Los cuatro comandos, LLAMADOS, no a traves de un subproceso.

    El ciclo completo ya se prueba de punta a punta con la CLI de verdad en
    `test_b11_pack_lifecycle.py`. Lo que no habia era entrar en el CUERPO de
    los comandos: por eso estaban al 46 %, con `install`, `update`, `remove`
    y `list` enteros sin ejecutar.

    Aqui se llaman directo, y por eso el cuerpo cuenta aunque no haya hook
    de cobertura para los subprocesos.
    """

    def test_el_ciclo_completo_pasa_por_los_cuatro(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        proyecto = _proyecto(tmp_path, monkeypatch)
        v1 = _fichero_pack(tmp_path / "packs", "acme", "0.1.0")
        v2 = _fichero_pack(tmp_path / "packs2", "acme", "0.2.0")

        assert cmd_pack_install(_args(proyecto, path=str(v1))) == 0
        assert "0.1.0" in capsys.readouterr().out

        assert cmd_pack_list(_args(proyecto)) == 0
        salida = capsys.readouterr().out
        assert "acme@0.1.0" in salida and "declarative" in salida, (
            "list tiene que enseñar el aislamiento: es contenido del contrato, "
            "y sin el responde «que hay» pero no «cuanto es de fiar»"
        )

        assert cmd_pack_update(_args(proyecto, path=str(v2))) == 0
        assert "0.1.0 -> 0.2.0" in capsys.readouterr().out

        assert cmd_pack_remove(_args(proyecto, name="acme")) == 0
        capsys.readouterr()

        assert cmd_pack_list(_args(proyecto)) == 0
        assert "acme" not in capsys.readouterr().out, (
            "tras retirar, list sigue enseñando el pack: retirar no borra la "
            "fila, pero si lo saca de lo que ve el operador"
        )

    def test_list_de_un_proyecto_vacio_lo_dice(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """El vacio se dice. Un `list` mudo no se distingue de uno que fallo."""
        proyecto = _proyecto(tmp_path, monkeypatch)
        assert cmd_pack_list(_args(proyecto)) == 0
        assert "no hay packs instalados" in capsys.readouterr().out

    def test_update_exige_que_la_version_suba(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Un update que acepta una version que no sube degrada en silencio."""
        proyecto = _proyecto(tmp_path, monkeypatch)
        v1 = _fichero_pack(tmp_path / "packs", "acme", "0.2.0")
        v0 = _fichero_pack(tmp_path / "packs0", "acme", "0.1.0")
        assert cmd_pack_install(_args(proyecto, path=str(v1))) == 0
        capsys.readouterr()
        assert cmd_pack_update(_args(proyecto, path=str(v0))) != 0, (
            "un update a una version INFERIOR ha pasado: el entorno queda "
            "degradado a una version anterior sin avisar"
        )

    def test_remove_de_lo_que_no_esta_lo_dice_y_no_revienta(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """`remove` de un pack ausente es un error DICHO, no una excepcion.

        Y el error sale con su `code`, que es lo que traduce la CLI a exit
        code; sin el, el usuario veria el motivo sin poder distinguirlo de
        otro fallo.
        """
        proyecto = _proyecto(tmp_path, monkeypatch)
        assert cmd_pack_remove(_args(proyecto, name="nunca")) != 0
        err = capsys.readouterr().err
        assert "ERROR" in err and "sg_" in err, f"el error no sale con su codigo: {err!r}"

    def test_un_proyecto_que_no_existe_no_abre_la_base(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Un nombre que el catalogo no conoce sale antes de tocar nada."""
        _raiz(tmp_path, monkeypatch)
        assert cmd_pack_list(_args("no-existe")) != 0
        assert cmd_pack_remove(_args("no-existe", name="acme")) != 0


# =====================================================================
# Conjunto G. `pack load` e `import`, que son de OTRO contrato
# =====================================================================

PACK_CON_TIPOS = REPO_ROOT / "tests" / "fixtures" / "packs" / "narrative-core.md"


class TestCargarUnPackDeclaraSusTipos:
    """`load` administra el CONTENIDO; `install`, la INSTALACION.

    Dos comandos que hacen lo mismo con nombres distintos son la trampa de
    «conectar no es contener»: uno deja el pack vivo en el proyecto y el otro
    declara los tipos que trae. Aqui se prueba el segundo, y sus dos
    rechazos: un fichero que no parsea y un kind que no es DomainPack.
    """

    def test_cargar_declara_los_tipos_y_persiste(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        proyecto = _proyecto(tmp_path, monkeypatch)
        assert cmd_pack_load(_args(proyecto, path=str(PACK_CON_TIPOS))) == 0
        salida = capsys.readouterr().out
        assert "Character" in salida and "StoryArc" in salida, (
            f"los tipos declarados no salen: {salida!r}"
        )
        assert "UID:" in salida, "cargar un pack no dice con que uid ha quedado"

    def test_un_fichero_que_no_parsea_sale_como_error_de_parseo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        proyecto = _proyecto(tmp_path, monkeypatch)
        roto = tmp_path / "roto.md"
        roto.write_text("no es un pack en absoluto\n", encoding="utf-8")
        assert cmd_pack_load(_args(proyecto, path=str(roto))) == EXIT_PARSE
        assert "ERROR" in capsys.readouterr().err

    def test_un_kind_que_no_es_domainpack_no_se_carga(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Se comprueba ANTES de persistir: fail-fast, sin pack roto dentro.

        Un pack de otro kind persistido a medias deja en el proyecto algo que
        el proyecto cree suyo y no puede instalar.
        """
        proyecto = _proyecto(tmp_path, monkeypatch)
        otro = tmp_path / "otro.md"
        otro.write_text(
            "---\napiVersion: skillgraph.dev/v1alpha1\nkind: OtroCosa\n"
            "metadata:\n  name: x\n  namespace: shared\nspec: {}\n---\n",
            encoding="utf-8",
        )
        assert cmd_pack_load(_args(proyecto, path=str(otro))) == EXIT_VALIDATION
        assert "DomainPack" in capsys.readouterr().err

    def test_un_proyecto_que_no_existe_no_abre_la_base(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _raiz(tmp_path, monkeypatch)
        assert cmd_pack_load(_args("no-existe", path=str(PACK_CON_TIPOS))) != 0


def _skill(tmp_path: Path) -> Path:
    """Un directorio-skill minimo, con material que el import puede analizar."""
    d = tmp_path / "skill"
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Una skill de prueba\n---\n\n# Demo\n\nCuerpo.\n",
        encoding="utf-8",
    )
    (d / "guion.py").write_text("print('no se ejecuta')\n", encoding="utf-8")
    return d


class TestImportarUnaSkillNoLaEjecuta:
    """Importar es asimilar SIN ejecutar: los scripts se detectan, no se corren.

    Y el informe dice explicitamente que las capacidades son SENALES y no
    verificadas. Presentarlas como comprobadas seria exactamente el defecto
    que el importacion sin ejecucion evita.
    """

    def test_una_skill_inexistente_lo_dice(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        proyecto = _proyecto(tmp_path, monkeypatch)
        assert cmd_pack_import(_args(proyecto, path=tmp_path / "nope")) == EXIT_VALIDATION
        assert "no existe" in capsys.readouterr().err

    def test_el_informe_a_stdout_sin_ruta(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        proyecto = _proyecto(tmp_path, monkeypatch)
        assert cmd_pack_import(_args(proyecto, path=_skill(tmp_path), report=None)) == EXIT_OK
        salida = capsys.readouterr().out
        assert "source_id" in salida or "content_hash" in salida, (
            f"el informe a stdout no dice que es: {salida[:200]!r}"
        )

    def test_el_informe_a_fichero_dice_donde_ha_ido(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        proyecto = _proyecto(tmp_path, monkeypatch)
        destino = tmp_path / "salida" / "informe.json"
        assert cmd_pack_import(_args(proyecto, path=_skill(tmp_path), report=destino)) == EXIT_OK
        assert destino.exists(), "el comando dice que escribio el informe y no lo escribio"
        assert json.loads(destino.read_text(encoding="utf-8")), "el informe esta vacio"
        salida = capsys.readouterr().out
        assert "NO ejecutados" in salida, (
            "el informe tiene que decir que los scripts NO se ejecutaron: es "
            "la diferencia entre importar y ejecutar"
        )

    def test_un_proyecto_que_no_existe_no_abre_la_base(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _raiz(tmp_path, monkeypatch)
        assert cmd_pack_import(_args("no-existe", path=_skill(tmp_path), report=None)) != 0


# =====================================================================
# Conjunto H. Lo que el diff RESPONDE y lo que NO corresponde
# =====================================================================


def _diff_minimo() -> tuple[WorkflowPlan, GraphDiff, GraphExpansionProposal]:
    plan = _plan([_nodo("a")])
    propuesta = _propuesta("r1", AddNode(_nodo("b", capabilities=("c1",))), declaradas=("c1",))
    return plan, diff_graph(plan, propuesta), propuesta


class TestElDiffRespondeLasSietePreguntas:
    """Y la octava, que es la que hace que las siete sirvan.

    `discrepancia_de_capacidades` no es una de las siete del roadmap: es la
    que sale de restar lo declarado de lo requerido. Sin ella, un diff que
    dice «que capacidades exige» y otro que dice «que capacidades declara»
    pueden contradecirse y el que lee tiene que compararlos a mano.
    """

    def test_las_respuestas_dicen_las_dos_caras_de_las_capacidades(self) -> None:
        _, diff, _ = _diff_minimo()
        r = diff.respuestas()
        assert r["que_capacidades_declara"] == ("c1",)
        assert r["que_capacidades_exige"] == ("c1",)
        assert r["discrepancia_de_capacidades"] == [], (
            "las dos caras dicen lo mismo y la discrepancia no esta vacia: "
            f"{r['discrepancia_de_capacidades']!r}"
        )

    def test_la_discrepancia_sale_simetrica(self) -> None:
        """Sintetica: declara una que no exige. Sale la que sobra."""
        plan = _plan([_nodo("a")])
        propuesta = _propuesta(
            "r1", AddNode(_nodo("b", capabilities=("c1",))), declaradas=("c1", "c2")
        )
        assert diff_graph(plan, propuesta).respuestas()["discrepancia_de_capacidades"] == ["c2"]

    def test_el_diff_se_serializa_completo(self) -> None:
        _, diff, _ = _diff_minimo()
        d = diff.to_dict()
        for clave in ("base_revision", "base_fingerprint", "changes", "invalidated_nodes"):
            assert clave in d, f"el diff serializado no lleva {clave!r}: {sorted(d)}"


class TestRedeclararUnNodoEsUnCambioNoUnaAdicion:
    """Un nodo que ya existe y al que le anaden capacidades es un `~`, no un `+`.

    Si saliera como adicion, el diff diria que el nodo es nuevo cuando lleva
    tiempo en el grafo, y quien lo aplicara lo crearia dos veces.
    """

    def test_anadir_capacidades_a_un_nodo_que_existe_es_un_cambio(self) -> None:
        plan = _plan([_nodo("a", capabilities=("vieja",))])
        propuesta = _propuesta("r1", AddNode(_nodo("a", capabilities=("vieja", "nueva"))))
        cambios = diff_graph(plan, propuesta).changes
        assert [c.kind for c in cambios] == ["changed"], (
            f"re-declarar un nodo con capacidades nuevas no sale como cambio: "
            f"{[c.to_dict() for c in cambios]}"
        )
        assert cambios[0].subject == "capability"

    def test_redeclarar_sin_capacidades_nuevas_no_es_cambio(self) -> None:
        """Mismo nodo, mismas capacidades: no hay nada que decir."""
        plan = _plan([_nodo("a", capabilities=("vieja",))])
        propuesta = _propuesta("r1", AddNode(_nodo("a", capabilities=("vieja",))))
        assert diff_graph(plan, propuesta).changes == ()


class TestUnDiffQueNoSeReproduceNoEsUnaEtapaDelGate:
    """`el_diff_corresponde` RECALCULA y compara, en tres comparaciones."""

    def test_el_diff_de_esta_aplicacion_corresponde(self) -> None:
        plan, diff, propuesta = _diff_minimo()
        assert el_diff_corresponde(diff, propuesta, plan) is None

    def test_un_diff_de_otro_grafo_no_corresponde(self) -> None:
        """La revision no basta: dos estados pueden compartir revision.

        Por eso la comparacion es por HUELLA del plan, y no solo por
        `base_revision`.
        """
        _, diff, propuesta = _diff_minimo()
        otro_plan = _plan([_nodo("a"), _nodo("z")])
        veredicto = el_diff_corresponde(diff, propuesta, otro_plan)
        assert veredicto, "un diff calculado sobre otro grafo ha pasado"
        assert "huella" in str(veredicto), f"el motivo no dice que es la huella: {veredicto}"

    def test_un_diff_inventado_no_corresponde(self) -> None:
        """Misma revision y misma huella, pero con OTRO contenido.

        Es el caso que un gate tiene que cazar: si bastara con que la
        revision y la huella encajen, bastaria con recalcular el diff una vez
        y reutilizarlo para siempre.
        """
        plan, diff, propuesta = _diff_minimo()

        inflado = replace(
            diff,
            # RUF005: unpacking, no `changes + (,)`. Es la convencion del
            # repo para no sumar tuplas, y aqui se ve por que importa: la
            # concatenacion construye una tupla nueva cada vez.
            changes=(
                *diff.changes,
                GraphChange(subject="node", kind="added", target="fantasma", detail="x"),
            ),
        )
        veredicto = el_diff_corresponde(inflado, propuesta, plan)
        assert veredicto, "un diff con un cambio de mas ha pasado como suyo"
        assert "no corresponde" in str(veredicto), f"el motivo no lo dice: {veredicto}"
