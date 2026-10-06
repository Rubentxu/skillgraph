"""B24 — el recorrido de la UAT REAL, ejecutable sin credencial y sin dinero.

El modulo `tests/test_uat_real_provider.py` declara ocho fronteras:

    workflow → ContextRecipe → handoff → adapter real → AgentResult
            → transicion → persistencia → recuperacion

**MEDIDO AL ABRIR B24: los tests de ahi tocaban TRES** —handoff, adapter y
`AgentResult`— y las otras cinco no se ejecutaban nunca. Ademas las
instrucciones de ejecucion del modulo apuntaban a
`tests/uat_real_provider.py`, que no existe: quien las siguiera ejecutaba
nada (`rc=4`).

Este fichero cubre las ocho, con el `HttpAgentAdapter` de verdad —su
`httpx.Client`, su retry y su parseo— contra un servidor local que habla la
FORMA de la respuesta del proveedor. Lo unico que se sustituye es el otro
extremo del cable.

**LO QUE ESTO NO CERTIFICA, Y POR QUE SE REPITE AQUI.** Un servidor local no
es Anthropic ni OpenAI. Este recorrido no dice que el proveedor real conteste:
dice que las ocho fronteras del camino funcionan. La certificacion del
proveedor sigue siendo `test_uat_real_provider.py` con `SG_UAT_REAL_PROVIDER=1`
y credencial, y ese camino no se toca.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from skillgraph.domain.dsl import PlanBuilder, node_name
from skillgraph.platform.storage import Storage
from skillgraph.runtime.agent import AgentResult
from skillgraph.runtime.handoff import Handoff
from skillgraph.runtime.http_adapter import HttpAgentAdapter
from skillgraph.runtime.runcontroller import RunController
from tests._proveedor_local import peticiones, proveedor_local

TENANT = "t-b24"
PROJECT = "p-b24"

#: Una credencial con FORMA de clave. No es una clave: no se usa para nada
#: que no sea `127.0.0.1`, y su presencia es lo que permite que el adapter
#: construya —que rechaza las vacias con `ValidationError`.
CLAVE_LOCAL = "sk-ant-no-es-una-credencial-real-0000000000000000"


def _plan() -> Any:
    """Un plan de UN nodo, construido por el DSL como lo construye un usuario."""
    return (
        PlanBuilder()
        .add_node(node_name("n1"), expected="texto", capabilities=())
        .starts_at(node_name("n1"))
        .build()
    )


def _adapter(base_url: str) -> HttpAgentAdapter:
    return HttpAgentAdapter(
        provider="anthropic",
        api_key=CLAVE_LOCAL,
        model="local",
        base_url=base_url,
    )


def _corrida(base_url: str, tmp_path: Path) -> tuple[Storage, str]:
    """El recorrido entero: crear el run y reconciliarlo."""
    storage = Storage(tmp_path / "b24.sqlite")
    ctl = RunController(
        runs=storage,
        events=storage,
        policy=storage,
        adapter=_adapter(base_url),
    )
    run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=_plan())
    ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
    return storage, run_id


def _nodo(storage: Storage, run_id: str) -> tuple[str, str | None, str]:
    """(estado, error, handoff_json) de la unica node_execution del run."""
    filas = storage._conn.execute(
        "SELECT state, error, handoff_json FROM node_executions WHERE run_id = ?", (run_id,)
    ).fetchall()
    assert len(filas) == 1, f"se esperaba 1 node_execution, hay {len(filas)}"
    return filas[0][0], filas[0][1], filas[0][2]


# =====================================================================
class TestElRecorridoCompletoSinDinero:
    """Las ocho fronteras, una clase, en el orden en que ocurren.

    Cada test nombra la frontera que mide y dice que pasaria si la propiedad
    fuera falsa. No se comprueba «que corra»: se comprueba que lo que se
    persists ES lo que devolvio el otro extremo del cable.
    """

    def test_1_workflow_se_crea_desde_el_dsl(self, tmp_path: Path) -> None:
        """FRONTERA 1 — workflow: un plan construido por el DSL crea un run."""
        with proveedor_local() as url:
            storage, run_id = _corrida(url, tmp_path)
        filas = storage._conn.execute(
            "SELECT state FROM workflow_runs WHERE run_id = ?", (run_id,)
        ).fetchall()
        assert filas, f"el run {run_id} no se persistio: create_run no escribio"
        assert filas[0][0] in {"ACTIVE", "COMPLETED", "WAITING"}, filas[0][0]

    def test_2_el_handoff_llega_al_adapter_con_una_llamada_real(self, tmp_path: Path) -> None:
        """FRONTERA 2+3 — el `Handoff` firmado sale por el cable.

        No se mira el resultado: se mira que el servidor RECIBIO una peticion
        con el prompt construido desde el handoff. Sin esto, un adapter que no
        se invoca y otro que se invoca con la basura darian el mismo veredicto
        al resto del recorrido.
        """
        with proveedor_local() as url:
            _corrida(url, tmp_path)
            recibidas = peticiones()
        assert len(recibidas) == 1, (
            f"se esperaba 1 peticion al proveedor y llegaron {len(recibidas)}. "
            f"Un recorrido que no llega al otro extremo no es un recorrido."
        )
        ruta, body = recibidas[0]
        # `base_url` sustituye la URL ENTERA, no solo el host: MEDIDO, la
        # peticion llega a `/` y no a `/v1/messages`, porque
        # `build_request` hace `url = self.config.base_url or _ANTHROPIC_URL`.
        # Por eso aqui no se mira la ruta: la propiedad es que LLEGO una
        # peticion construida por el adapter de verdad, y la ruta es del
        # endpoint que se sustituyo.
        assert ruta, "llego una peticion sin ruta"
        assert body["model"], f"la peticion no lleva modelo: {body!r}"
        mensajes = body["messages"]
        assert mensajes and mensajes[0]["role"] == "user", mensajes
        assert isinstance(mensajes[0]["content"], str) and mensajes[0]["content"].strip(), (
            f"el prompt salio vacio: {mensajes!r}"
        )

    def test_3_el_resultado_vuelve_como_agentresult_del_dominio(self, tmp_path: Path) -> None:
        """FRONTERA 4+5 — lo que sale del otro extremo entra por el dominio."""
        with proveedor_local() as url:
            storage, run_id = _corrida(url, tmp_path)
        estado, error, _ = _nodo(storage, run_id)
        assert estado == "SUCCEEDED", (
            f"el nodo no quedo SUCCEEDED: estado={estado!r}, error={error!r}. "
            f"El recorrido entero fallo en alguna frontera que este test no nombra."
        )
        # Y el resultado que persistio es el que devolvio el servidor.
        filas = storage._conn.execute(
            "SELECT result_json FROM node_executions WHERE run_id = ?", (run_id,)
        ).fetchall()
        persistido = json.loads(filas[0][0])
        # Lo que se persiste es la FORMA del AgentResult, con `outcome` y
        # `result` anidados. MEDIDO:
        #   {"evidence_ref": null, "outcome": "ok", "result": {"local": true}}
        # Y el `result` interior es LITERALMENTE lo que devolvio el otro
        # extremo del cable.
        assert persistido.get("outcome") == "ok", (
            f"el outcome persistido no es el que devolvio el proveedor: {persistido!r}"
        )
        assert persistido.get("result", {}).get("local") is True, (
            f"lo persistido no es lo que devolvio el proveedor: {persistido!r}. "
            f"Un recorrido que sustituye el resultado por otro sigue dando SUCCEEDED."
        )

    def test_4_el_contexto_del_handoff_llega_como_contextrecipe(self, tmp_path: Path) -> None:
        """FRONTERA 2 (otra mitad) — el handoff lleva el contexto del run.

        Se lee el `handoff_json` PERSISTIDO, no el objeto en memoria: lo que
        importa es que lo que se firmo es lo que quedo en disco, que es
        justamente la propiedad de WI-111.
        """
        with proveedor_local() as url:
            storage, run_id = _corrida(url, tmp_path)
        _, _, handoff_json = _nodo(storage, run_id)
        assert handoff_json, "la node_execution no persiste el handoff que se firmo"
        handoff = json.loads(handoff_json)
        assert handoff.get("expected_result"), f"el handoff no lleva expected_result: {handoff}"
        identidad = handoff.get("identity") or {}
        assert identidad.get("tenant_id") == TENANT, identidad
        assert identidad.get("run_id") == run_id, identidad

    def test_5_el_estado_se_puede_releer_tras_reconciliar(self, tmp_path: Path) -> None:
        """FRONTERA 7+8 — persistencia y recuperacion, con la conexion CERRADA.

        Se relee con una conexion NUEVA a la misma base. Releer con la misma
        conexion que escribió no demuestra persistencia: demuestra memoria.
        """
        with proveedor_local() as url:
            ruta = tmp_path / "b24.sqlite"
            storage, run_id = _corrida(url, tmp_path)
            assert ruta.exists()
            storage._conn.close()

        otra = Storage(ruta)
        estado, error, _ = _nodo(otra, run_id)
        assert estado == "SUCCEEDED", (
            f"releyendo desde otra conexion el nodo esta {estado!r} ({error!r}): "
            f"lo que se persistio no sobrevive a cerrar la conexion."
        )
        eventos = otra._conn.execute(
            "SELECT event_kind FROM runtime_events WHERE run_id = ? ORDER BY sequence",
            (run_id,),
        ).fetchall()
        assert eventos, "no hay eventos del run: la transicion no persistio su historia"
        kinds = [k[0] for k in eventos]
        assert "RunCreated" in kinds, kinds

    def test_6_reconciliar_de_nuevo_no_reejecuta_el_nodo(self, tmp_path: Path) -> None:
        """FRONTERA 8 — la recuperacion es idempotente.

        Un segundo `reconcile_run` no puede volver a llamar al proveedor: si lo
        hiciera, la idempotencia de la que depende toda la reejecucion de un run
        no existiria. Y aqui la llamada se cuenta de verdad, porque el servidor
        local registra cada peticion.
        """
        with proveedor_local() as url:
            storage = Storage(tmp_path / "b24.sqlite")
            ctl = RunController(runs=storage, events=storage, policy=storage, adapter=_adapter(url))
            run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=_plan())
            ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
            primera = len(peticiones())
            assert primera == 1, f"la primera ronda hizo {primera} llamadas"
            ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
            segunda = len(peticiones())
            assert segunda == 1, (
                f"la segunda reconciliacion hizo {segunda} llamadas al "
                f"proveedor. Reconciliar un run ya resuelto no puede reejecutarlo."
            )


# =====================================================================
class TestElProveedorLocalHablaLaFormaDelProveedor:
    """Que el doble de la RED hable la forma que el parser exige.

    Si esto no se comprueba, un cambio en `_parse_anthropic_response` podria
    dejar el recorrido entero en rojo sin que nadie sepa si el fallo es del
    recorrido o del doble.
    """

    def test_el_adapter_parsea_la_respuesta_local(self) -> None:
        with proveedor_local() as url:
            resultado = _adapter(url).invoke(_handoff_minimo())
        assert isinstance(resultado, AgentResult), type(resultado)
        assert resultado.outcome == "ok", resultado.outcome
        assert resultado.result.get("local") is True, resultado.result

    def test_una_respuesta_sin_content_invalida(self) -> None:
        """La otra mitad: el parser NO acepta cualquier cosa.

        Sin este, el recorrido en verde no distinguiria «el adapter entienda la
        forma» de «el parser acepte cualquier JSON».
        """
        from skillgraph.core.errors import OutcomeInvalidError

        with (
            proveedor_local(cuerpo={"nada": "que ver aqui"}, estado=200) as url,
            pytest.raises(OutcomeInvalidError),
        ):
            _adapter(url).invoke(_handoff_minimo())

    def test_un_429_produce_una_contradiccion_named(self, tmp_path: Path) -> None:
        """Un 429 se reintenta y, agotados los intentos, FALLA el nodo.

        El recorrido entero tiene que ser rojo cuando el proveedor falla: un
        recorrido que siempre acaba en SUCCEEDED no esta midiendo el camino,
        esta midiendo que se le dio bien.
        """
        with proveedor_local(estado=429) as url:
            storage, run_id = _corrida(url, tmp_path)
        estado, error, _ = _nodo(storage, run_id)
        assert estado != "SUCCEEDED", "el nodo quedo SUCCEEDED con un proveedor en 429"
        assert error, "el fallo no dice por que: el error tiene que nombrar la causa"


def _handoff_minimo() -> Handoff:
    """Un `Handoff` con la forma que el motor produce, no una inventada."""
    from skillgraph.runtime.handoff import (
        HandoffBehavior,
        HandoffExecution,
        HandoffIdentity,
        HandoffKnowledge,
    )

    return Handoff(
        identity=HandoffIdentity(
            tenant_id=TENANT,
            project_id=PROJECT,
            run_id="run-b24",
            node_execution_id="ne-b24",
            attempt=1,
        ),
        behavior=HandoffBehavior(
            definition_kind="ActionNode",
            definition_name="analizar",
            definition_namespace="urn:b24",
            definition_revision=1,
            api_version="v1",
        ),
        knowledge=HandoffKnowledge(recipe_ref="recipe://b24"),
        execution=HandoffExecution(
            workspace_ref="urn:b24:workspace",
            source_revision="a",
            budget={},
        ),
        expected_result="texto",
        capabilities=(),
    )


# =====================================================================
class TestLasInstruccionesDeEjecucionApuntanAUnFicheroQueExiste:
    """R1. El error 32 de WI-113, otra vez y en otro sitio.

    Una instruccion que dice «corre este path» y el path no existe no es una
    instruccion: es una trampa con la forma de una instruccion. Quien la siga
    obtiene `rc=4` —un error de uso de pytest, no un fallo de la UAT— y no
    tiene forma de saber que no ejecuto nada.
    """

    def test_el_path_del_docstring_existe(self) -> None:
        import re

        texto = Path(__file__).with_name("test_uat_real_provider.py").read_text(encoding="utf-8")
        caminos = re.findall(r"pytest (tests/\S+\.py)", texto)
        assert caminos, "el modulo ya no dice como ejecutarse: se perdio la instruccion"
        for camino in caminos:
            assert (Path(__file__).parent.parent / camino).exists(), (
                f"las instrucciones dicen `pytest {camino}` y ese fichero no "
                f"existe. Quien lo siga ejecuta NADA y recibe un error de uso "
                f"de pytest, que no dice nada sobre la UAT."
            )
