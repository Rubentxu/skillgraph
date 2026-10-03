"""B3 — la procedencia se PERSISTE, no solo se transporta.

`platform/ports/capabilities.py::CapabilityResult` lleva `adapter`: la
procedencia que B6 necesitara para responder «¿quien afirmo esto?».

El resultado que el sistema real produce y persiste es otro, y **no lo
llevaba**. MEDIDO antes de escribir nada
(`.pipelinek/b3_provenance_measure.py`), ejecutando un nodo de verdad:

    el Adapter persistido, campos: ['evidence_ref', 'outcome', 'result']
    hay campo 'adapter'      : False

    eventos por nodo:
      NodeCompleted        {node_execution_id, outcome, context_hash}
      EvidenceProduced     {node_execution_id, outcome, context_hash, evidence_ref}

    columnas de node_executions: node_execution_id, run_id, tenant_id,
      project_id, node_name, attempt, state, outcome, context_hash,
      handoff_json, result_json, error, started_at, finished_at

O sea: **ningún artefacto persistido dice qué adapter produjo el
resultado.** Y el motor SI lo sabe: es quien lo invoco.

**POR QUE ESTO ES DE B3 Y NO DE B6.** B6 quiere que toda afirmacion
distinga `observed` / `derived-deterministically` / `agent-inferred` /
`human-asserted`, y para eso tiene que poder contestar «¿quien?". Eso no
empieza a ser una pregunta en B6: se descubre ausente, porque cuando
llegue no habra de donde sacarla. La procedencia se pierde ANTES, en el
tipo que el motor escribe, y ese tipo vive en el runtime.

**Y NO SE AFIRMA QUE HAYA CAUSADO UN FALLO.** No lo ha causado: depende
de que cada adapter se acuerde de meter su nombre en `result`, y el
adapter de la medicion lo hizo. Lo que se mide es que el sistema no lo
sabe de forma ESTRUCTURAL, y que ahora lo dice sin que nadie se acuerde.

**POR QUE VA EN EL EVENTO Y NO EN `AgentResult`.** Porque el nombre del
adapter no es parte de la RESPUESTA del agente: es metadato del runtime,
y hay dos razones practicas para ponerlo ahi y no en el resultado:

1. `AgentResult.result` es un payload arbitrario que produce el MODELO.
   Anadirle un campo filled por el motor seria mezclar lo que el agente
   afirmo con lo que el motor sabe, y un agente que devolviera su propio
   campo `adapter` colisionaria con el.
2. El resultado se serializa con `result_to_jsonable` y se compara en
   tests; tocarlo afecta a la comparacion del contenido que el agente
   produjo. El evento es aditivo.

**LA COLUMNA EN `node_executions` SE QUEDA PARA B8**, porque anadir una
columna a una tabla existente es migracion, y las migraciones son de B8.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from skillgraph.domain.dsl import PlanBuilder, node_name
from skillgraph.platform.storage import Storage
from skillgraph.runtime.agent import AgentResult, adapter_name
from skillgraph.runtime.runcontroller import RunController

TENANT = "t-b3prov"
PROJECT = "p-b3prov"


class _AdapterConNombre:
    """Un AgentAdapter mas, que ademas declara como se llama.

    No es un espia ni un doble: hay tres adapters en el repo
    (`FakeAgentAdapter`, `HttpAgentAdapter` y el determinista). Este
    simplemente declara su nombre, que es lo que un adapter de un pack
    externo haria.
    """

    name = "adapter-de-prueba-explicito"

    def invoke(self, handoff: Any) -> AgentResult:
        return AgentResult(outcome="texto", result={"hecho": True}, evidence_ref="ev-b3")


class _AdapterSinNombre:
    """El caso por defecto: nadie declara nada."""

    def invoke(self, handoff: Any) -> AgentResult:
        return AgentResult(outcome="texto", result={"hecho": True})


def _plan() -> Any:
    return (
        PlanBuilder().add_node(node_name("n1"), expected="texto").starts_at(node_name("n1")).build()
    )


def _correr(adapter: Any) -> tuple[Storage, list[tuple[str, dict[str, Any]]]]:
    """Ejecuta UN nodo y devuelve (storage, (evento, payload) leidos de disco)."""
    tmp = tempfile.TemporaryDirectory()
    storage = Storage(Path(tmp.name) / "prov.sqlite")
    ctl = RunController(runs=storage, events=storage, policy=storage, adapter=adapter)
    run_id = ctl.create_run(tenant_id=TENANT, project_id=PROJECT, plan=_plan())
    ctl.reconcile_run(tenant_id=TENANT, project_id=PROJECT, run_id=run_id)
    filas = storage._conn.execute(
        "SELECT event_kind, payload_json FROM runtime_events WHERE run_id = ? ORDER BY sequence",
        (run_id,),
    ).fetchall()
    eventos: list[tuple[str, dict[str, Any]]] = []
    for kind, payload_json in filas:
        try:
            payload = json.loads(payload_json or "{}")
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict):
            eventos.append((kind, payload))
    return storage, eventos


class TestElNombreDelAdapter:
    """Como se llama un adapter, que hoy no lo sabe nadie."""

    def test_un_adapter_que_declara_nombre_lo_tiene(self) -> None:
        assert adapter_name(_AdapterConNombre()) == "adapter-de-prueba-explicito"

    def test_sin_declarar_usa_el_nombre_de_la_clase(self) -> None:
        """El default tiene que existir, o el arreglo seria opcional.

        Y opcional significa que un adapter que no se acuerde deja la
        procedencia vacia en silencio, que es el defecto que se viene a
        arreglar. Los tres adapters que hay hoy no declaran nombre, asi
        que sin este default el arreglo no cambiaria nada.
        """
        assert adapter_name(_AdapterSinNombre()) == "_AdapterSinNombre"

    def test_un_nombre_vacio_no_cuenta(self) -> None:
        """`name = ""` no es un nombre: es un olvido declarado.

        Sin esta comprobacion, un adapter con `name = ""` pasaria por el
        default y el resultado seria `_Adapter` en vez de "", que es peor
        que no tener nombre: parece que se sabe quien fue.
        """
        vacio = _AdapterSinNombre()
        vacio.name = ""  # type: ignore[attr-defined]
        assert adapter_name(vacio) == "_AdapterSinNombre"


class TestLaProcedenciaLlegaAlDisco:
    """La propiedad entera: ejecuto un nodo, leo, y se quien lo produjo."""

    def test_el_evento_de_completado_dice_quien(self) -> None:
        storage, eventos = _correr(_AdapterConNombre())
        completados = [p for k, p in eventos if k == "NodeCompleted"]
        assert completados, "no se emitio NodeCompleted"
        assert completados[0]["adapter"] == "adapter-de-prueba-explicito", (
            "el evento no dice que adapter produjo el resultado. Sin esto, "
            "«¿quien afirmo esto?» no tiene respuesta sobre lo que hay en "
            "disco, que es lo unico que sobrevive a la sesion."
        )
        storage.close()

    def test_el_evento_de_evidencia_tambien(self) -> None:
        """Los dos. La evidencia es la que B6 va a leer, y va con su
        propio evento: si solo lo llevara `NodeCompleted`, consultar la
        evidencia tendria que cruzarlo con otro evento para saber de
        donde salio."""
        storage, eventos = _correr(_AdapterConNombre())
        con_evidencia = [p for k, p in eventos if k == "EvidenceProduced"]
        assert con_evidencia
        assert con_evidencia[0]["adapter"] == "adapter-de-prueba-explicito"
        storage.close()

    def test_tambien_cuando_el_adapter_no_declara_nombre(self) -> None:
        """El caso REAL: los tres adapters del repo no declaran nombre.

        Si el test solo comprobara el caso del adapter que declara, el
        arreglo podria seguir vacio en produccion sin que nada se viera.
        """
        storage, eventos = _correr(_AdapterSinNombre())
        completados = [p for k, p in eventos if k == "NodeCompleted"]
        assert completados
        assert completados[0]["adapter"] == "_AdapterSinNombre"
        storage.close()

    def test_la_firma_de_node_completed_exige_el_adapter(self) -> None:
        """No es opcional, porque opcional es como esto se pierde.

        Si `adapter` tuviera un default, un call-site nuevo podria
        omitirlo y el evento volveria a no decir quien, sin que nada
        falle. Aqui se mira la FIRMA, no el cuerpo: es la propiedad que
        se puede comprobar sin depender de que exista un call-site.
        """
        import inspect

        from skillgraph.runtime.engine import EventBuilder

        for metodo in ("node_completed", "evidence_produced"):
            params = inspect.signature(getattr(EventBuilder, metodo)).parameters
            assert "adapter" in params, f"{metodo} no recibe `adapter`"
            assert params["adapter"].default is inspect.Parameter.empty, (
                f"{metodo} da default a `adapter`: un call-site nuevo "
                f"podria omitirlo y el evento volveria a no decir quien."
            )

    def test_el_resultado_del_agente_no_lleva_el_nombre(self) -> None:
        """Y el nombre NO se mete en `AgentResult`, a NINGUN nivel.

        `AgentResult` es lo que produjo el MODELO. Meter ahi el nombre
        del adapter mezcla dos cosas y, peor, un agente que devolviera
        su propio campo `adapter` colisionaria con el. La procedencia va
        en el evento, que es metadata del runtime.

        Se comprueban los **dos** niveles de `result_json`: la raiz y el
        `result` interior. La primera version de este test solo miraba
        el interior, y una mutacion que ponia `adapter` en la raiz —que
        es donde lo pondria `json.dumps({**result_to_jsonable(r),
        'adapter': ...})`— pasaba sin ser vista. Un guard que mira medio
        sitio es un guard que no mira.
        """
        storage, eventos = _correr(_AdapterConNombre())
        completados = [p for k, p in eventos if k == "NodeCompleted"]
        assert completados
        assert "adapter" in completados[0], "la procedencia va en el evento"
        filas = storage._conn.execute("SELECT result_json FROM node_executions").fetchall()
        assert filas, "no se persistio ningun node_execution"
        for r in filas:
            resultado = json.loads(r[0] or "{}")
            assert "adapter" not in resultado, (
                "el nombre del adapter se ha colado en la RAIZ del "
                "resultado persistido. Ahi es metadata del runtime, no "
                "contenido del agente, y colisiona con lo que el modelo "
                "devuelva."
            )
            assert "adapter" not in resultado.get("result", {}), (
                "el nombre del adapter se ha colado en `result`, que es el payload del AGENTE."
            )
        storage.close()
