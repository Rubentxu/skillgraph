"""WI-77 — El tercer eje del presupuesto (`max_events`) esta verificado.

Por que este fichero existe
---------------------------
Con el instrumento de cobertura fiable que landed WI-75, por primera vez
se puede afirmar que `run_budget_delegations.py` esta por debajo del
contrato de AGENTS §6.3 (core >=90 %): 83 %, con las lineas 91-105 sin
cubrir.

Esas lineas son el chequeo **2b**: el limite `max_events` del Run. No es un
detalle interno. Su docstring promete que emite un evento `BudgetExceeded`
con `kind="events"`, y la razon de ese evento es lo que el operador lee
en el timeline (v0.11.0) para entender POR QUE se aborto un run. Es un
control de gobernanza sin un solo test.

Los otros dos ejes si estan cubiertos: `max_visits` por nodo con
self-loop (chequeo 1, H4) y `max_visits` global del Run (chequeo 2a).

Que se mide
-----------
La decision y su evento observable, no la linea ejecutada:

1. Con el limite alcanzado devuelve True y emite `BudgetExceeded` con
   `kind="events"`, `limit` y `observed` correctos.
2. Por debajo del limite devuelve False y NO emite nada.
3. Sin `max_events` configurado devuelve False (sin limite, sin aborted).
4. El limite es inclusivo: contar exactamente el limite ya agota.

`_count_events` se sustituye por un contador controlado porque aqui lo que
se decide es "dado un limite y un observado, que hace el guard". Que
`_count_events` cuente bien los eventos de verdad es otro contrato, y lo
cubre `run_observability_delegations`. El resto —Storage, budget en disco,
append del evento— es real, sin mocks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from skillgraph.platform.storage import Storage
from skillgraph.resources.workflow import WorkflowNode, WorkflowPlan
from skillgraph.runtime.runcontroller import RunController

TENANT = "t"
PROJECT = "p"
NODE = "n"


def _node(name: str) -> WorkflowNode:
    return WorkflowNode(
        name=name,
        kind="ActionNode",
        namespace="shared",
        api_version="skillgraph.dev/v1alpha1",
        resource_revision=1,
        expected_result="text",
        capabilities=(),
        metadata={},
    )


def _plan(node_name: str = NODE) -> WorkflowPlan:
    return WorkflowPlan(nodes=(_node(node_name),), transitions=(), initial=node_name)


class _StubAdapter:
    """Adapter minimo: `_is_budget_exhausted` no llega a invocarlo."""

    def invoke(self, handoff: Any) -> Any:  # pragma: no cover - no se usa
        raise AssertionError("este test no debe llegar a invocar el adapter")


def _controller(tmp_path: Path, *, observed_events: int) -> RunController:
    storage = Storage(tmp_path / "p.sqlite")
    storage.ensure_schema()
    ctl = RunController(runs=storage, events=storage, policy=storage, adapter=_StubAdapter())
    # Se sustituye SOLO la lectura del contador: lo que se prueba aqui es la
    # decision del guard, no el conteo (que tiene su propio contrato).
    ctl._count_events = lambda **_: observed_events  # type: ignore[method-assign]
    return ctl


def _budget(
    ctl: RunController,
    run_id: str,
    *,
    max_events: int | None,
    max_visits: int | None = None,
    policy: str | None = None,
) -> None:
    if policy is not None:
        ctl._policy.upsert_policy(tenant_id=TENANT, policy=policy)  # type: ignore[attr-defined]
    ctl._policy.upsert_budget(  # type: ignore[attr-defined]
        tenant_id=TENANT,
        project_id=PROJECT,
        run_id=run_id,
        max_visits=max_visits,
        max_runtime_seconds=None,
        max_events=max_events,
    )


def _budget_events(ctl: RunController, run_id: str) -> list[Any]:
    """Eventos del Run leidos del storage, sin pasar por `_count_events`.

    `list_events_for_run` devuelve DTOs (`StoredEvent`), no `sqlite3.Row`:
    su `__getattr__` no admite claves no-string, asi que se accede por
    atributo y no con `dict(...)`.
    """
    return list(
        ctl._runs.list_events_for_run(  # type: ignore[attr-defined]
            tenant_id=TENANT, project_id=PROJECT, run_id=run_id
        )
    )


class TestMaxEventsBudget:
    def test_limit_reached_returns_true(self, tmp_path: Path) -> None:
        ctl = _controller(tmp_path, observed_events=5)
        _budget(ctl, "r1", max_events=5)

        assert ctl._is_budget_exhausted(_plan(), TENANT, PROJECT, "r1", prev_current=NODE)

    def test_limit_reached_emits_budget_exceeded_with_kind_events(self, tmp_path: Path) -> None:
        """El evento existe; sus VALORES dependen de la politica de redaccion.

        Con la politica por defecto (`metadata`, schema.py DEFAULT) los
        valores llegan a disco como `[REDACTED]` — contrato ya fijado por
        `test_runcontroller.py` bajo la etiqueta QW-B. Aqui se comprueba
        que el evento se emite y que conserva las claves.
        """
        ctl = _controller(tmp_path, observed_events=7)
        _budget(ctl, "r2", max_events=5)

        ctl._is_budget_exhausted(_plan(), TENANT, PROJECT, "r2", prev_current=NODE)

        emitted = [e for e in _budget_events(ctl, "r2") if e.event_kind == "BudgetExceeded"]
        assert len(emitted) == 1, f"esperaba 1 BudgetExceeded, hay {len(emitted)}: {emitted}"
        payload = emitted[0].payload
        assert emitted[0].event_kind == "BudgetExceeded"
        assert set(payload) == {"kind", "limit", "observed"}, payload
        # Politica por defecto: valores redactados, claves intactas (QW-B).
        assert payload["limit"] == "[REDACTED]", payload
        assert payload["observed"] == "[REDACTED]", payload

    def test_policy_none_exposes_the_violated_axis(self, tmp_path: Path) -> None:
        """Con `policy=none` se ve QUE eje se agoto: es el dato util.

        Este es el test que de verdad distingue `max_events` de
        `max_visits`: si el guard escribiera `kind="visits"` por error,
        aqui se veria.
        """
        ctl = _controller(tmp_path, observed_events=7)
        _budget(ctl, "r2n", max_events=5, policy="none")

        ctl._is_budget_exhausted(_plan(), TENANT, PROJECT, "r2n", prev_current=NODE)

        emitted = [e for e in _budget_events(ctl, "r2n") if e.event_kind == "BudgetExceeded"]
        assert len(emitted) == 1, emitted
        payload = emitted[0].payload
        assert payload["kind"] == "events", payload
        assert payload["limit"] == 5, payload
        assert payload["observed"] == 7, payload

    def test_under_limit_returns_false_and_emits_nothing(self, tmp_path: Path) -> None:
        ctl = _controller(tmp_path, observed_events=4)
        _budget(ctl, "r3", max_events=5)

        assert not ctl._is_budget_exhausted(_plan(), TENANT, PROJECT, "r3", prev_current=NODE)
        assert _budget_events(ctl, "r3") == [], "un budget no agotado no debe emitir eventos"

    def test_no_max_events_means_no_limit(self, tmp_path: Path) -> None:
        """Sin `max_events` no hay limite: muchos eventos no agotan nada."""
        ctl = _controller(tmp_path, observed_events=10_000)
        _budget(ctl, "r4", max_events=None)

        assert not ctl._is_budget_exhausted(_plan(), TENANT, PROJECT, "r4", prev_current=NODE)

    def test_limit_is_inclusive(self, tmp_path: Path) -> None:
        """Contar EXACTAMENTE el limite ya agota: el operador es `>=`."""
        ctl = _controller(tmp_path, observed_events=5)
        _budget(ctl, "r5", max_events=5)

        assert ctl._is_budget_exhausted(_plan(), TENANT, PROJECT, "r5", prev_current=NODE), (
            "5 eventos con limite 5 debe agotar (>=, no >)"
        )

    def test_events_check_is_reached_after_visits_check(self, tmp_path: Path) -> None:
        """Con ambos limites puestos,gana el que se cumple primero (orden 2a, 2b)."""
        ctl = _controller(tmp_path, observed_events=99)
        _budget(ctl, "r6", max_events=5, max_visits=10)

        assert ctl._is_budget_exhausted(_plan(), TENANT, PROJECT, "r6", prev_current=NODE)
        # max_visits=10 pero no hay self-loop ni ejecuciones previas, asi que
        # 2a no dispara y el que decide es 2b.
        emitted = [e for e in _budget_events(ctl, "r6") if e.event_kind == "BudgetExceeded"]
        assert len(emitted) == 1
        assert emitted[0].payload["kind"] == "[REDACTED]"

    @pytest.mark.parametrize("run_id", ["r7"])
    def test_absent_budget_means_no_exhaustion(self, tmp_path: Path, run_id: str) -> None:
        """Run sin fila de budget: nada que agotar."""
        ctl = _controller(tmp_path, observed_events=999)

        assert not ctl._is_budget_exhausted(_plan(), TENANT, PROJECT, run_id, prev_current=NODE)
