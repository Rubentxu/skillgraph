"""Los diez widgets del gate B7, proyectados sobre las vistas.

QUE HACE ESTE MODULO
--------------------
`views.py` da la FORMA (tabla, detalle, columnas). Aqui estan las
PROYECCIONES: para cada uno de los diez widgets que nombra el gate, una
funcion pura que toma lo que el dominio ya devolvio y devuelve una vista.

Son funciones puras a proposito. Una proyeccion que abriera la base, que
consultara el reloj o que decidiera por su cuenta que datos son
interesantes dejaria de ser una proyeccion y passaria a ser una segunda
via de consulta —que es el duplicado que este bloque existe para
impedir—. La proyeccion recibe la fila y la viste; quien decide que se
consulta es el controlador, que ya existe.

POR QUE HAY UNA FUNCION POR WIDGET, y no un mapa
-------------------------------------------------
Porque el gate dice que cada widget escala de summary card a panel a
full-screen, y cada uno tiene lo que poner en la tarjeta y lo que solo
aparece en el panel. `run_view` tiene que mostrar `current_node` en la
tarjeta y el `run_id` en el panel; `timeline_view` no tiene nada que
enseñar en una tabla de una fila. Un mapa `dict[str, callable]` con una
firma comun obligaria a las diez a la misma forma, y la forma comun es
justo lo que no tienen.

Y hay tres widgets que NO tienen modelo legible segun el medidor —
Timeline, Decisions, Policies— porque el dato existe y no hay forma de
leerlo. aqui se anaden las tres proyecciones que les faltan, y el
medidor lo comprueba.
"""

from __future__ import annotations

from typing import Any

from skillgraph.presentation.views import Column, DetailView, TableView

# --- Runs ----------------------------------------------------------------

_RUNS_COLUMNS: tuple[Column, ...] = (
    Column("run_id", "run_id"),
    Column("state", "state"),
    Column("current_node", "current_node"),
    Column("executed", "executed"),
    Column("events", "events"),
)


def run_view(runs: tuple[Any, ...]) -> TableView:
    """La lista de runs de un proyecto.

    Los campos salen de `RunSnapshot`, que ya existe en
    `runtime/run_types.py`. La proyeccion no consulta nada: traduce un
    objeto del dominio en una fila, y por eso el widget no puede
    desincronizarse del dominio salvo que el dominio cambie —y si cambia,
    el error sale aqui y no en dos superficies a la vez.
    """
    return TableView(
        kind="runs",
        columns=_RUNS_COLUMNS,
        rows=tuple(
            {
                "run_id": r.run_id,
                "state": r.state,
                "current_node": r.current_node or "-",
                "executed": ",".join(r.executed_nodes) or "-",
                "events": r.events_emitted,
            }
            for r in runs
        ),
    )


def run_detail(snapshot: Any, *, timeline: TableView | None = None) -> DetailView:
    """El panel de un run: el estado MAS el timeline que lo explico.

    El objetivo del bloque dice que un operador abre un run y ve «nodo
    actual, handoff, evidence, capabilities, decisions, graph diff,
    coste/budget y timeline». Este panel es el sitio donde se empiezan a
    juntar, y las secciones se anaden como se añadan.
    """
    secciones: list[tuple[str, tuple[TableView, ...]]] = []
    if timeline is not None:
        secciones.append(("timeline", (timeline,)))
    return DetailView(
        kind="run",
        title=f"run {snapshot.run_id}",
        fields=(
            ("run_id", snapshot.run_id),
            ("state", snapshot.state),
            ("current_node", snapshot.current_node or "-"),
            ("executed_nodes", snapshot.executed_nodes),
            ("events_emitted", snapshot.events_emitted),
        ),
        sections=tuple(secciones),
    )


# --- Timeline ------------------------------------------------------------
#
# Es uno de los tres que el medidor daba por SIN MODELO. El dato existe:
# `RuntimeEventLog` (runtime/run_types.py) ya expone la secuencia, que es
# justo lo que hace falta para ordenar. Lo que no existia era la lectura.


def timeline_view(eventos: tuple[Any, ...]) -> TableView:
    """La linea de tiempo de un run, en orden de secuencia.

    La fila lleva el `sequence` porque es lo que la hace una TIMELINE y no
    una lista: sin el, dos eventos con el mismo timestamp no tienen orden
    y el operador no puede leer la causa. `RuntimeEventLog` ya lo expone
    precisamente para esto —su docstring lo dice—, luego esta proyeccion
    no inventa el orden, lo usa.
    """
    return TableView(
        kind="timeline",
        columns=(
            Column("sequence", "seq"),
            Column("timestamp", "timestamp"),
            Column("kind", "kind"),
            Column("subject", "subject"),
        ),
        rows=tuple(
            {
                "sequence": getattr(e, "sequence", ""),
                "timestamp": getattr(e, "timestamp", ""),
                "kind": getattr(e, "kind", getattr(e, "event_type", "")),
                "subject": getattr(e, "node_id", "") or getattr(e, "subject", ""),
            }
            for e in eventos
        ),
    )


# --- Knowledge -----------------------------------------------------------

_CLAIMS_COLUMNS: tuple[Column, ...] = (
    Column("subject", "subject"),
    Column("predicate", "predicate"),
    Column("value", "value"),
    Column("source", "source"),
)


def knowledge_view(claims: tuple[Any, ...]) -> TableView:
    """Las afirmaciones de una entidad, con SU origen epistemico.

    Esta columna es la que B6 hizo posible y la que B7 necesita: sin
    `assertion_origin` el operador veria QUÉ se afirma y no QUIEN lo
    afirma, y un panel que no dice quien afirma no sirve para gobernarlo.
    Los dos bloques se pagan el uno al otro, y eso no estaba previsto al
    escribir ninguno de los dos.
    """
    return TableView(
        kind="knowledge",
        columns=(*_CLAIMS_COLUMNS, Column("origin", "origin")),
        rows=tuple(
            {
                "subject": c.subject_entity_id,
                "predicate": c.predicate,
                "value": c.object_literal,
                "source": c.source_id,
                "origin": c.assertion_origin,
            }
            for c in claims
        ),
    )


def evidence_view(evidencias: tuple[Any, ...]) -> TableView:
    """La evidencia que sostiene las afirmaciones."""
    return TableView(
        kind="evidence",
        columns=(
            Column("evidence_id", "evidence_id"),
            Column("kind", "kind"),
            Column("source", "source"),
            Column("observed_at", "observed_at"),
        ),
        rows=tuple(
            {
                "evidence_id": e.evidence_id,
                "kind": e.kind,
                "source": e.source_id,
                "observed_at": e.observed_at,
            }
            for e in evidencias
        ),
    )


# --- Decisions y Policies ------------------------------------------------
#
# Los otros dos que el medidor daba por SIN MODELO.


def decision_view(decisiones: tuple[Any, ...]) -> TableView:
    """Las decisiones que el sistema tomo y por que.

    Una decision sin su porque no es gobernable: el operador puede
    revertirla, pero no puedeizonar si el sistema va a volver a tomarla.
    Por eso la columna de motivo no es opcional, aunque el dato venga
    vacio en la mayoria de las filas — una decision sin motivo DICE que no
    lo tiene, y callarlo seria dejar al operador creyendo que existe.
    """
    return TableView(
        kind="decisions",
        columns=(
            Column("decision", "decision"),
            Column("outcome", "outcome"),
            Column("actor", "actor"),
            Column("reason", "reason"),
        ),
        rows=tuple(
            {
                "decision": _attr(d, "decision", _attr(d, "name", "")),
                "outcome": _attr(d, "outcome", _attr(d, "status", "")),
                "actor": _attr(d, "actor", _attr(d, "decided_by", "")),
                "reason": _attr(d, "reason", _attr(d, "explanation", "")),
            }
            for d in decisiones
        ),
    )


def policy_view(politicas: tuple[Any, ...]) -> TableView:
    """Las politicas que gobiernan los runs."""
    return TableView(
        kind="policies",
        columns=(
            Column("policy_id", "policy_id"),
            Column("name", "name"),
            Column("enforced", "enforced"),
        ),
        rows=tuple(
            {
                "policy_id": _attr(p, "policy_id", _attr(p, "id", "")),
                "name": _attr(p, "name", _attr(p, "kind", "")),
                "enforced": _attr(p, "enforced", ""),
            }
            for p in politicas
        ),
    )


# --- Resources, Diff, Capabilities, Graph --------------------------------


def resource_view(recursos: tuple[Any, ...]) -> TableView:
    """Los recursos y su estado observado.

    `observed_generation` se LEE de la fila y no se calcula: declarado
    mentiria en cuanto el spec cambiara por debajo, y sin ningun error.
    """
    return TableView(
        kind="resources",
        columns=(
            Column("uid", "uid"),
            Column("kind", "kind"),
            Column("generation", "generation"),
            Column("resource_version", "resource_version"),
        ),
        rows=tuple(
            {
                "uid": _attr(r, "uid", _attr(r, "resource_id", "")),
                "kind": _attr(r, "kind", ""),
                "generation": _attr(r, "observed_generation", _attr(r, "generation", "")),
                "resource_version": _attr(r, "resource_version", ""),
            }
            for r in recursos
        ),
    )


def diff_view(diff: Any) -> DetailView:
    """El diff del grafo, que B5 hizo comparable.

    Se muestra como detalle y no como tabla porque un diff es un
    DOCUMENTO —«que cambia, por que, que evidencia lo justifica, que coste
    anade, que capacidades exige, que nodos invalida, si es reversible»— y
    meter esas siete respuestas en filas de una tabla obliga al operador a
    reconstruirlas.
    """
    if diff is None:
        return DetailView(kind="diff", title="diff", fields=(("estado", "sin diff"),))
    return DetailView(
        kind="diff",
        title="diff del grafo",
        fields=(
            ("revision", _attr(diff, "revision", "")),
            ("cambios", len(getattr(diff, "changes", ()) or ())),
            ("capacidades_requeridas", getattr(diff, "required_capabilities", ())),
            ("capacidades_declaradas", getattr(diff, "declared_capabilities", ())),
            ("reversible", getattr(diff, "reversible", "")),
        ),
    )


def capability_view(capacidades: tuple[Any, ...]) -> TableView:
    """Las capabilities y si estan disponibles.

    La columna de disponibilidad es la que hace que este widget sirva para
    GOBERNAR y no solo para mirar: un operador que ve una capability
    pedida y no disponible sabe que el run va a fallar antes de que
    falle.
    """
    return TableView(
        kind="capabilities",
        columns=(
            Column("name", "name"),
            Column("declared", "declared"),
            Column("available", "available"),
        ),
        rows=tuple(
            {
                "name": _attr(c, "name", _attr(c, "capability_id", "")),
                "declared": _attr(c, "declared", ""),
                "available": _attr(c, "available", ""),
            }
            for c in capacidades
        ),
    )


def graph_view(nodes: tuple[Any, ...], *, aristas: tuple[Any, ...] = ()) -> DetailView:
    """El grafo: nodos y aristas, con la misma forma para los dos."""
    return DetailView(
        kind="graph",
        title="grafo",
        fields=(
            ("nodos", len(nodes)),
            ("aristas", len(aristas)),
        ),
        sections=(
            (
                "nodos",
                (
                    TableView(
                        kind="graph.nodes",
                        columns=(
                            Column("name", "name"),
                            Column("kind", "kind"),
                        ),
                        rows=tuple(
                            {"name": _attr(n, "name", ""), "kind": _attr(n, "kind", "")}
                            for n in nodes
                        ),
                    ),
                ),
            ),
        ),
    )


def _attr(objeto: Any, nombre: str, defecto: Any) -> Any:
    """Lee un atributo con defecto, tolerando las dos formas del dominio.

    Los objetos del dominio no exponen los mismos nombres en todos los
    sitios —un `Claim` tiene `subject_entity_id` y un `Resource` tiene
    `uid`—, y la proyeccion no debe romperse si uno se renombra: una
    columna vacia es un dato feo, y una excepcion al pintar es un panel que
    no abre. El defecto se ve en la salida, que es donde tiene que verse.
    """
    valor = getattr(objeto, nombre, None)
    return defecto if valor is None else valor
