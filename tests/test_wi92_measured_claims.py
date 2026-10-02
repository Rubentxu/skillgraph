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
from pathlib import Path
from typing import Final

from skillgraph.governance.receipts import ValidationReceipt

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
RECEIPTS_PY: Final = REPO_ROOT / "src/skillgraph/governance/receipts.py"
AGENT_PY: Final = REPO_ROOT / "src/skillgraph/runtime/agent.py"
CURRENT_MD: Final = REPO_ROOT / "CURRENT.md"


def _indice() -> dict[str, list[Path]]:
    indice: dict[str, list[Path]] = defaultdict(list)
    for base in ("src", "tests"):
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


def _citas_vivo() -> list[tuple[str, int]]:
    return [
        (nombre, int(linea))
        for nombre, linea in re.findall(r"([A-Za-z0-9_/]+\.py):(\d+)", _bloque_vivo())
    ]


class TestBlockCitationsDelCurrentVivoResuelven:
    def test_toda_cita_del_bloque_vivo_resuelve(self) -> None:
        indice = _indice()
        rotas: list[str] = []
        for nombre, linea in _citas_vivo():
            candidatas = indice.get(Path(nombre).name, [])
            if not candidatas:
                rotas.append(f"{nombre}:{linea} — no existe ese modulo")
                continue
            if len(candidatas) > 1:
                rotas.append(
                    f"{nombre}:{linea} — ambiguo: "
                    + ", ".join(str(c.relative_to(REPO_ROOT)) for c in candidatas)
                )
                continue
            total = len(candidatas[0].read_text(encoding="utf-8").splitlines())
            if linea > total:
                rotas.append(f"{nombre}:{linea} — el fichero tiene {total} lineas")
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
