"""WI-92 — lo que WI-90 registro como deuda, medido. Y dos guards.

Por que este fichero
--------------------
WI-90 cerro el round-trip de `FileSignature` y registro, SIN MEDIR, dos
sitios mas con "el mismo patron de inverso manual":
`governance/receipts.py:473-480` y `runtime/agent.py:57-64`.

Medidos, los dos son FALSOS como se enunciaron:

- `runtime/agent.py:51` `AgentResult.from_fixture` no es un inverso de
  un `to_dict`. Es un cargador de fixtures con `isinstance` explicito y
  errores TIPADOS (`ValidationError`, `OutcomeInvalidError`).
- `governance/receipts.py:466` tiene un par asimetrico real —el
  escritor usa el `to_payload()` publico y el lector es
  `_payload_to_receipt`, privado y escrito a mano— pero las claves
  CUADRAN hoy: 11 del dataclass, 11 de `to_payload`, 11 del lector. Y el
  caller captura `(KeyError, ValueError, TypeError)` y hace `continue`,
  que es justo lo que promete el docstring.

Lo que queda no es un defecto sino un RIESGO LATENTE, y es lo que este
fichero cierra: nada verifica que las tres listas sigan siendo la misma.
Si anadir un campo al dataclass, el escritor lo emite y el lector lo
ignora en silencio; si quitarlo, el lector levanta `KeyError` y el caller
descarta la fila sin dejar rastro: un receipt que deberia aplicarse no
aplica y no se ve.

Los dos guards de aqui (este y el del bloque vivo de CURRENT.md) no son
correcciones de un fallo: son la red que hace que la afirmacion "las
tres listas cuadran" siga siendo cierta. Se prueban con mutacion.
"""

from __future__ import annotations

import ast
import dataclasses
import re
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from skillgraph.governance.receipts import ValidationReceipt

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
RECEIPTS_PY: Final = REPO_ROOT / "src/skillgraph/governance/receipts.py"
AGENT_PY: Final = REPO_ROOT / "src/skillgraph/runtime/agent.py"
CURRENT_MD: Final = REPO_ROOT / "CURRENT.md"

# Una cita es `fichero.py:LINEA::simbolo`. El simbolo es OBLIGATORIO y el
# grupo es opcional en la regex solo para poder decir «no lo dice» con un
# mensaje util, en vez de dejar de encontrar la cita en silencio.
CITA: Final = r"([A-Za-z0-9_/]+\.py):(\d+)(?:::([A-Za-z_][A-Za-z0-9_]*))?"


def _indice() -> dict[str, list[Path]]:
    indice: dict[str, list[Path]] = defaultdict(list)
    # `scripts` entra en WI-93: es el primer bloque vivo que cita un modulo de
    # ahi (`check_coverage_floors.py`, el checker de suelos de AGENTS 6.3). Un
    # resolver que no conoce el directorio donde vive el codigo que el propio
    # bloque declara daria por rota una cita verdadera, que es peor que no
    # resolver: obliga a borrarla en vez de a corregirla.
    for base in ("src", "tests", "scripts"):
        for p in (REPO_ROOT / base).rglob("*.py"):
            indice[p.name].append(p)
    return indice


def _constante(val: ast.AST) -> str | None:
    if isinstance(val, ast.Constant) and isinstance(val.value, str):
        return val.value
    return None


def _es_lectura_de_payload(nodo: ast.AST) -> str | None:
    """Clave leida de `payload` por subscript o por `.get()`.

    Cubre las dos formas y SOLO las dos:
      - `payload["k"]`           subscript cuyo base es Name `payload`
      - `payload.get("k", ...)`  llamada cuyo func es `payload.get`

    `payload[f"k{i}"]` no cuenta: no es una clave fija.
    """
    if isinstance(nodo, ast.Subscript) and isinstance(nodo.value, ast.Name):
        return _constante(nodo.slice) if nodo.value.id == "payload" else None
    if (
        isinstance(nodo, ast.Call)
        and isinstance(nodo.func, ast.Attribute)
        and nodo.func.attr == "get"
        and isinstance(nodo.func.value, ast.Name)
        and nodo.func.value.id == "payload"
        and nodo.args
    ):
        return _constante(nodo.args[0])
    return None


def _funcion(nombre: str) -> ast.FunctionDef:
    arbol = ast.parse(RECEIPTS_PY.read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.FunctionDef) and nodo.name == nombre:
            return nodo
    raise AssertionError(f"{nombre} no encontrado en {RECEIPTS_PY.name}")


def _claves_to_payload() -> frozenset[str]:
    """Claves que emite `ValidationReceipt.to_payload`, leidas del AST.

    Se lee el AST y no se llama al metodo: el reader de este fichero
    tiene que seguir funcionando aunque el metodo este roto, que es
    justo el fallo que vigila.
    """
    for sub in ast.walk(_funcion("to_payload")):
        if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Dict):
            claves = [k.value for k in sub.value.keys if isinstance(k, ast.Constant)]
            return frozenset(claves)
    raise AssertionError("to_payload no devuelve un dict literal")


def _claves_lector() -> frozenset[str]:
    """Claves que lee `_payload_to_receipt`, leidas del AST.

    `tests_run` y `tests_passed` NO se leen con un subscript: pasan por
    `_declared_counter(payload, "k")`. Esas tambien se extraen del AST,
    mirando el segundo argumento de la llamada. NO se declaran a mano:
    declararlas seria punchar un agujero justo en el sitio que este
    guard existe para vigilar.
    """
    nodo = _funcion("_payload_to_receipt")
    leidas = {k for k in map(_es_lectura_de_payload, ast.walk(nodo)) if k}
    for sub in ast.walk(nodo):
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Name)
            and sub.func.id == "_declared_counter"
            and len(sub.args) == 2
        ):
            clave = _constante(sub.args[1])
            if clave:
                leidas.add(clave)
    return frozenset(leidas)


class TestElRoundTripDeValidationReceiptCuadraHoy:
    """La afirmacion que este guard mantiene cierta."""

    def test_escritor_lector_y_dataclass_dicen_lo_mismo(self) -> None:
        campos = frozenset(f.name for f in dataclasses.fields(ValidationReceipt))
        assert _claves_to_payload() == campos, (
            "to_payload y los campos del dataclass han divergido: el "
            "escritor emite una clave que el dataclass no tiene, o al reves."
        )
        assert _claves_lector() == campos, (
            f"el lector lee de mas: {sorted(_claves_lector() - campos)}; "
            f"y no lee: {sorted(campos - _claves_lector())}. Con una clave de "
            f"mas el campo se pierde en silencio. Con una de menos el lector "
            f"levanta KeyError y el caller descarta la fila sin rastro: un "
            f"receipt que deberia aplicarse no aplica y nadie se entera."
        )

    def test_el_lector_cubre_las_obligatorias(self) -> None:
        """Ninguna clave obligatoria puede desaparecer en silencio.

        `_declared_counter` cubre `tests_run`/`tests_passed` (WI-49). El
        resto son subscripts crudos, que es lo correcto: una clave
        ausente DEBE fallar. Lo que no debe pasar es que el lector se
        quede corto.
        """
        obligatorias = {
            "receipt_id",
            "command",
            "revision",
            "timestamp",
            "verdict",
            "artifact_path",
            "scope",
        }
        assert obligatorias <= _claves_lector(), (
            f"el lector ya no lee {sorted(obligatorias - _claves_lector())}"
        )


def _bloque_vivo() -> str:
    """El primer bloque de CURRENT.md: el puntero operativo de HOY.

    Las citas de bloques anteriores NO se comprueban. Son la foto de un
    codigo que ya no existe, y corregirlas seria falsificar la historia.
    Lo que se comprueba es que la foto de hoy apunte a donde dice.
    """
    texto = CURRENT_MD.read_text(encoding="utf-8")
    cabeceras = [m.start() for m in re.finditer(r"^> \*\*Bloque ", texto, re.M)]
    assert len(cabeceras) >= 2, (
        "CURRENT.md solo tiene un bloque; el guard asume que el primero es "
        "el vivo y el segundo empieza el historico"
    )
    return texto[: cabeceras[1]]


def _citas_vivo() -> list[tuple[str, int, str | None]]:
    # `re.findall` devuelve '' —no None— cuando el grupo opcional no
    # participa. Sin normalizar, una cita sin ancla llegaria aqui como
    # cadena vacia y el check de `simbolo is None` no la veria nunca.
    return [
        (nombre, int(linea), simbolo or None)
        for nombre, linea, simbolo in re.findall(CITA, _bloque_vivo())
    ]


def _deficiones(ruta: Path) -> dict[str, tuple[tuple[int, int], ...]]:
    """Simbolo -> span(s) que lo definen, leidos del AST.

    Se lee el AST y no se ejecuta el modulo: este fichero tiene que
    seguir funcionando aunque el fichero que cita este roto, que es
    justo el fallo que vigila.

    Un simbolo con MAS DE UN span se queda con todos. La ambiguedad es
    informacion: si se descartara en silencio, una cita a un nombre
    repetido diria «no existe» y señalaria al sitio equivocado.
    """
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    candidatas: dict[str, list[tuple[int, int]]] = defaultdict(list)

    def registrar(nombre: str, nodo: ast.AST) -> None:
        inicio = int(getattr(nodo, "lineno", 0))
        candidatas[nombre].append((inicio, int(getattr(nodo, "end_lineno", inicio))))

    for nodo in arbol.body:
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            registrar(nodo.name, nodo)
            for sub in getattr(nodo, "body", []):
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    registrar(f"{nodo.name}.{sub.name}", sub)
                    registrar(sub.name, sub)
        elif isinstance(nodo, ast.AnnAssign) and isinstance(nodo.target, ast.Name):
            registrar(nodo.target.id, nodo)
        elif isinstance(nodo, ast.Assign):
            for tgt in nodo.targets:
                if isinstance(tgt, ast.Name):
                    registrar(tgt.id, nodo)

    return {nombre: tuple(tramos) for nombre, tramos in candidatas.items()}


def _modulo_unico(indice: dict[str, list[Path]], nombre: str) -> tuple[Path | None, str]:
    """Resuelve el nombre de una cita a UN fichero, o explica por que no."""
    candidatas = indice.get(Path(nombre).name, [])
    if not candidatas:
        return None, f"{nombre} — no existe ese modulo"
    if len(candidatas) > 1:
        return None, f"{nombre} — ambiguo: " + ", ".join(
            str(c.relative_to(REPO_ROOT)) for c in candidatas
        )
    return candidatas[0], ""


def _problemas_de_la_cita(
    indice: dict[str, list[Path]], nombre: str, linea: int, simbolo: str | None
) -> tuple[str, ...]:
    """Los porques de que esta cita no diga la verdad. Vacio = correcta.

    La cita tiene que decir QUE apunta, no solo DONDE. Sin el simbolo
    no hay nada que verificar: `fichero.py:352` es cierto y no dice
    nada, y por eso WI-92 lo acepto dos veces.
    """
    donde, error = _modulo_unico(indice, nombre)
    if donde is None:
        return (f"{nombre}:{linea} — {error}",)
    if simbolo is None:
        return (f"{nombre}:{linea} — la cita no dice a que simbolo apunta",)

    total = len(donde.read_text(encoding="utf-8").splitlines())
    if linea > total:
        return (f"{nombre}:{linea} — el fichero tiene {total} lineas",)

    tramos = _deficiones(donde).get(simbolo)
    if not tramos:
        return (f"{nombre}:{linea} — {simbolo} no lo define {donde.name}",)
    if len(tramos) > 1:
        return (
            f"{nombre}:{linea} — {simbolo} es ambiguo en {donde.name}; cita el nombre completo",
        )
    inicio, fin = tramos[0]
    if inicio <= linea <= fin:
        return ()
    return (f"{nombre}:{linea} — {simbolo} esta en la linea {inicio}, no en la {linea}",)


def _problemas_del_bloque(citas: Sequence[tuple[str, int, str | None]]) -> tuple[str, ...]:
    """Verifica una lista de citas cualquiera, no solo las del bloque vivo.

    Existe para que la regla del ancla se pueda comprobar sobre una cita
    SIN ancla. Si el guard solo acepta citas ya parseadas, la regla «el
    ancla es obligatoria» queda fuera de alcance de cualquier prueba: el
    parser nunca produce una cita sin ancla, asi que el mutacion que la
    relaja —M3— pasaria verde sin que nadie lo note.
    """
    indice = _indice()
    return tuple(
        problema
        for nombre, linea, simbolo in citas
        for problema in _problemas_de_la_cita(indice, nombre, linea, simbolo)
    )


class TestLaCitaDeclaraQueSimboloApunta:
    """El contraejemplo del arreglo: citas que TIENEN linea y no dicen nada.

    Sin esto, un verificador que devolviera siempre `()` pasaria todo
    verde. Se comprueba sobre citas REALES de este repo, no sobre
    informes sinteticos: la pregunta es si el vercriptor distingue la
    cita verdadera de la que solo tiene un numero.
    """

    def test_la_cita_verdadera_no_produce_problemas(self) -> None:
        assert (
            _problemas_de_la_cita(_indice(), "tests/_gate_main_hotspot.py", 73, "hotspots_publicos")
            == ()
        )

    def test_linea_real_con_simbolo_equivocado_falla(self) -> None:
        """`:73` existe y es una linea real. No es la de `_cargar_auditor`.

        Es la forma exacta del fallo de WI-102: un numero que existe
        apuntando a otra cosa. El simbolo TIENE que existir —si no, la
        prueba pasaria por la rama de «no lo define» y no mediria nada,
        que es como se colaba la primera version— y por eso se usa
        `_cargar_auditor`, que existe de verdad entre 53 y 70.
        """
        problemas = _problemas_de_la_cita(
            _indice(), "tests/_gate_main_hotspot.py", 73, "_cargar_auditor"
        )
        assert problemas, (
            "una cita que apunta a la linea de otro simbolo se ha dado por "
            "buena: el guard sigue comprobando resolubilidad, no verdad"
        )
        assert any("53" in p for p in problemas), (
            "falla, pero no dice que linea es la buena: "
            f"{problemas}. Sin eso la prueba no distingue esta rama de la "
            "de «el simbolo no existe»."
        )

    def test_simbolo_que_no_existe_falla(self) -> None:
        problemas = _problemas_de_la_cita(
            _indice(), "tests/_gate_main_hotspot.py", 73, "no_existe_este_simbolo"
        )
        assert problemas, "el verificador acepta un simbolo que nadie define"

    def test_simbolo_existe_pero_en_otro_fichero_falla(self) -> None:
        """`checkers_de` existe en el repo, en otro fichero.

        El fallo es resolver por basename. Se comprueba que el error diga
        QUE fichero es el que deberia definirlo: si el verificador
        buscara en cualquier parte del repo, daria otro error —el de
        desalineacion— y por eso esta prueba lo distingue.
        """
        problemas = _problemas_de_la_cita(
            _indice(), "tests/_gate_main_hotspot.py", 73, "checkers_de"
        )
        assert problemas, (
            "el simbolo existe en el repo pero no en el fichero que la cita "
            "nombra: es el fallo de resolver por basename"
        )
        assert any("no lo define _gate_main_hotspot.py" in p for p in problemas), (
            f"el error no senala el fichero que deberia definirlo: {problemas}"
        )

    def test_linea_de_prosa_dentro_de_un_docstring_falla(self) -> None:
        """Las dos citas que WI-102 escribio mal, con su linea real.

        `:352` y `:479` de `check_ci_recipe_parity.py` caen en prosa de
        docstring. Existen. El guard las dio por buenas. Este es el
        contraejemplo historico, reproducido.
        """
        indice = _indice()
        for linea in (352, 479):
            assert _problemas_de_la_cita(
                indice, "scripts/check_ci_recipe_parity.py", linea, "checkers_de"
            ), f"la cita falsa a :{linea} se ha dado por buena"

    def test_una_cita_sin_ancla_no_pasa_la_verificacion(self) -> None:
        """La regla se comprueba sobre el VERIFICADOR, no sobre el parser.

        Mirar `_citas_vivo()` y contar las que no traen simbolo no
        comprueba nada del verificador: el parser nunca fabrica una cita
        sin ancla, de modo que relajar la regla dentro del verificador
        —la mutacion M3, la mas probable porque no rompe nada visible—
        pasaria verde. Aqui se le pasa la cita sin ancla directamente.
        """
        problemas = _problemas_del_bloque([("tests/_gate_main_hotspot.py", 73, None)])
        assert problemas, (
            "una cita sin simbolo pasa la verificacion: el ancla se ha "
            "vuelto opcional y el guard vuelve a ser el de WI-92"
        )

    def test_el_error_dice_donde_esta_el_simbolo(self) -> None:
        """Un verificador que dice «falso» sin decir dónde es un callejón.

        Cuando la linea se queda vieja —que es lo que pasa en cuanto
        alguien inserta una linea arriba— el mensaje tiene que senalar la
        linea buena, o el que lo arregla tiene que buscar a mano.
        """
        problemas = _problemas_de_la_cita(
            _indice(), "tests/_gate_main_hotspot.py", 70, "hotspots_publicos"
        )
        assert problemas
        assert any("73" in p for p in problemas), (
            f"el mensaje no dice donde esta el simbolo: {problemas}"
        )


class TestBlockCitationsDelCurrentVivoResuelven:
    def test_toda_cita_del_bloque_vivo_apunta_a_lo_que_dice(self) -> None:
        """La cita no solo tiene que existir: tiene que SEÑALAR.

        Antes (WI-92 … WI-103) bastaba con que `linea <= total`, asi que
        `check_ci_recipe_parity.py:352` —una linea de prosa dentro de
        un docstring— pasaba por buena. Ver `.pipelinek/wi104_measure.py`
        para la medicion con los cinco casos.
        """
        rotas = _problemas_del_bloque(_citas_vivo())
        assert not rotas, (
            "el bloque vivo de CURRENT.md cita codigo que no esta donde dice:\n  "
            + "\n  ".join(rotas)
        )

    def test_el_bloque_vivo_tiene_al_una_cita_que_verificar(self) -> None:
        """Un guard sobre cero citas no vigila nada."""
        assert _citas_vivo(), "el bloque vivo de CURRENT.md no cita ninguna linea"


class TestLaHipotesisRegistradaEraFalsa:
    """Lo que WI-92 midio, para que no se vuelva a dar por buena.

    Estas aserciones no describen un defecto: describen su AUSENCIA. Si
    alguien reintroduce un `from_dict` duplicado, o convierte el cargador
    de fixtures en un inverso a mano, el codigo cambia y estas aserciones
    avisan.
    """

    def test_agent_result_from_fixture_valida_el_dict_antes_de_usarlo(self) -> None:
        """La PRIMERA instruccion tiene que validar la forma del payload.

        No basta con que el cuerpo contenga `isinstance`: la primera
        version de esta asercion hacia justo eso, y la mutacion M4 la
        esquivó — el fichero tiene CUATRO comprobaciones `isinstance` en
        `from_fixture`, asi que borrar una deja tres y la palabra sigue
        ahi. Un assert sobre una subcadena comprueba que la palabra
        exista, no la propiedad.
        """
        arbol = ast.parse(AGENT_PY.read_text(encoding="utf-8"))
        fn = next(
            n
            for n in ast.walk(arbol)
            if isinstance(n, ast.FunctionDef) and n.name == "from_fixture"
        )
        primero = fn.body[0]
        assert isinstance(primero, ast.If), (
            "la primera instruccion de from_fixture ya no es una guarda: "
            f"es {type(primero).__name__}. El payload se usaria sin validar."
        )
        valida_dict = any(
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Name)
            and sub.func.id == "isinstance"
            and len(sub.args) == 2
            and isinstance(sub.args[0], ast.Name)
            and sub.args[0].id == "payload"
            and isinstance(sub.args[1], ast.Name)
            and sub.args[1].id == "dict"
            for sub in ast.walk(primero)
        )
        assert valida_dict, (
            "la primera guarda de from_fixture ya no comprueba que el "
            "payload sea un dict. Ha pasado de cargador tipado a inverso "
            "escrito a mano, que es la hipotesis que WI-90 registro y "
            "WI-92 retracto."
        )

    def test_receipts_conserva_el_par_que_se_medio(self) -> None:
        """WI-90 era `to_dict` publico sin `from_dict`.

        Aqui el escritor es `to_payload` (publico) y el lector es
        `_payload_to_receipt` (privado, a mano). No es el mismo defecto:
        el lector es privado y el caller lo protege. El guard lo vigila
        para que nadie replique el patron sin darse cuenta.
        """
        metodos = {
            n.name
            for n in ast.walk(ast.parse(RECEIPTS_PY.read_text(encoding="utf-8")))
            if isinstance(n, ast.FunctionDef)
        }
        assert "to_payload" in metodos
        assert "_payload_to_receipt" in metodos
