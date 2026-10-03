"""B4 — la mitad OBSERVADA de la separación CRD-like deja de ser inalcanzable.

La tabla `resources` **ya tenía** la forma completa: `spec_json`,
`status_json`, `generation`, `resource_version`. Y la mitad observada era
**inalcanzable**, medido antes de escribir una línea
(`scripts/measure_b4_observed_state.py`, versionado y no en `.pipelinek/`):

```
1 INSERT en resources, 0 UPDATE   -> status_json NOT NULL DEFAULT '{}'
Brick.spec = True, Brick.status = False
conditions en src/                = []
generation se escribe             = False
ejecución contra la base real     -> status_json='{}' generation=1
```

`'{}'` para siempre es el peor de los dos mundos: el campo es NOT NULL, así
que el sistema **parece** tener estado y no lo tiene.

**Y POR QUÉ `status` NO VA EN `Brick`.** `Brick` es lo DECLARADO: lo que
alguien escribe y pide que exista. Si llevara `status`, un pack podría
declarar el estado de su propio recurso, la mitad observada dejaría de estar
observada y el sistema no podría distinguir `observed` de
`human-asserted` — que es la distinción que B6 necesita. La separación es
de TIPO, no de convención, y `test_el_tipo_declarado_no_tiene_status` la
vigila por AST.

**LA INVARIANTE QUE SE ROMPE SOLA** es
`test_escribir_status_no_sube_generation`: basta con que un `UPDATE` de
status suba también `generation` y el sistema sigue funcionando
exactamente igual. Mide **antes y después**, no el valor final, porque un
guard que mira solo el final pasa con cualquier valor.

**Y EL CONTRASALTO DEL BLOQUE**, que es la forma nueva:
`TestLaMedicionQueAbrioElBloqueDejaDeDarElHueco` exige que el instrumento
que mide el hueco deje de reportarlo. No es un guard que solo sabe decir «el
hueco sigue ahí» —que no distinguiría «no he arreglado nada» de «lo he
arreglado»—: es el mismo error que el primer gate de B3, con la espejo
puesta, donde la propiedad medida la cumplía un singleton mejor que un valor.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from skillgraph.core.errors import ValidationError
from skillgraph.platform.storage import Storage
from skillgraph.resources.bricks import Brick, ResourceIdentity
from skillgraph.resources.status import Condition, ConditionStatus, ResourceStatus

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / "src" / "skillgraph"

TENANT = "t-b4"
PROJECT = "p-b4"


def _brick(nombre: str = "code-analysis") -> Brick:
    return Brick(
        identity=ResourceIdentity(
            tenant_id=TENANT,
            project_id=PROJECT,
            namespace="packs",
            kind="DomainPack",
            name=nombre,
        ),
        api_version="skillgraph.io/v1",
        kind="DomainPack",
        spec={"capacities": ["code.analysis"]},
    )


def _ready() -> Condition:
    return Condition(
        type="Ready",
        status="True",
        reason="Observed",
        message="el pack se resolvio",
        last_transition="2026-10-03T00:00:00Z",
    )


def _desconocido() -> Condition:
    return Condition(
        type="Synced",
        status="Unknown",
        reason="NoIntentado",
        message="nadie ha intentado sincronizarlo",
        last_transition="2026-10-03T00:00:00Z",
    )


@pytest.fixture
def almacen() -> Any:
    tmp = tempfile.TemporaryDirectory()
    st = Storage(Path(tmp.name) / "b4.sqlite")
    st._b4_tmp = tmp  # type: ignore[attr-defined]
    yield st
    st.close()
    tmp.cleanup()


def _persistir(almacen: Any, brick: Brick | None = None) -> str:
    return almacen.upsert_resource(brick=brick or _brick())


class TestElTipoDeStatusYCerradoEInmutable:
    """R1. Un tipo, y no un dict con otro nombre."""

    def test_es_frozen_y_slots(self) -> None:
        """`AGENTS.md 1.1`. Y se comprueba lanzando, no leyendo flags."""
        status = ResourceStatus(phase="Running", conditions=(_ready(),), observed_generation=1)
        with pytest.raises(FrozenInstanceError):
            status.phase = "Failed"  # type: ignore[misc]
        assert not hasattr(status, "__dict__"), (
            "sin `__dict__` no hay por donde colar un atributo nuevo: "
            "`frozen=True` congela el enlace, y `slots` quita la segunda "
            "puerta de entrada"
        )

    def test_las_condiciones_son_tupla(self) -> None:
        """Nunca `list` ni `set`: el orden de una condición se lee."""
        status = ResourceStatus(
            phase="Running", conditions=[_ready(), _desconocido()], observed_generation=1
        )
        assert isinstance(status.conditions, tuple)
        assert tuple(c.type for c in status.conditions) == ("Ready", "Synced")

    def test_unknown_no_es_false(self) -> None:
        """La tercera mitad de la pregunta de un operador.

        `Unknown` no es `False`: con `bool`, un recurso recién creado parece
        roto, y «no se ha intentado» se lee como «falló».
        """
        assert ConditionStatus is not bool
        assert "Unknown" in ConditionStatus.__args__  # type: ignore[attr-defined]
        assert _desconocido().status == "Unknown"

    def test_una_condicion_no_puede_repetirse(self) -> None:
        """`Ready=True` y `Ready=False` no son «dos estados».

        Son un status que no sabe qué está observando. Se valida al
        construir, no al persistir: el error es de quien lo construye, y se
        le dice a quien lo construye.
        """
        with pytest.raises(ValidationError) as exc:
            ResourceStatus(
                phase="Running",
                conditions=(
                    _ready(),
                    Condition(
                        type="Ready",
                        status="False",
                        reason="NoObservado",
                        message="contradice la anterior",
                        last_transition="2026-10-03T00:00:01Z",
                    ),
                ),
                observed_generation=1,
            )
        assert "Ready" in str(exc.value), (
            "el error tiene que decir QUAL condicion se repite: un "
            "'status invalido' sin nombre obliga a buscar a mano"
        )

    def test_una_condicion_sin_tipo_se_rechaza(self) -> None:
        with pytest.raises(ValidationError):
            Condition(
                type="  ",
                status="True",
                reason="X",
                message="Y",
                last_transition="2026-10-03T00:00:00Z",
            )


class TestElStatusLlegaALaFila:
    """R2. El primer `UPDATE` sobre `resources` del repo."""

    def test_el_status_llega_a_la_fila(self, almacen: Any) -> None:
        """**Ejecuta y lee la fila.** No deduce del codigo.

        Un instrumento que no produce el caso no mide el caso, y lo que no
        sale de la ejecucion no es un dato — la leccion de B3, que sustituyo
        el `KnowledgeController` por un doble con un metodo que no existia y
        escribio igual una conclusion.
        """
        uid = _persistir(almacen)
        status = ResourceStatus(phase="Running", conditions=(_ready(),), observed_generation=1)
        almacen.update_resource_status(uid=uid, status=status)

        fila = almacen._conn.execute(
            "SELECT status_json, generation, resource_version FROM resources WHERE uid = ?",
            (uid,),
        ).fetchone()
        guardado = json.loads(fila["status_json"])
        assert guardado["phase"] == "Running"
        assert guardado["conditions"][0]["type"] == "Ready"
        assert guardado["conditions"][0]["status"] == "True"

    def test_el_mismo_status_da_el_mismo_texto(self, almacen: Any) -> None:
        """El texto persistido es reproducible.

        Y este test **sustituye a uno más débil que la sonda M6
        desdesmontó**, que merece decirse con su nombre. La primera versión
        comparaba dos escrituras del MISMO objeto y por eso pasaba
        también sin `sort_keys`: el orden de las claves lo fija el literal
        de `to_dict`, así que la propiedad era vacua y la sonda que la
        quería medir no podía distinguir nada. Un guard que mide una
        propiedad que se cumple por construcción no mide nada.

        La propiedad que sí carga con algo es el **round-trip**: lo que sale
        de `status_to_json` tiene que volver a ser el mismo status al
        leerlo, y eso depende de que `to_dict` no pierda ningún campo.
        """
        uid = _persistir(almacen)
        a = ResourceStatus(
            phase="Running", conditions=(_ready(), _desconocido()), observed_generation=4
        )
        almacen.update_resource_status(uid=uid, status=a)
        primero = almacen._conn.execute(
            "SELECT status_json FROM resources WHERE uid = ?", (uid,)
        ).fetchone()["status_json"]
        almacen.update_resource_status(uid=uid, status=a)
        segundo = almacen._conn.execute(
            "SELECT status_json FROM resources WHERE uid = ?", (uid,)
        ).fetchone()["status_json"]
        assert primero == segundo

    def test_el_ida_y_vuelta_conserva_el_status(self) -> None:
        """Round-trip: serializar y leer devuelve **el mismo** status.

        Si `to_dict` pierde un campo, la fila guarda menos de lo que el
        status dice, y el operador ve un status distinto del que se
        escribio — sin ningun error, porque la escritura fue valida.
        """
        from skillgraph.resources.status import status_from_json, status_to_json

        original = ResourceStatus(
            phase="Degraded",
            conditions=(_ready(), _desconocido()),
            observed_generation=7,
        )
        recuperado = status_from_json(status_to_json(original))
        assert recuperado == original
        assert recuperado.observed_generation == 7, (
            "el round-trip pierde `observed_generation`: el status que se "
            "lee dice que observa otra generacion que la que se escribio"
        )

    def test_un_uid_que_no_existe_es_error_del_dominio(self, almacen: Any) -> None:
        """No un `None` silencioso: un status que no se ha escrito no se
        puede leer como un status vacio."""
        from skillgraph.core.errors import NotFoundError

        with pytest.raises(NotFoundError):
            almacen.update_resource_status(
                uid="no-existe/este/uid",
                status=ResourceStatus(phase="X", conditions=(), observed_generation=1),
            )


class TestLaLecturaDevuelveElTipo:
    """R3. La primera vez que `status_json` deja de ser texto."""

    def test_la_lectura_devuelve_el_tipo_y_no_el_texto(self, almacen: Any) -> None:
        uid = _persistir(almacen)
        almacen.update_resource_status(
            uid=uid,
            status=ResourceStatus(phase="Degraded", conditions=(_ready(),), observed_generation=1),
        )
        leido = almacen.get_resource_status(uid=uid)
        assert isinstance(leido, ResourceStatus)
        assert leido.phase == "Degraded"
        assert leido.conditions[0].type == "Ready"
        assert leido.conditions[0].status == "True"

    def test_sin_status_es_none_y_no_un_status_vacio(self, almacen: Any) -> None:
        """`None` no es lo mismo que un status sin condiciones.

        «no hay status escrito» y «hay un status y no tiene condiciones» son
        preguntas distintas, y un operador las contesta distinto.
        """
        uid = _persistir(almacen)
        assert almacen.get_resource_status(uid=uid) is None

        almacen.update_resource_status(
            uid=uid, status=ResourceStatus(phase="Pending", conditions=(), observed_generation=1)
        )
        vacio = almacen.get_resource_status(uid=uid)
        assert vacio is not None
        assert vacio.phase == "Pending"
        assert vacio.conditions == ()


class TestLaInvarianteGeneration:
    """R4. `generation` es del spec; `resource_version` es de todo."""

    def test_escribir_status_no_sube_generation(self, almacen: Any) -> None:
        """Mide ANTES y DESPUÉS, no el valor final.

        La invariante se puede romper sin que nada falle: basta con que el
        `UPDATE` de status suba también `generation`, y el sistema sigue
        funcionando igual. Un guard que mirase solo el valor final pasaría
        con cualquier valor.
        """
        uid = _persistir(almacen)
        antes = almacen._conn.execute(
            "SELECT generation, resource_version FROM resources WHERE uid = ?", (uid,)
        ).fetchone()
        almacen.update_resource_status(
            uid=uid,
            status=ResourceStatus(phase="Running", conditions=(_ready(),), observed_generation=1),
        )
        despues = almacen._conn.execute(
            "SELECT generation, resource_version FROM resources WHERE uid = ?", (uid,)
        ).fetchone()

        assert despues["generation"] == antes["generation"], (
            f"escribir status subio generation de {antes['generation']} a "
            f"{despues['generation']}. generation identifica la version del "
            "SPEC; si sube con el status, el status deja de poder situarse "
            "en el spec que observo."
        )
        assert despues["resource_version"] == antes["resource_version"] + 1, (
            "resource_version es el reloj de CUALQUIER escritura: si no "
            "sube, dos escrituras son indistinguibles y no hay forma de "
            "saber que algo cambio."
        )

    def test_el_status_lleva_la_generacion_que_observa(self, almacen: Any) -> None:
        """`observed_generation` lo lee QUIEN ESCRIBE de la fila.

        Si lo declarara el status, el campo mentiría en cuanto el spec
        cambiara por debajo: seguiría diciendo la generación que el status
        creía, no la que observó.
        """
        uid = _persistir(almacen)
        almacen.update_resource_status(
            uid=uid,
            status=ResourceStatus(phase="Running", conditions=(), observed_generation=999),
        )
        leido = almacen.get_resource_status(uid=uid)
        assert leido is not None
        real = almacen._conn.execute(
            "SELECT generation FROM resources WHERE uid = ?", (uid,)
        ).fetchone()["generation"]
        assert leido.observed_generation == real, (
            f"el status dice que observo la {leido.observed_generation} y la "
            f"real es la {real}: el status se esta declarando a si mismo en "
            "vez de leer lo que observa"
        )


class TestElTipoDeclaradoNoTieneStatus:
    """R5. `Brick` es lo declarado. Sin exceptions."""

    #: El campo no tiene que existir en el **tipo**, y se mira el AST. Un
    #: `hasattr(Brick, "status")` distinguiría un atributo de una propiedad y
    #: además daría `True` por el `status` de `StoredResource` si alguien
    #: metiera el campo por una puerta lateral.
    def test_el_tipo_declarado_no_tiene_status(self) -> None:
        declarados = _campos_de("Brick")
        assert "status" not in declarados, (
            f"Brick lleva `status`: {sorted(declarados)}. Es lo DECLARADO. "
            "Con status dentro, un pack declara el estado de su propio "
            "recurso y la mitad observada deja de estar observada."
        )
        assert "spec" in declarados, "el contrasalto: Brick tiene que seguir teniendo spec"

    def test_los_dos_lados_son_tipos_distintos(self) -> None:
        """La separación es de TIPO, no de convención.

        Dos tipos que se parecieran —o el mismo tipo con dos nombres— no
        permitirían distinguir `observed` de `human-asserted` en ninguna
        capa, y la distinción se pierde antes de llegar a la base.
        """
        assert ResourceStatus is not Brick
        assert set(_campos_de("ResourceStatus")) & {"spec", "markdown_body"} == set()
        assert {"phase", "conditions", "observed_generation"} <= set(_campos_de("ResourceStatus"))


class TestLaMedicionQueAbrioElBloqueDejaDeDarElHueco:
    """EL CONTRASALTO DEL BLOQUE, y tiene una forma nueva.

    El instrumento que mide el hueco tiene que **dejar de reportarlo**. Si
    siguiera diciendo `INALCANZABLE` con el arreglo puesto, o el arreglo no
    esta, o el instrumento miente. Y al reves: un guard que solo sabe decir
    «el hueco sigue ahi» no distingue «no he arreglado nada» de «lo he
    arreglado» — el error del primer gate de B3, donde la propiedad medida la
    cumplia un singleton MEJOR que un valor.
    """

    def test_la_medicion_ya_no_reporta_el_hueco(self) -> None:
        script = RAIZ / "scripts" / "measure_b4_observed_state.py"
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=RAIZ,
            capture_output=True,
            text=True,
        )
        salida = proc.stdout + proc.stderr
        assert "INALCANZABLE" not in salida, (
            "el instrumento sigue diciendo que la mitad observada es "
            f"inalcanzable, con el arreglo ya puesto:\n{salida}"
        )
        assert proc.returncode == 0, (
            f"el instrumento sale con {proc.returncode}; deberia salir con 0 "
            "cuando el hueco esta cerrado, porque su veredicto es «ya es "
            "alcanzable» y no «no se que medir»"
        )

    def test_la_medicion_detecta_al_menos_un_tercer_lado(self) -> None:
        """La contraprueba: el instrumento tiene que seguir midiendo.

        Si `verificar()` dejara de distinguir, el test de arriba pasaría en
        verde mirando y no viendo — que es el M2 de WI-110 aplicado a un
        instrumento nuevo.
        """
        sys.path.insert(0, str(RAIZ / "scripts"))
        import measure_b4_observed_state as med

        datos = med.medir()
        assert datos["1_esquema_declara_las_dos_mitades"]["spec_json"] is True
        assert datos["2_dominio_tiene_tipo_para_la_mitad_observada"]["Brick.spec"] is True
        assert isinstance(datos["3_hay_camino_de_escritura"]["UPDATE"], list)
        assert isinstance(datos["4_conditions_existe"]["condiciones_en_dominio"], list)

    def test_la_medicion_ve_un_arbol_que_no_es_el_repo(self) -> None:
        """Y en la otra dirección: sobre un árbol sintético, ve lo que hay.

        Una derivación que devuelve siempre «no hay nada» pasaría el primer
        test en verde para siempre.
        """
        sys.path.insert(0, str(RAIZ / "scripts"))
        import measure_b4_observed_state as med

        with tempfile.TemporaryDirectory() as tmp:
            arbol = Path(tmp)
            (arbol / "resources").mkdir()
            (arbol / "resources" / "status.py").write_text(
                "class Condition:\n    type: str\n", encoding="utf-8"
            )
            assert med._constantes.__module__  # el instrumento es importable
            campos = _campos_de_en_arbol(arbol, "Condition")
            assert campos == {"type"}, f"vio {sorted(campos)}"

    def test_el_instrumento_no_reventa_ante_un_update_de_otra_tabla(self) -> None:
        """Un `UPDATE` que no es de `resources` no debe romperlo.

        La primera versión partía el fichero entero por la palabra `SET` y
        reventaba con `IndexError` en el primer fichero con un `UPDATE` de
        otra tabla. Un instrumento que revienta parece que midió.
        """
        sys.path.insert(0, str(RAIZ / "scripts"))
        import measure_b4_observed_state as med

        with tempfile.TemporaryDirectory() as tmp:
            arbol = Path(tmp)
            (arbol / "otro.py").write_text(
                'SQL = "UPDATE runtime_events SET outcome = ? WHERE event_id = ?"\n',
                encoding="utf-8",
            )
            escrituras = med._escrituras_de_en_arbol(arbol, "resources")
            assert escrituras["UPDATE"] == [], (
                f"no hay UPDATE de resources, y vio {escrituras['UPDATE']}"
            )


def _campos_de(clase: str) -> set[str]:
    """Campos declarados de una clase, por AST sobre el árbol real.

    Se lee el AST y no el objeto: `dataclasses.fields` no distingue un campo
    de una clase defined de un atributo que se haya colado con `setattr`, y
    un guard que no distingue eso no vigila la frontera que dice vigilar.
    """
    for p in sorted(SRC.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        arbol = ast.parse(p.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ClassDef) and nodo.name == clase:
                return {
                    sub.target.id
                    for sub in nodo.body
                    if isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name)
                }
    raise AssertionError(f"la clase {clase} no existe en {SRC}")


def _campos_de_en_arbol(raiz: Path, clase: str) -> set[str]:
    for p in sorted(raiz.rglob("*.py")):
        arbol = ast.parse(p.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ClassDef) and nodo.name == clase:
                return {
                    sub.target.id
                    for sub in nodo.body
                    if isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name)
                }
    return set()
