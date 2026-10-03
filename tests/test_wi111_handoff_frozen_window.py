"""WI-111: la ventana entre el hash persistido y el hash recalculado.

`AGENTS.md` linea 9 y `handoff.py:9` declaran que el Handoff "Es
INMUTABLE (dataclass frozen, slots=True)". `AGENTS.md` linea 428 dice que
el Adapter "recibe el hash firmado; nunca lo recalcula".

Ninguna de las dos afirmaciones se sostiene. `frozen=True` congela el
ENLACE del atributo, no su VALOR, y `HandoffExecution.budget` esta
anotado `dict[str, int]`. Un dict dentro de un frozen se muta sin que
nada se queje.

La segunda parte es la grave, y estos tests la miden sobre disco, no
sobre el codigo: un guard que solo leyera el texto del repositorio
mediria la regla, no el defecto.

El motor, en `node_execution_delegations.py`:

    linea 219  context_hash = handoff.context_hash     # PRE, se persiste
    linea 241  update_node_execution_handoff(...)     #    fila + handoff_json
    linea 127  self._adapter.invoke(handoff)          # el Adapter recibe
                                                      #    el objeto VIVO
    linea 144  context_hash=handoff.context_hash      # POST, se recalcula

Medido antes de arreglar nada (`.pipelinek/wi111_measure.py`):

    fila node_executions.context_hash : 0063e7dfd167afc6...
    evento NodeCompleted               : 951a2d3a16cf7ea8...
    evento EvidenceProduced            : 951a2d3a16cf7ea8...
    hash que el Adapter vio AL ENTRAR  : 0063e7dfd167afc6...
    budget en handoff_json persistido  : {'max_nodes': 1}

La fila describe el handoff de ANTES y los eventos el de DESPUES. Los dos
describen la misma node_execution.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from skillgraph.core.errors import ValidationError
from skillgraph.core.recipe import ContextRecipe
from skillgraph.domain.dsl import PlanBuilder, node_name
from skillgraph.platform.storage import Storage
from skillgraph.runtime.agent import AgentResult
from skillgraph.runtime.handoff import (
    Handoff,
    HandoffBehavior,
    HandoffExecution,
    HandoffIdentity,
    HandoffKnowledge,
)
from skillgraph.runtime.runcontroller import RunController

TENANT = "t-wi111"
PROJECT = "p-wi111"

# El repo redacta el payload de algunos eventos a proposito
# (`runtime/redaction.py`). No es el defecto que se busca aqui, asi que
# estos tests comparan solo lo que NO pasa por la redaccion.
REDACTED = "[REDACTED]"


def _handoff(budget: dict[str, int] | None = None) -> Handoff:
    return Handoff(
        identity=HandoffIdentity(TENANT, PROJECT, "r1", "ne1", 1),
        behavior=HandoffBehavior("ActionNode", "b", "ns", 1, "v1"),
        knowledge=HandoffKnowledge("recipe://x"),
        execution=HandoffExecution(
            "ws://y", "rev1", budget if budget is not None else {"tokens": 100}
        ),
        expected_result="text",
    )


class _AdapterQueMuta:
    """Adapter que cumple el Protocol y ESCRIBE en el handoff que recibe.

    No es un adapter malicioso. Es uno honesto que hace lo correcto desde
    su punto de vista —anotar lo que necesita— y el repo no le impide
    seguir escribiendo en la estructura que le dice que es inmutable.
    """

    def __init__(self) -> None:
        self.hash_al_entrar: str | None = None

    def invoke(self, handoff: Handoff) -> AgentResult:
        self.hash_al_entrar = handoff.context_hash
        handoff.execution.budget["presupuesto_inyectado"] = 10**9
        return AgentResult(outcome="text", result={"texto": "ok"}, evidence_ref="ev-1")


class _AdapterHonesto:
    """Adapter que NO muta. Debe seguir funcionando tras el arreglo."""

    def __init__(self) -> None:
        self.hash_al_entrar: str | None = None

    def invoke(self, handoff: Handoff) -> AgentResult:
        self.hash_al_entrar = handoff.context_hash
        return AgentResult(outcome="text", result={"texto": "ok"}, evidence_ref="ev-1")


def _plan() -> Any:
    return (
        PlanBuilder().add_node(node_name("n1"), expected="text").starts_at(node_name("n1")).build()
    )


def _resolver(*_a: Any, **_k: Any) -> ContextRecipe:
    return ContextRecipe(recipe_ref="recipe-test/v1")


def _correr(adapter: Any) -> tuple[Storage, str, str]:
    """Ejecuta UN nodo con el adapter dado. Devuelve (storage, run_id, fila_hash)."""
    tmp = tempfile.TemporaryDirectory()
    storage = Storage(Path(tmp.name) / "wi111.sqlite")
    ctl = RunController(
        runs=storage,
        events=storage,
        policy=storage,
        adapter=adapter,
        recipe_resolver=_resolver,
        knowledge=storage,
    )
    run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=_plan())
    ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
    fila = storage._conn.execute(
        "SELECT context_hash FROM node_executions WHERE run_id = ?", (run_id,)
    ).fetchone()
    return storage, run_id, (fila[0] if fila else "")


def _hashes_de_eventos(storage: Storage, run_id: str) -> list[tuple[str, str]]:
    """Los (evento, context_hash) que NO pasaron por redaccion."""
    salida: list[tuple[str, str]] = []
    filas = storage._conn.execute(
        "SELECT event_kind, payload_json FROM runtime_events WHERE run_id = ? ORDER BY sequence",
        (run_id,),
    ).fetchall()
    for kind, payload in filas:
        datos = json.loads(payload)
        if not isinstance(datos, dict):
            continue
        ch = datos.get("context_hash")
        if isinstance(ch, str) and ch != REDACTED:
            salida.append((kind, ch))
    return salida


class TestElBudgetNoEsUnDictMutable:
    """C1: la estructura que el repo declara inmutable no se puede escribir."""

    def test_escribir_en_el_budget_lanza_excepcion(self) -> None:
        h = _handoff()
        with pytest.raises(TypeError):
            h.execution.budget["tokens"] = 999  # type: ignore[index]

    def test_el_budget_no_expone_un_dict(self) -> None:
        h = _handoff()
        assert not isinstance(h.execution.budget, dict)

    def test_el_budget_se_puede_leer(self) -> None:
        h = _handoff({"tokens": 100})
        assert h.execution.budget["tokens"] == 100

    def test_el_valor_recibido_no_se_aliasa_al_llamante(self) -> None:
        """Si el llamante conserva el dict, mutarlo no puede alterar el handoff."""
        externo = {"tokens": 100}
        h = _handoff(externo)
        externo["tokens"] = 999
        assert h.execution.budget["tokens"] == 100

    def test_un_budget_que_no_es_mapping_es_rechazado(self) -> None:
        """Sin esta comprobacion, un string pasa como budget y el handoff
        queda corrupto: `context_hash` serializa un string donde deberia
        haber un mapping, y el fallo aparece lejos de su causa.

        M3 en las mutaciones desactivaba el `isinstance` y el resto del
        guard seguia verde: ninguna otra prueba miraba este contrato.
        """
        for malo in ("no-es-mapping", 42, ["tokens", 100]):
            with pytest.raises(ValidationError) as exc:
                HandoffExecution("ws://y", "rev1", malo)  # type: ignore[arg-type]
            assert "budget" in str(exc.value)

    def test_frozen_sigue_bloqueando_el_atributo(self) -> None:
        """El bloqueo del ENLACE no se pierde por arreglar el del VALOR."""
        h = _handoff()
        with pytest.raises(FrozenInstanceError):
            h.execution = HandoffExecution("otro", "z", {})  # type: ignore[misc]


class TestElHashNoSeRecalculaDespuesDelInvoke:
    """C2 y C3: la fila y los eventos no pueden describir handoffs distintos.

    Tras el arreglo, un Adapter que intenta escribir en el budget falla con
    `TypeError` y el nodo queda FAILED. Es la forma correcta: la escritura
    ilegal no llega a existir, asi que no hay segunda descripcion que
    contradiga a la primera. Por eso estos tests no exigen que el nodo
    complete; exigen que no exista la divergencia.
    """

    def test_todos_los_hashes_legibles_coinciden_con_la_fila(self) -> None:
        """La propiedad, sin importar como termino el nodo."""
        for adapter in (_AdapterHonesto(), _AdapterQueMuta()):
            storage, run_id, fila_hash = _correr(adapter)
            for kind, ch in _hashes_de_eventos(storage, run_id):
                assert ch == fila_hash, (
                    f"con {type(adapter).__name__}, el evento {kind} lleva "
                    f"{ch[:12]}... y la fila lleva {fila_hash[:12]}..."
                )

    def test_el_hash_persistido_es_el_que_vio_el_adapter(self) -> None:
        adapter = _AdapterQueMuta()
        _storage, _run_id, fila_hash = _correr(adapter)
        assert fila_hash == adapter.hash_al_entrar

    def test_intentar_mutar_falla_y_no_deja_evento_de_exito(self) -> None:
        """La mitad peligrosa: que el fallo no se produzca en silencio.

        Un arreglo que dejara pasar la escritura y luego corrigiera el hash
        despues tambien haria que los hashes coincidieran. Este test
        distingue las dos cosas: exige que la escritura ILEGAL no llegue a
        tener efecto, y que por tanto no exista un NodeCompleted con un hash
        distinto del ya firmado.
        """
        storage, run_id, fila_hash = _correr(_AdapterQueMuta())
        tipos = {
            kind
            for kind, _payload in storage._conn.execute(
                "SELECT event_kind, payload_json FROM runtime_events WHERE run_id = ?",
                (run_id,),
            )
        }
        assert "NodeFailed" in tipos, "el intento de mutacion no fallo el nodo"
        assert "NodeCompleted" not in tipos, (
            "el nodo completo pese a que el Adapter escribio en el handoff: "
            "la escritura ilegal se aplico y el hash se corrigio despues"
        )
        assert fila_hash

    def test_el_hash_no_se_calcula_una_segunda_vez(self) -> None:
        """C3, por via estructural: el hash que viaja es el que se firmo.

        Un handoff con el budget inmutable da el mismo hash siempre, asi
        que M4 (volver a calcularlo despues del invoke) no se ve mirando
        VALORES: hay que mirar CUANTAS VECES lo calcula el MOTOR. Este
        contador es lo que la distingue de un arreglo que solo moviera
        la linea de codigo.

        Se cuenta por ORIGEN: la lectura que hace el propio Adapter no es
        una recalculacion del motor, asi que se excluye. Lo que se exige
        es que el Core lo calcule una vez, al firmarlo.
        """
        original = Handoff.context_hash.fget  # type: ignore[attr-defined]
        desde_adapter = {"dentro": False}
        llamadas_del_motor: list[str] = []

        def contando(self: Handoff) -> str:
            if not desde_adapter["dentro"]:
                llamadas_del_motor.append("motor")
            return original(self)  # type: ignore[misc]

        class _AdapterQueNoMira:
            """Adapter que no lee el hash: asi toda llamada es del motor."""

            def invoke(self, handoff: Handoff) -> AgentResult:
                desde_adapter["dentro"] = True
                try:
                    return AgentResult(outcome="text", result={"t": "ok"}, evidence_ref="ev-1")
                finally:
                    desde_adapter["dentro"] = False

        Handoff.context_hash = property(contando)  # type: ignore[assignment]
        try:
            _storage, _run_id, _fila = _correr(_AdapterQueNoMira())
        finally:
            Handoff.context_hash = property(original)  # type: ignore[assignment]

        assert len(llamadas_del_motor) == 1, (
            f"el motor calculo el hash {len(llamadas_del_motor)} veces; "
            "lo correcto es una: la que lo firma y persiste"
        )

    def test_un_adapter_honesto_no_rompe_nada(self) -> None:
        storage, run_id, fila_hash = _correr(_AdapterHonesto())
        assert fila_hash
        hashes = _hashes_de_eventos(storage, run_id)
        assert hashes, "un adapter honesto debe llegar a emitir NodeCompleted"
        for _kind, ch in hashes:
            assert ch == fila_hash

    def test_el_handoff_json_persistido_no_tiene_la_clave_inyectada(self) -> None:
        """Sonda: la fila describe el handoff tal y como se firmo.

        Sin esta comprobacion, "los hashes coinciden" podria deberse a que
        la fila se hubiera escrito despues. Con ella se ve que la fila
        precede al Adapter, que es lo que la hace ser la firma.
        """
        tmp = tempfile.TemporaryDirectory()
        storage = Storage(Path(tmp.name) / "wi111.sqlite")
        ctl = RunController(
            runs=storage,
            events=storage,
            policy=storage,
            adapter=_AdapterQueMuta(),
            recipe_resolver=_resolver,
            knowledge=storage,
        )
        run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=_plan())
        ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
        fila = storage._conn.execute(
            "SELECT handoff_json FROM node_executions WHERE run_id = ?", (run_id,)
        ).fetchone()
        budget = json.loads(fila[0])["execution"]["budget"]
        assert "presupuesto_inyectado" not in budget


class TestLaPropiedadDeDeduplicacionNoSeRompe:
    """C4: la regla de oro de `handoff.py:16` sigue valiendo."""

    def test_dos_handoffs_iguales_dan_el_mismo_hash(self) -> None:
        a = _handoff({"tokens": 100})
        b = _handoff({"tokens": 100})
        assert a.context_hash == b.context_hash

    def test_el_orden_de_insercion_no_cambia_el_hash(self) -> None:
        a = _handoff({"x": 1, "y": 2})
        b = _handoff({"y": 2, "x": 1})
        assert a.context_hash == b.context_hash

    def test_un_budget_distinto_da_un_hash_distinto(self) -> None:
        a = _handoff({"tokens": 100})
        b = _handoff({"tokens": 200})
        assert a.context_hash != b.context_hash

    def test_el_hash_sigue_siendo_sha256_hex_de_64(self) -> None:
        h = _handoff()
        assert len(h.context_hash) == 64
        assert all(c in "0123456789abcdef" for c in h.context_hash)


class TestElRoundTripSigueSerializando:
    """C5: `to_dict()` no puede dejar de producir un dict plano."""

    def test_to_dict_devuelve_un_dict_plano(self) -> None:
        """El budget de `to_dict` tiene que ser un dict de verdad.

        Comparar con `==` NO sirve: un `MappingProxyType` compara igual que
        un dict, asi que un test que solo mira el valor pasa aunque lo que
        devuelva no sea serializable. Lo que discrimina es el tipo, y
        sobre todo que `json.dumps` lo acepte.
        """
        d = _handoff().to_dict()
        assert isinstance(d, dict)
        assert isinstance(d["execution"]["budget"], dict)
        assert d["execution"]["budget"] == {"tokens": 100}

    def test_el_budget_de_to_dict_es_json_serializable(self) -> None:
        """Sonda de M5: si `to_dict` devolviera el mapping vivo, este
        `json.dumps` lanzaria TypeError. El `==` de arriba no lo veria."""
        json.dumps(_handoff().to_dict())

    def test_el_budget_del_dict_es_copia_y_no_alias(self) -> None:
        """Si `to_dict` devolviera el dict vivo, mutarlo alteraria el handoff.

        Compara contra el MISMO handoff, no contra uno nuevo: comparar dos
        llamadas distintas a `_handoff()` no puede fallar nunca, y asi el
        test pasaba con la mutacion M5 puesta sin ver nada.
        """
        h = _handoff()
        antes = h.to_dict()
        antes["execution"]["budget"]["tokens"] = 999
        despues = h.to_dict()
        assert despues["execution"]["budget"]["tokens"] == 100
