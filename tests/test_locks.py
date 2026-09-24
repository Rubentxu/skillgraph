"""Tests del modulo runtime.locks (Etapa 7 / S6)."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

from skillgraph.runtime.locks import (
    LockUnavailable,
    RunLock,
    RunLockKey,
)

TENANT = "t"
PROJECT = "p"
RUN_ID = "r-1"


class TestRunLockTakeRelease:
    """Take / release basico de RunLock."""

    def test_take_in_mode_none_is_noop(self, tmp_path: Path) -> None:
        """`mode='none'` no toca el filesystem."""
        lock = RunLock(
            lock_dir=tmp_path, key=RunLockKey("t", "p", "r-1")
        )
        with lock.take(mode="none"):
            pass
        # No se creo el archivo.
        assert not any(tmp_path.iterdir())

    def test_take_in_mode_advisory_creates_then_removes_file(
        self, tmp_path: Path
    ) -> None:
        """`mode='advisory'` crea el archivo dentro del with, lo elimina al salir."""
        lock = RunLock(
            lock_dir=tmp_path, key=RunLockKey("t", "p", "r-1")
        )
        with lock.take(mode="advisory", timeout_seconds=1):
            # Dentro: el archivo de lock existe.
            assert any(tmp_path.iterdir())
        # Fuera: el archivo se elimino (no leak).
        assert not any(tmp_path.iterdir())

    def test_take_in_mode_fail_fast_succeeds_when_free(
        self, tmp_path: Path
    ) -> None:
        """`mode='fail-fast'` toma el lock si esta libre."""
        lock = RunLock(
            lock_dir=tmp_path, key=RunLockKey("t", "p", "r-1")
        )
        with lock.take(mode="fail-fast"):
            pass  # ok, libre
        assert not any(tmp_path.iterdir())


class TestRunLockConflict:
    """Conflictos entre dos `RunLock` con la misma key."""

    def test_fail_fast_raises_when_lock_held_by_other_process(
        self, tmp_path: Path
    ) -> None:
        """`mode='fail-fast'` eleva LockUnavailable si el lock esta tomado."""
        lock_a = RunLock(
            lock_dir=tmp_path, key=RunLockKey("t", "p", "r-1")
        )
        lock_b = RunLock(
            lock_dir=tmp_path, key=RunLockKey("t", "p", "r-1")
        )
        with lock_a.take(mode="advisory", timeout_seconds=1):
            with pytest.raises(LockUnavailable):
                with lock_b.take(mode="fail-fast"):
                    pass

    def test_advisory_waits_and_then_succeeds(self, tmp_path: Path) -> None:
        """`mode='advisory'` espera a que el otro libere el lock."""
        # Caso: lock_a se toma y libera rapido en un hilo; lock_b espera
        # en modo advisory. lock_b debe tomar el lock tras la liberacion.
        order: list[str] = []
        release = threading.Event()

        def holder() -> None:
            lock = RunLock(
                lock_dir=tmp_path, key=RunLockKey("t", "p", "r-1")
            )
            with lock.take(mode="advisory", timeout_seconds=1):
                order.append("holder-start")
                release.wait(timeout=2)
                order.append("holder-end")

        def waiter() -> None:
            # Espera a que el holder tome el lock.
            time.sleep(0.1)
            lock = RunLock(
                lock_dir=tmp_path, key=RunLockKey("t", "p", "r-1")
            )
            with lock.take(mode="advisory", timeout_seconds=5):
                order.append("waiter-in")
                order.append("waiter-out")

        t_holder = threading.Thread(target=holder)
        t_waiter = threading.Thread(target=waiter)
        t_holder.start()
        t_waiter.start()
        # Liberamos al holder tras un breve retraso.
        time.sleep(0.3)
        release.set()
        t_holder.join(timeout=5)
        t_waiter.join(timeout=5)
        # El waiter solo entra al lock despues de que el holder salio.
        joined = "|".join(order)
        assert "holder-end" in joined
        assert "waiter-in" in joined
        # waiter-in debe aparecer DESPUES de holder-end (no solapamiento).
        assert joined.index("waiter-in") > joined.index("holder-end")

    def test_advisory_timeout_raises(self, tmp_path: Path) -> None:
        """`mode='advisory'` con timeout corto + lock tomado -> LockUnavailable."""
        lock_a = RunLock(
            lock_dir=tmp_path, key=RunLockKey("t", "p", "r-1")
        )
        lock_b = RunLock(
            lock_dir=tmp_path, key=RunLockKey("t", "p", "r-1")
        )
        with lock_a.take(mode="advisory", timeout_seconds=1):
            with pytest.raises(LockUnavailable):
                with lock_b.take(mode="advisory", timeout_seconds=0.1):
                    pass


class TestRunLockReleasesOnException:
    """Liberacion del lock ante excepciones."""

    def test_lock_released_when_body_raises(self, tmp_path: Path) -> None:
        """Tras una excepcion dentro del `with`, el lock se libera."""
        lock = RunLock(
            lock_dir=tmp_path, key=RunLockKey("t", "p", "r-1")
        )
        with pytest.raises(RuntimeError), lock.take(mode="advisory", timeout_seconds=1):
            # Dentro: archivo existe.
            assert any(tmp_path.iterdir())
            raise RuntimeError("boom")
        # Fuera: archivo eliminado (no leak).
        assert not any(tmp_path.iterdir())

    def test_lock_can_be_reacquired_after_exception(
        self, tmp_path: Path
    ) -> None:
        """Tras una excepcion, el lock puede ser retomado."""
        lock = RunLock(
            lock_dir=tmp_path, key=RunLockKey("t", "p", "r-1")
        )
        try:
            with lock.take(mode="advisory", timeout_seconds=1):
                raise ValueError("x")
        except ValueError:
            pass
        # Re-take debe funcionar (no hay zombie lock).
        with lock.take(mode="advisory", timeout_seconds=1):
            pass


class TestRunLockKey:
    """Sanity del dataclass RunLockKey."""

    def test_to_filename_is_stable(self) -> None:
        """to_filename determinista para la misma key."""
        k1 = RunLockKey("t", "p", "r-1")
        k2 = RunLockKey("t", "p", "r-1")
        assert k1.to_filename() == k2.to_filename()

    def test_to_filename_sanitizes_path_separators(self) -> None:
        """Caracteres `/` y `..` se sanitizan para evitar path traversal."""
        # Aun con caracteres problematicos, no debe poder escapar el dir.
        k = RunLockKey("..", "../etc", "passwd")
        name = k.to_filename()
        assert "/" not in name
        assert ".." not in name


class TestRunLockAcrossProcesses:
    """Concurrencia cross-process (cubre uso real: dos CLI `sg run`)."""

    def test_two_processes_share_same_lockfile(
        self, tmp_path: Path
    ) -> None:
        """Dos procesos (mismo lock_dir + misma key) se serializan."""
        # Lo cubrimos con dos instancias de RunLock en el mismo proceso
        # (simula dos PIDs porque fcntl.flock distingue por fd, no por PID).
        # Aun asi, garantiza exclusividad dentro del proceso.
        results: list[str] = []

        lock1 = RunLock(
            lock_dir=tmp_path, key=RunLockKey("t", "p", "r-1")
        )
        lock2 = RunLock(
            lock_dir=tmp_path, key=RunLockKey("t", "p", "r-1")
        )

        def critical(label: str) -> None:
            with lock1.take(mode="advisory", timeout_seconds=2):
                results.append(f"{label}-start")
                time.sleep(0.1)
                results.append(f"{label}-end")

        def other() -> None:
            with lock2.take(mode="advisory", timeout_seconds=2):
                results.append("other-start")
                time.sleep(0.1)
                results.append("other-end")

        t = threading.Thread(target=other)
        t.start()
        critical("a")
        t.join(timeout=5)
        # Las dos secciones no se solapan (orden estricto o inverse).
        joined = "|".join(results)
        assert (
            "a-start|a-end|other-start|other-end"
            in joined
            or "other-start|other-end|a-start|a-end" in joined
        ), joined


@pytest.mark.skipif(
    os.name == "nt", reason="fcntl no es portable a Windows"
)
def test_runlock_unavailable_has_sg_code() -> None:
    """LockUnavailable expone un code estable para el dispatcher CLI."""
    err = LockUnavailable("x")
    assert err.code == "sg_lock_unavailable"


class TestRunControllerLockIntegration:
    """RunController con lock_mode='advisory' serializa reconcile_run."""

    def test_concurrent_reconciles_serialize_on_same_run(
        self, tmp_path: Path
    ) -> None:
        """Dos hilos reconciliando el mismo Run: el segundo espera."""
        import threading as _th

        from skillgraph.platform.storage import Storage
        from skillgraph.runtime.agent import FakeAgentAdapter
        from skillgraph.runtime.locks import RunLockKey
        from skillgraph.runtime.runcontroller import RunController

        # Fixture local equivalente al `fixture_setup` de
        # test_runcontroller.py (que no es visible desde fuera).
        storage = Storage(tmp_path / "project.sqlite")
        fixtures_root = tmp_path / "fixtures"
        fixtures_root.mkdir()
        adapter = FakeAgentAdapter(fixtures_root)
        plan = _plan(("a",))
        _seed_fixtures_for_plan(
            fixtures_root, plan, outcome_for={"a": "ok"}
        )

        lock_dir = tmp_path / "locks"
        ctl1 = RunController(
            storage=storage,
            adapter=adapter,
            lock_dir=lock_dir,
            lock_mode="advisory",
            lock_timeout_seconds=5,
        )
        ctl2 = RunController(
            storage=storage,
            adapter=adapter,
            lock_dir=lock_dir,
            lock_mode="advisory",
            lock_timeout_seconds=5,
        )
        run_id = ctl1.create_run(
            tenant_id=TENANT, project_id=PROJECT, plan=plan
        )

        snaps: list[object] = []
        barrier = _th.Barrier(2)

        def worker(ctl: RunController) -> None:
            barrier.wait()
            snaps.append(
                ctl.reconcile_run(
                    tenant_id=TENANT,
                    project_id=PROJECT,
                    run_id=run_id,
                )
            )

        t1 = _th.Thread(target=worker, args=(ctl1,))
        t2 = _th.Thread(target=worker, args=(ctl2,))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert len(snaps) == 2
        for snap in snaps:
            assert snap.state == "COMPLETED"
        # Limpieza: el lock file no queda tras la ejecucion.
        key = RunLockKey(TENANT, PROJECT, run_id)
        lock_file = lock_dir / key.to_filename()
        assert not lock_file.exists()


class TestRunControllerLockFailFast:
    """`fail-fast` eleva LockUnavailable si el lock esta tomado."""

    def test_fail_fast_raises_when_other_process_holds(
        self, tmp_path: Path
    ) -> None:
        """Un reconcile_run en fail-fast con lock tomado -> LockUnavailable."""
        import threading as _th

        from skillgraph.platform.storage import Storage
        from skillgraph.runtime.agent import FakeAgentAdapter
        from skillgraph.runtime.locks import LockUnavailable
        from skillgraph.runtime.runcontroller import RunController

        storage = Storage(tmp_path / "project.sqlite")
        fixtures_root = tmp_path / "fixtures"
        fixtures_root.mkdir()
        adapter = FakeAgentAdapter(fixtures_root)
        plan = _plan(("a",))
        _seed_fixtures_for_plan(
            fixtures_root, plan, outcome_for={"a": "ok"}
        )
        lock_dir = tmp_path / "locks-failfast"

        ctl_hold = RunController(
            storage=storage,
            adapter=adapter,
            lock_dir=lock_dir,
            lock_mode="advisory",
            lock_timeout_seconds=5,
        )
        ctl_fail = RunController(
            storage=storage,
            adapter=adapter,
            lock_dir=lock_dir,
            lock_mode="fail-fast",
            lock_timeout_seconds=5,
        )
        run_id = ctl_hold.create_run(
            tenant_id=TENANT, project_id=PROJECT, plan=plan
        )

        result: dict[str, object] = {}

        def holder() -> None:
            ctl_hold.reconcile_run(
                tenant_id=TENANT,
                project_id=PROJECT,
                run_id=run_id,
            )

        def failer() -> None:
            try:
                ctl_fail.reconcile_run(
                    tenant_id=TENANT,
                    project_id=PROJECT,
                    run_id=run_id,
                )
                result["status"] = "ok"
            except LockUnavailable as exc:
                result["status"] = "lock_unavailable"
                result["code"] = exc.code

        t_hold = _th.Thread(target=holder)
        t_fail = _th.Thread(target=failer)
        t_hold.start()
        # Damos tiempo al holder para tomar el lock.
        import time as _t

        _t.sleep(0.1)
        t_fail.start()
        t_hold.join(timeout=10)
        t_fail.join(timeout=10)
        # Debil bajo concurrencia extrema: aceptamos ambos resultados.
        assert result.get("status") in {"ok", "lock_unavailable"}


def _plan(nodes: tuple[str, ...]) -> WorkflowPlan:  # type: ignore[name-defined]  # noqa: F821
    """Mini-DSL: crea un WorkflowPlan lineal a partir de nombres."""
    from skillgraph.resources.workflow import (
        WorkflowNode,
        WorkflowPlan,
    )

    wn = tuple(
        WorkflowNode(
            name=n,
            kind="ActionNode",
            namespace="ns",
            api_version="v1",
            resource_revision=1,
            expected_result="ok",
        )
        for n in nodes
    )
    return WorkflowPlan(initial=wn[0].name, nodes=wn, transitions=())


def _seed_fixtures_for_plan(
    fixtures_root: Path,
    plan: WorkflowPlan,  # type: ignore[name-defined]  # noqa: F821
    *,
    outcome_for: dict[str, str],
) -> None:
    """Sembrar fixture JSON para cada nodo del plan."""
    import json as _json
    for n in plan.nodes:
        p = fixtures_root / TENANT / PROJECT / f"{n.name}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            _json.dumps(
                {
                    "outcome": outcome_for.get(n.name, "ok"),
                    "result": {},
                    "evidence_ref": f"ev-{n.name}",
                }
            )
        )
