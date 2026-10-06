"""B14: la autoridad de coherencia no se puede engañar con una clave duplicada.

El hallazgo
-----------
Al cerrar B13 se anadio una segunda clave `current_workitem` en `STATE.yaml`.
Seis ficheros de test leian el estado con `yaml.safe_load` —que se queda con
la clave duplicada por la ultima— y `scripts/project_truth.py` lo leia entero
con regex —que se queda con la primera—. Resultado medido:

    yaml.safe_load          -> B13_cerrado
    regex de project_truth  -> B13
    project_truth           -> coherente: true, contradicciones: []

Y ese tool es la respuesta a «¿donde esta el proyecto?», en la que B0..B13 se
apoyan. Un verificador que dice «coherente» cuando no lo esta es PEOR que no
tener verificador, porque las dos mitades de la propiedad se apoyan en el.

Que se mide aqui
----------------
No «que el YAML tenga una clave repetida» —eso lo hace el parser— sino que
**el verificador no pueda decir coherente cuando el estado no lo es**, y que
diga POR QUE. Los cuatro conjuntos son disjuntos y cada uno declara en su
docstring que es lo UNICO que mide, para que ninguno tape a otro.

LA DEFORMACION, Y POR QUE B23 LA MUDO DE SITIO (B23)
----------------------------------------------------
Hasta B22 este fichero deformaba el ARBOL REAL: escribia `__version__ =
"7.7.7"` en `src/skillgraph/__init__.py`, escribia en `STATE.yaml` y BORRABA
`CURRENT.md`. MEDIDO por que era peligroso y no por que se viera: durante la
suite completa ese `__init__.py` tuvo DOS contenidos —el real en 195 649
lecturas y el inyectado en 1 214— y el predicado de reproducibilidad del gate
de 1.0 lo leia como linea base. Perdio el informe entero de veinte
propiedades.

Bloqueado por diseno, porque `project_truth.py` derivaba su RAIZ de `__file__`
y ningun sandbox daba una respuesta de verdad. MEDIDO entonces: con los
cuatro ficheros que el script lee, la colecta sale `rc=5` y el verificador
responde `ilegible` POR EL MOTIVO EQUIVOCADO; copiando el arbol entero salen
722 ficheros y `rc=3` porque la copia no es un repositorio.

B23 le dio al instrumento una raiz por parametro, y con ella se abre esto: las
tres deformaciones apuntan a un arbol EN `tmp_path`. Los mecanismos NO se
borran —miden cosas reales: la version incoherente, la clave duplicada, el
fichero ausente y la coleccion interrumpida—; lo que cambia es DONDE, no QUE.

**Y LO QUE NO SE PUEDE REPRODUCIR EN UN SANDBOX, MEDIDO, NO SUPUESTO.** Romper
el `__init__.py` del sandbox NO hace fallar la colecta: si el test no importa
`skillgraph` el fichero no se lee, y si lo importa resuelve al PAQUETE
INSTALADO, no al `src/` del sandbox. Los dos casos dan `rc=0` y 1 test
colectado. La interrupcion se provoca por donde de verdad interrumpe: un test
con error de sintaxis, que deja `2 tests collected, 1 error` con `rc=2` — la
misma linea parcial que B14 cerro.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
STATE = RAIZ / "STATE.yaml"
SCRIPT = RAIZ / "scripts" / "project_truth.py"


# --------------------------------------------------------------------------
# El arbol de verdad (B23)
# --------------------------------------------------------------------------

BLOQUE = "B14"
VERSION = "0.14.0.dev0"
RELEASE = "0.14.0"


def _arbol_de_verdad(base: Path) -> Path:
    """Un proyecto que el verificador puede leer DE VERDAD.

    Lo minimo que hace falta, y por que cada cosa esta:

    - `.git` con un tag: `tag_real()` lo consulta, y sin el daria `None` y
      el cruce de release no tendria contra que medir.
    - un `tests/` con un test propio: `total_colectado()` cuenta lo que
      colecta, y sin tests daria `rc=5` — el motivo equivocado, que es justo
      lo que hacia que un sandbox no sirviera.
    - `tests.total` igual a lo que ese test colecta: si no, el verificador
      direia que el proyecto se contradice, y todos los tests que deforman
      una sola cosa medirian el ruido de fondo en vez de su mutacion.

    Se construye por COPIA de los ficheros reales y no escritos a mano: un
    estado sintetico que no se parece al del proyecto haria que los tests
    midieran una forma de estado que no existe.
    """
    (base / "src" / "skillgraph").mkdir(parents=True)
    (base / "tests").mkdir(parents=True)
    shutil.copy2(RAIZ / "STATE.yaml", base / "STATE.yaml")
    shutil.copy2(RAIZ / "CURRENT.md", base / "CURRENT.md")
    (base / "src" / "skillgraph" / "__init__.py").write_text(
        f'__version__ = "{VERSION}"\n', encoding="utf-8"
    )
    (base / "tests" / "test_del_arbol.py").write_text(
        "def test_del_arbol() -> None:\n    assert True\n", encoding="utf-8"
    )
    _con_git(base, RELEASE)
    return base


def _con_git(base: Path, tag: str) -> None:
    for cmd in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "b23@b23"],
        ["git", "config", "user.name", "b23"],
        ["git", "add", "-A"],
        ["git", "commit", "-qm", "arbol"],
        ["git", "tag", f"v{tag}"],
    ):
        subprocess.run(cmd, cwd=base, capture_output=True, check=False)


def _rota(raiz: Path, bloque: str, version: str, release: str, total: int) -> None:
    """Deja el estado del sandbox cuadrando con el sandbox.

    `STATE.yaml` y `ROADMAP.md` se copian del repo real, asi que declaran la
    version y la cifra del REPO, no las del arbol. Sin esta rotacion el
    verificador mediria seis contradicciones de fondo y cada test que deforma
    una sola cosa veria un rojo que no es el suyo.

    Se reescriben los TRES sitios que declaran esas truths —el estado, la
    version y la ventana del roadmap— porque ahora los tres se cruzan. Y esa
    es justamente la garantia que B23 compro: hasta hace un rato, mover el
    bloque exigia tres ficheros y nadie lo notaba si se olvidaba uno.
    """
    import yaml

    estado = yaml.safe_load((raiz / "STATE.yaml").read_text(encoding="utf-8"))
    estado["release"]["tag"] = f"v{release}"
    estado["roadmap"]["current_workitem"] = bloque
    estado["tests"]["total"] = total
    (raiz / "STATE.yaml").write_text(
        yaml.safe_dump(estado, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )

    (raiz / "CURRENT.md").write_text(
        f"> **Bloque {bloque} del arbol de prueba.**\n>\n> Lo unico que dice es el bloque.\n",
        encoding="utf-8",
    )

    (raiz / "ROADMAP.md").write_text(
        "# Roadmap\n\n"
        "## Dónde está el proyecto\n\n"
        f"> Bloque vivo: **{bloque}** — El árbol de la prueba\n"
        f"> Versión activa `{version}` · último tag `v{release}` · {total} tests · 16/16 UAT\n"
        "\n"
        "## El mapa\n\n"
        "| Bloque | Objetivo | Resultado |\n|---|---|---|\n"
        f"| **{bloque}** | El árbol de la prueba | Se mide de verdad |\n",
        encoding="utf-8",
    )


@pytest.fixture
def arbol(tmp_path: Path) -> Path:
    """Un proyecto completo, disposable y coherente."""
    base = _arbol_de_verdad(tmp_path / "arbol")
    _rota(base, BLOQUE, VERSION, RELEASE, 1)
    return base


def _carga() -> object:
    spec = importlib.util.spec_from_file_location("project_truth_b14", SCRIPT)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["project_truth_b14"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def _ejecuta(raiz: Path | None = None) -> tuple[int, dict | None, str]:
    """El verificador de verdad, en subproceso: es lo que importa.

    Importarlo y llamarlo dentro de la sesion que ya esta colectando tests da
    un `pytest --collect-only` que colecta la sesion equivocada, y el
    recuento real sale mal. Es el mismo motivo por el que el propio tool usa
    subproceso, y por eso aqui no se hace la excepcion.

    `raiz` es el arbol que se mide, y es un PARAMETRO desde B23: sin el,
    medir un sandbox era imposible y por eso todos los tests deformaban el
    arbol real. `None` significa «el repositorio», que es lo que necesitan los
    tests que solo comprueban que el verificador responde.
    """
    comando = [sys.executable, str(SCRIPT)]
    if raiz is not None:
        comando += ["--raiz", str(raiz)]
    proc = subprocess.run(
        comando,
        cwd=raiz if raiz is not None else RAIZ,
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    salida = proc.stdout + proc.stderr
    try:
        return proc.returncode, json.loads(salida), salida
    except json.JSONDecodeError:
        return proc.returncode, None, salida


class _EstadoRestaurado:
    """Muta un `STATE.yaml` —el del sandbox— y lo devuelve byte a byte.

    Un test que deja el estado sucio es peor que un test que no existe: el
    siguiente lee un estado que nadie escribio y el fallo aparece en el sitio
    equivocado. Por eso se comprueba el sha256, no se «deshace» en silencio.
    """

    def __init__(self, raiz: Path) -> None:
        self._estado = raiz / "STATE.yaml"
        self._original = self._estado.read_bytes()
        self._sha = hashlib.sha256(self._original).hexdigest()

    def __enter__(self) -> _EstadoRestaurado:
        return self

    def __exit__(self, *_exc: object) -> None:
        self._estado.write_bytes(self._original)
        actual = hashlib.sha256(self._estado.read_bytes()).hexdigest()
        assert actual == self._sha, "STATE.yaml no volvio a su estado original"


def _con_clave_duplicada(raiz: Path, clave: str, valor_nuevo: str) -> str:
    """El estado con la MISMA clave declarada dos veces, con valores distintos.

    Se hace sobre el fichero real, no sobre una copia: el defecto nacio de dos
    consumidores leyendo el mismo fichero, y una copia sintetica no lo
    reproduce.
    """
    texto = (raiz / "STATE.yaml").read_text(encoding="utf-8")
    patron = re.compile(rf"^(\s*){re.escape(clave)}:\s*(.+)$", re.MULTILINE)
    if patron.search(texto) is None:
        raise AssertionError(f"STATE.yaml ya no declara la clave {clave!r}")
    # Dos claves con el MISMO nombre y distinto valor, al mismo nivel.
    return patron.sub(
        lambda m: f"{m.group(1)}{clave}: {m.group(2)}\n{m.group(1)}{clave}: {valor_nuevo}",
        texto,
        count=1,
    )


def _valor_de(raiz: Path, clave: str) -> str:
    """El valor que el estado REAL declara para `clave`, leido del fichero.

    Se deriva en vez de escribirse porque un contrasalto atado a un valor vivo
    se vuelve no-op en cuanto el valor cambia, y un no-op en un contrasalto es
    peor que no escribirlo: el guard sigue verde y ya no mide su propia via de
    manifestacion. MEDIDO en este fichero: con `current_workitem: B13` escrito a
    mano, el paso a B14 dejo de mutar el estado y el test seguia dando verde.
    """
    texto = (raiz / "STATE.yaml").read_text(encoding="utf-8")
    patron = re.compile(rf"^(\s*){re.escape(clave)}:\s*(\S+)", re.MULTILINE)
    encontrado = patron.search(texto)
    if encontrado is None:
        raise AssertionError(f"STATE.yaml ya no declara {clave!r} con esa forma")
    return encontrado.group(2)


class _inyectado:
    """Escribe `texto` en STATE.yaml y lo restaura al salir.

    Se apoya en el mismo `_EstadoRestaurado` que usan los demas tests, para
    que restaurar sea siempre la MISMA comprobacion por sha256 y no una
    segunda via que se pueda olvidar.
    """

    def __init__(self, raiz: Path, texto: str) -> None:
        self._estado = raiz / "STATE.yaml"
        self._texto = texto
        self._restaurador = _EstadoRestaurado(raiz)

    def __enter__(self) -> _inyectado:
        self._restaurador.__enter__()
        self._estado.write_text(self._texto, encoding="utf-8")
        return self

    def __exit__(self, *exc: object) -> None:
        self._restaurador.__exit__(*exc)


def _rechaza(raiz: Path, estado_nuevo: str, campo: str, que: str) -> None:
    """El verificador rechaza un valor mal tipado POR EL TIPO, y lo dice.

    **Por que se exige el `ilegible` y no basta `coherente: false`.** La
    version anterior de este helper aceptaba tres salidas, y con la
    comprobacion de tipo deshabilitada los tres tests de tipo seguian en
    verde: `total: 'muchos'` no cuadra con el recuento real, luego el
    verificador decia `coherente: false` — por el motivo equivocado — y la
    asercion debil lo contaba como aprobado. MEDIDO con la sonda M3 del
    harness: `if False:` en la comprobacion de tipo y `3 passed`.

    Un verificador al que se le rompe una cosa y sigue dando «esto no cuadra»
    no ha comprobado NADA de la cosa que se rompio. Por eso el rechazo tiene
    que ser el del TIPO: `ilegible` nombrando el campo.
    """
    with _inyectado(raiz, estado_nuevo):
        salida = _ejecuta(raiz)[1]
    if salida is None:
        raise AssertionError(
            f"{que}: el verificador no devolvio JSON. Si fallo al LEER el estado, "
            f"tiene que decirlo con «ilegible», no desaparecer."
        )
    if "ilegible" not in salida:
        raise AssertionError(
            f"{que}: el verificador NO rechazo el valor por su tipo. Djo: {salida}.\n"
            f"Si hay una contradiccion de otro tipo, el estado no cuadra por otra "
            f"razon y este test no midio lo que dice medir. Lo que se espera es un "
            f"«ilegible» que nombre {campo!r}."
        )
    assert campo in salida["ilegible"], (
        f"{que}: el verificador lo rechazo pero sin nombrar el campo: {salida['ilegible']!r}"
    )


# =====================================================================
class TestElEstadoSeLeeDeUnaSolaManera:
    """Lo UNICO que mide: que no queden readers de STATE por regex.

    La propiedad no es «el tool funciona» —eso lo mide el ejecutarlo— sino que
    no haya dos caminos de lectura. Un regex sobre el mismo fichero que otro
    consumidor parsea con YAML puede discrepar en silencio, y el caso esta
    medido: `yaml.safe_load` dio `B13_cerrado` y el regex `B13`.
    """

    def test_no_queda_ningun_regex_sobre_state_yaml(self) -> None:
        arbol = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        patrones: list[tuple[str, int]] = []
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Assign):
                continue
            if not (
                isinstance(nodo.value, ast.Call)
                and getattr(nodo.value.func, "attr", "") == "compile"
                and nodo.value.args
                and isinstance(nodo.value.args[0], ast.Constant)
            ):
                continue
            patron = str(nodo.value.args[0].value)
            if "total:" not in patron and "current_workitem:" not in patron:
                continue
            for destino in nodo.targets:
                if isinstance(destino, ast.Name) and destino.id.startswith("_"):
                    # Un regex cuyo PATRON menciona una clave de STATE.yaml.
                    patrones.append((destino.id, nodo.lineno))
        assert not patrones, (
            f"quedan readers por regex de STATE.yaml: {patrones}. Cada uno puede "
            f"encontrar una clave distinta de la que encuentra el parser YAML, y con "
            f"dos consumidores eso es una contradiccion que nadie ve."
        )

    def test_el_estado_se_parsea_una_sola_vez_por_ejecucion(self) -> None:
        """CONTRA-SALTO del anterior por su otra via de manifestacion.

        Si alguien quita el regex pero mete un segundo `yaml.load` en otra
        funcion, el anterior pasa y la lectura unica deja de ser unica. Cuenta
        los PUNTOS DE ENTRADA, no los nombres: el patron del argumento cambia
        si alguien escribe `yaml.load(_lee(...))` en vez de
        `yaml.load("STATE.yaml")`, y un guard que buscara el literal dejaria de
        ver el segundo sitio.
        """
        texto = SCRIPT.read_text(encoding="utf-8")
        entradas = [
            nodo.lineno
            for nodo in ast.walk(ast.parse(texto))
            if isinstance(nodo, ast.Call)
            and isinstance(nodo.func, ast.Attribute)
            and isinstance(nodo.func.value, ast.Name)
            and nodo.func.value.id == "yaml"
            and nodo.func.attr in {"load", "safe_load", "full_load", "unsafe_load"}
        ]
        assert len(entradas) == 1, (
            f"STATE.yaml se parsea en {len(entradas)} sitios: {entradas}. Una sola "
            f"lectura es lo que hace imposible que este tool y los tests digan cosas "
            f"distintas del mismo estado."
        )


# =====================================================================
class TestUnaClaveDuplicadaNoPasaPorAlto:
    """Lo UNICO que mide: el comportamiento ante una clave repetida."""

    def test_una_clave_repetida_hace_el_estado_ilegible(self, arbol: Path) -> None:
        """El contrato: con la misma clave dos veces, el estado NO se lee.

        **Por que se exige `ilegible` y no basta con que cambie el veredicto.**
        Con el constructor de claves duplicadas retirado —la sonda M2 del
        harness— YAML toma la ULTIMA clave y el verificador dice, textual,
        `workitem: STATE declara B99_inventado, CURRENT declara B13`. Elige
        una de las dos declaraciones y la presenta como la verdad, atribuyendo
        la otra a otro fichero. El veredicto cambia, luego un test de «cambia
        el veredicto» pasa, y no deberia: aceptar «el tool escogio una» es
        aceptar el defecto que este bloque cierra.

        No se sabe cual de las dos quiso el autor, luego la lectura honesta es
        negarse a leer. Un `0` o un `None` aqui seria el cero silencioso
        contra el que WI-115 puso un contrasalto, un nivel mas arriba.
        """
        with _inyectado(arbol, _con_clave_duplicada(arbol, "current_workitem", "B99_inventado")):
            salida = _ejecuta(arbol)[1]
        assert salida is not None, "el verificador no devolvio JSON con la clave repetida"
        assert "ilegible" in salida, (
            f"una clave repetida no hizo el estado ilegible: {salida}. El verificador "
            f"tiene que negarse a leer un estado donde la misma clave aparece dos veces "
            f"con valores distintos, en vez de elegir una."
        )
        assert "current_workitem" in salida["ilegible"], (
            f"el estado es ilegible pero el mensaje no nombra la clave: {salida['ilegible']!r}"
        )

    def test_el_valor_que_se_lee_no_es_uno_de_los_dos_a_eleccion(self, arbol: Path) -> None:
        """CONTRA-SALTO del anterior por su otra via de manifestacion.

        Si alguien arregla la excepcion poniendo un `break` en el bucle de
        claves el mecanismo deja de lanzar, el estado se lee entero, y el
        verificador publica una de las dos declaraciones como si fuera la
        verdad. Este comprueba que no publica NINGUNA de las dos.

        **El conjunto prohibido se DERIVA del estado, no se escribe.** La
        primera version tenia `{"B13", "B99_inventado"}` a mano, y al pasar el
        workitem vivo a B14 ese `B13` dejo de ser una de las dos declaraciones:
        el `break` hipotetico publicaria `B14`, que el conjunto no prohibia, y
        el contrasalto pasaria en verde midiendo exactamente el defecto que
        describe. Un contrasalto que se desactiva al cambiar el calendario ya
        no es un contrasalto.
        """
        declarado = _valor_de(arbol, "current_workitem")
        with _inyectado(arbol, _con_clave_duplicada(arbol, "current_workitem", "B99_inventado")):
            salida = _ejecuta(arbol)[1]
        assert salida is not None
        publicado = str(salida.get("workitem_state", ""))
        assert publicado not in {declarado, "B99_inventado"}, (
            f"el verificador publico {publicado!r} como el workitem declarado, y hay dos "
            f"declaraciones en el fichero ({declarado!r} y 'B99_inventado'). Escoger una "
            f"es el defecto."
        )


class TestLosTiposNoSeAdelantan:
    # ====================================================================
    """Lo UNICO que mide: que un valor de tipo equivocado no pase por bueno.

    Antes, `total: <lo que sea>` se leia con un regex que pedia digitos, y un
    `tag:` sin `v` se leia con un regex mas tolerante. Con YAML, un tipo
    equivocado llega hasta el verificador si no se comprueba, y ahi es donde se
    convierte en `coherente: true` con un campo sin sentido.
    """

    def test_un_total_que_no_es_entero_se_rechaza(self, arbol: Path) -> None:
        _rechaza(
            arbol,
            re.sub(
                r"^(\s*total:)\s*\d+",
                r"\g<1> 'muchos'",
                (arbol / "STATE.yaml").read_text(encoding="utf-8"),
                count=1,
                flags=re.MULTILINE,
            ),
            "total",
            "un total que no es entero",
        )

    def test_un_tag_sin_la_v_se_rechaza(self, arbol: Path) -> None:
        _rechaza(
            arbol,
            re.sub(
                r"^(\s*tag:\s*)v",
                r"\g<1>",
                (arbol / "STATE.yaml").read_text(encoding="utf-8"),
                count=1,
                flags=re.MULTILINE,
            ),
            "tag",
            "un tag sin la v",
        )

    def test_un_workitem_vacio_se_rechaza(self, arbol: Path) -> None:
        _rechaza(
            arbol,
            re.sub(
                r"^(\s*current_workitem:).*$",
                r"\g<1>",
                (arbol / "STATE.yaml").read_text(encoding="utf-8"),
                count=1,
                flags=re.MULTILINE,
            ),
            "current_workitem",
            "un workitem vacio",
        )


# =====================================================================
class TestUnRecuentoQueNoSeTerminoNoSePublica:
    """Lo UNICO que mide: que un numero que no se pudo medir no se publique.

    **Por que NO es un no-op.** El fallo que este test vigila va en la
    direccion «dice que no cuadra» cuando el estado SI cuadra. B14 cierra la
    direccion contraria, «dice que cuadra» cuando no, que es la peligrosa; este
    no la invierte, la que ya era. Se incluye porque se ha MEDIDO en el
    instrumento de este mismo bloque, y porque un verificador que afirma un
    numero que no conto es del mismo GENERO que uno que afirma una coherencia
    que no midio: los dos son la autoridad de coherencia hablando de algo que
    no sabe.

    MEDIDO: con `src/skillgraph/__init__.py` mutilado, pytest no termina la
    colecta, imprime «2867 tests collected, 27 errors» y sale con rc=2. El
    numero es real —son los tests que llego a ver— pero no es EL recuento, y
    el verificador lo publicaba con su nombre: «tests: STATE declara 3284, el
    arbol colecta 2867». Sin 417 tests y sin decir por que.
    """

    def test_una_colecta_interrumpida_no_publica_un_recuento(self, arbol: Path) -> None:
        """MEDIDO, y por que la interrupcion va por aqui y no por `__init__.py`.

        Romper el `__init__.py` del SANDBOX no hace fallar su colecta: si el
        test no importa `skillgraph` el fichero no se lee, y si lo importa
        resuelve al PAQUETE INSTALADO, no al `src/` del sandbox. Los dos casos
        dan `rc=0` con 1 test colectado — MEDIDO, no supuesto.

        En el arbol real el mecanismo era otro: todos los tests importan el
        paquete del repo, luego mutilar su `__init__.py` los rompia a todos.
        Aqui la interrupcion se provoca donde de verdad interrumpe: un test
        con error de sintaxis deja `2 tests collected, 1 error` con `rc=2`,
        que es EXACTAMENTE la linea parcial que B14 cerro. Lo que el guard
        vigila —que un recuento de una colecta que no termino no se
        publique— se reproduce igual.

        **Y LA AFIRMACION SE ENDURECIO EN B23, PORQUE MEDIDA ERA INSUFICIENTE.**
        La version anterior comprobaba `not any(c.startswith("tests:") ...)`.
        MEDIDO con la sonda M5 del harness de B23: desactivando la
        comprobacion del codigo de salida, el verificador lee el numero
        PARCIAL y publica `coherente: true` con `tests_reales: 2` — el
        parcial coincide con el declarado, luego no hay contradiccion `tests:`
        que emitir, y el test pasaba en verde con un numero que no se conto.
        Una asercion que mira la CONTRADICCION no ve la PUBLICACION. La de
        ahora exige lo que la propiedad dice: que el verificador se NIEGUE a
        publicar el recuento y lo diga con `ilegible`, que es la lectura
        honesta de una colecta que no termino.
        """
        (arbol / "tests" / "test_roto.py").write_text("def roto(:\n    pass\n", encoding="utf-8")
        rc, salida, crudo = _ejecuta(arbol)
        assert salida is not None, crudo[:250]

        # (1) No se publica un recuento de una colecta que no termino. Esta es
        # la asercion que M5 caza: sin ella el guard pasa con un numero falso.
        assert "ilegible" in salida, (
            f"una colecta interrumpida dio un veredicto en vez de una negativa: {salida}. "
            f"El numero de una colecta que no termino es el numero de otra magnitud, y "
            f"publicarlo con nombre propio es afirmar que se conto lo que no se conto."
        )
        assert "tests_reales" not in salida, (
            f"el verificador publico un recuento de una colecta que no termino: {salida}. "
            f"El numero parcial es real —son los tests que llego a ver— pero no es EL "
            f"recuento, y sin una contradiccion `tests:` que lo delate pasaria en verde."
        )

        # (2) El motivo dice que la colecta no termino, no solo que algo fallo.
        assert "no terminó" in salida["ilegible"] or "no termino" in salida["ilegible"], (
            f"el motivo no dice que la colecta no termino: {salida['ilegible']!r}"
        )
        assert rc == 2, f"una colecta que no se pudo medir tiene que salir con 2, dio {rc}"


# =====================================================================
class TestLoQueYaFuncionabaSigueFuncionando:
    """CONTRA-SALTO de la direccion contraria: que el arreglo no rompa nada.

    Un guard que solo sabe decir que no, aplicado a un verificador que se
    acaba de endurecer, es indistinguible de uno que lo ha roto.

    **Por que este conjunto NO es dueño del recuento de tests.** Una
    asercion `coherente is True` sobre el estado real fallaria cada vez que se
    anadiera un test nuevo sin actualizar `tests.total` -es decir, durante
    casi todo el desarrollo- y ese papel ya lo tiene
    `tests/test_wi115_state_total_truthfulness.py`. Reclamarlo aqui ataria
    este guard al ritmo de un contador que no es suyo y dejaria de medir lo
    que mide. Lo que se mide es que **el endurecimiento no introdujo ninguna
    contradiccion NUEVA**: las unicas admitidas son las del recuento, que son
    de WI-115.
    """

    def test_el_verificador_corre_y_devuelve_json_valido(self) -> None:
        """Sin `raiz`: este mira el REPOSITORIO REAL, y es deliberado.

        Es el control de que el verificador responde sobre el proyecto de
        verdad, no solo sobre un sandbox construido por los tests. No deforma
        nada —solo lee— luego no tiene por que moverse a `tmp_path`.
        """
        rc, salida, crudo = _ejecuta()
        assert rc in (0, 1), f"el verificador no sabe responder: rc={rc} {crudo[:250]!r}"
        assert salida is not None, f"la salida no es JSON: {crudo[:250]!r}"
        assert isinstance(salida.get("coherente"), bool), salida
        for clave in ("bloque", "release", "tag_vcs", "version", "workitem_state"):
            assert clave in salida, f"falta {clave} en el veredicto: {salida}"

    def test_el_endurecimiento_no_introdujo_contradicciones_nuevas(self) -> None:
        """Sin `raiz`, como el anterior: control del repositorio REAL.

        Es el otro sentido del contrasalto. Los tests de arriba comprueban que
        el verificador RECHAZA lo que esta mal; este comprueba que no
        inventa contradicciones donde no hay nada. Sin el, un verificador que
        dijera «incoherente» a todo —por cualquier cosa, o por una ventana
        desfasada— seria indistinguible de uno que endurece de verdad.
        """
        _, salida, _ = _ejecuta()
        assert salida is not None
        nuevas = [c for c in (salida.get("contradicciones") or []) if not c.startswith("tests:")]
        assert not nuevas, (
            f"contradicciones que no son del recuento, y por tanto no son de WI-115: {nuevas}"
        )

    def test_un_total_desalineado_sigue_detectandose(self, arbol: Path) -> None:
        texto = re.sub(
            r"^(\s*total:)\s*\d+",
            r"\g<1> 9999",
            (arbol / "STATE.yaml").read_text(encoding="utf-8"),
            count=1,
            flags=re.MULTILINE,
        )
        with _inyectado(arbol, texto):
            _, salida, _ = _ejecuta(arbol)
        assert salida is not None and salida.get("coherente") is False
        assert any("tests" in c for c in salida.get("contradicciones") or []), (
            f"la contradiccion no habla de los tests: {salida.get('contradicciones')}"
        )

    def test_un_workitem_que_no_existe_sigue_detectandose(self, arbol: Path) -> None:
        """El workitem se DERIVA del estado, no esta escrito en el test.

        MEDIDO: la primera version hacia `.replace("  current_workitem: B13",
        ...)`. Al cambiar el workitem vivo a B14 el replace se volvio un no-op,
        el estado se quedaba coherente y el test caia sin que nadie hubiera
        tocado el verificador. Un guard atado al valor de un campo vivo no
        mide el verificador: mide el calendario.
        """
        texto, cambios = re.subn(
            r"^(\s*current_workitem:).*$",
            r"\g<1> B99_inventado",
            (arbol / "STATE.yaml").read_text(encoding="utf-8"),
            count=1,
            flags=re.MULTILINE,
        )
        assert cambios == 1, (
            "STATE.yaml ya no declara `current_workitem` con esa forma; este test "
            "no sabria que mutar y pasaria por no hacer nada"
        )
        with _inyectado(arbol, texto):
            _, salida, _ = _ejecuta(arbol)
        assert salida is not None and salida.get("coherente") is False
        assert any("workitem" in c for c in salida.get("contradicciones") or []), (
            f"la contradiccion no habla del workitem: {salida.get('contradicciones')}"
        )

    def test_una_version_incoherente_sigue_detectandose(self, arbol: Path) -> None:
        init = arbol / "src" / "skillgraph" / "__init__.py"
        init.write_text('__version__ = "7.7.7"\n', encoding="utf-8")
        _, salida, _ = _ejecuta(arbol)
        assert salida is not None and salida.get("coherente") is False

    def test_falta_de_un_fichero_sigue_siendo_ruidosa(self, arbol: Path) -> None:
        actual = arbol / "CURRENT.md"
        original = actual.read_bytes()
        try:
            actual.unlink()
            rc, salida, crudo = _ejecuta(arbol)
        finally:
            actual.write_bytes(original)
        assert rc != 0, f"sin CURRENT.md el verificador deberia fallar: {crudo[:200]}"
        assert salida is None or "ilegible" in salida
