"""WI-114: un `event_id` repetido tiene que salir como `IdempotencyError`
por CUALQUIER camino de escritura, no solo por los cinco que hoy lo
hacen.

AGENTS.md §8 declara «Idempotencia por constraint, no por código» y
§1.2 que el dominio lanza siempre un error tipado de `SkillGraphError`.
MEDIDO antes de tocar nada:

    6 sitios escriben eventos. 5 traducen. 1 no.

    y el helper del que dependen cuatro de los cinco tiene un docstring
    que dice «Re-raise como `IdempotencyError` cuando el UNIQUE se
    viola» y su cuerpo hace `except BaseException: raise`.

El hueco no es que hoy falle: es que hoy funciona porque cinco personas
distintas se acordado. El fallo, si uno no se acuerda, es
`sqlite3.IntegrityError` atravesando `except SkillGraphError` y
saliendo como Traceback al usuario — el defecto que WI-109 cerró para
el `json.loads` de la CLI.

**POR QUE ESTOS TESTS EJECUTAN Y NO LEEN.** Un guard por AST sobre
`_insert_event_in_tx` vería que el cuerpo es un `cur.execute(INSERT…)`
y concluiría que el UNIQUE se encarga. Lo que se mide es qué clase
sale de verdad cuando el INSERT choca, que es la única forma de saber
si la frontera del dominio se sostiene.

**EL CONJUNTO SE DERIVA DEL ARBOL.** Ni la lista de caminos de
escritura ni la de funciones que deben traducir están escritas aquí.
Las dos se sacan del AST, que es lo que evita que un camino nuevo
entre en silencio: sería la misma trampa que DIRECTORIOS_NO_RECETA
(WI-99) y que el «conectar != contener» de WI-102.
"""

from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import pytest

from skillgraph.core.errors import IdempotencyError, SkillGraphError
from skillgraph.platform.storage import Storage
from skillgraph.runtime.engine import RuntimeEvent

RAIZ = Path(__file__).resolve().parent.parent
SRC = RAIZ / "src" / "skillgraph"

# Los helpers que acaban escribiendo en `runtime_events`. El NOMBRE de los
# helpers si se declara: lo que no se declara es la lista de sitios.
HELPERS = frozenset({"_insert_event_in_tx", "_atomic_state_and_event"})


def modulos() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def funciones_con_escritura() -> list[tuple[Path, ast.FunctionDef]]:
    """Cada funcion del nucleo que acaba escribiendo un evento."""
    salida = []
    for path in modulos():
        texto = path.read_text(encoding="utf-8")
        try:
            arbol = ast.parse(texto)
        except SyntaxError:  # pragma: no cover
            continue
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for llamada in ast.walk(nodo):
                if (
                    isinstance(llamada, ast.Call)
                    and isinstance(llamada.func, ast.Attribute)
                    and llamada.func.attr in HELPERS
                ):
                    salida.append((path, nodo))
                    break
    return salida


def captura_el_error_del_adapter(nodo: ast.AST) -> list[ast.ExceptHandler]:
    """`except sqlite3.IntegrityError` dentro de esta funcion."""
    salida = []
    for hijo in ast.walk(nodo):
        if not isinstance(hijo, ast.Try):
            continue
        for mano in hijo.handlers:
            exc = mano.type
            if (
                isinstance(exc, ast.Attribute)
                and exc.attr == "IntegrityError"
                and isinstance(exc.value, ast.Name)
                and exc.value.id == "sqlite3"
            ):
                salida.append(mano)
    return salida


def evento(eid: str) -> RuntimeEvent:
    return RuntimeEvent(
        event_id=eid,
        tenant_id="t-wi114",
        project_id="p-wi114",
        event_kind="RunCreated",
        run_id=None,
        resource_ref="run/1",
        causation_id=None,
        correlation_id=None,
        payload={"n": 1},
    )


def storage_limpia() -> Storage:
    return Storage(":memory:")


class TestLaFronteraDeDominio:
    """La propiedad: lo que sale del helper es del dominio."""

    def test_un_event_id_repetido_sale_como_idempotency_error(self) -> None:
        """El contrato, ejecutado: insertar dos veces el mismo evento.

        Este es el test ROJO que justifica el bloque. Antes de WI-114
        salia `sqlite3.IntegrityError`, que no es `SkillGraphError` y no
        entra por el `except` que traduce a exit code.
        """
        st = storage_limpia()
        ev = evento("evt-frontera")
        st._insert_event_in_tx(st._conn.cursor(), ev)
        with pytest.raises(IdempotencyError):
            st._insert_event_in_tx(st._conn.cursor(), ev)

    def test_el_error_traspasado_pertenece_al_dominio(self) -> None:
        """No basta con el nombre: tiene que estar en la jerarquia.

        Un `IdempotencyError` que no colgase de `SkillGraphError` se
        escapa del `except` de la CLI igual que un `sqlite3.IntegrityError`,
        y el nombre correcto daria la sensacion de un contrato que existe.
        """
        st = storage_limpia()
        ev = evento("evt-jerarquia")
        st._insert_event_in_tx(st._conn.cursor(), ev)
        with pytest.raises(SkillGraphError) as info:
            st._insert_event_in_tx(st._conn.cursor(), ev)
        assert isinstance(info.value, IdempotencyError)
        assert info.value.code == "sg_idempotency"

    def test_no_lo_atiende_el_adapter_sino_el_dominio(self) -> None:
        """El error que sale no puede ser un builtin de sqlite3.

        Esta es la asercion que un guard por lectura no puede hacer: por
        AST se ve el `cur.execute` y nada mas. Lo que dice el tipo de la
        excepcion es lo unico que separa «traducido» de «atraviesado».
        """
        st = storage_limpia()
        ev = evento("evt-adapter")
        st._insert_event_in_tx(st._conn.cursor(), ev)
        with pytest.raises(IdempotencyError) as info:
            st._insert_event_in_tx(st._conn.cursor(), ev)
        assert not isinstance(info.value, sqlite3.IntegrityError), (
            "sale la excepcion cruda del adapter: el dominio no la ha "
            "traducido y la CLI la va a dejar pasar como Traceback"
        )

    def test_el_mensaje_dice_que_evento_se_duplico(self) -> None:
        """El error tiene que senalar el `event_id` implicito.

        Un verificador que dice «falso» sin decir «donde» deja al que
        corrige en un callejon sin salida: es la leccion de WI-104
        aplicada a los mensajes de error.
        """
        st = storage_limpia()
        ev = evento("evt-mensaje")
        st._insert_event_in_tx(st._conn.cursor(), ev)
        with pytest.raises(IdempotencyError) as info:
            st._insert_event_in_tx(st._conn.cursor(), ev)
        assert "evt-mensaje" in str(info.value)


class TestElConjuntoVieneDelArbol:
    """El guard no mantiene una lista de sitios: la deriva."""

    def test_se_encuentra_al_menos_un_camino_que_escriba_eventos(self) -> None:
        """Contrasalto: si esto no encuentra nada, todo lo de abajo pasa
        por vacuidad y el guard no mide nada.

        Es el M2 de WI-110 aplicado aqui: una medicion que devuelve
        siempre la lista vacia es indistinguible de una que no mide, y
        un guard que solo sabe pasar no esta probado.
        """
        sitios = funciones_con_escritura()
        assert len(sitios) >= 6, (
            f"se esperaban al menos 6 funciones con escritura de eventos y "
            f"se han encontrado {len(sitios)}: "
            f"{[(p.name, n.name) for p, n in sitios]}. Si el refactor movio "
            f"la escritura, el conjunto derivado cambio y hay que releerlo."
        )

    def test_ningun_camino_atrapa_el_error_del_adapter(self) -> None:
        """Tras WI-114 la traduccion la hace el helper.

        Un `except sqlite3.IntegrityError` en un camino de escritura ya
        no se dispara nunca: es codigo muerto, y codigo muerto que parece
        vivo es peor que codigo muerto, porque el lector deduce de ahi que
        la traduccion depende de el.
        """
        culpables = []
        for path, nodo in funciones_con_escritura():
            for mano in captura_el_error_del_adapter(nodo):
                linea = getattr(mano, "lineno", 0)
                culpables.append(f"{path.name}::{nodo.name}:{linea}")
        assert not culpables, (
            "estos caminos de escritura siguen atrapa"
            f"{'n' if len(culpables) > 1 else ''} sqlite3.IntegrityError, "
            "pero la traduccion la hace el helper y ese except ya no se "
            f"dispara: {culpables}"
        )

    def test_el_helper_que_traduce_se_usa_de_verdad(self) -> None:
        """La traduccion no puede quedarse en un helper muerto.

        Si `_insert_event_in_tx` dejara de usarse, el guard de arriba
        pasaria —no habria ningun camino que atrape el error del adapter
        porque no habria caminos— y la propiedad se perderia en silencio.
        """
        usos = 0
        for _path, nodo in funciones_con_escritura():
            usos += sum(
                1
                for llamada in ast.walk(nodo)
                if isinstance(llamada, ast.Call)
                and isinstance(llamada.func, ast.Attribute)
                and llamada.func.attr in HELPERS
            )
        assert usos >= 6, (
            f"solo {usos} llamadas a los helpers de escritura: la "
            "derivacion del conjunto esta medindo algo que ya no se usa"
        )
