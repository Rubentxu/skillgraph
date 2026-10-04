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
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
STATE = RAIZ / "STATE.yaml"
SCRIPT = RAIZ / "scripts" / "project_truth.py"


def _carga() -> object:
    spec = importlib.util.spec_from_file_location("project_truth_b14", SCRIPT)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["project_truth_b14"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def _ejecuta() -> tuple[int, dict | None, str]:
    """El verificador de verdad, en subproceso: es lo que importa.

    Importarlo y llamarlo dentro de la sesion que ya esta colectando tests da
    un `pytest --collect-only` que colecta la sesion equivocada, y el
    recuento real sale mal. Es el mismo motivo por el que el propio tool usa
    subproceso, y por eso aqui no se hace la excepcion.
    """
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=RAIZ,
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
    """Muta STATE.yaml y lo devuelve byte a byte, o falla ruidosamente.

    Un test que deja el estado sucio es peor que un test que no existe: el
    siguiente lee un estado que nadie escribio y el fallo aparece en el sitio
    equivocado. Por eso se comprueba el sha256, no se «deshace» en silencio.
    """

    def __init__(self) -> None:
        self._original = STATE.read_bytes()
        self._sha = hashlib.sha256(self._original).hexdigest()

    def __enter__(self) -> _EstadoRestaurado:
        return self

    def __exit__(self, *_exc: object) -> None:
        STATE.write_bytes(self._original)
        actual = hashlib.sha256(STATE.read_bytes()).hexdigest()
        assert actual == self._sha, "STATE.yaml no volvio a su estado original"


def _con_clave_duplicada(clave: str, valor_nuevo: str) -> str:
    """El estado con la MISMA clave declarada dos veces, con valores distintos.

    Se hace sobre el fichero real, no sobre una copia: el defecto nacio de dos
    consumidores leyendo el mismo fichero, y una copia sintetica no lo
    reproduce.
    """
    texto = STATE.read_text(encoding="utf-8")
    patron = re.compile(rf"^(\s*){re.escape(clave)}:\s*(.+)$", re.MULTILINE)
    if patron.search(texto) is None:
        raise AssertionError(f"STATE.yaml ya no declara la clave {clave!r}")
    # Dos claves con el MISMO nombre y distinto valor, al mismo nivel.
    return patron.sub(
        lambda m: f"{m.group(1)}{clave}: {m.group(2)}\n{m.group(1)}{clave}: {valor_nuevo}",
        texto,
        count=1,
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

    def test_una_clave_repetida_cambia_el_veredicto(self) -> None:
        """La propiedad, aislada: anadir una clave repetida CAMBIA el veredicto.

        **Por que se compara contra una linea base y no se mira `coherente`.**
        La primera version de este test afirmaba `coherente is not True`, y
        pasaba en verde con el tool VULNERABLE: en ese momento el estado ya era
        incoherente por otra cosa (el recuento de tests), y `coherente: false`
        no dice de que. Un guard que pasa por una causa ajena al objeto que
        vigila es un guard que no vigila, y es el mismo falso verde que B13
        cerro en el gate de 1.0.

        Comparar el veredicto con y sin la clave repetida aisla la propiedad y
        de paso hace que el test no dependa de si el estado circundante esta
        bien.
        """
        base = _ejecuta()[1]
        with (
            _EstadoRestaurado(),
            _inyectado(_con_clave_duplicada("current_workitem", "B99_inventado")),
        ):
            con_doble = _ejecuta()[1]
        assert base is not None, "el verificador no responde sobre el estado real"
        assert con_doble is not None, "el verificador no responde con la clave repetida"
        antes = (
            base.get("coherente"),
            tuple(base.get("contradicciones") or ()),
            base.get("ilegible", ""),
        )
        despues = (
            con_doble.get("coherente"),
            tuple(con_doble.get("contradicciones") or ()),
            con_doble.get("ilegible", ""),
        )
        assert antes != despues, (
            f"una clave duplicada no cambio el veredicto.\n  sin ella: {base}\n"
            f"  con ella: {con_doble}\nUn verificador al que se le anade una "
            f"contradiccion al estado y no se inmuta no esta mirando el estado."
        )

    def test_el_mensaje_nombra_la_clave_y_las_versiones_en_contradicto(self) -> None:
        """Un verificador que dice «falso» sin decir cual era la verdad deja a
        quien corrige haciendo la cuenta a mano, que es el trabajo que el
        verificador existe para evitar."""
        with (
            _EstadoRestaurado(),
            _inyectado(_con_clave_duplicada("current_workitem", "B99_inventado")),
        ):
            _, salida, texto = _ejecuta()
        if salida is None or "ilegible" in salida:
            # La via de la excepcion: tambien vale, pero tiene que NOMBRAR la clave.
            assert "current_workitem" in texto, f"la excepcion no nombra la clave: {texto[:300]!r}"
            return
        contradicciones = " ".join(salida.get("contradicciones") or [])
        assert contradicciones, f"coherente:false sin nombrar nada: {salida}"
        assert "B99_inventado" in contradicciones, (
            f"la contradiccion no nombra el valor que no coincide: {contradicciones!r}"
        )


def _inyectado(texto: str) -> object:
    class _Inyecta:
        def __enter__(self) -> None:
            STATE.write_text(texto, encoding="utf-8")

        def __exit__(self, *_exc: object) -> None:
            return None

    return _Inyecta()


# =====================================================================


def _rechaza(estado_nuevo: str, debe_mencionar: str, que: str) -> None:
    """El verificador RECHAZA un estado con la forma `estado_nuevo`.

    «Rechazar» tiene tres salidas legitimas y las tres valen, pero solo si el
    verificador DIJO por que:

    1. `ilegible`, nombrando el campo — la via de la excepcion.
    2. `coherente: false`, cuando el valor se pudo leer pero no cuadra.
    3. salida ilegible — el verificador fallo al leer el estado.

    Lo que NO vale es un `coherente: true`, ni un crash mudo sin decir nada:
    un verificador que se rompe con un tipo raro no esta rechazando el tipo,
    esta roto, y las dos cosas se parecen en el codigo de salida.
    """
    with _EstadoRestaurado(), _inyectado(estado_nuevo):
        salida = _ejecuta()[1]
    if salida is None:
        raise AssertionError(
            f"{que}: el verificador no devolvio JSON. Si fallo al LEER el estado, "
            f"tiene que decirlo con «ilegible», no desaparecer."
        )
    if "ilegible" in salida:
        assert debe_mencionar in salida["ilegible"], (
            f"{que}: el verificador lo rechazo pero sin nombrar el campo: {salida['ilegible']!r}"
        )
        return
    assert salida.get("coherente") is not True, f"{que}: el verificador dijo coherente. {salida}"


# ====================================================================
class TestLosTiposNoSeAdelantan:
    # ====================================================================
    """Lo UNICO que mide: que un valor de tipo equivocado no pase por bueno.

    Antes, `total: <lo que sea>` se leia con un regex que pedia digitos, y un
    `tag:` sin `v` se leia con un regex mas tolerante. Con YAML, un tipo
    equivocado llega hasta el verificador si no se comprueba, y ahi es donde se
    convierte en `coherente: true` con un campo sin sentido.
    """

    def test_un_total_que_no_es_entero_se_rechaza(self) -> None:
        _rechaza(
            re.sub(
                r"^(\s*total:)\s*\d+",
                r"\g<1> 'muchos'",
                STATE.read_text(encoding="utf-8"),
                count=1,
                flags=re.MULTILINE,
            ),
            "total",
            "un total que no es entero",
        )

    def test_un_tag_sin_la_v_se_rechaza(self) -> None:
        _rechaza(
            re.sub(
                r"^(\s*tag:\s*)v",
                r"\g<1>",
                STATE.read_text(encoding="utf-8"),
                count=1,
                flags=re.MULTILINE,
            ),
            "tag",
            "un tag sin la v",
        )

    def test_un_workitem_vacio_se_rechaza(self) -> None:
        _rechaza(
            re.sub(
                r"^(\s*current_workitem:).*$",
                r"\g<1>",
                STATE.read_text(encoding="utf-8"),
                count=1,
                flags=re.MULTILINE,
            ),
            "current_workitem",
            "un workitem vacio",
        )


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
        rc, salida, crudo = _ejecuta()
        assert rc in (0, 1), f"el verificador no sabe responder: rc={rc} {crudo[:250]!r}"
        assert salida is not None, f"la salida no es JSON: {crudo[:250]!r}"
        assert isinstance(salida.get("coherente"), bool), salida
        for clave in ("bloque", "release", "tag_vcs", "version", "workitem_state"):
            assert clave in salida, f"falta {clave} en el veredicto: {salida}"

    def test_el_endurecimiento_no_introdujo_contradicciones_nuevas(self) -> None:
        _, salida, _ = _ejecuta()
        assert salida is not None
        nuevas = [c for c in (salida.get("contradicciones") or []) if not c.startswith("tests:")]
        assert not nuevas, (
            f"contradicciones que no son del recuento, y por tanto no son de WI-115: {nuevas}"
        )

    def test_un_total_desalineado_sigue_detectandose(self) -> None:
        texto = re.sub(
            r"^(\s*total:)\s*\d+",
            r"\g<1> 9999",
            STATE.read_text(encoding="utf-8"),
            count=1,
            flags=re.MULTILINE,
        )
        with _EstadoRestaurado(), _inyectado(texto):
            _, salida, _ = _ejecuta()
        assert salida is not None and salida.get("coherente") is False
        assert any("tests" in c for c in salida.get("contradicciones") or []), (
            f"la contradiccion no habla de los tests: {salida.get('contradicciones')}"
        )

    def test_un_workitem_que_no_existe_sigue_detectandose(self) -> None:
        texto = STATE.read_text(encoding="utf-8").replace(
            "  current_workitem: B13", "  current_workitem: B99", 1
        )
        with _EstadoRestaurado(), _inyectado(texto):
            _, salida, _ = _ejecuta()
        assert salida is not None and salida.get("coherente") is False
        assert any("workitem" in c for c in salida.get("contradicciones") or []), (
            f"la contradiccion no habla del workitem: {salida.get('contradicciones')}"
        )

    def test_una_version_incoherente_sigue_detectandose(self) -> None:
        init = RAIZ / "src" / "skillgraph" / "__init__.py"
        original = init.read_bytes()
        try:
            init.write_text('__version__ = "7.7.7"\n', encoding="utf-8")
            _, salida, _ = _ejecuta()
        finally:
            init.write_bytes(original)
        assert salida is not None and salida.get("coherente") is False

    def test_falta_de_un_fichero_sigue_siendo_ruidosa(self) -> None:
        actual = RAIZ / "CURRENT.md"
        original = actual.read_bytes()
        try:
            actual.unlink()
            rc, salida, crudo = _ejecuta()
        finally:
            actual.write_bytes(original)
        assert rc != 0, f"sin CURRENT.md el verificador deberia fallar: {crudo[:200]}"
        assert salida is None or "ilegible" in salida
