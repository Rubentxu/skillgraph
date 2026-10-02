"""Delegaciones de `RunController`: lectura del estado de un run: listados, detalle, logs, snapshot y frontier.

WI-67, ADR-0019 fase 2. Extraccion estranguladora de metodos de
`RunController` hacia un mixin por dominio. Cuerpos movidos
**verbatim**: sin logica, ramas ni rutas de error nuevas.

Por que mixin y no `__getattr__`: `__getattr__` rompe el tipado
estatico que AGENTS.md 4.1 exige explicito. El mixin conserva las
anotaciones reales, mantiene `RunController` como la misma clase
y obliga a cero ediciones en los callers.

Invariante: este modulo solo usa `self.*`. No captura estado, no
importa `RunController` (seria un ciclo) y no define lo que la
clase mantiene. Red: `tests/test_wi67_runcontroller_mixins.py`.
"""

from __future__ import annotations

from skillgraph.resources.workflow import WorkflowPlan
from skillgraph.runtime.engine import RuntimeEvent
from skillgraph.runtime.run_types import (
    RunSnapshot,
    RuntimeEventLog,
    has_self_loop,
)


class RunObservabilityDelegations:
    """Lectura del estado de un run: listados, detalle, logs, snapshot y frontier.

    8 metodos, 214 LoC movidos de `RunController` (WI-67).
    Cuerpos verbatim: ver `runcontroller.py` @ WI-67.
    """

    def list_runs(
        self,
        *,
        tenant_id: str,
        project_id: str,
        state: str | None = None,
        limit: int = 50,
    ) -> tuple[RunSnapshot, ...]:
        """Lista Runs de un (tenant, project) ordenados por mas reciente.

        Inspeccion read-only: NO emite eventos NI modifica estado.
        Complementa `cancel_run`: el operador primero lista, decide
        cual cancelar.

        Args:
            state: filtro opcional por estado exacto.
            limit: tope de runs devueltos (default 50).

        Returns:
            Tupla inmutable de `RunSnapshot` ordenada por created_at
            DESC. El snapshot expone run_id, state, current_node y
            la lista de nodos ejecutados (via `_executed_node_names`).
        """
        rows = self._runs.list_runs(
            tenant_id=tenant_id,
            project_id=project_id,
            state=state,
            limit=limit,
        )
        snapshots: list[RunSnapshot] = []
        for row in rows:
            executed = self._executed_node_names(
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=row.run_id,
            )
            snapshots.append(
                RunSnapshot(
                    run_id=row.run_id,
                    state=row.state,  # type: ignore[arg-type]
                    current_node=row.current_node,
                    executed_nodes=executed,
                    events_emitted=self._count_events(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        run_id=row.run_id,
                    ),
                )
            )
        return tuple(snapshots)

    def show_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> RunSnapshot:
        """Devuelve el snapshot de un Run por id.

        Inspeccion read-only: NO emite eventos. Levanta `NotFoundError`
        si el run no existe (delegado en `Storage.get_run`).
        """
        row = self._runs.get_run(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
        )
        executed = self._executed_node_names(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
        )
        return RunSnapshot(
            run_id=row.run_id,
            state=row.state,  # type: ignore[arg-type]
            current_node=row.current_node,
            executed_nodes=executed,
            events_emitted=self._count_events(
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run_id,
            ),
        )

    def logs_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> tuple[RuntimeEventLog, ...]:
        """Devuelve el timeline de eventos de un Run en orden monotono.

        Inspeccion read-only: NO emite eventos. Levanta `NotFoundError`
        si el run no existe (delegado en `Storage.get_run`; lo
        validamos ANTES de leer eventos para fallar rapido si el
        run no existe vs. devolver una tupla vacia).

        WI-32.2 (audit 2026-09-27): ``list_events_for_run`` devuelve
        ``list[StoredEvent]`` (DTO inmutable). Construimos
        ``RuntimeEvent`` directamente desde los atributos del DTO;
        ya no hay conversion ``Row -> dict -> RuntimeEvent``.
        """
        # Validacion temprana: si el run no existe, error tipado
        # en lugar de una tupla vacia confusa.
        self._runs.get_run(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
        )
        rows = self._runs.list_events_for_run(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
        )
        out: list[RuntimeEventLog] = []
        for d in rows:
            # StoredEvent ya tiene los campos deserializados (payload
            # JSON parseado por el adapter en ``platform/``).
            out.append(
                RuntimeEventLog(
                    sequence=int(d.sequence),
                    event=RuntimeEvent(
                        event_id=d.event_id,
                        tenant_id=d.tenant_id,
                        project_id=d.project_id,
                        event_kind=d.event_kind,
                        run_id=d.run_id,
                        resource_ref=d.resource_ref,
                        causation_id=d.causation_id,
                        correlation_id=d.correlation_id,
                        payload=d.payload,
                        timestamp=d.timestamp,
                        schema_version=d.schema_version,
                    ),
                )
            )
        return tuple(out)

    def _count_events(self, *, tenant_id: str, project_id: str, run_id: str) -> int:
        """Cuenta eventos asociados a un Run (read-only).

        Delega en `Storage.list_events_for_run` (regla "Storage
        encapsula SQL"); no toca `_conn` directamente.
        """
        rows = self._runs.list_events_for_run(
            tenant_id=tenant_id, project_id=project_id, run_id=run_id
        )
        return len(rows)

    def _snapshot(self, tenant_id: str, project_id: str, run_id: str) -> RunSnapshot:
        run = self._load_run(tenant_id, project_id, run_id)
        return RunSnapshot(
            run_id=run_id,
            state=run.state,
            current_node=run.current_node,
            executed_nodes=self._executed_node_names(tenant_id, project_id, run_id),
            events_emitted=len(
                self._runs.list_events_for_run(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    run_id=run_id,
                )
            ),
        )

    def _calculate_frontier(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        plan: WorkflowPlan,
    ) -> list[str]:
        """Lista de nombres de nodo listos para ejecutar.

        Reglas:
        - Un nodo aparece en la frontier si:
          * Nunca se ha ejecutado (no hay NodeExecution para el run+name).
          * Su unico NodeExecution esta en READY (interrumpido y
            recuperado) o FAILED (a reintentar, aunque por ahora no
            incrementamos attempt automaticamente).
        - El plan es un DAG simple: un nodo solo se ejecuta si su
          current_node = su nombre, O si es el initial y el run esta
          recien creado.
        """
        run_row = self._load_run(tenant_id, project_id, run_id)
        current = run_row.current_node
        if current is None:
            return []

        # Miramos si el current ya esta completado.
        existing = self._node_executions_for(tenant_id, project_id, run_id, current)
        last = existing[-1] if existing else None
        if last is None:
            return [current]
        # H4: si last es SUCCEEDED, es ciclo solo si el plan declara una
        # auto-transicion desde current hacia si mismo. Sin self-loop
        # declarada, es nodo terminal post-exito: devolver [].
        if last.state == "SUCCEEDED":
            node = plan.node(current)
            if not has_self_loop(plan, current):
                return []
            if node.max_visits is not None and len(existing) >= node.max_visits:
                return []
            return [current]
        if last.state in {"SUCCEEDED", "FAILED", "STOPPED", "CANCELLED"}:
            return []
        return [current]

    def _count_executed(self, tenant_id: str, project_id: str, run_id: str) -> int:
        return len(self._executed_node_names(tenant_id, project_id, run_id))

    def _executed_node_names(self, tenant_id: str, project_id: str, run_id: str) -> tuple[str, ...]:
        # Lectura pura: delega en `Storage.list_executed_node_names`
        # (H9-BSlice3-S1). DISTINCT + ORDER BY node_name ASC determinista.
        return self._runs.list_executed_node_names(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
        )
